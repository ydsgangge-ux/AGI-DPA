"""
多用户身份验证管理器

账户体系：
  - 每个用户有独立的 user_id、显示名、认证方式（人脸/密码短语）
  - 认证方式可叠加（同一用户既注册人脸，又设密码）
  - 记忆和画像按 user_id 隔离

状态机：NO_FACE → GUEST → VERIFIED(user_id)
"""

import hashlib
import json
import sqlite3
from engine.db_guard import guarded_connect
import threading
import uuid
from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict


class AuthState(Enum):
    NO_FACE  = "no_face"    # 未注册任何用户
    GUEST    = "guest"      # 未认证，游客模式
    VERIFIED = "verified"   # 已认证


class UserAccount:
    def __init__(self, user_id: str, name: str, auth_methods: List[str],
                 passphrase_hash: Optional[str], created_at: str):
        self.user_id         = user_id
        self.name            = name
        self.auth_methods    = auth_methods   # ['face', 'passphrase']
        self.passphrase_hash = passphrase_hash
        self.created_at      = created_at


class AuthManager:

    def __init__(self, db_path: str):
        self.db_path           = db_path
        self._state            = AuthState.NO_FACE
        self._current_user_id  = None
        self._current_name     = None
        self._lock             = threading.Lock()
        self._guest_session_id = None
        self._init_db()

    # ── 数据库 ──────────────────────────────────

    def _init_db(self):
        with guarded_connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS user_accounts (
                    user_id         TEXT PRIMARY KEY,
                    name            TEXT NOT NULL,
                    auth_methods    TEXT DEFAULT '[]',
                    passphrase_hash TEXT,
                    created_at      TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS auth_config (
                    key TEXT PRIMARY KEY, value TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS guest_sessions (
                    session_id TEXT PRIMARY KEY,
                    started_at TEXT NOT NULL,
                    ended_at   TEXT,
                    photo_b64  TEXT,
                    messages   TEXT DEFAULT '[]'
                )
            """)
            conn.commit()

    # ── 账户管理 ─────────────────────────────────

    def list_users(self) -> List[UserAccount]:
        with guarded_connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT user_id, name, auth_methods, passphrase_hash, created_at "
                "FROM user_accounts ORDER BY created_at"
            ).fetchall()
        return [UserAccount(r[0], r[1], json.loads(r[2] or "[]"), r[3], r[4])
                for r in rows]

    def get_user(self, user_id: str) -> Optional[UserAccount]:
        with guarded_connect(self.db_path) as conn:
            r = conn.execute(
                "SELECT user_id, name, auth_methods, passphrase_hash, created_at "
                "FROM user_accounts WHERE user_id=?", (user_id,)
            ).fetchone()
        if r:
            return UserAccount(r[0], r[1], json.loads(r[2] or "[]"), r[3], r[4])
        return None

    def has_any_user(self) -> bool:
        with guarded_connect(self.db_path) as conn:
            n = conn.execute("SELECT COUNT(*) FROM user_accounts").fetchone()[0]
        return n > 0

    def create_user(self, name: str, passphrase: str = "") -> UserAccount:
        """创建新用户账户，返回账户对象"""
        uid = str(uuid.uuid4())[:8]
        methods = []
        ph = None
        if passphrase.strip():
            ph = hashlib.sha256(passphrase.strip().encode()).hexdigest()
            methods.append("passphrase")
        now = datetime.now().isoformat()
        with guarded_connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO user_accounts VALUES (?,?,?,?,?)",
                (uid, name, json.dumps(methods), ph, now)
            )
            conn.commit()
        return UserAccount(uid, name, methods, ph, now)

    def update_passphrase(self, user_id: str, passphrase: str):
        ph = hashlib.sha256(passphrase.strip().encode()).hexdigest()
        with guarded_connect(self.db_path) as conn:
            # 确保 passphrase 在 auth_methods 里
            row = conn.execute(
                "SELECT auth_methods FROM user_accounts WHERE user_id=?", (user_id,)
            ).fetchone()
            if row:
                methods = json.loads(row[0] or "[]")
                if "passphrase" not in methods:
                    methods.append("passphrase")
                conn.execute(
                    "UPDATE user_accounts SET passphrase_hash=?, auth_methods=? WHERE user_id=?",
                    (ph, json.dumps(methods), user_id)
                )
                conn.commit()

    def add_face_method(self, user_id: str):
        """标记该用户已注册人脸"""
        with guarded_connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT auth_methods FROM user_accounts WHERE user_id=?", (user_id,)
            ).fetchone()
            if row:
                methods = json.loads(row[0] or "[]")
                if "face" not in methods:
                    methods.append("face")
                conn.execute(
                    "UPDATE user_accounts SET auth_methods=? WHERE user_id=?",
                    (json.dumps(methods), user_id)
                )
                conn.commit()

    def delete_user(self, user_id: str):
        with guarded_connect(self.db_path) as conn:
            conn.execute("DELETE FROM user_accounts WHERE user_id=?", (user_id,))
            conn.commit()

    # ── 认证 ────────────────────────────────────

    def verify_passphrase(self, passphrase: str) -> Optional[UserAccount]:
        """
        用密码短语认证，自动匹配对应用户
        返回匹配的用户账户，或 None
        """
        if not passphrase.strip():
            return None
        ph = hashlib.sha256(passphrase.strip().encode()).hexdigest()
        with guarded_connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT user_id, name, auth_methods, passphrase_hash, created_at "
                "FROM user_accounts WHERE passphrase_hash=?", (ph,)
            ).fetchone()
        if row:
            user = UserAccount(row[0], row[1], json.loads(row[2] or "[]"), row[3], row[4])
            with self._lock:
                self._state           = AuthState.VERIFIED
                self._current_user_id = user.user_id
                self._current_name    = user.name
            self._end_guest_session()
            return user
        return None

    def has_registered_faces(self) -> bool:
        """是否有任何用户注册了人脸"""
        try:
            with guarded_connect(self.db_path) as conn:
                n = conn.execute(
                    "SELECT COUNT(*) FROM face_embeddings"
                ).fetchone()[0]
            return n > 0
        except Exception:
            return False

    def verify_face(self, image_rgb=None, threshold: float = 0.5) -> dict:
        """人脸验证，识别是哪个用户"""
        if not self.has_any_user():
            with self._lock:
                self._state = AuthState.NO_FACE
            return {"ok": True, "state": AuthState.NO_FACE,
                    "user_id": None, "reason": "尚未注册任何用户"}

        photo_b64 = None
        if image_rgb is None:
            try:
                from engine.face_recognition_engine import CameraThread
                cam       = CameraThread(camera_id=0)
                image_rgb = cam.get_frame_rgb(timeout_sec=6.0)
                if image_rgb is not None:
                    photo_b64 = self._frame_to_b64(image_rgb)
            except Exception:
                pass

        if image_rgb is None:
            with self._lock:
                self._state = AuthState.GUEST
            self._start_guest_session(photo_b64=None)
            return {"ok": False, "state": AuthState.GUEST,
                    "user_id": None, "reason": "摄像头不可用，以游客模式继续"}

        # 检查是否有注册人脸的用户
        if not self.has_registered_faces():
            # 有账户但没人注册人脸，直接游客
            with self._lock:
                self._state = AuthState.GUEST
            self._start_guest_session(photo_b64=photo_b64)
            return {"ok": True, "state": AuthState.GUEST,
                    "user_id": None, "reason": "所有用户均未注册人脸，以游客模式继续"}

        try:
            from engine.face_recognition_engine import FaceDatabase
            result = FaceDatabase(self.db_path).identify(image_rgb, threshold=threshold)

            if result.get("identified"):
                # face_embeddings 的 user_id 对应账户的 user_id
                uid   = result.get("user_id", "")
                user  = self.get_user(uid)
                name  = user.name if user else uid
                with self._lock:
                    self._state           = AuthState.VERIFIED
                    self._current_user_id = uid
                    self._current_name    = name
                self._end_guest_session()
                return {"ok": True, "state": AuthState.VERIFIED,
                        "user_id": uid, "confidence": result.get("confidence", 0),
                        "reason": f"欢迎回来，{name}"}
            else:
                with self._lock:
                    self._state           = AuthState.GUEST
                    self._current_user_id = None
                self._start_guest_session(photo_b64=photo_b64)
                return {"ok": True, "state": AuthState.GUEST,
                        "user_id": None, "reason": "未识别到已注册用户，以游客模式继续"}
        except Exception as e:
            with self._lock:
                self._state = AuthState.GUEST
            self._start_guest_session(photo_b64=None)
            return {"ok": False, "state": AuthState.GUEST,
                    "user_id": None, "reason": f"识别异常: {e}"}

    def login(self, user: UserAccount):
        """直接登录（用于注册后自动登录）"""
        with self._lock:
            self._state           = AuthState.VERIFIED
            self._current_user_id = user.user_id
            self._current_name    = user.name
        self._end_guest_session()

    # ── 游客存证 ─────────────────────────────────

    def _frame_to_b64(self, image_rgb) -> Optional[str]:
        try:
            import io, base64
            from PIL import Image
            buf = io.BytesIO()
            Image.fromarray(image_rgb).save(buf, format="JPEG", quality=70)
            return base64.b64encode(buf.getvalue()).decode()
        except Exception:
            return None

    def _start_guest_session(self, photo_b64=None):
        sid = str(uuid.uuid4())[:8]
        with self._lock:
            self._guest_session_id = sid
        with guarded_connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO guest_sessions VALUES (?,?,?,?,?)",
                (sid, datetime.now().isoformat(), None, photo_b64, "[]")
            )
            conn.commit()

    def _end_guest_session(self):
        with self._lock:
            sid = self._guest_session_id
            self._guest_session_id = None
        if sid:
            with guarded_connect(self.db_path) as conn:
                conn.execute(
                    "UPDATE guest_sessions SET ended_at=? WHERE session_id=?",
                    (datetime.now().isoformat(), sid)
                )
                conn.commit()

    def log_guest_message(self, user_msg: str, ai_response: str):
        with self._lock:
            sid   = self._guest_session_id
            state = self._state
        if not sid or state != AuthState.GUEST:
            return
        try:
            with guarded_connect(self.db_path) as conn:
                row = conn.execute(
                    "SELECT messages FROM guest_sessions WHERE session_id=?", (sid,)
                ).fetchone()
                if row:
                    msgs = json.loads(row[0])
                    msgs.append({"time": datetime.now().strftime("%H:%M:%S"),
                                 "user": user_msg[:150], "response": ai_response[:150]})
                    conn.execute(
                        "UPDATE guest_sessions SET messages=? WHERE session_id=?",
                        (json.dumps(msgs, ensure_ascii=False), sid)
                    )
                    conn.commit()
        except Exception:
            pass

    def get_guest_sessions(self, limit: int = 20) -> list:
        try:
            with guarded_connect(self.db_path) as conn:
                rows = conn.execute(
                    "SELECT session_id, started_at, ended_at, photo_b64, messages "
                    "FROM guest_sessions ORDER BY started_at DESC LIMIT ?", (limit,)
                ).fetchall()
            result = []
            for r in rows:
                msgs = json.loads(r[4] or "[]")
                result.append({"session_id": r[0], "started_at": r[1], "ended_at": r[2],
                               "has_photo": bool(r[3]), "photo_b64": r[3],
                               "msg_count": len(msgs), "messages": msgs})
            return result
        except Exception:
            return []

    def clear_guest_sessions(self):
        with guarded_connect(self.db_path) as conn:
            conn.execute("DELETE FROM guest_sessions")
            conn.commit()

    # ── 状态查询 ─────────────────────────────────

    @property
    def state(self) -> AuthState:
        with self._lock:
            return self._state

    @property
    def user_id(self) -> Optional[str]:
        with self._lock:
            return self._current_user_id

    @property
    def current_name(self) -> Optional[str]:
        with self._lock:
            return self._current_name

    def is_verified(self) -> bool:
        return self.state == AuthState.VERIFIED

    def is_guest(self) -> bool:
        return self.state == AuthState.GUEST

    def is_no_face(self) -> bool:
        return self.state == AuthState.NO_FACE

    def lock(self):
        with self._lock:
            self._state           = AuthState.GUEST if self.has_any_user() else AuthState.NO_FACE
            self._current_user_id = None
            self._current_name    = None
        if self.has_any_user():
            self._start_guest_session()

    def status_text(self) -> str:
        s = self.state
        if s == AuthState.VERIFIED:
            return f"🟢 {self._current_name or '已认证用户'}"
        elif s == AuthState.GUEST:
            return "🔴 游客模式（点击解锁）"
        return "🟡 未注册用户（点击注册）"

    def guest_system_prompt(self) -> str:
        return (
            "【⚠️ 安全模式·游客身份】\n"
            "当前用户未通过身份验证，是陌生访客。\n"
            "严格遵守：\n"
            "1. 绝不透露任何私人记忆、对话历史、个人信息\n"
            "2. 不提及认识任何特定用户\n"
            "3. 友善交流，保持信息保护\n"
            "4. 可提示对方：输入密码短语或人脸识别可解锁完整功能\n"
            "你的人格和基本能力正常，记忆和用户信息已保护。"
        )
