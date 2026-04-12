"""
世界引擎 - 时间→场景映射 + 场景推算 + 离线补算
支持节假日覆盖 + 天气影响
"""
import random
from datetime import datetime, timedelta, date
from typing import Optional, List, Tuple
from .character import (
    CharacterCard, WorldState, SceneEnum, LogEntry, SCENE_LABELS
)
from .holiday_calendar import (
    get_holiday, is_public_holiday, is_workday_override,
    get_holiday_scene, get_holiday_mood_delta, get_upcoming_holidays
)


def _time_to_minutes(t: str) -> int:
    """'HH:MM' -> 分钟数"""
    h, m = t.split(":")
    return int(h) * 60 + int(m)


def _get_scene_schedule(card: CharacterCard) -> dict:
    """从人物卡解析时刻表为分钟数"""
    s = card.daily_schedule
    return {
        "wake_up": _time_to_minutes(s.wake_up),
        "leave_home": _time_to_minutes(s.leave_home),
        "arrive_work": _time_to_minutes(s.arrive_work),
        "lunch_start": _time_to_minutes(s.lunch_break_start),
        "lunch_end": _time_to_minutes(s.lunch_break_end),
        "leave_work": _time_to_minutes(s.leave_work),
        "arrive_home": _time_to_minutes(s.arrive_home),
        "sleep": _time_to_minutes(s.sleep),
    }


def get_current_scene(
    card: CharacterCard,
    now: Optional[datetime] = None,
    day_seed: Optional[int] = None,
    event_overrides: Optional[dict] = None,
    weather_service=None,
) -> Tuple[SceneEnum, str]:
    """
    根据时间和人物卡推算当前场景。
    返回 (场景枚举, 场景标签)。
    event_overrides: 事件系统对当天时刻表的修改，如 {"leave_work": 21*60}
    weather_service: 天气服务实例（恶劣天气可能影响场景）
    """
    now = now or datetime.now()
    today = now.date()
    seed = day_seed or (now.year * 10000 + now.month * 100 + now.day)

    # ── 优先级1：法定节假日 → 走节假日专属场景 ──
    if is_public_holiday(today):
        holiday_scene = get_holiday_scene(today, now.hour, seed)
        if holiday_scene:
            # 天气恶劣时可能留在室内
            if weather_service:
                scene_hint = weather_service.get_scene_hint()
                if scene_hint and now.hour >= 8 and now.hour < 22:
                    try:
                        forced_scene = SceneEnum(scene_hint)
                        return forced_scene, SCENE_LABELS[forced_scene]
                    except ValueError:
                        pass
            return holiday_scene

    # ── 优先级2：调休工作日（周末但要上班）→ 按工作日逻辑 ──
    weekday = now.weekday()
    is_weekend = weekday >= 5
    is_actually_workday = not is_weekend or is_workday_override(today)

    sched = _get_scene_schedule(card)

    # 应用事件覆盖
    if event_overrides:
        sched.update(event_overrides)

    # 天气导致的通勤延迟
    if weather_service and is_actually_workday:
        commute_delay = weather_service.get_commute_delay()
        if commute_delay > 0:
            sched["arrive_work"] += commute_delay
            sched["arrive_home"] += commute_delay // 2

    minute = now.hour * 60 + now.minute

    if is_actually_workday:
        # ── 工作日/调休日逻辑 ──
        if minute < sched["wake_up"]:
            return SceneEnum.HOME_SLEEPING, SCENE_LABELS[SceneEnum.HOME_SLEEPING]
        elif minute < sched["leave_home"]:
            return SceneEnum.HOME_MORNING, SCENE_LABELS[SceneEnum.HOME_MORNING]
        elif minute < sched["arrive_work"]:
            return SceneEnum.COMMUTE_TO_WORK, SCENE_LABELS[SceneEnum.COMMUTE_TO_WORK]
        elif minute < sched["lunch_start"]:
            # 5% 概率开会
            rng = random.Random(seed + 3)
            if rng.random() < 0.05:
                return SceneEnum.OFFICE_MEETING, SCENE_LABELS[SceneEnum.OFFICE_MEETING]
            return SceneEnum.OFFICE_WORKING, SCENE_LABELS[SceneEnum.OFFICE_WORKING]
        elif minute < sched["lunch_end"]:
            return SceneEnum.OFFICE_LUNCH, SCENE_LABELS[SceneEnum.OFFICE_LUNCH]
        elif minute < sched["leave_work"]:
            return SceneEnum.OFFICE_WORKING, SCENE_LABELS[SceneEnum.OFFICE_WORKING]
        elif minute < sched["arrive_home"]:
            # 如果 leave_work 很晚（加班），检查是否深夜
            if sched.get("leave_work", 18*60) >= 21 * 60:
                return SceneEnum.OVERTIME, SCENE_LABELS[SceneEnum.OVERTIME]
            return SceneEnum.COMMUTE_TO_HOME, SCENE_LABELS[SceneEnum.COMMUTE_TO_HOME]
        elif minute < sched["sleep"]:
            # 傍晚随机触发
            rng = random.Random(seed + 4)
            # 天气恶劣时留在室内
            if weather_service and weather_service.get_scene_hint():
                return SceneEnum.HOME_EVENING, SCENE_LABELS[SceneEnum.HOME_EVENING]
            if rng.random() < 0.15:
                return SceneEnum.CAFE, SCENE_LABELS[SceneEnum.CAFE]
            elif rng.random() < 0.10:
                return SceneEnum.SUPERMARKET, SCENE_LABELS[SceneEnum.SUPERMARKET]
            return SceneEnum.HOME_EVENING, SCENE_LABELS[SceneEnum.HOME_EVENING]
        else:
            return SceneEnum.HOME_SLEEPING, SCENE_LABELS[SceneEnum.HOME_SLEEPING]
    else:
        # ── 周末逻辑 ──
        if minute < _time_to_minutes("09:30"):
            return SceneEnum.HOME_SLEEPING, SCENE_LABELS[SceneEnum.HOME_SLEEPING]
        elif minute < _time_to_minutes("12:00"):
            return SceneEnum.HOME_WEEKEND_LAZY, SCENE_LABELS[SceneEnum.HOME_WEEKEND_LAZY]
        elif minute < _time_to_minutes("13:30"):
            rng = random.Random(seed + 1)
            scenes = [SceneEnum.HOME_EVENING, SceneEnum.CAFE, SceneEnum.STREET_WANDERING]
            # 天气恶劣时留在室内
            if weather_service and weather_service.get_scene_hint():
                scenes = [SceneEnum.HOME_EVENING, SceneEnum.HOME_EVENING, SceneEnum.HOME_EVENING]
            s = rng.choice(scenes)
            return s, SCENE_LABELS[s]
        elif minute < _time_to_minutes("18:00"):
            rng = random.Random(seed + 2)
            scenes = [SceneEnum.PARK, SceneEnum.STREET_WANDERING, SceneEnum.CAFE, SceneEnum.HOME_EVENING]
            if weather_service and weather_service.get_scene_hint():
                scenes = [SceneEnum.HOME_EVENING, SceneEnum.CAFE, SceneEnum.SUPERMARKET, SceneEnum.HOME_EVENING]
            s = rng.choice(scenes)
            return s, SCENE_LABELS[s]
        elif minute < sched["sleep"]:
            rng = random.Random(seed + 5)
            if rng.random() < 0.12:
                return SceneEnum.FRIEND_HANGOUT, SCENE_LABELS[SceneEnum.FRIEND_HANGOUT]
            return SceneEnum.HOME_EVENING, SCENE_LABELS[SceneEnum.HOME_EVENING]
        else:
            return SceneEnum.HOME_SLEEPING, SCENE_LABELS[SceneEnum.HOME_SLEEPING]


def get_day_seed(now: Optional[datetime] = None) -> int:
    """当天日期作为随机种子"""
    now = now or datetime.now()
    return now.year * 10000 + now.month * 100 + now.day


def get_time_period_label(now: Optional[datetime] = None) -> str:
    """获取时段描述（含节假日标注）"""
    now = now or datetime.now()
    weekday_names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    label = f"{weekday_names[now.weekday()]} {now.strftime('%H:%M')}"

    holiday = get_holiday(now.date())
    if holiday and holiday["type"] not in ("workday", "shopping"):
        label += f"（{holiday['label']}）"

    return label


def get_festive_log_entry(now: Optional[datetime] = None) -> Optional[str]:
    """
    如果今天是特殊节日，返回一条节日相关日志条目。
    用于在 tick 中注入节日氛围。
    """
    now = now or datetime.now()
    holiday = get_holiday(now.date())
    if not holiday or holiday["type"] in ("workday", "shopping"):
        return None

    label = holiday["label"]
    htype = holiday["type"]

    # 法定长假
    if htype == "public_holiday":
        templates = {
            "元旦": ["新年第一天，发了条朋友圈", "许了个新年愿望"],
            "春节": ["贴了副春联", "收到了好几个红包", "和家里人包了饺子", "看了一会儿春晚"],
            "清明节": ["去给长辈扫了墓", "路上塞车，开了好久才到"],
            "劳动节": ["五一小长假，终于可以不用设闹钟了", "假期第一天睡到了自然醒"],
            "端午节": ["吃了妈妈寄来的粽子", "买了艾草挂在门口"],
            "中秋节": ["吃了一块蛋黄月饼", "和家人视频赏月"],
            "国庆节": ["朋友圈被旅行照刷屏了", "哪儿都是人，还是待在家吧"],
        }
        seed = now.year * 10000 + now.month * 100 + now.day + now.hour
        rng = random.Random(seed)
        entries = templates.get(label, [f"{label}快乐"])
        return rng.choice(entries)

    # 现代节日
    if htype == "modern":
        templates = {
            "情人节": ["朋友圈全是秀恩爱的", "给自己买了束花"],
            "妇女节": ["公司发了下午茶", "和女同事一起吃了顿好的"],
            "儿童节": ["偷偷吃了根棒棒糖", "看到儿童节的氛围觉得好怀念"],
            "七夕": ["被七夕的营销刷屏了", "路边全是卖花的"],
            "圣诞节": ["收到了朋友寄的苹果", "街上到处都是圣诞装饰"],
            "跨年夜": ["守岁看跨年晚会", "发了条跨年朋友圈"],
            "年末": ["开始整理这一年的照片", "写了年终总结", "想着今年的目标好像一个都没完成"],
        }
        entries = templates.get(label, [])
        if entries:
            seed = now.year * 10000 + now.month * 100 + now.day + now.hour
            rng = random.Random(seed)
            return rng.choice(entries)

    # 传统节日
    if htype == "traditional":
        templates = {
            "小年": ["买了点灶糖", "开始准备年货了"],
            "重阳节": ["给爸妈打了个电话", "想起了外公外婆"],
        }
        entries = templates.get(label, [])
        if entries:
            seed = now.year * 10000 + now.month * 100 + now.day + now.hour
            rng = random.Random(seed)
            return rng.choice(entries)

    return None


def get_holiday_info(now: Optional[datetime] = None) -> Optional[dict]:
    """获取当前日期的节假日信息（供 API 返回）"""
    now = now or datetime.now()
    h = get_holiday(now.date())
    if not h:
        return None
    return {
        "label": h["label"],
        "type": h["type"],
        "mood_delta": h["mood_delta"],
    }


def catchup_world_state(
    last_state: WorldState,
    card: CharacterCard,
    now: Optional[datetime] = None,
) -> Tuple[WorldState, List[str]]:
    """
    离线补算：计算离线期间发生的事。
    返回 (新的world_state, 补算日志列表)。
    不逐帧计算，只取关键节点。
    """
    now = now or datetime.now()
    last_time = datetime.fromisoformat(last_state.last_updated) if last_state.last_updated else now - timedelta(hours=1)
    delta = now - last_time

    logs = []

    if delta.total_seconds() < 300:
        return last_state, logs

    hours_offline = delta.total_seconds() / 3600
    name = card.basic.name

    if hours_offline < 6:
        logs.append(f"你不在的时候，{name}一直在{SCENE_LABELS.get(SceneEnum(last_state.current_scene), last_state.current_scene)}")
    elif hours_offline < 24:
        activities = ["睡了个午觉", "发了一会儿呆", "刷了一会儿手机", "出去走了走"]
        logs.append(f"你不在的这段时间，{name}{random.choice(activities)}")
        if last_state.mood < 50:
            logs.append("看起来心情不太好的样子")
    elif hours_offline < 72:
        days_offline = int(hours_offline / 24)
        logs.append(f"已经{days_offline}天没见了，{name}的日子照常过着")
        daily_activities = [
            "还是每天按部就班地上班下班",
            "工作好像挺忙的，经常加班",
            "周末好像出去逛了逛",
        ]
        logs.append(random.choice(daily_activities))

        # 离线期间如果经过了节假日，提及
        for i in range(max(1, int(delta.days))):
            past_day = (now.date() - timedelta(days=i))
            h = get_holiday(past_day)
            if h and h["type"] == "public_holiday":
                logs.append(f"{h['label']}的时候{random.choice(['在家休息了', '出去逛了逛', '和朋友们聚了聚'])}")
                break
    else:
        days_offline = int(hours_offline / 24)
        logs.append(f"你离开了{days_offline}天，{name}的生活还在继续")

    # 计算当前正确状态
    scene, label = get_current_scene(card, now)
    last_state.current_scene = scene.value
    last_state.current_activity = ""
    last_state.last_updated = now.isoformat()
    last_state.today_date = now.strftime("%Y-%m-%d")
    last_state.today_log = [LogEntry(time=now.strftime("%H:%M"), event=l) for l in logs]

    return last_state, logs
