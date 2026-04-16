"""
语音合成引擎（TTS）
优先级：edge-tts（微软在线，高质量）> pyttsx3（离线兜底）> 静默降级

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
    edge-tts 生成 mp3 → winsound/系统播放器 播放
    edge-tts 失败时自动降级到 pyttsx3（离线）
    """

    def __init__(self):
        self._backend    = None   # 'edge' | 'pyttsx3' | None
        self._pyttsx3_engine = None
        self._lock       = threading.Lock()
        self._play_thread: Optional[threading.Thread] = None
        self._stop_flag  = False

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
            "edge":    "Microsoft Edge TTS（高质量）",
            "pyttsx3": "系统 TTS（离线兜底）",
            "none":    "未安装（pip install edge-tts）"
        }.get(b, "未知")

    def stop(self):
        """停止当前播放"""
        self._stop_flag = True
        if sys.platform == "win32":
            try:
                import winsound
                winsound.PlaySound(None, winsound.SND_PURGE)
            except Exception:
                pass
        if self._pyttsx3_engine is not None:
            try:
                self._pyttsx3_engine.stop()
            except Exception:
                pass

    def speak(self, text: str, on_done: Optional[Callable] = None,
              on_error: Optional[Callable] = None):
        """
        异步朗读文本（不阻塞 UI）
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
        """Edge TTS 合成 + 播放"""
        clean = re.sub(r'[*#`_\[\]()]', '', text)
        clean = re.sub(r'\n+', '。', clean).strip()
        if not clean:
            return False

        tmp = tempfile.NamedTemporaryFile(
            delete=False, suffix=".mp3", prefix="agi_tts_"
        )
        tmp.close()
        tmp_path = tmp.name

        try:
            import edge_tts

            async def _synthesize():
                communicate = edge_tts.Communicate(
                    text=clean,
                    voice=self.voice,
                    rate=self.rate,
                    volume=self.volume
                )
                await communicate.save(tmp_path)

            # 独立事件循环，避免与 Qt 事件循环冲突
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

            # 播放
            return self._play_mp3(tmp_path)

        except Exception as e:
            print(f"[TTS] edge-tts 失败: {e}")
            try:
                os.unlink(tmp_path)
            except Exception:
                pass
            return False

    def _play_mp3(self, file_path: str) -> bool:
        """播放 mp3 文件"""
        if sys.platform == "win32":
            return self._play_winsound(file_path)
        elif sys.platform == "darwin":
            return self._play_system(file_path, ["afplay"])
        else:
            # Linux: 依次尝试
            for player in ["mpg123", "ffplay", "mplayer"]:
                if self._play_system(file_path, [player, "-q"]):
                    return True
            return False

    def _play_winsound(self, file_path: str) -> bool:
        """Windows MCI 播放 MP3（支持任意线程，无需消息循环）"""
        try:
            import ctypes
            mci = ctypes.windll.winmm
            alias = "agi_tts"
            # 关闭之前的
            mci.mciSendStringW(f"close {alias}", None, 0, None)
            # 打开并播放
            short_path = os.path.abspath(file_path)
            ret = mci.mciSendStringW(
                f'open "{short_path}" type mpegvideo alias {alias}',
                None, 0, None
            )
            if ret != 0:
                # 取错误信息
                buf = ctypes.create_unicode_buffer(256)
                mci.mciGetErrorStringW(ret, buf, 256)
                print(f"[TTS] MCI open 失败: {buf.value}")
                return False
            mci.mciSendStringW(f"play {alias} wait", None, 0, None)
            return True
        except Exception as e:
            print(f"[TTS] MCI 播放失败: {e}")
            return False
        finally:
            try:
                import ctypes
                ctypes.windll.winmm.mciSendStringW(f"close agi_tts", None, 0, None)
            except Exception:
                pass
            try:
                os.unlink(file_path)
            except Exception:
                pass

    def _play_system(self, file_path: str, cmd: list) -> bool:
        """用外部播放器播放"""
        try:
            import subprocess
            subprocess.run(cmd + [file_path], check=True, capture_output=True)
            return True
        except Exception as e:
            print(f"[TTS] 播放器失败: {e}")
            return False
        finally:
            try:
                os.unlink(file_path)
            except Exception:
                pass

    def _speak_pyttsx3(self, text: str):
        """pyttsx3 离线朗读"""
        clean = re.sub(r'[*#`_\[\]()]', '', text)
        clean = re.sub(r'\n+', '，', clean).strip()
        with self._lock:
            if self._pyttsx3_engine and not self._stop_flag:
                self._pyttsx3_engine.say(clean)
                self._pyttsx3_engine.runAndWait()

    @staticmethod
    def _estimate_mp3_duration(path: str) -> float:
        """估算 mp3 时长（秒）"""
        try:
            size = os.path.getsize(path)
            return max(1.0, size / 16000)
        except Exception:
            return 5.0

    def set_voice(self, voice_id: str):
        self.voice = voice_id

    def set_rate(self, percent: int):
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
