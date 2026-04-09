"""
语音合成引擎（TTS）
优先级：edge-tts（微软，免费无限制）> pyttsx3（系统TTS）> 静默降级

安装：pip install edge-tts
推荐中文声音：
  zh-CN-XiaoxiaoNeural   小晓（女，温柔自然，默认）
  zh-CN-YunxiNeural      云希（男，活泼）
  zh-CN-YunjianNeural    云健（男，成熟稳重）
  zh-TW-HsiaoChenNeural  台湾中文（女）
"""

import asyncio
import os
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
    设计为懒加载：import 时不执行，第一次调用时才检测依赖
    """

    def __init__(self):
        self._backend    = None   # 'edge' | 'pyttsx3' | None
        self._pyttsx3_engine = None
        self._lock       = threading.Lock()
        self._play_thread: Optional[threading.Thread] = None
        self._stop_flag  = False

        # 配置
        self.voice       = "zh-CN-XiaoxiaoNeural"
        self.rate        = "+0%"    # 语速调节：+10% 快10%，-10% 慢10%
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
            # 尝试设置中文声音
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
            "pyttsx3": "系统 TTS（基础质量）",
            "none":    "未安装（pip install edge-tts）"
        }.get(b, "未知")

    def stop(self):
        """停止当前播放"""
        self._stop_flag = True

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
            self._play_thread.join(timeout=1.0)

        self._stop_flag = False

        def _run():
            backend = self._detect_backend()
            print(f"[TTS] 后端={backend}, 文本={text[:30]}...")
            try:
                if backend == "edge":
                    self._speak_edge(text)
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

    def _speak_edge(self, text: str):
        """Edge TTS 朗读"""
        import edge_tts
        import subprocess
        import sys

        # 清理 markdown 标记，避免朗读出 * # 等符号
        import re
        clean = re.sub(r'[*#`_\[\]()]', '', text)
        clean = re.sub(r'\n+', '。', clean).strip()
        if not clean:
            return

        # 写临时音频文件
        tmp = tempfile.NamedTemporaryFile(
            delete=False, suffix=".mp3", prefix="agi_tts_"
        )
        tmp.close()
        tmp_path = tmp.name

        async def _synthesize():
            communicate = edge_tts.Communicate(
                text=clean,
                voice=self.voice,
                rate=self.rate,
                volume=self.volume
            )
            await communicate.save(tmp_path)

        asyncio.run(_synthesize())

        if self._stop_flag:
            os.unlink(tmp_path)
            return

        # 播放音频（跨平台）
        try:
            if sys.platform == "win32":
                # Windows: 用 winsound 异步播放，不阻塞线程
                import winsound
                winsound.PlaySound(tmp_path, winsound.SND_FILENAME | winsound.SND_ASYNC)
                # 等待播放完成（异步播放无法精确检测，估算时长）
                try:
                    duration = self._estimate_mp3_duration(tmp_path)
                    if not self._stop_flag:
                        import time as _time
                        _time.sleep(duration)
                except Exception:
                    pass
            elif sys.platform == "darwin":
                subprocess.run(["afplay", tmp_path], check=True)
            else:
                # Linux: 尝试 mpg123 / ffplay / aplay
                for player in ["mpg123", "ffplay", "mplayer"]:
                    if subprocess.run(
                        ["which", player],
                        capture_output=True
                    ).returncode == 0:
                        subprocess.run(
                            [player, "-q", tmp_path],
                            capture_output=True
                        )
                        break
        finally:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass

    def _speak_pyttsx3(self, text: str):
        """pyttsx3 后备方案"""
        import re
        clean = re.sub(r'[*#`_\[\]()]', '', text)
        clean = re.sub(r'\n+', '，', clean).strip()
        with self._lock:
            if self._pyttsx3_engine and not self._stop_flag:
                self._pyttsx3_engine.say(clean)
                self._pyttsx3_engine.runAndWait()

    @staticmethod
    def _estimate_mp3_duration(path: str) -> float:
        """粗略估算 mp3 时长（秒），用于异步播放时等待"""
        try:
            size = os.path.getsize(path)
            # mp3 平均码率约 128kbps = 16KB/s
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
            "安装完成后重启应用即可使用高质量中文语音。\n"
            "不需要 API Key，不需要联网账号。"
        )


# 全局单例
_tts_instance: Optional[TTSEngine] = None

def get_tts() -> TTSEngine:
    global _tts_instance
    if _tts_instance is None:
        _tts_instance = TTSEngine()
    return _tts_instance
