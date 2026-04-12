"""
心情引擎 - 心情值计算
"""
from datetime import datetime
from typing import Optional, List


def calculate_mood(
    scene: str = "",
    current_hour: int = 0,
    is_weekend: bool = False,
    today_events_mood_delta: List[int] = None,
    recent_interaction_hours: Optional[float] = None,
    task_queue_length: int = 0,
    weather: str = "",
    sleep_penalty: int = 0,
) -> int:
    """
    计算心情值 (0-100)。
    """
    now = datetime.now()
    if not current_hour:
        current_hour = now.hour

    base = 70
    modifiers = []

    # 时间相关
    if is_weekend:
        modifiers.append(+10)
    if current_hour < 8:
        modifiers.append(-5)
    if current_hour > 23:
        modifiers.append(-8)

    # 场景相关
    scene_mods = {
        "CAFE": +12,
        "PARK": +8,
        "FRIEND_HANGOUT": +10,
        "OVERTIME": -15,
        "HOME_WEEKEND_LAZY": +5,
        "STREET_WANDERING": +3,
    }
    if scene in scene_mods:
        modifiers.append(scene_mods[scene])

    # 事件累积
    if today_events_mood_delta:
        modifiers.extend(today_events_mood_delta)

    # AGI-DPA 交互影响
    if recent_interaction_hours is not None and recent_interaction_hours <= 1:
        modifiers.append(+8)
    if task_queue_length > 5:
        modifiers.append(-10)
    elif task_queue_length == 0:
        modifiers.append(+5)

    # 天气
    if weather == "rainy":
        modifiers.append(-5)
    elif weather == "sunny" and is_weekend:
        modifiers.append(+5)

    # 睡眠惩罚（前一天加班等累积疲劳）
    if sleep_penalty:
        modifiers.append(sleep_penalty)

    mood = base + sum(modifiers)
    return max(0, min(100, mood))


def get_mood_tone(mood: int) -> str:
    """根据心情值返回描述语气"""
    if mood > 80:
        return "light"
    elif mood >= 60:
        return "normal"
    elif mood >= 40:
        return "tired"
    else:
        return "down"


def get_mood_emoji(mood: int) -> str:
    """根据心情值返回表情"""
    if mood >= 80:
        return "😊"
    elif mood >= 60:
        return "🙂"
    elif mood >= 40:
        return "😐"
    elif mood >= 20:
        return "😔"
    else:
        return "😢"
