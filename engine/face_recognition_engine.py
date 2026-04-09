"""
人脸识别模块
引擎优先级：face_recognition(dlib) > InsightFace > OpenCV

安装说明：
  方案A - face_recognition（推荐）：
    1. 安装 CMake：https://cmake.org/download/
    2. 安装 Visual Studio C++ 生成工具：https://visualstudio.microsoft.com/visual-cpp-build-tools/
    3. pip install dlib face_recognition

  方案B - InsightFace：
    pip install insightface onnxruntime opencv-python

  方案C - OpenCV（仅检测，不识别身份）：
    pip install opencv-python
"""

import os
import json
import warnings
from engine.db_guard import guarded_connect
import numpy as np
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Tuple, Any
import base64
import io

# Suppress pkg_resources deprecation warning from face_recognition_models
warnings.filterwarnings("ignore", message=".*pkg_resources is deprecated.*")

_engine      = None
_engine_name = "none"
_initialized = False


def _init_engine():
    global _engine, _engine_name

    # 方案1：face_recognition (dlib)
    try:
        import face_recognition as fr
        _engine      = fr
        _engine_name = "face_recognition"
        print("[OK] 人脸识别：face_recognition (dlib，精度99.38%)")
        return
    except ImportError:
        pass
    except Exception as e:
        print(f"  face_recognition 初始化失败: {e}")

    # 方案2：InsightFace
    try:
        import insightface
        from insightface.app import FaceAnalysis
        app = FaceAnalysis(name="buffalo_sc", providers=["CPUExecutionProvider"])
        app.prepare(ctx_id=-1, det_size=(640, 640))
        _engine      = app
        _engine_name = "insightface"
        print("[OK] 人脸识别：InsightFace (buffalo_sc) - CPU模式")
        return
    except ImportError:
        pass
    except Exception as e:
        print(f"  InsightFace 初始化失败: {e}")

    # 方案3：OpenCV
    try:
        import cv2
        model_dir = Path(__file__).parent.parent / "assets" / "face_models"
        proto  = str(model_dir / "deploy.prototxt")
        model  = str(model_dir / "res10_300x300_ssd_iter_140000.caffemodel")
        if Path(proto).exists() and Path(model).exists():
            net          = cv2.dnn.readNetFromCaffe(proto, model)
            _engine      = {"cv2": cv2, "net": net}
            _engine_name = "opencv_dnn"
            print("[OK] 人脸识别：OpenCV DNN（仅检测）")
        else:
            _engine      = {"cv2": cv2}
            _engine_name = "opencv_haar"
            print("[OK] 人脸识别：OpenCV Haar（仅检测）")
        return
    except ImportError:
        pass

    _engine_name = "none"
    print("⚠️  人脸识别：无可用引擎，推荐安装 face_recognition")


def _ensure_engine():
    global _initialized
    if _initialized:
        return
    _initialized = True
    try:
        _init_engine()
    except Exception as e:
        print(f"[人脸识别] 引擎初始化异常: {e}")


def get_engine_name() -> str:
    _ensure_engine()
    return _engine_name


def is_available() -> bool:
    _ensure_engine()
    return _engine_name != "none"


def can_identify() -> bool:
    _ensure_engine()
    return _engine_name in ("face_recognition", "insightface")


def detect_faces(image_rgb: np.ndarray) -> List[Dict]:
    _ensure_engine()
    if _engine_name == "none":
        return []
    try:
        if _engine_name == "face_recognition":
            return _detect_face_recognition(image_rgb)
        elif _engine_name == "insightface":
            return _detect_insightface(image_rgb)
        elif _engine_name in ("opencv_dnn", "opencv_haar"):
            return _detect_opencv(image_rgb)
    except Exception as e:
        print(f"[人脸检测] 失败: {e}")
    return []


def get_face_embedding(image_rgb: np.ndarray) -> Optional[List[float]]:
    faces = detect_faces(image_rgb)
    if not faces:
        return None
    best = max(faces, key=lambda f: f.get("confidence", 0))
    return best.get("embedding")


def compare_faces(emb1: List[float], emb2: List[float],
                  threshold: float = 0.6) -> Tuple[bool, float]:
    if not emb1 or not emb2 or len(emb1) != len(emb2):
        return False, 0.0
    a = np.array(emb1)
    b = np.array(emb2)
    if _engine_name == "face_recognition":
        dist = float(np.linalg.norm(a - b))
        return dist < threshold, max(0.0, 1.0 - dist)
    else:
        cos = float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-8))
        return cos > (1.0 - threshold), cos


def _detect_face_recognition(image_rgb: np.ndarray) -> List[Dict]:
    fr        = _engine
    locations = fr.face_locations(image_rgb)
    encodings = fr.face_encodings(image_rgb, locations)
    result = []
    for (top, right, bottom, left), enc in zip(locations, encodings):
        result.append({"bbox": [left, top, right, bottom],
                       "confidence": 1.0, "embedding": enc.tolist()})
    return result


def _detect_insightface(image_rgb: np.ndarray) -> List[Dict]:
    import cv2
    img_bgr = cv2.cvtColor(image_rgb, cv2.COLOR_RGB2BGR)
    faces   = _engine.get(img_bgr)
    result  = []
    for face in faces:
        bbox = face.bbox.astype(int).tolist()
        result.append({
            "bbox": bbox, "confidence": float(face.det_score),
            "embedding": face.normed_embedding.tolist()
                         if hasattr(face, "normed_embedding") else None,
            "age":    int(face.age) if hasattr(face, "age") else None,
            "gender": face.sex if hasattr(face, "sex") else None,
        })
    return result


def _detect_opencv(image_rgb: np.ndarray) -> List[Dict]:
    import cv2
    cv2_mod = _engine.get("cv2", cv2)
    img_bgr = cv2_mod.cvtColor(image_rgb, cv2.COLOR_RGB2BGR)
    h, w    = img_bgr.shape[:2]
    result  = []
    if _engine_name == "opencv_dnn" and "net" in _engine:
        blob = cv2_mod.dnn.blobFromImage(img_bgr, 1.0, (300, 300), (104, 117, 123))
        _engine["net"].setInput(blob)
        detections = _engine["net"].forward()
        for i in range(detections.shape[2]):
            conf = float(detections[0, 0, i, 2])
            if conf > 0.5:
                x1 = int(detections[0, 0, i, 3] * w)
                y1 = int(detections[0, 0, i, 4] * h)
                x2 = int(detections[0, 0, i, 5] * w)
                y2 = int(detections[0, 0, i, 6] * h)
                result.append({"bbox": [x1,y1,x2,y2], "confidence": conf, "embedding": None})
    else:
        gray    = cv2_mod.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
        cascade = cv2_mod.CascadeClassifier(
            cv2_mod.data.haarcascades + "haarcascade_frontalface_default.xml")
        for (x, y, fw, fh) in cascade.detectMultiScale(gray, 1.1, 4):
            result.append({"bbox": [x, y, x+fw, y+fh], "confidence": 0.8, "embedding": None})
    return result


class CameraThread:
    def __init__(self, camera_id: int = 0):
        self.camera_id = camera_id

    def get_frame_rgb(self, timeout_sec: float = 10.0) -> Optional[np.ndarray]:
        """采集一帧，含超时保护"""
        import threading
        result = [None]
        err_msg = [None]
        done   = threading.Event()

        def _capture():
            try:
                import cv2
                cap = cv2.VideoCapture(self.camera_id)
                if not cap.isOpened():
                    err_msg[0] = "VideoCapture 打开失败"
                    done.set()
                    return
                ret, frame = cap.read()
                cap.release()
                if ret and frame is not None:
                    result[0] = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                else:
                    err_msg[0] = "cap.read() 返回空帧"
            except Exception as e:
                err_msg[0] = str(e)
            finally:
                done.set()

        t = threading.Thread(target=_capture, daemon=True)
        t.start()
        done.wait(timeout=timeout_sec)
        if result[0] is None and err_msg[0]:
            print(f"[CameraThread] {err_msg[0]}")
        return result[0]

    def capture_to_base64(self) -> Optional[str]:
        frame = self.get_frame_rgb()
        if frame is None:
            return None
        try:
            from PIL import Image
            img = Image.fromarray(frame)
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=85)
            return base64.b64encode(buf.getvalue()).decode()
        except Exception:
            return None


class FaceDatabase:
    def __init__(self, db_path: str):
        self.db_path = db_path
        import sqlite3
        with guarded_connect(db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS face_embeddings (
                    user_id TEXT NOT NULL, label TEXT,
                    embedding TEXT NOT NULL, engine TEXT,
                    photo_b64 TEXT, created_at TEXT, notes TEXT
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_user ON face_embeddings(user_id)")
            conn.commit()

    def register(self, user_id: str, image_rgb: np.ndarray,
                 label: str = "", notes: str = "") -> Dict:
        faces = detect_faces(image_rgb)
        if not faces:
            return {"ok": False, "error": "未检测到人脸，请确保光线充足、正对摄像头"}
        best = max(faces, key=lambda f: (
            (f["bbox"][2]-f["bbox"][0]) * (f["bbox"][3]-f["bbox"][1])))
        if best.get("embedding") is None:
            return {"ok": False, "error": f"当前引擎（{_engine_name}）不支持身份识别，请安装 face_recognition"}
        try:
            from PIL import Image
            img = Image.fromarray(image_rgb)
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=70)
            photo_b64 = base64.b64encode(buf.getvalue()).decode()
        except Exception:
            photo_b64 = ""
        import sqlite3
        with guarded_connect(self.db_path) as conn:
            conn.execute("INSERT INTO face_embeddings VALUES (?,?,?,?,?,?,?)",
                         (user_id, label or user_id,
                          json.dumps(best["embedding"]),
                          _engine_name, photo_b64,
                          datetime.now().isoformat(), notes))
            conn.commit()
        return {"ok": True, "user_id": user_id,
                "confidence": best.get("confidence", 1.0), "engine": _engine_name}

    def identify(self, image_rgb: np.ndarray, threshold: float = 0.6) -> Dict:
        faces = detect_faces(image_rgb)
        if not faces:
            return {"ok": False, "identified": False, "reason": "未检测到人脸"}
        best_face = max(faces, key=lambda f: f.get("confidence", 0))
        query_emb = best_face.get("embedding")
        if query_emb is None:
            return {"ok": False, "identified": False, "reason": "当前引擎不支持身份识别"}
        import sqlite3
        with guarded_connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT user_id, label, embedding FROM face_embeddings").fetchall()
        if not rows:
            return {"ok": True, "identified": False, "reason": "人脸库为空，请先注册"}
        best_match, best_score = None, -1.0
        for user_id, label, emb_json in rows:
            matched, score = compare_faces(query_emb, json.loads(emb_json), threshold)
            if score > best_score:
                best_score = score
                best_match = {"user_id": user_id, "label": label, "matched": matched}
        if best_match and best_match["matched"]:
            return {"ok": True, "identified": True,
                    "user_id": best_match["user_id"], "label": best_match["label"],
                    "confidence": round(best_score, 3), "engine": _engine_name}
        return {"ok": True, "identified": False,
                "reason": "未匹配到已注册用户", "best_score": round(best_score, 3)}

    def list_users(self) -> List[Dict]:
        import sqlite3
        with guarded_connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT user_id, label, engine, created_at, notes "
                "FROM face_embeddings ORDER BY created_at DESC").fetchall()
        return [{"user_id": r[0], "label": r[1], "engine": r[2],
                 "created_at": r[3], "notes": r[4]} for r in rows]

    def delete_user(self, user_id: str) -> bool:
        import sqlite3
        with guarded_connect(self.db_path) as conn:
            conn.execute("DELETE FROM face_embeddings WHERE user_id=?", (user_id,))
            conn.commit()
        return True
