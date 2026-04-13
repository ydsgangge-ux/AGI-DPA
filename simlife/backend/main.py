"""
SimLife FastAPI 后端入口
端口 8769
"""
import json
import sys
import os
import webbrowser
import threading
from pathlib import Path
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

# ── 路径 ──────────────────────────────────────────────
SIMLIFE_DIR = Path(__file__).parent.parent
DATA_DIR = SIMLIFE_DIR / "data"
FRONTEND_DIR = SIMLIFE_DIR / "frontend"

sys.path.insert(0, str(SIMLIFE_DIR.parent))

from simlife.backend.character import (
    CharacterCard, WorldState, LogEntry, SceneEnum, SCENE_LABELS
)
from simlife.backend.world_engine import (
    get_current_scene, get_day_seed, get_time_period_label, catchup_world_state
)
from simlife.backend.event_engine import (
    load_event_library, load_scheduled_events, save_scheduled_events,
    load_event_history, record_triggered_event,
    check_daily_micro_events, check_random_events, check_scheduled_events,
    apply_event_consequences, add_scheduled_events
)
from simlife.backend.mood_engine import calculate_mood, get_mood_tone
from simlife.backend.npc_engine import load_npc_cards, get_active_npcs
from simlife.backend.agidpa_reader import AGIDPAReader
from simlife.backend.weather import WeatherService
from simlife.backend.world_engine import get_holiday_info, get_festive_log_entry

# ── 全局状态 ───────────────────────────────────────────
character_card: Optional[CharacterCard] = None
world_state: Optional[WorldState] = None
agidpa_reader: Optional[AGIDPAReader] = None
weather_service: Optional[WeatherService] = None
last_tick_scene: Optional[str] = None

# ── App ───────────────────────────────────────────────
app = FastAPI(title="SimLife", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 挂载静态文件（前端）
FRONTEND_DIR.mkdir(parents=True, exist_ok=True)


def _load_config() -> dict:
    config_path = DATA_DIR / "simlife_config.json"
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def _load_character_card() -> Optional[CharacterCard]:
    path = DATA_DIR / "character_card.json"
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return CharacterCard(**data)
    return None


def _save_character_card(card: CharacterCard):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = DATA_DIR / "character_card.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(card.model_dump(), f, ensure_ascii=False, indent=2)


def _load_world_state() -> WorldState:
    path = DATA_DIR / "world_state.json"
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return WorldState(**data)
    return WorldState()


def _save_world_state(state: WorldState):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = DATA_DIR / "world_state.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state.model_dump(), f, ensure_ascii=False, indent=2)


def _tick():
    """核心时钟：计算当前场景、检查事件、更新状态"""
    global character_card, world_state, agidpa_reader, last_tick_scene

    if not character_card or not world_state:
        return

    now = datetime.now()
    today = now.strftime("%Y-%m-%d")

    # 新的一天，重置
    if world_state.today_date != today:
        world_state.today_date = today
        world_state.today_log = []
        world_state.today_events_triggered = []
        # 继承前一天加班的疲劳
        if world_state.current_scene == "OVERTIME":
            world_state.sleep_mood_penalty = -5
        else:
            world_state.sleep_mood_penalty = 0

        # 新的一天注入节日日志（第一条）
        festive_log = get_festive_log_entry(now)
        if festive_log:
            world_state.today_log.append(LogEntry(
                time="09:00", event=festive_log
            ))

    # 离线补算
    last_updated = datetime.fromisoformat(world_state.last_updated) if world_state.last_updated else None
    if last_updated and (now - last_updated).total_seconds() > 300:
        world_state, catchup_logs = catchup_world_state(world_state, character_card, now)
        last_tick_scene = world_state.current_scene

    # 事件覆盖（今日已触发事件的后果）
    event_overrides = {}
    for evt_id in world_state.today_events_triggered:
        consequence = apply_event_consequences(evt_id, 0)
        event_overrides.update(consequence.get("schedule_overrides", {}))

    # 计算场景（传入天气服务）
    day_seed = get_day_seed(now)
    scene, label = get_current_scene(
        character_card, now, day_seed,
        event_overrides or None,
        weather_service=weather_service,
    )

    # 场景变化
    scene_changed = scene.value != world_state.current_scene
    if scene_changed:
        world_state.current_scene = scene.value
        time_str = now.strftime("%H:%M")
        if last_tick_scene:
            old_label = SCENE_LABELS.get(SceneEnum(last_tick_scene), last_tick_scene)
            world_state.today_log.append(LogEntry(
                time=time_str, event=f"→ {label}"
            ))

        # 生成 activity 描述
        try:
            from simlife.backend.generator import generate_activity_description
            events_summary = "; ".join([l.event for l in world_state.today_log[-5:]])
            activity = generate_activity_description(
                character_card.model_dump(),
                scene.value, label,
                events_summary,
                world_state.mood
            )
            world_state.current_activity = activity
        except Exception as e:
            print(f"[SimLife] Activity生成失败: {e}")
            world_state.current_activity = f"在{label}"

        last_tick_scene = scene.value

    # 检查微事件（每 5 分钟检查一次，不再仅限场景变化或整15分钟）
    if scene_changed or (now.minute % 5 == 0):
        micro = check_daily_micro_events(
            character_card.model_dump(),
            scene.value,
            day_seed,
            world_state.today_events_triggered
        )
        if micro and micro["id"] not in world_state.today_events_triggered:
            world_state.today_events_triggered.append(micro["id"])
            record_triggered_event(micro)
            world_state.today_log.append(LogEntry(
                time=now.strftime("%H:%M"),
                event=micro["label"]
            ))

    # 检查随机事件
    rand_evt = check_random_events(
        character_card.model_dump(),
        scene.value,
        day_seed,
        world_state.today_events_triggered,
        now,
    )
    if rand_evt and rand_evt["id"] not in world_state.today_events_triggered:
        world_state.today_events_triggered.append(rand_evt["id"])
        record_triggered_event(rand_evt)
        world_state.today_log.append(LogEntry(
            time=now.strftime("%H:%M"),
            event=rand_evt["label"]
        ))

    # 检查排期事件
    scheduled = load_scheduled_events()
    triggered, remaining = check_scheduled_events(scheduled, now)
    for evt in triggered:
        if evt["id"] not in world_state.today_events_triggered:
            world_state.today_events_triggered.append(evt["id"])
            record_triggered_event(evt)
            world_state.today_log.append(LogEntry(
                time=now.strftime("%H:%M"),
                event=evt["label"]
            ))
    if triggered:
        save_scheduled_events(remaining)

    # 计算心情（加入天气 + 节假日修正）
    is_weekend = now.weekday() >= 5
    mood_deltas = []
    for eid in world_state.today_events_triggered:
        hist = load_event_history()
        for h in hist:
            if h.get("id") == eid:
                mood_deltas.append(h.get("mood_delta", 0))
                break

    interaction_hours = None
    task_len = 0
    if agidpa_reader and agidpa_reader.is_available():
        if agidpa_reader.recent_interaction_within_hours(3):
            interaction_hours = 0.1
        else:
            interaction_hours = None
        task_len = agidpa_reader.get_task_queue_length()

    # 天气心情修正
    weather_mood_delta = 0
    if weather_service:
        weather_mood_delta = weather_service.get_mood_delta()

    # 节假日心情修正
    holiday_mood_delta = 0
    from simlife.backend.holiday_calendar import get_holiday_mood_delta
    holiday_mood_delta = get_holiday_mood_delta(now.date())

    mood_deltas.append(weather_mood_delta)
    mood_deltas.append(holiday_mood_delta)

    world_state.mood = calculate_mood(
        scene=scene.value,
        current_hour=now.hour,
        is_weekend=is_weekend,
        today_events_mood_delta=mood_deltas,
        recent_interaction_hours=interaction_hours,
        task_queue_length=task_len,
        sleep_penalty=world_state.sleep_mood_penalty,
    )

    # 激活 NPC
    active = get_active_npcs(scene.value, world_state.today_events_triggered)
    world_state.active_npcs = [n.get("id", "") for n in active]

    # 限制日志数量
    if len(world_state.today_log) > 50:
        world_state.today_log = world_state.today_log[-50:]

    # 保存
    world_state.last_updated = now.isoformat()
    _save_world_state(world_state)


# ── API 路由 ──────────────────────────────────────────

@app.get("/api/world/state")
def api_world_state():
    _tick()
    if not world_state:
        return {"error": "世界未初始化"}

    # 天气信息
    weather_data = {"label": "多云", "emoji": "⛅", "temp": ""}
    if weather_service:
        w = weather_service.get_weather()
        weather_data = {
            "label": w.get("label", "多云"),
            "emoji": w.get("emoji", "⛅"),
            "temp": w.get("temp", ""),
            "text": w.get("text", ""),
        }

    # 节假日信息
    holiday_info = get_holiday_info()

    return {
        "scene": world_state.current_scene,
        "scene_label": SCENE_LABELS.get(
            SceneEnum(world_state.current_scene), world_state.current_scene
        ),
        "activity": world_state.current_activity,
        "mood": world_state.mood,
        "active_npcs": world_state.active_npcs,
        "today_date": world_state.today_date,
        "time_label": get_time_period_label(),
        "latest_log": [
            {"time": l.time, "event": l.event}
            for l in world_state.today_log[-20:]
        ],
        "weather": weather_data,
        "holiday": holiday_info,
    }


@app.get("/api/character")
def api_get_character():
    if not character_card:
        return {"initialized": False}
    return {"initialized": True, "card": character_card.model_dump()}


@app.post("/api/character")
def api_set_character(data: dict):
    global character_card
    try:
        character_card = CharacterCard(**data)
        _save_character_card(character_card)
        # 初始化世界状态
        global world_state
        world_state = WorldState(
            last_updated=datetime.now().isoformat(),
            today_date=datetime.now().strftime("%Y-%m-%d"),
            current_scene="HOME_EVENING",
            current_activity="刚设置好，在看看新家",
        )
        _save_world_state(world_state)
        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(400, str(e))


@app.post("/api/setup/generate")
def api_setup_generate(data: dict):
    """首次设置：根据锚点生成人物卡"""
    global character_card

    try:
        from simlife.backend.generator import generate_character_card, generate_npc_cards

        anchor = data.get("anchor", {})
        card_data = generate_character_card(anchor)
        if not card_data:
            raise HTTPException(500, "人物卡生成失败")

        character_card = CharacterCard(**card_data)
        _save_character_card(character_card)

        # 生成 NPC
        npc_data = generate_npc_cards(card_data)
        if npc_data:
            from simlife.backend.npc_engine import save_npc_cards
            save_npc_cards(npc_data)

        # 初始化世界状态
        global world_state
        now = datetime.now()
        scene, label = get_current_scene(character_card, now)
        world_state = WorldState(
            last_updated=now.isoformat(),
            current_scene=scene.value,
            current_activity=f"世界开始了，{label}",
            today_date=now.strftime("%Y-%m-%d"),
        )
        _save_world_state(world_state)

        return {"status": "ok", "card": character_card.model_dump()}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"生成失败: {e}")


@app.get("/api/npcs")
def api_get_npcs():
    return {"npcs": load_npc_cards()}


@app.get("/api/events/history")
def api_event_history():
    return {"history": load_event_history()[-30:]}


@app.get("/api/events/scheduled")
def api_scheduled_events():
    return {"scheduled": load_scheduled_events()}


@app.get("/api/status")
def api_status():
    return {
        "initialized": character_card is not None,
        "version": "1.0.0",
    }


# ── 前端静态文件 ─────────────────────────────────────

@app.get("/")
def serve_index():
    index_path = FRONTEND_DIR / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    return "<h1>SimLife</h1><p>前端文件未找到，请运行 setup.py</p>"


# 挂载前端静态文件（JS/CSS/图片）
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


@app.on_event("startup")
def on_startup():
    global character_card, world_state, agidpa_reader, weather_service

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # 加载人物卡
    character_card = _load_character_card()

    # 加载世界状态
    if character_card:
        world_state = _load_world_state()

    # AGI-DPA 读取器
    config = _load_config()
    agidpa_path = config.get("agidpa_data_path", "")
    agidpa_reader = AGIDPAReader(agidpa_path)

    # 天气服务（Open-Meteo 免费 API，无需配置 Key，根据人物卡城市自动定位）
    city = character_card.basic.city if character_card else "上海"
    weather_service = WeatherService(city=city)
    geo = weather_service._geo
    if geo:
        print(f"[SimLife] 天气服务已启用（{city}，{geo[0]:.2f}°N {geo[1]:.2f}°E）")
    else:
        print(f"[SimLife] 天气服务：城市「{city}」未找到坐标，使用季节推断")

    print("[SimLife] 后端启动")
    if character_card:
        print(f"[SimLife] 角色: {character_card.basic.name}")
        h = get_holiday_info()
        if h:
            print(f"[SimLife] 今天: {h['label']}（{h['type']}）")
        _tick()
    else:
        print("[SimLife] 未初始化，请访问设置页面")

    # ── 后台定时 tick 线程（不依赖前端轮询，每 3 分钟自动推进一次）──
    def _background_tick_loop():
        while True:
            try:
                import time
                time.sleep(180)  # 每 3 分钟
                _tick()
            except Exception as e:
                print(f"[SimLife] 后台tick出错: {e}")

    _bg_thread = threading.Thread(target=_background_tick_loop, daemon=True)
    _bg_thread.start()
    print("[SimLife] 后台定时 tick 已启动（每 3 分钟）")


def run_server(port: int = 87659, open_browser: bool = True):
    """启动服务器"""
    import uvicorn

    def _open():
        import time
        time.sleep(1.5)
        webbrowser.open(f"http://127.0.0.1:{port}")

    if open_browser:
        threading.Thread(target=_open, daemon=True).start()

    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="SimLife 后端")
    parser.add_argument("--port", type=int, default=8769)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    run_server(port=args.port, open_browser=not args.no_browser)
