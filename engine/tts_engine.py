"""
语音合成引擎（TTS）
优先级：edge-tts + QMediaPlayer（高质量在线）> pyttsx3（离线兜底）> 静默降级

安装：pip install edge-tts
推荐中文声音：
  zh-CN-XiaoxiaoNeural   小晓（女，温柔自然，默认）
  zh-CN-YunxiNeural      云希（男，活泼）
  zh-CN-YunjianNeural    云健（男，成熟稳重）
  zh-TW-HsiaoChenNeural  台湾中文（女）
"""

import asyncio
import os
import re
import sys
import threading
import tempfile
from pathlib import Path
from typing import Optional, Callable


# 可选声音列表（供 UI 展示）
VOICE_OPTIONS = [
    ("zh-CN-XiaoxiaoNeural",  "小晓·女·温柔（推荐）"),
    ("zh-CN-XiaoyiNeural",    "小艺·女·活泼"),
    ("zh-CN-YunxiNeural",     "云希·男·活泼"),
    ("zh-CN-YunjianNeural",   "云健·男·稳重"),
    ("zh-CN-YunyangNeural",   "云扬·男·新闻播报"),
    ("zh-TW-HsiaoChenNeural", "晓臻·台湾·女"),
    ("zh-HK-HiuMaanNeural",   "晓曼·粤语·女"),
]


class TTSEngine:
    """
    语音合成引擎
    播放层：优先 QMediaPlayer（Qt 内置，精确控制），回退 winsound / 系统播放器
    合成层：edge-tts（在线高质量）失败时自动降级 pyttsx3（离线）
    """

    def __init__(self):
        self._backend    = None   # 'edge' | 'pyttsx3' | None
        self._pyttsx3_engine = None
        self._lock       = threading.Lock()
        self._play_thread: Optional[threading.Thread] = None
        self._stop_flag  = False

        # QMediaPlayer 实例（懒初始化）
        self._media_player = None
        self._qapp = None

        # 配置
        self.voice       = "zh-CN-XiaoxiaoNeural"
        self.rate        = "+0%"
        self.volume      = "+0%"
        self.enabled     = True

    def _detect_backend(self):
        """检测可用后端（只执行一次）"""
        if self._backend is not None:
            return self._backend
        try:
            import edge_tts
            self._backend = "edge"
            return "edge"
        except ImportError:
            pass
        try:
            import pyttsx3
            engine = pyttsx3.init()
            voices = engine.getProperty("voices")
            for v in voices:
                if "zh" in v.id.lower() or "chinese" in v.name.lower():
                    engine.setProperty("voice", v.id)
                    break
            self._pyttsx3_engine = engine
            self._backend = "pyttsx3"
            return "pyttsx3"
        except Exception:
            pass
        self._backend = "none"
        return "none"

    def is_available(self) -> bool:
        return self._detect_backend() in ("edge", "pyttsx3")

    def get_backend_name(self) -> str:
        b = self._detect_backend()
        return {
            "edge":    "Microsoft Edge TTS + QMediaPlayer",
            "pyttsx3": "系统 TTS（离线兜底）",
            "none":    "未安装（pip install edge-tts）"
        }.get(b, "未知")

    def _ensure_qt_player(self):
        """懒初始化 QMediaPlayer，确保在主线程创建"""
        if self._media_player is not None:
            return True
        try:
            from PyQt6.QtCore import QUrl, QCoreApplication
            from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput

            # 确保 QApplication 存在
            app = QCoreApplication.instance()
            if app is None:
                return False
            self._qapp = app

            self._media_player = QMediaPlayer()
            self._audio_output = QAudioOutput()
            self._media_player.setAudioOutput(self._audio_output)
            self._media_player.setVolume(1.0)
            return True
        except Exception as e:
            print(f"[TTS] QMediaPlayer 初始化失败: {e}")
            return False

    def stop(self):
        """停止当前播放"""
        self._stop_flag = True
        # 停止 QMediaPlayer
        if self._media_player is not None:
            try:
                from PyQt6.QtMultimedia import QMediaPlayer
                self._media_player.stop()
            except Exception:
                pass
        # 停止 pyttsx3
        if self._pyttsx3_engine is not None:
            try:
                self._pyttsx3_engine.stop()
            except Exception:
                pass

    def speak(self, text: str, on_done: Optional[Callable] = None,
              on_error: Optional[Callable] = None):
        """
        异步朗读文本（不阻塞 UI）
        text: 要朗读的文本
        on_done(): 播放完成回调
        on_error(msg): 出错回调
        """
        if not self.enabled or not text.strip():
            return

        # 停止上一条
        self._stop_flag = True
        if self._play_thread and self._play_thread.is_alive():
            self._play_thread.join(timeout=1.5)

        self._stop_flag = False

        def _run():
            backend = self._detect_backend()
            print(f"[TTS] 后端={backend}, 文本={text[:30]}...")
            try:
                if backend == "edge":
                    success = self._speak_edge(text)
                    # edge-tts 失败时自动降级到 pyttsx3
                    if not success:
                        print("[TTS] edge-tts 失败，降级到 pyttsx3")
                        if self._pyttsx3_engine is None:
                            self._try_init_pyttsx3()
                        if self._pyttsx3_engine:
                            self._speak_pyttsx3(text)
                        else:
                            print("[TTS] 无可用后端")
                elif backend == "pyttsx3":
                    self._speak_pyttsx3(text)
                else:
                    print("[TTS] 无可用后端，请安装: pip install edge-tts")
                if on_done and not self._stop_flag:
                    on_done()
            except Exception as e:
                print(f"[TTS] 播放失败: {e}")
                if on_error:
                    on_error(str(e))

        self._play_thread = threading.Thread(target=_run, daemon=True)
        self._play_thread.start()

    def _try_init_pyttsx3(self):
        """尝试初始化 pyttsx3 作为降级方案"""
        try:
            import pyttsx3
            engine = pyttsx3.init()
            voices = engine.getProperty("voices")
            for v in voices:
                if "zh" in v.id.lower() or "chinese" in v.name.lower():
                    engine.setProperty("voice", v.id)
                    break
            self._pyttsx3_engine = engine
            self._backend = "pyttsx3"
        except Exception as e:
            print(f"[TTS] pyttsx3 初始化失败: {e}")

    def _speak_edge(self, text: str) -> bool:
        """
        Edge TTS 朗读 + QMediaPlayer 播放
        返回 True 表示成功，False 表示失败（需要降级）
        """
        # 清理 markdown 标记
        clean = re.sub(r'[*#`_\[\]()]', '', text)
        clean = re.sub(r'\n+', '。', clean).strip()
        if not clean:
            return False

        # 写临时音频文件
        tmp = tempfile.NamedTemporaryFile(
            delete=False, suffix=".mp3", prefix="agi_tts_"
        )
        tmp.close()
        tmp_path = tmp.name

        try:
            # 1. 合成 mp3
            import edge_tts

            async def _synthesize():
                communicate = edge_tts.Communicate(
                    text=clean,
                    voice=self.voice,
                    rate=self.rate,
                    volume=self.volume
                )
                await communicate.save(tmp_path)

            # 使用新的事件循环，避免冲突
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(_synthesize())
            finally:
                loop.close()

            if not os.path.exists(tmp_path) or os.path.getsize(tmp_path) < 100:
                print("[TTS] edge-tts 生成的文件为空或过小")
                return False

            if self._stop_flag:
                os.unlink(tmp_path)
                return False

            # 2. 播放 mp3
            return self._play_audio(tmp_path)

        except Exception as e:
            print(f"[TTS] edge-tts 失败: {e}")
            try:
                os.unlink(tmp_path)
            except Exception:
                pass
            return False

    def _play_audio(self, file_path: str) -> bool:
        """
        播放音频文件
        优先 QMediaPlayer，回退 winsound / 系统播放器
        """
        # 方案 1：QMediaPlayer（推荐）
        if self._ensure_qt_player():
            return self._play_with_qt(file_path)

        # 方案 2：winsound（Windows）
        if sys.platform == "win32":
            return self._play_with_winsound(file_path)

        # 方案 3：系统播放器
        return self._play_with_system(file_path)

    def _play_with_qt(self, file_path: str) -> bool:
        """使用 QMediaPlayer 播放（主线程安全）"""
        try:
            from PyQt6.QtCore import QUrl, QEventLoop
            from PyQt6.QtMultimedia import QMediaPlayer

            finished = threading.Event()
            error_msg = [None]

            def _on_state_changed(state):
                if state == QMediaPlayer.StoppedState:
                    finished.set()
                elif state == QMediaPlayer.ErrorState:
                    error_msg[0] = str(self._media_player.errorString())
                    finished.set()

            def _on_media_status(status):
                if status == QMediaPlayer.MediaStatus.EndOfMedia:
                    finished.set()

            # 在主线程中操作 QMediaPlayer
            def _setup_and_play():
                try:
                    self._media_player.stateChanged.connect(_on_state_changed)
                    self._media_player.mediaStatusChanged.connect(_on_media_status)
                    self._media_player.setSource(QUrl.fromLocalFile(file_path))
                    self._media_player.play()
                except Exception as e:
                    error_msg[0] = str(e)
                    finished.set()

            if self._qapp and threading.current_thread() is not self._qapp.thread():
                # 非主线程：通过信号安全调用
                from PyQt6.QtCore import QTimer
                QTimer.singleShot(0, _setup_and_play)
            else:
                _setup_and_play()

            # 等待播放完成或停止
            finished.wait(timeout=300)  # 最多 5 分钟
            return error_msg[0] is None

        except Exception as e:
            print(f"[TTS] QMediaPlayer 播放失败: {e}")
            return False
        finally:
            try:
                os.unlink(file_path)
            except Exception:
                pass

    def _play_with_winsound(self, file_path: str) -> bool:
        """winsound 回退（Windows）"""
        try:
            import winsound
            winsound.PlaySound(file_path, winsound.SND_FILENAME | winsound.SND_ASYNC)
            # 估算等待
            try:
                duration = self._estimate_mp3_duration(file_path)
                if not self._stop_flag:
                    import time as _time
                    _time.sleep(duration)
            except Exception:
                pass
            winsound.PlaySound(None, winsound.SND_PURGE)
            return True
        except Exception as e:
            print(f"[TTS] winsound 播放失败: {e}")
            return False
        finally:
            try:
                os.unlink(file_path)
            except Exception:
                pass

    def _play_with_system(self, file_path: str) -> bool:
        """系统默认播放器回退"""
        try:
            import subprocess
            if sys.platform == "darwin":
                subprocess.run(["afplay", file_path], check=True, capture_output=True)
            else:
                for player in ["mpg123", "ffplay", "mplayer"]:
                    if subprocess.run(
                        ["which", player], capture_output=True
                    ).returncode == 0:
                        subprocess.run(
                            [player, "-q", file_path], capture_output=True
                        )
                        break
                else:
                    # Windows 最后兜底
                    if sys.platform == "win32":
                        os.startfile(file_path)
            return True
        except Exception as e:
            print(f"[TTS] 系统播放器失败: {e}")
            return False
        finally:
            try:
                os.unlink(file_path)
            except Exception:
                pass

    def _speak_pyttsx3(self, text: str):
        """pyttsx3 离线朗读"""
        import re
        clean = re.sub(r'[*#`_\[\]()]', '', text)
        clean = re.sub(r'\n+', '，', clean).strip()
        with self._lock:
            if self._pyttsx3_engine and not self._stop_flag:
                self._pyttsx3_engine.say(clean)
                self._pyttsx3_engine.runAndWait()

    @staticmethod
    def _estimate_mp3_duration(path: str) -> float:
        """粗略估算 mp3 时长（秒）"""
        try:
            size = os.path.getsize(path)
            return max(1.0, size / 16000)
        except Exception:
            return 5.0

    def set_voice(self, voice_id: str):
        self.voice = voice_id

    def set_rate(self, percent: int):
        """percent: -50 ~ +50"""
        sign = "+" if percent >= 0 else ""
        self.rate = f"{sign}{percent}%"

    @staticmethod
    def install_guide() -> str:
        return (
            "安装 Edge TTS（推荐，完全免费）：\n"
            "  pip install edge-tts\n\n"
            "离线备选方案（无需联网）：\n"
            "  pip install pyttsx3\n\n"
            "安装完成后重启应用即可使用语音朗读。"
        )


# 全局单例
_tts_instance: Optional[TTSEngine] = None

def get_tts() -> TTSEngine:
    global _tts_instance
    if _tts_instance is None:
        _tts_instance = TTSEngine()
    return _tts_instance
