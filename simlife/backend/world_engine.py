"""
世界引擎 - 时间→场景映射 + 场景推算 + 离线补算
支持节假日覆盖 + 天气影响 + 多种工作模式（上班族/自由职业/学生）
"""
import random
from datetime import datetime, timedelta, date
from typing import Optional, List, Tuple
from .character import (
    CharacterCard, WorldState, SceneEnum, LogEntry, SCENE_LABELS,
    WorkStyle, WORK_STYLE_SCENES, detect_work_style,
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
    sched = {
        "wake_up": _time_to_minutes(s.wake_up),
        "leave_home": _time_to_minutes(s.leave_home),
        "arrive_work": _time_to_minutes(s.arrive_work),
        "lunch_start": _time_to_minutes(s.lunch_break_start),
        "lunch_end": _time_to_minutes(s.lunch_break_end),
        "leave_work": _time_to_minutes(s.leave_work),
        "arrive_home": _time_to_minutes(s.arrive_home),
        "sleep": _time_to_minutes(s.sleep),
    }
    # 自由职业扩展字段
    if hasattr(s, "work_start") and s.work_start:
        sched["work_start"] = _time_to_minutes(s.work_start)
    if hasattr(s, "work_end") and s.work_end:
        sched["work_end"] = _time_to_minutes(s.work_end)
    return sched


def _get_work_style(card: CharacterCard) -> WorkStyle:
    """获取角色的工作模式"""
    if hasattr(card.basic, "work_style") and card.basic.work_style:
        try:
            return WorkStyle(card.basic.work_style)
        except ValueError:
            pass
    return detect_work_style(card.basic.occupation)


def _pick_work_scene(card: CharacterCard, seed: int, hour: int) -> SceneEnum:
    """根据工作地点权重随机选择一个工作场景"""
    weights = {"home": 50, "cafe": 25, "outdoor": 15, "studio": 10}
    if hasattr(card.basic, "work_location_weights") and card.basic.work_location_weights:
        weights = card.basic.work_location_weights

    scene_map = {
        "home": SceneEnum.HOME_WORKING,
        "cafe": SceneEnum.CAFE_WORKING,
        "outdoor": SceneEnum.OUTDOOR_WORKING,
        "studio": SceneEnum.STUDIO_WORKING,
    }

    # 根据小时微调权重（早上更可能在家，下午更可能外出）
    adjusted = dict(weights)
    if hour >= 14:  # 下午
        if "outdoor" in adjusted:
            adjusted["outdoor"] = int(adjusted.get("outdoor", 15) * 1.5)
        if "cafe" in adjusted:
            adjusted["cafe"] = int(adjusted.get("cafe", 25) * 1.3)

    # 加权随机
    total = sum(adjusted.values())
    if total == 0:
        return SceneEnum.HOME_WORKING

    r = random.Random(seed + hour * 7)
    pick = r.randint(1, total)
    cumulative = 0
    for loc, weight in adjusted.items():
        cumulative += weight
        if pick <= cumulative:
            return scene_map.get(loc, SceneEnum.HOME_WORKING)

    return SceneEnum.HOME_WORKING


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
    根据工作模式（上班族/自由职业/学生）使用不同的场景逻辑。
    """
    now = now or datetime.now()
    today = now.date()
    seed = day_seed or (now.year * 10000 + now.month * 100 + now.day)

    work_style = _get_work_style(card)

    # ── 优先级1：法定节假日 → 走节假日专属场景 ──
    if is_public_holiday(today):
        holiday_scene = get_holiday_scene(today, now.hour, seed)
        if holiday_scene:
            if weather_service:
                scene_hint = weather_service.get_scene_hint()
                if scene_hint and now.hour >= 8 and now.hour < 22:
                    try:
                        forced_scene = SceneEnum(scene_hint)
                        return forced_scene, SCENE_LABELS[forced_scene]
                    except ValueError:
                        pass
            return holiday_scene

    # ── 优先级2：调休工作日 → 按工作日逻辑 ──
    weekday = now.weekday()
    is_weekend = weekday >= 5
    is_actually_workday = not is_weekend or is_workday_override(today)

    sched = _get_scene_schedule(card)

    if event_overrides:
        sched.update(event_overrides)

    # 天气导致的通勤延迟（仅上班族）
    if weather_service and is_actually_workday and work_style == WorkStyle.OFFICE:
        commute_delay = weather_service.get_commute_delay()
        if commute_delay > 0:
            sched["arrive_work"] += commute_delay
            sched["arrive_home"] += commute_delay // 2

    minute = now.hour * 60 + now.minute

    if is_actually_workday:
        if work_style in (WorkStyle.FREELANCE, WorkStyle.REMOTE):
            return _freelance_workday_scene(card, sched, minute, seed, now.hour, weather_service)
        elif work_style == WorkStyle.STUDENT:
            return _student_workday_scene(card, sched, minute, seed, now.hour, weather_service)
        else:
            return _office_workday_scene(card, sched, minute, seed, now.hour, weather_service)
    else:
        # ── 周末逻辑 ──
        return _weekend_scene(card, sched, minute, seed, now.hour, weather_service, work_style)


def _office_workday_scene(card, sched, minute, seed, hour, weather_service):
    """上班族工作日场景"""
    if minute < sched["wake_up"]:
        return SceneEnum.HOME_SLEEPING, SCENE_LABELS[SceneEnum.HOME_SLEEPING]
    elif minute < sched["leave_home"]:
        return SceneEnum.HOME_MORNING, SCENE_LABELS[SceneEnum.HOME_MORNING]
    elif minute < sched["arrive_work"]:
        return SceneEnum.COMMUTE_TO_WORK, SCENE_LABELS[SceneEnum.COMMUTE_TO_WORK]
    elif minute < sched["lunch_start"]:
        rng = random.Random(seed + 3)
        if rng.random() < 0.05:
            return SceneEnum.OFFICE_MEETING, SCENE_LABELS[SceneEnum.OFFICE_MEETING]
        return SceneEnum.OFFICE_WORKING, SCENE_LABELS[SceneEnum.OFFICE_WORKING]
    elif minute < sched["lunch_end"]:
        return SceneEnum.OFFICE_LUNCH, SCENE_LABELS[SceneEnum.OFFICE_LUNCH]
    elif minute < sched["leave_work"]:
        return SceneEnum.OFFICE_WORKING, SCENE_LABELS[SceneEnum.OFFICE_WORKING]
    elif minute < sched["arrive_home"]:
        if sched.get("leave_work", 18*60) >= 21 * 60:
            return SceneEnum.OVERTIME, SCENE_LABELS[SceneEnum.OVERTIME]
        return SceneEnum.COMMUTE_TO_HOME, SCENE_LABELS[SceneEnum.COMMUTE_TO_HOME]
    elif minute < sched["sleep"]:
        rng = random.Random(seed + 4)
        if weather_service and weather_service.get_scene_hint():
            return SceneEnum.HOME_EVENING, SCENE_LABELS[SceneEnum.HOME_EVENING]
        if rng.random() < 0.15:
            return SceneEnum.CAFE, SCENE_LABELS[SceneEnum.CAFE]
        elif rng.random() < 0.10:
            return SceneEnum.SUPERMARKET, SCENE_LABELS[SceneEnum.SUPERMARKET]
        return SceneEnum.HOME_EVENING, SCENE_LABELS[SceneEnum.HOME_EVENING]
    else:
        return SceneEnum.HOME_SLEEPING, SCENE_LABELS[SceneEnum.HOME_SLEEPING]


def _freelance_workday_scene(card, sched, minute, seed, hour, weather_service):
    """自由职业工作日场景 — 灵活、多样化"""
    work_start = sched.get("work_start", 10 * 60)
    work_end = sched.get("work_end", 18 * 60)
    lunch_start = sched.get("lunch_start", 12 * 60 + 30)
    lunch_end = sched.get("lunch_end", 14 * 60)

    if minute < sched["wake_up"]:
        return SceneEnum.HOME_SLEEPING, SCENE_LABELS[SceneEnum.HOME_SLEEPING]
    elif minute < work_start:
        return SceneEnum.HOME_MORNING, SCENE_LABELS[SceneEnum.HOME_MORNING]
    elif minute < lunch_start:
        # 上午工作时段 — 根据权重随机选工作地点
        scene = _pick_work_scene(card, seed, hour)
        return scene, SCENE_LABELS[scene]
    elif minute < lunch_end:
        # 午休 — 自由职业者午餐更灵活
        rng = random.Random(seed + 6)
        options = [SceneEnum.HOME_EVENING, SceneEnum.CAFE, SceneEnum.STREET_WANDERING, SceneEnum.SUPERMARKET]
        weights_lunch = [0.35, 0.30, 0.20, 0.15]
        pick = rng.choices(options, weights=weights_lunch, k=1)[0]
        return pick, SCENE_LABELS[pick]
    elif minute < work_end:
        # 下午工作时段
        scene = _pick_work_scene(card, seed + 100, hour)
        return scene, SCENE_LABELS[scene]
    elif minute < sched["sleep"]:
        # 晚间 — 自由职业者可能继续工作或休息
        rng = random.Random(seed + 7)
        evening_options = [
            (SceneEnum.HOME_EVENING, 0.40),
            (SceneEnum.PARK, 0.15),
            (SceneEnum.STREET_WANDERING, 0.15),
            (SceneEnum.CAFE, 0.15),
            (SceneEnum.SUPERMARKET, 0.10),
            (SceneEnum.FRIEND_HANGOUT, 0.05),
        ]
        # 天气恶劣时留在室内
        if weather_service and weather_service.get_scene_hint():
            evening_options = [
                (SceneEnum.HOME_EVENING, 0.60),
                (SceneEnum.CAFE, 0.20),
                (SceneEnum.SUPERMARKET, 0.10),
                (SceneEnum.HOME_WORKING, 0.10),  # 天气不好继续在家工作
            ]
        scenes, weights = zip(*evening_options)
        pick = rng.choices(scenes, weights=weights, k=1)[0]
        return pick, SCENE_LABELS[pick]
    else:
        return SceneEnum.HOME_SLEEPING, SCENE_LABELS[SceneEnum.HOME_SLEEPING]


def _student_workday_scene(card, sched, minute, seed, hour, weather_service):
    """学生工作日场景"""
    if minute < sched["wake_up"]:
        return SceneEnum.HOME_SLEEPING, SCENE_LABELS[SceneEnum.HOME_SLEEPING]
    elif minute < sched["leave_home"]:
        return SceneEnum.HOME_MORNING, SCENE_LABELS[SceneEnum.HOME_MORNING]
    elif minute < sched["arrive_work"]:
        return SceneEnum.COMMUTE_TO_WORK, SCENE_LABELS[SceneEnum.COMMUTE_TO_WORK]
    elif minute < sched["lunch_start"]:
        return SceneEnum.OFFICE_WORKING, SCENE_LABELS[SceneEnum.OFFICE_WORKING]
    elif minute < sched["lunch_end"]:
        return SceneEnum.OFFICE_LUNCH, SCENE_LABELS[SceneEnum.OFFICE_LUNCH]
    elif minute < sched["leave_work"]:
        return SceneEnum.OFFICE_WORKING, SCENE_LABELS[SceneEnum.OFFICE_WORKING]
    elif minute < sched["sleep"]:
        rng = random.Random(seed + 8)
        if minute < sched.get("work_end", 21 * 60):
            # 学生可能晚上自习
            if rng.random() < 0.3:
                return SceneEnum.CAFE_WORKING, SCENE_LABELS[SceneEnum.CAFE_WORKING]
            elif rng.random() < 0.3:
                return SceneEnum.HOME_WORKING, SCENE_LABELS[SceneEnum.HOME_WORKING]
        evening_options = [
            (SceneEnum.HOME_EVENING, 0.35),
            (SceneEnum.CAFE, 0.20),
            (SceneEnum.STREET_WANDERING, 0.15),
            (SceneEnum.PARK, 0.15),
            (SceneEnum.FRIEND_HANGOUT, 0.15),
        ]
        if weather_service and weather_service.get_scene_hint():
            evening_options = [(SceneEnum.HOME_EVENING, 0.70), (SceneEnum.CAFE, 0.30)]
        scenes, weights = zip(*evening_options)
        pick = rng.choices(scenes, weights=weights, k=1)[0]
        return pick, SCENE_LABELS[pick]
    else:
        return SceneEnum.HOME_SLEEPING, SCENE_LABELS[SceneEnum.HOME_SLEEPING]


def _weekend_scene(card, sched, minute, seed, hour, weather_service, work_style):
    """周末场景"""
    # 自由职业者周末可能也在工作（概率降低）
    rng = random.Random(seed)

    if minute < _time_to_minutes("09:30"):
        return SceneEnum.HOME_SLEEPING, SCENE_LABELS[SceneEnum.HOME_SLEEPING]
    elif minute < _time_to_minutes("12:00"):
        return SceneEnum.HOME_WEEKEND_LAZY, SCENE_LABELS[SceneEnum.HOME_WEEKEND_LAZY]
    elif minute < _time_to_minutes("13:30"):
        scenes = [SceneEnum.HOME_EVENING, SceneEnum.CAFE, SceneEnum.STREET_WANDERING]
        if weather_service and weather_service.get_scene_hint():
            scenes = [SceneEnum.HOME_EVENING] * 3
        # 自由职业者周末偶尔工作
        if work_style == WorkStyle.FREELANCE and rng.random() < 0.20:
            return _pick_work_scene(card, seed, hour), SCENE_LABELS[_pick_work_scene(card, seed, hour)]
        s = rng.choice(scenes)
        return s, SCENE_LABELS[s]
    elif minute < _time_to_minutes("18:00"):
        scenes = [SceneEnum.PARK, SceneEnum.STREET_WANDERING, SceneEnum.CAFE, SceneEnum.HOME_EVENING]
        if weather_service and weather_service.get_scene_hint():
            scenes = [SceneEnum.HOME_EVENING, SceneEnum.CAFE, SceneEnum.SUPERMARKET, SceneEnum.HOME_EVENING]
        s = rng.choice(scenes)
        return s, SCENE_LABELS[s]
    elif minute < sched["sleep"]:
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
    """如果今天是特殊节日，返回一条节日相关日志条目。"""
    now = now or datetime.now()
    holiday = get_holiday(now.date())
    if not holiday or holiday["type"] in ("workday", "shopping"):
        return None

    label = holiday["label"]
    htype = holiday["type"]

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
    """离线补算：计算离线期间发生的事。"""
    now = now or datetime.now()
    last_time = datetime.fromisoformat(last_state.last_updated) if last_state.last_updated else now - timedelta(hours=1)
    delta = now - last_time

    logs = []

    if delta.total_seconds() < 300:
        return last_state, logs

    hours_offline = delta.total_seconds() / 3600
    name = card.basic.name
    work_style = _get_work_style(card)

    if hours_offline < 6:
        scene_label = SCENE_LABELS.get(SceneEnum(last_state.current_scene), last_state.current_scene)
        logs.append(f"你不在的时候，{name}一直在{scene_label}")
    elif hours_offline < 24:
        activities = ["睡了个午觉", "发了一会儿呆", "刷了一会儿手机", "出去走了走"]
        logs.append(f"你不在的这段时间，{name}{random.choice(activities)}")
        if last_state.mood < 50:
            logs.append("看起来心情不太好的样子")
    elif hours_offline < 72:
        days_offline = int(hours_offline / 24)
        logs.append(f"已经{days_offline}天没见了，{name}的日子照常过着")
        # 根据工作模式选择不同的补算描述
        if work_style == WorkStyle.FREELANCE:
            daily_activities = [
                "这几天一直在赶一个项目",
                "好像去咖啡馆办公了好几次",
                "在家待的时间比较多",
            ]
        elif work_style == WorkStyle.STUDENT:
            daily_activities = [
                "这几天一直在复习",
                "好像去图书馆了好几次",
                "和同学一起吃了顿火锅",
            ]
        else:
            daily_activities = [
                "还是每天按部就班地上班下班",
                "工作好像挺忙的，经常加班",
                "周末好像出去逛了逛",
            ]
        logs.append(random.choice(daily_activities))

        for i in range(max(1, int(delta.days))):
            past_day = (now.date() - timedelta(days=i))
            h = get_holiday(past_day)
            if h and h["type"] == "public_holiday":
                logs.append(f"{h['label']}的时候{random.choice(['在家休息了', '出去逛了逛', '和朋友们聚了聚'])}")
                break
    else:
        days_offline = int(hours_offline / 24)
        logs.append(f"你离开了{days_offline}天，{name}的生活还在继续")

    scene, label = get_current_scene(card, now)
    last_state.current_scene = scene.value
    last_state.current_activity = ""
    last_state.last_updated = now.isoformat()
    last_state.today_date = now.strftime("%Y-%m-%d")
    last_state.today_log = [LogEntry(time=now.strftime("%H:%M"), event=l) for l in logs]

    return last_state, logs
