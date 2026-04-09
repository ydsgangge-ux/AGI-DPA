"""
LLM 客户端
支持：DeepSeek / OpenAI / Anthropic Claude / Google Gemini / Groq / Ollama / Mock

所有客户端统一接口：
  generate(prompt, system, max_tokens, temperature, messages) -> str
"""

import json
import urllib.request
import urllib.error
from typing import List, Dict, Optional


# ── 通用 OpenAI 格式客户端（DeepSeek/OpenAI/Groq/任何兼容接口）──────────
class OpenAICompatClient:
    """兼容 OpenAI Chat Completions API 格式的通用客户端"""

    def __init__(self, api_key: str, base_url: str, model: str):
        self.api_key  = api_key
        self.base_url = base_url.rstrip("/")
        self.model    = model

    def generate(self, prompt: str, system: str = None,
                 max_tokens: int = 1000, temperature: float = 0.7,
                 messages: List[Dict] = None) -> str:
        if messages is None:
            msgs = []
            if system:
                msgs.append({"role": "system", "content": system})
            msgs.append({"role": "user", "content": prompt})
        else:
            msgs = messages

        payload = json.dumps({
            "model": self.model, "messages": msgs,
            "max_tokens": max_tokens, "temperature": temperature
        }, ensure_ascii=False).encode("utf-8")

        req = urllib.request.Request(
            f"{self.base_url}/chat/completions", data=payload,
            headers={"Content-Type": "application/json; charset=utf-8",
                     "Authorization": f"Bearer {self.api_key}"}
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read())["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"HTTP {e.code}: {body[:300]}")
        except urllib.error.URLError as e:
            raise RuntimeError(f"Network error: {e.reason}")


# ── DeepSeek ──────────────────────────────────────────────────────────────
class DeepSeekClient(OpenAICompatClient):
    def __init__(self, api_key: str, model: str = "deepseek-chat"):
        super().__init__(api_key,
                         "https://api.deepseek.com/v1",
                         model)


# ── OpenAI ───────────────────────────────────────────────────────────────
class OpenAIClient(OpenAICompatClient):
    def __init__(self, api_key: str, model: str = "gpt-4o-mini"):
        super().__init__(api_key,
                         "https://api.openai.com/v1",
                         model)


# ── Groq（免费额度充足，速度极快）────────────────────────────────────────
class GroqClient(OpenAICompatClient):
    def __init__(self, api_key: str, model: str = "llama-3.3-70b-versatile"):
        super().__init__(api_key,
                         "https://api.groq.com/openai/v1",
                         model)


# ── 通义千问 (Qwen / 阿里云 DashScope) ───────────────────────────────────
class QwenClient(OpenAICompatClient):
    def __init__(self, api_key: str, model: str = "qwen-plus"):
        super().__init__(api_key,
                         "https://dashscope.aliyuncs.com/compatible-mode/v1",
                         model)


# ── 智谱 GLM (ZhipuAI) ──────────────────────────────────────────────────
class ZhipuClient(OpenAICompatClient):
    def __init__(self, api_key: str, model: str = "glm-4-flash"):
        super().__init__(api_key,
                         "https://open.bigmodel.cn/api/paas/v4",
                         model)


# ── 豆包 (Doubao / 字节跳动 火山引擎) ────────────────────────────────────
class DoubaoClient(OpenAICompatClient):
    def __init__(self, api_key: str, model: str = "doubao-pro-32k"):
        super().__init__(api_key,
                         "https://ark.cn-beijing.volces.com/api/v3",
                         model)


# ── Kimi (Moonshot / 月之暗面) ──────────────────────────────────────────
class KimiClient(OpenAICompatClient):
    def __init__(self, api_key: str, model: str = "moonshot-v1-8k"):
        super().__init__(api_key,
                         "https://api.moonshot.cn/v1",
                         model)


# ── 文心一言 (Baidu ERNIE) ───────────────────────────────────────────────
class BaiduClient(OpenAICompatClient):
    def __init__(self, api_key: str, model: str = "ernie-speed-128k"):
        super().__init__(api_key,
                         "https://qianfan.baidubce.com/v2",
                         model)


# ── 讯飞星火 (SparkDesk) ────────────────────────────────────────────────
class SparkClient(OpenAICompatClient):
    def __init__(self, api_key: str, model: str = "generalv3.5"):
        super().__init__(api_key,
                         "https://spark-api-open.xf-yun.com/v1",
                         model)


# ── Anthropic Claude ──────────────────────────────────────────────────────
class ClaudeClient:
    BASE_URL = "https://api.anthropic.com/v1/messages"

    def __init__(self, api_key: str, model: str = "claude-3-5-haiku-20241022"):
        self.api_key = api_key
        self.model   = model

    def generate(self, prompt: str, system: str = None,
                 max_tokens: int = 1000, temperature: float = 0.7,
                 messages: List[Dict] = None) -> str:
        if messages is None:
            msgs = [{"role": "user", "content": prompt}]
        else:
            # 过滤掉 system 角色（Claude 单独传）
            msgs = [m for m in messages if m.get("role") != "system"]
            if not msgs:
                msgs = [{"role": "user", "content": prompt}]

        body = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": msgs
        }
        if system:
            body["system"] = system

        payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            self.BASE_URL, data=payload,
            headers={
                "Content-Type": "application/json",
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01"
            }
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                data = json.loads(r.read())
                return data["content"][0]["text"]
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Claude HTTP {e.code}: {body[:300]}")
        except urllib.error.URLError as e:
            raise RuntimeError(f"Network error: {e.reason}")


# ── Google Gemini ─────────────────────────────────────────────────────────
class GeminiClient:
    BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"

    def __init__(self, api_key: str, model: str = "gemini-1.5-flash"):
        self.api_key = api_key
        self.model   = model

    def generate(self, prompt: str, system: str = None,
                 max_tokens: int = 1000, temperature: float = 0.7,
                 messages: List[Dict] = None) -> str:
        # 构建 Gemini 格式
        contents = []
        if messages:
            for m in messages:
                role = "user" if m["role"] == "user" else "model"
                contents.append({"role": role,
                                  "parts": [{"text": m["content"]}]})
        else:
            if system:
                contents.append({"role": "user",
                                  "parts": [{"text": f"[System]: {system}\n\n{prompt}"}]})
            else:
                contents.append({"role": "user", "parts": [{"text": prompt}]})

        body = {
            "contents": contents,
            "generationConfig": {
                "maxOutputTokens": max_tokens,
                "temperature": temperature
            }
        }
        if system and not messages:
            body["systemInstruction"] = {"parts": [{"text": system}]}

        url = (f"{self.BASE_URL}/{self.model}:generateContent"
               f"?key={self.api_key}")
        payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            url, data=payload,
            headers={"Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                data = json.loads(r.read())
                return data["candidates"][0]["content"]["parts"][0]["text"]
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Gemini HTTP {e.code}: {body[:300]}")
        except urllib.error.URLError as e:
            raise RuntimeError(f"Network error: {e.reason}")


# ── Ollama 本地 ───────────────────────────────────────────────────────────
class OllamaClient:
    def __init__(self, model: str = "qwen2.5:7b",
                 base_url: str = "http://localhost:11434"):
        self.model    = model
        self.base_url = base_url.rstrip("/")
        self.api_key  = "ollama"

    def generate(self, prompt: str, system: str = None,
                 max_tokens: int = 1000, temperature: float = 0.7,
                 messages: List[Dict] = None) -> str:
        if messages is None:
            msgs = []
            if system:
                msgs.append({"role": "system", "content": system})
            msgs.append({"role": "user", "content": prompt})
        else:
            msgs = messages

        payload = json.dumps({
            "model": self.model, "messages": msgs, "stream": False,
            "options": {"num_predict": max_tokens, "temperature": temperature}
        }, ensure_ascii=False).encode("utf-8")

        req = urllib.request.Request(
            f"{self.base_url}/api/chat", data=payload,
            headers={"Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.loads(r.read())["message"]["content"]
        except urllib.error.URLError as e:
            raise RuntimeError(
                f"Ollama connection failed ({self.base_url}): {e.reason}\n"
                "Please run: ollama serve"
            )

    def list_models(self) -> List[str]:
        try:
            req = urllib.request.Request(f"{self.base_url}/api/tags")
            with urllib.request.urlopen(req, timeout=5) as r:
                return [m["name"] for m in json.loads(r.read()).get("models", [])]
        except Exception:
            return []

    def is_running(self) -> bool:
        try:
            urllib.request.urlopen(f"{self.base_url}/api/tags", timeout=3)
            return True
        except Exception:
            return False


# ── Mock（无 API 时降级）─────────────────────────────────────────────────
class MockClient:
    def generate(self, prompt: str, system: str = None,
                 max_tokens: int = 1000, temperature: float = 0.7,
                 messages: List[Dict] = None) -> str:
        if any(k in prompt for k in ["emotion", "needs_deep_memory",
                                      "情绪类型", "初步感受", "感知结果"]):
            return json.dumps({
                "emotion": {"primary": "curious", "secondary": None,
                            "intensity": 0.6, "valence": 0.4},
                "initial_thoughts": "Interesting question.",
                "topic_tags": ["conversation"], "needs_deep_memory": True,
                "task_type": "chat", "task_description": ""
            }, ensure_ascii=False)
        if any(k in prompt for k in ["inner_reasoning", "storage_decision",
                                      "need_tools", "response_intent"]):
            return json.dumps({
                "inner_reasoning": "Need to respond thoughtfully.",
                "response_intent": "Give a helpful response",
                "response_tone": "natural",
                "need_tools": False, "tool_task": "",
                "storage_decision": {"should_store": False, "importance": 0.3,
                    "modality": "semantic", "what_to_remember": "", "reason": "Mock"}
            }, ensure_ascii=False)
        return ("(Mock mode) Please configure an API key in Settings.\n"
                "Supported: DeepSeek / OpenAI / Claude / Gemini / Groq / "
                "Qwen / Zhipu / Doubao / Kimi / Baidu / SparkDesk / Ollama")


# ── 工厂函数 ──────────────────────────────────────────────────────────────
PROVIDER_INFO = {
    "deepseek": {
        "name": "DeepSeek",
        "url":  "https://platform.deepseek.com",
        "models": ["deepseek-chat", "deepseek-reasoner"],
        "default_model": "deepseek-chat",
    },
    "openai": {
        "name": "OpenAI",
        "url":  "https://platform.openai.com",
        "models": ["gpt-4o-mini", "gpt-4o", "gpt-4-turbo", "gpt-3.5-turbo"],
        "default_model": "gpt-4o-mini",
    },
    "claude": {
        "name": "Anthropic Claude",
        "url":  "https://console.anthropic.com",
        "models": ["claude-3-5-haiku-20241022", "claude-3-5-sonnet-20241022",
                   "claude-3-opus-20240229"],
        "default_model": "claude-3-5-haiku-20241022",
    },
    "gemini": {
        "name": "Google Gemini",
        "url":  "https://aistudio.google.com",
        "models": ["gemini-1.5-flash", "gemini-1.5-pro", "gemini-2.0-flash-exp"],
        "default_model": "gemini-1.5-flash",
    },
    "groq": {
        "name": "Groq (Free tier available)",
        "url":  "https://console.groq.com",
        "models": ["llama-3.3-70b-versatile", "llama-3.1-8b-instant",
                   "mixtral-8x7b-32768", "gemma2-9b-it"],
        "default_model": "llama-3.3-70b-versatile",
    },
    # ── 国产大模型 ──
    "qwen": {
        "name": "通义千问 Qwen",
        "url":  "https://dashscope.console.aliyun.com",
        "models": ["qwen-turbo", "qwen-plus", "qwen-max", "qwen-long",
                   "qwen-vl-plus", "qwen-math-plus"],
        "default_model": "qwen-plus",
    },
    "zhipu": {
        "name": "智谱 GLM",
        "url":  "https://open.bigmodel.cn",
        "models": ["glm-4-flash", "glm-4-air", "glm-4-plus", "glm-4-long",
                   "glm-4v-plus"],
        "default_model": "glm-4-flash",
    },
    "doubao": {
        "name": "豆包 Doubao",
        "url":  "https://console.volcengine.com/ark",
        "models": ["doubao-pro-32k", "doubao-pro-128k", "doubao-lite-32k",
                   "doubao-pro-4k"],
        "default_model": "doubao-pro-32k",
    },
    "kimi": {
        "name": "Kimi (Moonshot)",
        "url":  "https://platform.moonshot.cn",
        "models": ["moonshot-v1-8k", "moonshot-v1-32k", "moonshot-v1-128k"],
        "default_model": "moonshot-v1-8k",
    },
    "baidu": {
        "name": "文心一言 Baidu",
        "url":  "https://console.bce.baidu.com/qianfan",
        "models": ["ernie-speed-128k", "ernie-lite-8k", "ernie-4.0-8k",
                   "ernie-4.0-turbo-8k"],
        "default_model": "ernie-speed-128k",
    },
    "spark": {
        "name": "讯飞星火 SparkDesk",
        "url":  "https://xinghuo.xfyun.cn",
        "models": ["generalv3.5", "generalv3", "4.0Ultra"],
        "default_model": "generalv3.5",
    },
    "ollama": {
        "name": "Ollama (Local, Free)",
        "url":  "https://ollama.ai",
        "models": [],
        "default_model": "qwen2.5:7b",
    },
}


def create_client(api_key: str = None, provider: str = "deepseek",
                  model: str = None,
                  ollama_model: str = "qwen2.5:7b",
                  ollama_url: str = "http://localhost:11434") -> object:

    info = PROVIDER_INFO.get(provider, {})
    effective_model = model or info.get("default_model", "")

    if provider == "ollama":
        client = OllamaClient(model=ollama_model, base_url=ollama_url)
        if client.is_running():
            print(f"✅ Ollama connected, model: {ollama_model}")
        else:
            print(f"⚠️  Ollama not running ({ollama_url}), run: ollama serve")
        return client

    if not api_key or api_key in ("", "YOUR_API_KEY_HERE"):
        print("⚠️  No API key configured, using Mock mode")
        return MockClient()

    if provider == "deepseek":
        print(f"✅ DeepSeek API configured ({effective_model})")
        return DeepSeekClient(api_key, model=effective_model)
    elif provider == "openai":
        print(f"✅ OpenAI API configured ({effective_model})")
        return OpenAIClient(api_key, model=effective_model)
    elif provider == "claude":
        print(f"✅ Anthropic Claude configured ({effective_model})")
        return ClaudeClient(api_key, model=effective_model)
    elif provider == "gemini":
        print(f"✅ Google Gemini configured ({effective_model})")
        return GeminiClient(api_key, model=effective_model)
    elif provider == "groq":
        print(f"✅ Groq configured ({effective_model})")
        return GroqClient(api_key, model=effective_model)
    elif provider == "qwen":
        print(f"✅ 通义千问 configured ({effective_model})")
        return QwenClient(api_key, model=effective_model)
    elif provider == "zhipu":
        print(f"✅ 智谱 GLM configured ({effective_model})")
        return ZhipuClient(api_key, model=effective_model)
    elif provider == "doubao":
        print(f"✅ 豆包 configured ({effective_model})")
        return DoubaoClient(api_key, model=effective_model)
    elif provider == "kimi":
        print(f"✅ Kimi configured ({effective_model})")
        return KimiClient(api_key, model=effective_model)
    elif provider == "baidu":
        print(f"✅ 文心一言 configured ({effective_model})")
        return BaiduClient(api_key, model=effective_model)
    elif provider == "spark":
        print(f"✅ 讯飞星火 configured ({effective_model})")
        return SparkClient(api_key, model=effective_model)

    print("⚠️  Unknown provider, using Mock mode")
    return MockClient()
