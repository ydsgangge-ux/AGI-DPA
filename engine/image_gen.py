"""
pollinations.ai 图片生成模块
生成两种图片：人物自拍 / 周边风景
"""

import os
import uuid
import time
import urllib.request
import urllib.parse
from pathlib import Path
from datetime import datetime
from typing import Optional, Tuple

# 旧域名稳定可用，新域名(gen)可能被地域限制 401，做回退
_BASES = [
    "https://image.pollinations.ai/prompt",
    "https://gen.pollinations.ai/image",
]
DEFAULT_WIDTH = 1024
DEFAULT_HEIGHT = 1024
TIMEOUT = 120


def get_image_dir() -> Path:
    if os.name == "nt":
        root = Path(os.environ.get("APPDATA", str(Path.home()))) / "AGI-Desktop"
    else:
        root = Path.home() / ".agi-desktop"
    d = root / "images"
    d.mkdir(parents=True, exist_ok=True)
    return d


# ── 场景池（随机选取，避免重复）──
_SELFIE_SCENES = [
    "in a cozy cafe, holding a coffee cup, warm lighting",
    "standing by a window, looking outside, natural light",
    "sitting at a desk with books, soft lamp light",
    "walking in a park, autumn leaves falling",
    "in a library, reading a book, quiet atmosphere",
    "on a rooftop at dusk, city skyline background",
    "in a flower garden, spring morning",
    "at a beach, ocean waves, sunset",
    "in a rain-soaked street, neon reflections",
    "cooking in a kitchen, warm home feeling",
    "in an art studio, painting, creative atmosphere",
    "riding a bicycle on a tree-lined path",
    "in a music room, playing piano, afternoon sun",
    "at a train station, waiting, cinematic lighting",
    "in a snow-covered street, winter evening",
]

_LANDSCAPE_SCENES = [
    "a serene mountain lake at dawn, mist over water, reflection",
    "a winding path through a lavender field, purple horizon",
    "a quiet bamboo forest, dappled sunlight filtering through",
    "a coastal cliff at golden hour, waves crashing below",
    "a starry night sky over rolling hills, milky way visible",
    "cherry blossom trees along a river bank, petals falling",
    "a cozy cabin in snowy mountains, smoke from chimney",
    "an old stone bridge over a crystal clear stream",
    "a sunflower field stretching to the horizon, blue sky",
    "a misty ancient temple hidden in mountains",
    "autumn forest with red and gold leaves, a small waterfall",
    "a tranquil Japanese garden with koi pond and maple trees",
    "a vast desert with sand dunes under a dramatic sunset",
    "a lighthouse on a rocky shore, stormy sky, dramatic waves",
    "a field of fireflies in a dark forest, magical glow",
]


def build_image_prompt(personality: dict, image_type: str = None) -> str:
    """
    根据人格设定生成图片 prompt。
    image_type: "selfie" 或 "scenery"，None 时随机选
    """
    avatar = personality.get("avatar_prompt", "").strip()
    name = personality.get("name", "")

    # 没有设置人物描述时的默认形象
    if not avatar:
        avatar = "a young woman with gentle eyes, soft smile, casual outfit"

    if image_type is None:
        image_type = "selfie" if time.time_ns() % 2 == 0 else "scenery"

    # 根据时段微调光线
    hour = datetime.now().hour
    if 6 <= hour < 10:
        light = "soft morning light"
    elif 10 <= hour < 14:
        light = "bright daylight"
    elif 14 <= hour < 17:
        light = "warm afternoon light"
    elif 17 <= hour < 20:
        light = "golden hour lighting"
    else:
        light = "twilight ambiance"

    if image_type == "selfie":
        scene = _SELFIE_SCENES[time.time_ns() % len(_SELFIE_SCENES)]
        prompt = f"({avatar}), {scene}, {light}, high quality, detailed, anime art style"
    else:
        scene = _LANDSCAPE_SCENES[time.time_ns() % len(_LANDSCAPE_SCENES)]
        prompt = f"{scene}, {light}, beautiful landscape, high quality, detailed, anime art style"

    return prompt, image_type


def generate_image_url(prompt: str, width=DEFAULT_WIDTH, height=DEFAULT_HEIGHT) -> str:
    encoded = urllib.parse.quote(prompt)
    return f"{_BASES[0]}/{encoded}?width={width}&height={height}&nologo=true&nofeed=true"


def download_image(url: str, save_path: str = None) -> Optional[str]:
    if save_path is None:
        save_path = str(
            get_image_dir()
            / f"gen_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}.jpg"
        )

    encoded = urllib.parse.quote(url.split("/")[-1].split("?")[0])
    query = url.split("?", 1)[1] if "?" in url else ""

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "image/*",
    }

    for base in _BASES:
        try:
            full_url = f"{base}/{encoded}?{query}" if query else f"{base}/{encoded}"
            req = urllib.request.Request(full_url, headers=headers)
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                ct = resp.headers.get("Content-Type", "")
                if "image" not in ct:
                    continue
                data = resp.read()
                if len(data) < 1000:
                    continue
                with open(save_path, "wb") as f:
                    f.write(data)
                print(f"[图片生成] 已保存: {save_path} ({len(data)//1024}KB)")
                return save_path
        except Exception as e:
            print(f"[图片生成] 域名 {base} 失败: {e}")
            continue

    print("[图片生成] 所有域名均失败")
    return None


def generate_and_download(personality: dict) -> Optional[Tuple[str, str, str]]:
    """
    一站式：根据人格生成图片。
    返回 (prompt, image_path, image_type) 或 None
    """
    prompt, image_type = build_image_prompt(personality)
    url = generate_image_url(prompt)
    print(f"[图片生成] {image_type}: {prompt[:80]}...")
    image_path = download_image(url)
    if image_path:
        return (prompt, image_path, image_type)
    return None
