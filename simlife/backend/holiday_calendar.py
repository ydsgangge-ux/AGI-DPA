"""
节假日日历 - 中国法定节假日 + 节日氛围
覆盖场景逻辑：节假日期间不按工作日/周末走，走节假日专属路线
"""

from datetime import date, timedelta
from typing import Optional, Tuple
import random

# ── 节假日类型 ──────────────────────────────────────

class HolidayType:
    # 法定长假（全国放假）
    PUBLIC_HOLIDAY = "public_holiday"
    # 调休工作日（周末但要上班）
    WORKDAY = "workday"
    # 传统节日（不放假但有氛围）
    TRADITIONAL = "traditional"
    # 现代节日/电商节（不放假但有活动）
    MODERN = "modern"
    # 特殊日期（双11、618等）
    SHOPPING = "shopping"


# ── 2025-2027 年国务院放假安排 ─────────────────────────
# 每年年初需要更新，数据来源：国务院办公厅通知
# 格式：(start, end, type, label, scenes, mood_delta)

# scenes: 假期期间角色的主要场景分布（权重列表）
_HOLIDAY_SCHEDULE: dict = {}

def _build_2026():
    """2026年放假安排"""
    return [
        # 元旦
        ((2026,1,1), (2026,1,3), HolidayType.PUBLIC_HOLIDAY, "元旦",
         [("HOME_EVENING", 5), ("STREET_WANDERING", 2), ("CAFE", 1), ("PARK", 2)], +8),
        # 春节（预估）
        ((2026,2,16), (2026,2,22), HolidayType.PUBLIC_HOLIDAY, "春节",
         [("HOME_EVENING", 6), ("STREET_WANDERING", 2), ("FRIEND_HANGOUT", 2)], +15),
        # 清明节（预估）
        ((2026,4,4), (2026,4,6), HolidayType.PUBLIC_HOLIDAY, "清明节",
         [("HOME_EVENING", 3), ("STREET_WANDERING", 2), ("PARK", 3), ("SUPERMARKET", 2)], +3),
        # 劳动节（预估）
        ((2026,5,1), (2026,5,5), HolidayType.PUBLIC_HOLIDAY, "劳动节",
         [("HOME_EVENING", 3), ("PARK", 3), ("STREET_WANDERING", 3), ("CAFE", 1), ("FRIEND_HANGOUT", 2)], +10),
        # 端午节（预估）
        ((2026,6,19), (2026,6,21), HolidayType.PUBLIC_HOLIDAY, "端午节",
         [("HOME_EVENING", 5), ("STREET_WANDERING", 2), ("FRIEND_HANGOUT", 2), ("SUPERMARKET", 1)], +5),
        # 中秋节（预估）
        ((2026,9,12), (2026,9,14), HolidayType.PUBLIC_HOLIDAY, "中秋节",
         [("HOME_EVENING", 5), ("FRIEND_HANGOUT", 3), ("PARK", 2)], +8),
        # 国庆节（预估）
        ((2026,10,1), (2026,10,7), HolidayType.PUBLIC_HOLIDAY, "国庆节",
         [("HOME_EVENING", 2), ("PARK", 3), ("STREET_WANDERING", 3), ("CAFE", 2),
          ("FRIEND_HANGOUT", 2), ("SUPERMARKET", 1)], +12),

        # 调休工作日（这些周末要上班）
        ((2026,1,24), (2026,1,24), HolidayType.WORKDAY, "元旦调休", [], 0),
        ((2026,2,14), (2026,2,14), HolidayType.WORKDAY, "春节调休", [], 0),
        ((2026,2,15), (2026,2,15), HolidayType.WORKDAY, "春节调休", [], 0),
        ((2026,4,26), (2026,4,26), HolidayType.WORKDAY, "清明调休", [], 0),
        ((2026,9,27), (2026,9,27), HolidayType.WORKDAY, "中秋调休", [], 0),
        ((2026,10,10), (2026,10,10), HolidayType.WORKDAY, "国庆调休", [], 0),

        # 传统节日（不放假但影响心情和日志）
        # 小年
        ((2026,2,8), (2026,2,8), HolidayType.TRADITIONAL, "小年",
         [("HOME_EVENING", 8), ("SUPERMARKET", 2)], +5),
        # 情人节
        ((2026,2,14), (2026,2,14), HolidayType.MODERN, "情人节",
         [("HOME_EVENING", 3), ("CAFE", 3), ("STREET_WANDERING", 2), ("FRIEND_HANGOUT", 2)], +3),
        # 妇女节
        ((2026,3,8), (2026,3,8), HolidayType.MODERN, "妇女节",
         [("OFFICE_WORKING", 5), ("CAFE", 3), ("FRIEND_HANGOUT", 2)], +5),
        # 植树节
        ((2026,3,12), (2026,3,12), HolidayType.TRADITIONAL, "植树节",
         [("HOME_EVENING", 8), ("PARK", 2)], +2),
        # 儿童节
        ((2026,6,1), (2026,6,1), HolidayType.MODERN, "儿童节",
         [("HOME_EVENING", 6), ("CAFE", 2), ("STREET_WANDERING", 2)], +8),
        # 七夕
        ((2026,8,19), (2026,8,19), HolidayType.TRADITIONAL, "七夕",
         [("HOME_EVENING", 5), ("CAFE", 2), ("STREET_WANDERING", 3)], +3),
        # 教师节
        ((2026,9,10), (2026,9,10), HolidayType.MODERN, "教师节",
         [("HOME_EVENING", 8), ("CAFE", 2)], +2),
        # 重阳节（预估）
        ((2026,10,25), (2026,10,25), HolidayType.TRADITIONAL, "重阳节",
         [("HOME_EVENING", 8), ("PARK", 2)], +2),
        # 圣诞节
        ((2026,12,25), (2026,12,25), HolidayType.MODERN, "圣诞节",
         [("HOME_EVENING", 4), ("CAFE", 3), ("STREET_WANDERING", 2), ("FRIEND_HANGOUT", 1)], +5),
        # 跨年
        ((2026,12,31), (2026,12,31), HolidayType.MODERN, "跨年夜",
         [("HOME_EVENING", 3), ("CAFE", 2), ("STREET_WANDERING", 3), ("FRIEND_HANGOUT", 2)], +10),

        # 电商/现代节日
        # 520
        ((2026,5,20), (2026,5,20), HolidayType.SHOPPING, "520",
         [("HOME_EVENING", 7), ("CAFE", 2), ("STREET_WANDERING", 1)], +3),
        # 618
        ((2026,6,18), (2026,6,18), HolidayType.SHOPPING, "618",
         [("HOME_EVENING", 9), ("SUPERMARKET", 1)], 0),
        # 双11
        ((2026,11,11), (2026,11,11), HolidayType.SHOPPING, "双11",
         [("HOME_EVENING", 8), ("SUPERMARKET", 2)], 0),
        # 双12
        ((2026,12,12), (2026,12,12), HolidayType.SHOPPING, "双12",
         [("HOME_EVENING", 9), ("SUPERMARKET", 1)], 0),
        # 年末
        ((2026,12,28), (2026,12,31), HolidayType.MODERN, "年末",
         [("HOME_EVENING", 5), ("OFFICE_WORKING", 3), ("CAFE", 1), ("FRIEND_HANGOUT", 1)], -3),
    ]


def _build_2025():
    """2025年放假安排"""
    return [
        ((2025,1,1), (2025,1,1), HolidayType.PUBLIC_HOLIDAY, "元旦",
         [("HOME_EVENING", 5), ("STREET_WANDERING", 2), ("CAFE", 1), ("PARK", 2)], +8),
        ((2025,1,28), (2025,2,4), HolidayType.PUBLIC_HOLIDAY, "春节",
         [("HOME_EVENING", 6), ("STREET_WANDERING", 2), ("FRIEND_HANGOUT", 2)], +15),
        ((2025,4,4), (2025,4,6), HolidayType.PUBLIC_HOLIDAY, "清明节",
         [("HOME_EVENING", 3), ("STREET_WANDERING", 2), ("PARK", 3), ("SUPERMARKET", 2)], +3),
        ((2025,5,1), (2025,5,5), HolidayType.PUBLIC_HOLIDAY, "劳动节",
         [("HOME_EVENING", 3), ("PARK", 3), ("STREET_WANDERING", 3), ("CAFE", 1), ("FRIEND_HANGOUT", 2)], +10),
        ((2025,5,31), (2025,6,2), HolidayType.PUBLIC_HOLIDAY, "端午节",
         [("HOME_EVENING", 5), ("STREET_WANDERING", 2), ("FRIEND_HANGOUT", 2), ("SUPERMARKET", 1)], +5),
        ((2025,10,1), (2025,10,8), HolidayType.PUBLIC_HOLIDAY, "国庆节",
         [("HOME_EVENING", 2), ("PARK", 3), ("STREET_WANDERING", 3), ("CAFE", 2),
          ("FRIEND_HANGOUT", 2), ("SUPERMARKET", 1)], +12),
        ((2025,10,6), (2025,10,6), HolidayType.PUBLIC_HOLIDAY, "中秋节",
         [("HOME_EVENING", 5), ("FRIEND_HANGOUT", 3), ("PARK", 2)], +8),

        # 调休工作日
        ((2025,1,26), (2025,1,26), HolidayType.WORKDAY, "春节调休", [], 0),
        ((2025,2,8), (2025,2,8), HolidayType.WORKDAY, "春节调休", [], 0),
        ((2025,4,27), (2025,4,27), HolidayType.WORKDAY, "五一调休", [], 0),
        ((2025,9,28), (2025,9,28), HolidayType.WORKDAY, "国庆调休", [], 0),
        ((2025,10,11), (2025,10,11), HolidayType.WORKDAY, "国庆调休", [], 0),

        # 传统节日
        ((2025,2,14), (2025,2,14), HolidayType.MODERN, "情人节",
         [("HOME_EVENING", 3), ("CAFE", 3), ("STREET_WANDERING", 2), ("FRIEND_HANGOUT", 2)], +3),
        ((2025,3,8), (2025,3,8), HolidayType.MODERN, "妇女节",
         [("OFFICE_WORKING", 5), ("CAFE", 3), ("FRIEND_HANGOUT", 2)], +5),
        ((2025,8,10), (2025,8,10), HolidayType.TRADITIONAL, "七夕",
         [("HOME_EVENING", 5), ("CAFE", 2), ("STREET_WANDERING", 3)], +3),
        ((2025,12,25), (2025,12,25), HolidayType.MODERN, "圣诞节",
         [("HOME_EVENING", 4), ("CAFE", 3), ("STREET_WANDERING", 2), ("FRIEND_HANGOUT", 1)], +5),
        ((2025,12,31), (2025,12,31), HolidayType.MODERN, "跨年夜",
         [("HOME_EVENING", 3), ("CAFE", 2), ("STREET_WANDERING", 3), ("FRIEND_HANGOUT", 2)], +10),

        # 电商节
        ((2025,5,20), (2025,5,20), HolidayType.SHOPPING, "520",
         [("HOME_EVENING", 7), ("CAFE", 2), ("STREET_WANDERING", 1)], +3),
        ((2025,6,18), (2025,6,18), HolidayType.SHOPPING, "618",
         [("HOME_EVENING", 9), ("SUPERMARKET", 1)], 0),
        ((2025,11,11), (2025,11,11), HolidayType.SHOPPING, "双11",
         [("HOME_EVENING", 8), ("SUPERMARKET", 2)], 0),
        ((2025,12,12), (2025,12,12), HolidayType.SHOPPING, "双12",
         [("HOME_EVENING", 9), ("SUPERMARKET", 1)], 0),
    ]


def _build_2027():
    """2027年放假安排（预估）"""
    return [
        ((2027,1,1), (2027,1,3), HolidayType.PUBLIC_HOLIDAY, "元旦",
         [("HOME_EVENING", 5), ("STREET_WANDERING", 2), ("CAFE", 1), ("PARK", 2)], +8),
        ((2027,2,6), (2027,2,12), HolidayType.PUBLIC_HOLIDAY, "春节",
         [("HOME_EVENING", 6), ("STREET_WANDERING", 2), ("FRIEND_HANGOUT", 2)], +15),
        ((2027,4,4), (2027,4,6), HolidayType.PUBLIC_HOLIDAY, "清明节",
         [("HOME_EVENING", 3), ("STREET_WANDERING", 2), ("PARK", 3), ("SUPERMARKET", 2)], +3),
        ((2027,5,1), (2027,5,5), HolidayType.PUBLIC_HOLIDAY, "劳动节",
         [("HOME_EVENING", 3), ("PARK", 3), ("STREET_WANDERING", 3), ("CAFE", 1), ("FRIEND_HANGOUT", 2)], +10),
        ((2027,6,9), (2027,6,11), HolidayType.PUBLIC_HOLIDAY, "端午节",
         [("HOME_EVENING", 5), ("STREET_WANDERING", 2), ("FRIEND_HANGOUT", 2), ("SUPERMARKET", 1)], +5),
        ((2027,10,1), (2027,10,7), HolidayType.PUBLIC_HOLIDAY, "国庆节",
         [("HOME_EVENING", 2), ("PARK", 3), ("STREET_WANDERING", 3), ("CAFE", 2),
          ("FRIEND_HANGOUT", 2), ("SUPERMARKET", 1)], +12),

        # 传统节日
        ((2027,2,14), (2027,2,14), HolidayType.MODERN, "情人节",
         [("HOME_EVENING", 3), ("CAFE", 3), ("STREET_WANDERING", 2), ("FRIEND_HANGOUT", 2)], +3),
        ((2027,3,8), (2027,3,8), HolidayType.MODERN, "妇女节",
         [("OFFICE_WORKING", 5), ("CAFE", 3), ("FRIEND_HANGOUT", 2)], +5),
        ((2027,8,8), (2027,8,8), HolidayType.TRADITIONAL, "七夕",
         [("HOME_EVENING", 5), ("CAFE", 2), ("STREET_WANDERING", 3)], +3),
        ((2027,12,25), (2027,12,25), HolidayType.MODERN, "圣诞节",
         [("HOME_EVENING", 4), ("CAFE", 3), ("STREET_WANDERING", 2), ("FRIEND_HANGOUT", 1)], +5),
        ((2027,12,31), (2027,12,31), HolidayType.MODERN, "跨年夜",
         [("HOME_EVENING", 3), ("CAFE", 2), ("STREET_WANDERING", 3), ("FRIEND_HANGOUT", 2)], +10),
    ]


# ── 缓存 ─────────────────────────────────────────────

_schedule_cache: list = []
_cache_year: int = 0


def _get_schedule(year: int) -> list:
    """获取指定年份的节假日数据"""
    global _schedule_cache, _cache_year
    if _cache_year == year and _schedule_cache:
        return _schedule_cache

    builders = {2025: _build_2025, 2026: _build_2026, 2027: _build_2027}
    builder = builders.get(year)
    if builder:
        _schedule_cache = builder()
    else:
        # 没有数据的年份，只保留固定传统节日
        _schedule_cache = _build_fixed_holidays(year)
    _cache_year = year
    return _schedule_cache


def _build_fixed_holidays(year: int) -> list:
    """没有放假安排数据的年份，只生成固定日期节日"""
    return [
        ((year,1,1), (year,1,1), HolidayType.PUBLIC_HOLIDAY, "元旦",
         [("HOME_EVENING", 5), ("PARK", 3), ("STREET_WANDERING", 2)], +8),
        ((year,2,14), (year,2,14), HolidayType.MODERN, "情人节",
         [("HOME_EVENING", 3), ("CAFE", 3), ("STREET_WANDERING", 2), ("FRIEND_HANGOUT", 2)], +3),
        ((year,3,8), (year,3,8), HolidayType.MODERN, "妇女节",
         [("OFFICE_WORKING", 5), ("CAFE", 3), ("FRIEND_HANGOUT", 2)], +5),
        ((year,5,1), (year,5,1), HolidayType.PUBLIC_HOLIDAY, "劳动节",
         [("HOME_EVENING", 3), ("PARK", 3), ("STREET_WANDERING", 3), ("FRIEND_HANGOUT", 1)], +10),
        ((year,6,1), (year,6,1), HolidayType.MODERN, "儿童节",
         [("HOME_EVENING", 6), ("CAFE", 2), ("STREET_WANDERING", 2)], +8),
        ((year,10,1), (year,10,1), HolidayType.PUBLIC_HOLIDAY, "国庆节",
         [("HOME_EVENING", 2), ("PARK", 3), ("STREET_WANDERING", 3), ("CAFE", 2)], +12),
        ((year,11,11), (year,11,11), HolidayType.SHOPPING, "双11",
         [("HOME_EVENING", 8), ("SUPERMARKET", 2)], 0),
        ((year,12,25), (year,12,25), HolidayType.MODERN, "圣诞节",
         [("HOME_EVENING", 4), ("CAFE", 3), ("STREET_WANDERING", 2), ("FRIEND_HANGOUT", 1)], +5),
        ((year,12,31), (year,12,31), HolidayType.MODERN, "跨年夜",
         [("HOME_EVENING", 3), ("CAFE", 2), ("STREET_WANDERING", 3), ("FRIEND_HANGOUT", 2)], +10),
    ]


# ── 公开接口 ─────────────────────────────────────────


def get_holiday(d: date = None) -> Optional[dict]:
    """
    查询指定日期的节假日信息。
    返回 None 表示普通日，
    返回 {"type": str, "label": str, "scenes": [...], "mood_delta": int} 表示节假日。
    """
    d = d or date.today()
    schedule = _get_schedule(d.year)

    for entry in schedule:
        start = date(*entry[0])
        end = date(*entry[1])
        if start <= d <= end:
            return {
                "type": entry[2],
                "label": entry[3],
                "scenes": entry[4],
                "mood_delta": entry[5],
                "start": start,
                "end": end,
            }
    return None


def is_public_holiday(d: date = None) -> bool:
    """是否法定假日（放假）"""
    h = get_holiday(d)
    return h is not None and h["type"] in (
        HolidayType.PUBLIC_HOLIDAY,
    )


def is_workday_override(d: date = None) -> bool:
    """是否调休工作日（周末但需要上班）"""
    h = get_holiday(d)
    return h is not None and h["type"] == HolidayType.WORKDAY


def is_festive(d: date = None) -> bool:
    """是否有节日氛围（包括法定、传统、现代、电商）"""
    h = get_holiday(d)
    return h is not None and h["type"] != HolidayType.WORKDAY


def get_holiday_scene(d: date, hour: int, day_seed: int) -> Optional[Tuple[str, str]]:
    """
    获取节假日场景。仅在法定长假期间调用。
    返回 (scene_enum, scene_label) 或 None。
    """
    h = get_holiday(d)
    if not h or h["type"] != HolidayType.PUBLIC_HOLIDAY:
        return None

    scenes = h["scenes"]
    if not scenes:
        return None

    # 睡觉时段
    if hour < 7 or hour >= 23:
        from .character import SceneEnum, SCENE_LABELS
        return SceneEnum.HOME_SLEEPING, SCENE_LABELS[SceneEnum.HOME_SLEEPING]

    # 用种子按权重选场景
    weighted = []
    for scene_name, weight in scenes:
        weighted.extend([scene_name] * weight)

    rng = random.Random(day_seed + hour)
    chosen = rng.choice(weighted)

    from .character import SceneEnum, SCENE_LABELS
    try:
        scene_enum = SceneEnum(chosen)
        return scene_enum, SCENE_LABELS[scene_enum]
    except ValueError:
        return SceneEnum.HOME_EVENING, SCENE_LABELS[SceneEnum.HOME_EVENING]


def get_holiday_mood_delta(d: date = None) -> int:
    """获取节假日心情修正值"""
    h = get_holiday(d)
    if not h:
        return 0
    return h["mood_delta"]


def get_upcoming_holidays(d: date = None, days: int = 14) -> list:
    """获取未来 N 天内的节日列表（用于生成节日相关日志）"""
    d = d or date.today()
    upcoming = []
    for i in range(1, days + 1):
        future = d + timedelta(days=i)
        h = get_holiday(future)
        if h and h["type"] not in (HolidayType.WORKDAY, HolidayType.SHOPPING):
            upcoming.append({
                "date": future.isoformat(),
                "label": h["label"],
                "type": h["type"],
                "days_away": i,
            })
    return upcoming
