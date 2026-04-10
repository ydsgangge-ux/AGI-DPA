"""
多模态 LLM 客户端（独立于文本 LLM）
用于图片/视频/音频的理解分析，作为工具被 B 层按需调用

支持：
  - OpenAI GPT-4o / GPT-4V
  - Anthropic Claude (vision)
  - Google Gemini (multimodal)
  - 通义千问 Qwen-VL
  - 智谱 GLM-4V
  - Ollama 本地多模态模型 (llava, llava-llama3, bakllava 等)
"""

import os
import json
import base64
import urllib.request
import urllib.error
from typing import Dict, Optional, List, Tuple, Any
from pathlib import Path


# ── 多模态服务商信息 ──────────────────────────────────────────
VISION_PROVIDER_INFO = {
    "openai": {
        "name": "OpenAI (GPT-4o)",
        "url": "https://platform.openai.com",
        "models": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo"],
        "default_model": "gpt-4o",
        "supports": ["image", "video_note"],
    },
    "claude": {
        "name": "Anthropic Claude (Vision)",
        "url": "https://console.anthropic.com",
        "models": ["claude-3-5-sonnet-20241022", "claude-3-5-haiku-20241022",
                   "claude-3-opus-20240229"],
        "default_model": "claude-3-5-sonnet-20241022",
        "supports": ["image"],
    },
    "gemini": {
        "name": "Google Gemini (Multimodal)",
        "url": "https://aistudio.google.com",
        "models": ["gemini-2.0-flash", "gemini-1.5-pro", "gemini-1.5-flash"],
        "default_model": "gemini-2.0-flash",
        "supports": ["image", "video", "audio"],
    },
    "qwen": {
        "name": "通义千问 Qwen-VL",
        "url": "https://dashscope.console.aliyun.com",
        "models": ["qwen-vl-plus", "qwen-vl-max"],
        "default_model": "qwen-vl-plus",
        "supports": ["image"],
    },
    "zhipu": {
        "name": "智谱 GLM-4V",
        "url": "https://open.bigmodel.cn",
        "models": ["glm-4v-plus", "glm-4v"],
        "default_model": "glm-4v-plus",
        "supports": ["image"],
    },
    "ollama": {
        "name": "Ollama (Local Vision)",
        "url": "https://ollama.ai",
        "models": ["llava", "llava:13b", "llava-llama3", "bakllava",
                   "llava-phi3", "minicpm-v"],
        "default_model": "llava",
        "supports": ["image"],
    },
}


def _encode_file_to_base64(file_path: str) -> Tuple[str, str]:
    """
    将文件编码为 base64，返回 (base64_str, media_type)
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"文件不存在: {file_path}")

    with open(file_path, "rb") as f:
        data = f.read()

    ext = path.suffix.lower().lstrip(".")
    media_map = {
        # 图片
        "jpg": "image/jpeg", "jpeg": "image/jpeg",
        "png": "image/png", "gif": "image/gif",
        "webp": "image/webp", "bmp": "image/bmp",
        # 视频
        "mp4": "video/mp4", "avi": "video/x-msvideo",
        "mov": "video/quicktime", "mkv": "video/x-matroska",
        "webm": "video/webm",
        # 音频
        "mp3": "audio/mpeg", "wav": "audio/wav",
        "ogg": "audio/ogg", "flac": "audio/flac",
        "m4a": "audio/mp4", "aac": "audio/aac",
        "wma": "audio/x-ms-wma",
    }
    media_type = media_map.get(ext, "application/octet-stream")
    b64_str = base64.b64encode(data).decode("utf-8")
    return b64_str, media_type


class VisionClient:
    """
    多模态 LLM 客户端基类
    独立于文本 LLM，专门处理图片/视频/音频的理解分析
    """

    def __init__(self, provider: str, model: str, api_key: str = "",
                 base_url: str = ""):
        self.provider = provider
        self.model = model
        self.api_key = api_key
        self.base_url = base_url.rstrip("/") if base_url else ""

    def analyze(self, file_path: str, question: str = "",
                max_tokens: int = 2000, temperature: float = 0.3) -> Dict:
        """
        分析文件（图片/视频/音频），返回结果

        Args:
            file_path: 文件路径
            question: 关于文件的问题
            max_tokens: 最大 token 数
            temperature: 温度

        Returns:
            {"ok": True, "description": "..."} 或 {"ok": False, "error": "..."}
        """
        try:
            b64_str, media_type = _encode_file_to_base64(file_path)

            # 判断媒体类型
            modality = "image"
            if media_type.startswith("video/"):
                modality = "video"
            elif media_type.startswith("audio/"):
                modality = "audio"

            # 检查 provider 是否支持该类型
            info = VISION_PROVIDER_INFO.get(self.provider, {})
            supported = info.get("supports", [])
            if modality not in supported:
                return {
                    "ok": False,
                    "error": f"{info.get('name', self.provider)} 不支持 {modality} 类型",
                    "tip": "请切换到支持该类型的多模态模型（如 Gemini 支持视频和音频）"
                }

            prompt = question or "请详细描述这个文件的内容。"

            if self.provider == "openai":
                return self._call_openai(b64_str, media_type, prompt,
                                         max_tokens, temperature)
            elif self.provider == "claude":
                return self._call_claude(b64_str, media_type, prompt,
                                        max_tokens, temperature)
            elif self.provider == "gemini":
                return self._call_gemini(b64_str, media_type, prompt,
                                         max_tokens, temperature)
            elif self.provider == "qwen":
                return self._call_openai_compat(b64_str, media_type, prompt,
                                                max_tokens, temperature)
            elif self.provider == "zhipu":
                return self._call_openai_compat(b64_str, media_type, prompt,
                                                max_tokens, temperature)
            elif self.provider == "ollama":
                return self._call_ollama(b64_str, media_type, prompt,
                                         max_tokens, temperature)
            else:
                return {"ok": False, "error": f"不支持的多模态服务商: {self.provider}"}

        except FileNotFoundError as e:
            return {"ok": False, "error": str(e)}
        except Exception as e:
            return {"ok": False, "error": f"分析失败: {e}"}

    def _call_openai(self, b64_str: str, media_type: str, prompt: str,
                     max_tokens: int, temperature: float) -> Dict:
        """OpenAI Vision API (GPT-4o / GPT-4V)"""
        data_url = f"data:{media_type};base64,{b64_str}"
        payload = json.dumps({
            "model": self.model,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "image_url",
                     "image_url": {"url": data_url}},
                    {"type": "text", "text": prompt}
                ]
            }],
            "max_tokens": max_tokens,
            "temperature": temperature
        }, ensure_ascii=False).encode("utf-8")

        req = urllib.request.Request(
            f"{self.base_url}/chat/completions" if self.base_url
            else "https://api.openai.com/v1/chat/completions",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}"
            }
        )
        with urllib.request.urlopen(req, timeout=60) as r:
            data = json.loads(r.read())
        return {
            "ok": True,
            "description": data["choices"][0]["message"]["content"],
            "model": self.model,
            "provider": "openai"
        }

    def _call_claude(self, b64_str: str, media_type: str, prompt: str,
                     max_tokens: int, temperature: float) -> Dict:
        """Anthropic Claude Vision API"""
        # Claude 仅支持图片
        if not media_type.startswith("image/"):
            return {"ok": False, "error": "Claude 目前仅支持图片分析"}

        payload = json.dumps({
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "image",
                     "source": {"type": "base64", "media_type": media_type,
                                "data": b64_str}},
                    {"type": "text", "text": prompt}
                ]
            }]
        }, ensure_ascii=False).encode("utf-8")

        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01"
            }
        )
        with urllib.request.urlopen(req, timeout=60) as r:
            data = json.loads(r.read())
        return {
            "ok": True,
            "description": data["content"][0]["text"],
            "model": self.model,
            "provider": "claude"
        }

    def _call_gemini(self, b64_str: str, media_type: str, prompt: str,
                     max_tokens: int, temperature: float) -> Dict:
        """Google Gemini Multimodal API（支持图片、视频、音频）"""
        parts = [
            {"inline_data": {"mime_type": media_type, "data": b64_str}},
            {"text": prompt}
        ]

        body = {
            "contents": [{"parts": parts}],
            "generationConfig": {
                "maxOutputTokens": max_tokens,
                "temperature": temperature
            }
        }

        url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
               f"{self.model}:generateContent?key={self.api_key}")
        payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(url, data=payload,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=120) as r:
            data = json.loads(r.read())
        return {
            "ok": True,
            "description": data["candidates"][0]["content"]["parts"][0]["text"],
            "model": self.model,
            "provider": "gemini"
        }

    def _call_openai_compat(self, b64_str: str, media_type: str, prompt: str,
                            max_tokens: int, temperature: float) -> Dict:
        """
        OpenAI 兼容格式的 Vision API
        适用于：通义千问 Qwen-VL、智谱 GLM-4V
        """
        data_url = f"data:{media_type};base64,{b64_str}"

        # 根据不同服务商设置 base_url
        if not self.base_url:
            if self.provider == "qwen":
                self.base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
            elif self.provider == "zhipu":
                self.base_url = "https://open.bigmodel.cn/api/paas/v4"

        payload = json.dumps({
            "model": self.model,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "image_url",
                     "image_url": {"url": data_url}},
                    {"type": "text", "text": prompt}
                ]
            }],
            "max_tokens": max_tokens,
            "temperature": temperature
        }, ensure_ascii=False).encode("utf-8")

        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}"
            }
        )
        with urllib.request.urlopen(req, timeout=60) as r:
            data = json.loads(r.read())
        return {
            "ok": True,
            "description": data["choices"][0]["message"]["content"],
            "model": self.model,
            "provider": self.provider
        }

    def _call_ollama(self, b64_str: str, media_type: str, prompt: str,
                     max_tokens: int, temperature: float) -> Dict:
        """Ollama 本地 Vision API"""
        if not self.base_url:
            self.base_url = "http://localhost:11434"

        # Ollama 的图片格式
        payload = json.dumps({
            "model": self.model,
            "messages": [{
                "role": "user",
                "content": prompt,
                "images": [b64_str]
            }],
            "stream": False,
            "options": {"num_predict": max_tokens, "temperature": temperature}
        }, ensure_ascii=False).encode("utf-8")

        req = urllib.request.Request(
            f"{self.base_url}/api/chat",
            data=payload,
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=120) as r:
            data = json.loads(r.read())
        return {
            "ok": True,
            "description": data["message"]["content"],
            "model": self.model,
            "provider": "ollama"
        }


def create_vision_client(
    provider: str = None,
    model: str = None,
    api_key: str = None,
    base_url: str = None,
    config: dict = None
) -> Optional[VisionClient]:
    """
    工厂函数：创建多模态客户端

    优先使用传入参数，其次从 config 字典读取，最后使用默认值。
    如果没有配置有效的 API Key 且不是 Ollama，返回 None。
    """
    if config is None:
        try:
            from desktop.config import load_config
            config = load_config()
        except Exception:
            config = {}

    eff_provider = provider or config.get("vision_provider", "")
    eff_model = model or config.get("vision_model", "")
    eff_api_key = api_key or config.get("vision_api_key", "")
    eff_base_url = base_url or config.get("vision_base_url", "")

    if not eff_provider:
        # 自动推断：如果没有专门配 vision，看主 LLM 是否支持多模态
        main_provider = config.get("api_provider", "")
        if main_provider in ("openai", "claude", "gemini", "qwen", "zhipu", "ollama"):
            eff_provider = main_provider
            eff_api_key = eff_api_key or config.get("api_key", "")
            if main_provider == "ollama":
                eff_base_url = eff_base_url or config.get("ollama_url", "")
            # 如果是同一个 provider，尝试用 vision 专用模型
            info = VISION_PROVIDER_INFO.get(main_provider, {})
            eff_model = eff_model or info.get("default_model", "")
        else:
            return None

    if not eff_model:
        info = VISION_PROVIDER_INFO.get(eff_provider, {})
        eff_model = info.get("default_model", "")

    if eff_provider == "ollama":
        return VisionClient(
            provider="ollama",
            model=eff_model,
            base_url=eff_base_url or "http://localhost:11434"
        )

    if not eff_api_key or eff_api_key in ("", "YOUR_API_KEY_HERE"):
        return None

    return VisionClient(
        provider=eff_provider,
        model=eff_model,
        api_key=eff_api_key,
        base_url=eff_base_url
    )


def check_vision_available(config: dict = None) -> Dict:
    """
    检查多模态能力是否可用，返回状态信息
    """
    if config is None:
        try:
            from desktop.config import load_config
            config = load_config()
        except Exception:
            config = {}

    eff_provider = config.get("vision_provider", "")
    eff_model = config.get("vision_model", "")
    eff_api_key = config.get("vision_api_key", "")

    # 没有专门配置 vision
    if not eff_provider:
        main_provider = config.get("api_provider", "")
        if main_provider in ("openai", "claude", "gemini", "qwen", "zhipu", "ollama"):
            info = VISION_PROVIDER_INFO.get(main_provider, {})
            return {
                "available": bool(config.get("api_key") or main_provider == "ollama"),
                "source": "auto_inherit",
                "provider": main_provider,
                "model": info.get("default_model", ""),
                "message": f"自动继承主 LLM（{info.get('name', main_provider)}）的多模态能力"
            }
        return {
            "available": False,
            "source": "none",
            "provider": "",
            "model": "",
            "message": "当前主 LLM 不支持多模态，请在设置中配置多模态模型"
        }

    # 有专门配置
    if eff_provider == "ollama":
        return {
            "available": True,
            "source": "dedicated",
            "provider": eff_provider,
            "model": eff_model or "llava",
            "message": f"Ollama 本地多模态: {eff_model or 'llava'}"
        }

    if eff_api_key and eff_api_key not in ("", "YOUR_API_KEY_HERE"):
        info = VISION_PROVIDER_INFO.get(eff_provider, {})
        return {
            "available": True,
            "source": "dedicated",
            "provider": eff_provider,
            "model": eff_model,
            "message": f"{info.get('name', eff_provider)} ({eff_model})"
        }

    return {
        "available": False,
        "source": "missing_key",
        "provider": eff_provider,
        "model": eff_model,
        "message": f"已选择 {eff_provider} 但未配置 API Key"
    }
