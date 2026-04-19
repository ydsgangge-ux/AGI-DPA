"""
生日引擎 - 性格→星座匹配、生日生成、生日事件检测
"""
import random
from datetime import date, datetime
from typing import Optional, List, Tuple


# ── 星座日期范围 ─────────────────────────────────────────
# 格式: (起始月, 起始日, 结束月, 结束日)
# 摩羯座跨年，特殊处理
ZODIAC_RANGES: dict = {
    "白羊座":   ((3, 21), (4, 19)),
    "金牛座":   ((4, 20), (5, 20)),
    "双子座":   ((5, 21), (6, 21)),
    "巨蟹座":   ((6, 22), (7, 22)),
    "狮子座":   ((7, 23), (8, 22)),
    "处女座":   ((8, 23), (9, 22)),
    "天秤座":   ((9, 23), (10, 23)),
    "天蝎座":   ((10, 24), (11, 22)),
    "射手座":   ((11, 23), (12, 21)),
    "摩羯座":   ((12, 22), (1, 19)),
    "水瓶座":   ((1, 20), (2, 18)),
    "双鱼座":   ((2, 19), (3, 20)),
}

ZODIAC_EMOJI: dict = {
    "白羊座": "♈", "金牛座": "♉", "双子座": "♊",
    "巨蟹座": "♋", "狮子座": "♌", "处女座": "♍",
    "天秤座": "♎", "天蝎座": "♏", "射手座": "♐",
    "摩羯座": "♑", "水瓶座": "♒", "双鱼座": "♓",
}

ZODIAC_ELEMENT: dict = {
    "白羊座": "火", "金牛座": "土", "双子座": "风",
    "巨蟹座": "水", "狮子座": "火", "处女座": "土",
    "天秤座": "风", "天蝎座": "水", "射手座": "火",
    "摩羯座": "土", "水瓶座": "风", "双鱼座": "水",
}

# ── 性格关键词 → 星座映射 ─────────────────────────────────
ZODIAC_PERSONALITY: dict = {
    "白羊座": [
        "热情", "冲动", "勇敢", "直率", "积极", "冒险",
        "竞争", "急性子", "果断", "主动", "活力", "大胆",
        "好强", "坦率", "执行力", "热血",
    ],
    "金牛座": [
        "务实", "稳重", "固执", "爱美", "耐心", "享受",
        "美食", "理财", "可靠", "坚持", "踏实", "慢热",
        "节俭", "物质", "安全感", "执着",
    ],
    "双子座": [
        "好奇", "多变", "社交", "机智", "活泼", "健谈",
        "灵活", "聪明", "新鲜", "风趣", "善变", "口才",
        "适应力", "思维快", "八卦", "随性",
    ],
    "巨蟹座": [
        "温柔", "敏感", "顾家", "念旧", "体贴", "感性",
        "母性", "保护", "直觉", "情感", "细心", "包容",
        "恋家", "依赖", "情绪化", "善良",
    ],
    "狮子座": [
        "自信", "领导力", "热情", "骄傲", "大方", "创造",
        "表达", "浪漫", "慷慨", "戏剧", "阳光", "强势",
        "表现欲", "气场", "乐观", "英雄主义",
    ],
    "处女座": [
        "细致", "完美主义", "务实", "谦逊", "分析", "挑剔",
        "整洁", "勤奋", "精确", "理性", "谨慎", "有条理",
        "吹毛求疵", "内敛", "效率", "自律",
    ],
    "天秤座": [
        "优雅", "和谐", "犹豫", "公正", "审美", "和平",
        "品味", "合作", "温和", "社交", "公平", "善解人意",
        "优柔寡断", "外貌协会", "高情商", "知性",
    ],
    "天蝎座": [
        "神秘", "执着", "洞察力", "深沉", "专注", "强烈",
        "复杂", "决心", "掌控", "敏锐", "冷静", "独立",
        "占有欲", "记仇", "战略", "内敛",
    ],
    "射手座": [
        "自由", "乐观", "冒险", "直率", "哲学", "旅行",
        "开放", "幽默", "探索", "豁达", "好奇", "不羁",
        "理想主义", "运动", "大大咧咧", "远方",
    ],
    "摩羯座": [
        "勤奋", "务实", "规划", "沉稳", "责任", "目标",
        "自律", "成熟", "保守", "坚韧", "踏实", "隐忍",
        "事业心", "传统", "大器晚成", "严谨",
    ],
    "水瓶座": [
        "独立", "创新", "理性", "叛逆", "理想", "友善",
        "独特", "前卫", "思考", "突破", "博爱", "另类",
        "特立独行", "人道主义", "科技感", "理性",
    ],
    "双鱼座": [
        "浪漫", "敏感", "艺术", "善解人意", "梦想", "温柔",
        "同情", "想象", "感性", "多情", "梦幻", "文艺",
        "佛系", "灵感", "治愈", "易感动",
    ],
}


# ── 核心函数 ─────────────────────────────────────────────


def match_zodiac(personality: str) -> str:
    """
    根据性格描述匹配最合适的星座。
    返回星座名称（中文）。
    """
    if not personality:
        # 无性格描述时随机选一个
        return random.choice(list(ZODIAC_RANGES.keys()))

    scores: dict = {}
    for zodiac, keywords in ZODIAC_PERSONALITY.items():
        score = 0
        for kw in keywords:
            if kw in personality:
                score += 1
        if score > 0:
            scores[zodiac] = score

    if not scores:
        # 没有匹配到任何关键词，随机选
        return random.choice(list(ZODIAC_RANGES.keys()))

    # 取最高分的星座（同分随机选一个）
    max_score = max(scores.values())
    top_zodiacs = [z for z, s in scores.items() if s == max_score]
    return random.choice(top_zodiacs)


def _is_in_zodiac_range(month: int, day: int, zodiac: str) -> bool:
    """判断给定月日是否在指定星座范围内"""
    if zodiac not in ZODIAC_RANGES:
        return False
    (sm, sd), (em, ed) = ZODIAC_RANGES[zodiac]

    if sm <= em:
        # 不跨年的星座（大多数）
        return (month == sm and day >= sd) or (month == em and day <= ed) or (sm < month < em)
    else:
        # 跨年的星座（摩羯座 12/22 - 1/19）
        return (month == sm and day >= sd) or (month == em and day <= ed) or month > sm or month < em


def generate_birth_date(
    zodiac: str,
    age: int,
    reference_date: Optional[date] = None,
) -> str:
    """
    根据星座和年龄生成一个随机的合法生日日期。
    确保在 reference_date 当天，此人的年龄确实等于 age。
    返回 "YYYY-MM-DD" 格式。
    """
    ref = reference_date or date.today()
    year = ref.year

    # 计算可能的出生年份
    possible_dates: List[date] = []

    for birth_year in [year - age - 1, year - age]:
        if zodiac not in ZODIAC_RANGES:
            continue
        (sm, sd), (em, ed) = ZODIAC_RANGES[zodiac]

        if sm <= em:
            # 不跨年
            try:
                start_d = date(birth_year, sm, sd)
                end_d = date(birth_year, em, ed)
                # 检查每个日期
                if start_d <= end_d:
                    cur = start_d
                    while cur <= end_d:
                        # 验证年龄
                        actual_age = _calc_age(cur, ref)
                        if actual_age == age:
                            possible_dates.append(cur)
                        cur += __import__("datetime").timedelta(days=1)
            except ValueError:
                pass
        else:
            # 跨年（摩羯座）
            # 第一段: 12/22 - 12/31
            try:
                start_d = date(birth_year, sm, sd)
                end_d = date(birth_year, 12, 31)
                cur = start_d
                while cur <= end_d:
                    actual_age = _calc_age(cur, ref)
                    if actual_age == age:
                        possible_dates.append(cur)
                    cur += __import__("datetime").timedelta(days=1)
            except ValueError:
                pass
            # 第二段: 1/1 - 1/19
            try:
                start_d = date(birth_year, 1, 1)
                end_d = date(birth_year, em, ed)
                cur = start_d
                while cur <= end_d:
                    actual_age = _calc_age(cur, ref)
                    if actual_age == age:
                        possible_dates.append(cur)
                    cur += __import__("datetime").timedelta(days=1)
            except ValueError:
                pass

    if not possible_dates:
        # 回退：直接用星座范围的某一年
        (sm, sd), _ = ZODIAC_RANGES.get(zodiac, ((1, 1), (1, 31)))
        birth_year = year - age
        try:
            return date(birth_year, sm, sd).isoformat()
        except ValueError:
            return f"{birth_year}-{sm:02d}-{sd:02d}"

    return random.choice(possible_dates).isoformat()


def _calc_age(birth_date: date, reference: date) -> int:
    """计算在 reference 日期时的年龄"""
    age = reference.year - birth_date.year
    if (reference.month, reference.day) < (birth_date.month, birth_date.day):
        age -= 1
    return age


def get_zodiac_from_date(birth_date_str: str) -> str:
    """根据出生日期返回星座名称"""
    try:
        d = date.fromisoformat(birth_date_str)
    except (ValueError, TypeError):
        return ""

    for zodiac in ZODIAC_RANGES:
        if _is_in_zodiac_range(d.month, d.day, zodiac):
            return zodiac
    return ""


def get_birthday_mood(birth_date_str: str, reference: Optional[date] = None) -> int:
    """
    如果今天（reference）是生日，返回心情修正值。
    不是生日返回 0。
    """
    if not birth_date_str:
        return 0
    ref = reference or date.today()
    try:
        bd = date.fromisoformat(birth_date_str)
    except (ValueError, TypeError):
        return 0

    if bd.month == ref.month and bd.day == ref.day:
        return 20  # 生日当天心情大 boost
    return 0


# ── 生日日志模板 ─────────────────────────────────────────


_BIRTHDAY_SELF_LOGS = [
    "今天是自己的生日，发了条朋友圈纪念一下",
    "生日快乐，给自己买了一杯平时舍不得喝的咖啡",
    "又长大了一岁，许了个愿望",
    "生日收到了几个朋友的祝福，有点开心",
    "今天是自己生日，但还是正常上了班",
    "给自己买了一个小蛋糕",
]

_BIRTHDAY_FAMILY_LOGS = [
    "今天是自己生日，妈妈一大早就发来了祝福",
    "生日收到了妈妈寄的礼物",
    "爸爸发了条简短的生日祝福",
    "爸妈打视频来祝生日快乐，聊了好一会儿",
    "今天过生日，收到了爸妈的红包",
]

_BIRTHDAY_FRIEND_LOGS = [
    "闺蜜记住了自己的生日，约晚上一起吃饭庆祝",
    "收到了好朋友送的生日礼物，包装特别用心",
    "同事偷偷给自己准备了小蛋糕，好感动",
    "朋友们给自己办了一个小小的惊喜派对",
]


def get_birthday_log(
    birth_date_str: str,
    relation: str = "self",
    reference: Optional[date] = None,
) -> Optional[str]:
    """
    如果今天是指定人物的生日，返回一条随机日志。
    relation: "self"（主角）, "family"（家人）, "friend"（朋友/同事）, "other"（其他）
    不是生日返回 None。
    """
    if not birth_date_str:
        return None
    ref = reference or date.today()
    try:
        bd = date.fromisoformat(birth_date_str)
    except (ValueError, TypeError):
        return None

    if bd.month != ref.month or bd.day != ref.day:
        return None

    templates = {
        "self": _BIRTHDAY_SELF_LOGS + _BIRTHDAY_FAMILY_LOGS + _BIRTHDAY_FRIEND_LOGS,
        "family": ["今天是{}的生日，记得打个电话" if relation == "family" else "今天是家人生日"],
        "friend": ["今天是朋友的生日，准备了一份小礼物"],
        "other": [],
    }

    pool = templates.get(relation, templates["other"])
    if not pool:
        return None

    seed = ref.year * 10000 + ref.month * 100 + ref.day
    rng = random.Random(seed)
    return rng.choice(pool)


def check_birthdays_today(
    character_birth_date: str,
    npc_cards: Optional[List[dict]] = None,
    reference: Optional[date] = None,
) -> List[dict]:
    """
    检查今天是否是主角或任何 NPC 的生日。
    返回 [{"name": ..., "relation": ..., "log": ..., "mood_delta": ...}]
    """
    ref = reference or date.today()
    results = []

    # 检查主角生日
    char_log = get_birthday_log(character_birth_date, "self", ref)
    if char_log:
        results.append({
            "name": "自己",
            "relation": "self",
            "log": char_log,
            "mood_delta": 20,
        })

    # 检查 NPC 生日
    if npc_cards:
        for npc in npc_cards:
            npc_bd = npc.get("birth_date", "")
            relation = npc.get("relation", "")
            name = npc.get("name", "")

            # 跳过"不显示"名字的 NPC（如妈妈在 UI 中不显示）
            if name == "不显示":
                name = npc.get("relation", "某人")

            # 根据关系分类
            if relation in ("妈妈", "爸爸", "家人"):
                rel_type = "family"
            elif relation in ("闺蜜", "好友", "同事", "大学室友"):
                rel_type = "friend"
            else:
                rel_type = "other"

            npc_log = get_birthday_log(npc_bd, rel_type, ref)
            if npc_log:
                # 替换模板中的占位符
                npc_log = npc_log.replace("{}", name)
                results.append({
                    "name": name,
                    "relation": relation,
                    "log": npc_log,
                    "mood_delta": 8 if rel_type == "family" else 5,
                })

    return results


def get_upcoming_birthdays(
    character_birth_date: str,
    npc_cards: Optional[List[dict]] = None,
    days: int = 14,
    reference: Optional[date] = None,
) -> List[dict]:
    """
    获取未来 N 天内的生日列表。
    返回 [{"name": ..., "relation": ..., "date": ..., "days_away": ..., "zodiac": ...}]
    """
    ref = reference or date.today()
    results = []

    # 主角
    if character_birth_date:
        info = _check_upcoming(character_birth_date, "自己", "主角", ref, days)
        if info:
            results.append(info)

    # NPC
    if npc_cards:
        for npc in npc_cards:
            npc_bd = npc.get("birth_date", "")
            name = npc.get("name", "")
            relation = npc.get("relation", "")
            if name == "不显示":
                name = relation
            if npc_bd:
                info = _check_upcoming(npc_bd, name, relation, ref, days)
                if info:
                    results.append(info)

    return results


def _check_upcoming(
    birth_date_str: str,
    name: str,
    relation: str,
    ref: date,
    days: int,
) -> Optional[dict]:
    """检查单个人的生日是否在未来 N 天内"""
    try:
        bd = date.fromisoformat(birth_date_str)
    except (ValueError, TypeError):
        return None

    zodiac = get_zodiac_from_date(birth_date_str)
    emoji = ZODIAC_EMOJI.get(zodiac, "")

    for i in range(0, days + 1):
        future = ref + __import__("datetime").timedelta(days=i)
        if future.month == bd.month and future.day == bd.day:
            return {
                "name": name,
                "relation": relation,
                "date": future.isoformat(),
                "days_away": i,
                "zodiac": zodiac,
                "emoji": emoji,
            }
    return None


def auto_generate_birthday(
    personality: str,
    age: int,
    reference_date: Optional[date] = None,
) -> dict:
    """
    一站式生成：性格 → 星座匹配 → 随机生日。
    返回 {"zodiac": "...", "zodiac_emoji": "...", "birth_date": "..."}
    """
    zodiac = match_zodiac(personality)
    bd = generate_birth_date(zodiac, age, reference_date)
    return {
        "zodiac": zodiac,
        "zodiac_emoji": ZODIAC_EMOJI.get(zodiac, ""),
        "birth_date": bd,
    }
