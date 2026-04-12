"""
SimLife 客户端 - 主 AGI-DPA 系统读取 SimLife 生活状态
通过 HTTP API (端口 8765) 或直接读文件（更可靠）获取状态
"""

import json
import urllib.request
import urllib.error
from pathlib import Path
from typing import Optional
from datetime import datetime

# 场景枚举 → 中文标签（与 simlife/backend/character.py 保持一致）
_SCENE_LABELS = {
    "HOME_SLEEPING": "睡觉",
    "HOME_MORNING": "晨间准备",
    "HOME_EVENING": "晚间放松",
    "HOME_WEEKEND_LAZY": "周末赖床",
    "COMMUTE_TO_WORK": "去公司",
    "COMMUTE_TO_HOME": "回家",
    "OFFICE_WORKING": "工作中",
    "OFFICE_MEETING": "开会",
    "OFFICE_LUNCH": "午休觅食",
    "CAFE": "咖啡馆",
    "PARK": "公园",
    "SUPERMARKET": "超市",
    "STREET_WANDERING": "街头闲逛",
    "FRIEND_HANGOUT": "和朋友在外",
    "OVERTIME": "加班",
}


class SimLifeClient:
    """
    SimLife 状态读取客户端。
    优先直接读 world_state.json（SimLife 未启动也能用），
    回退到 HTTP API（获取实时最新状态）。
    """

    def __init__(self, simlife_port: int = 8765):
        self.port = simlife_port
        self._state_file = Path(__file__).parent.parent / "simlife" / "data" / "world_state.json"
        self._character_file = Path(__file__).parent.parent / "simlife" / "data" / "character_card.json"
        self._cache = None
        self._cache_time = None
        self._cache_ttl = 10  # 缓存10秒

    def _read_file_state(self) -> Optional[dict]:
        """直接读 world_state.json（零依赖）"""
        if not self._state_file.exists():
            return None
        try:
            with open(self._state_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    def _read_character(self) -> Optional[dict]:
        """读人物卡"""
        if not self._character_file.exists():
            return None
        try:
            with open(self._character_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    def _fetch_api_state(self) -> Optional[dict]:
        """通过 HTTP API 获取最新状态（触发 _tick）"""
        try:
            url = f"http://127.0.0.1:{self.port}/api/world/state"
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=3) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception:
            return None

    def get_state(self, use_api: bool = False) -> Optional[dict]:
        """
        获取 SimLife 世界状态。
        use_api=True 时优先尝试 HTTP（获取实时状态），失败回退文件。
        use_api=False 时直接读文件。
        """
        if use_api:
            data = self._fetch_api_state()
            if data and "error" not in data:
                self._cache = data
                self._cache_time = datetime.now()
                return data

        # 回退到文件
        return self._read_file_state()

    def is_available(self) -> bool:
        """SimLife 是否已初始化（有人物卡）"""
        return self._character_file.exists() and self._state_file.exists()

    def is_running(self) -> bool:
        """SimLife 后端是否在运行"""
        try:
            url = f"http://127.0.0.1:{self.port}/api/status"
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=2) as r:
                data = json.loads(r.read().decode("utf-8"))
                return data.get("initialized", False)
        except Exception:
            return False

    def format_for_prompt(self) -> str:
        """
        格式化为可注入 AGI 对话 prompt 的文本。
        返回空字符串表示 SimLife 不可用。
        """
        # 优先 API（实时），回退文件（快照）
        state = self.get_state(use_api=True)
        if not state or "error" in state:
            state = self._read_file_state()
        if not state:
            return ""

        character = self._read_character()
        name = ""
        city = ""
        if character:
            name = character.get("basic", {}).get("name", "")
            city = character.get("basic", {}).get("city", "")

        # 兼容 API 返回和 JSON 文件两种格式
        scene_label = state.get("scene_label", "") or _SCENE_LABELS.get(state.get("current_scene", ""), "")
        activity = state.get("activity", "") or state.get("current_activity", "")
        mood = state.get("mood", 70)
        today_date = state.get("today_date", "")

        # today_log: API 返回 [{"time":..., "event":...}]，文件里是 LogEntry 对象序列化
        today_log = state.get("latest_log", []) or state.get("today_log", [])

        # 如果 current_activity 为空，用 today_log 最后一条作为当前活动
        if not activity and today_log:
            last_entry = today_log[-1]
            if isinstance(last_entry, dict):
                activity = last_entry.get("event", "")
            elif hasattr(last_entry, "event"):
                activity = last_entry.event

        # 心情描述
        if mood >= 80:
            mood_desc = "心情不错"
        elif mood >= 60:
            mood_desc = "状态还行"
        elif mood >= 40:
            mood_desc = "有点累"
        else:
            mood_desc = "心情不太好"

        lines = ["【当前生活状态（SimLife）】"]

        if today_date:
            lines.append(f"日期：{today_date}")

        if activity:
            lines.append(f"正在：{activity}")
        elif scene_label:
            lines.append(f"场景：{scene_label}")

        lines.append(f"心情：{mood_desc}（{mood}/100）")

        # 最近的 3 条事件（不含最后一条，因为已经作为"正在"展示了）
        if len(today_log) > 1:
            recent = today_log[-4:-1] if len(today_log) >= 4 else today_log[:-1]
            events_str = "、".join(
                l.get("event", "") if isinstance(l, dict) else getattr(l, "event", "")
                for l in recent
            )
            if events_str:
                lines.append(f"今天还发生了：{events_str}")

        return "\n".join(lines)

    def get_character_info(self) -> Optional[dict]:
        """
        获取角色基本信息（供 UI 展示）。
        返回 {"name": ..., "city": ..., "age": ..., "appearance": ...} 或 None。
        """
        ch = self._read_character()
        if not ch:
            return None
        basic = ch.get("basic", {})
        return {
            "name": basic.get("name", ""),
            "city": basic.get("city", ""),
            "age": basic.get("age", ""),
            "personality": basic.get("personality_traits", ""),
            "appearance": ch.get("appearance", {}),
        }

    def get_life_summary(self) -> Optional[dict]:
        """
        获取完整的生活摘要（供 UI 面板展示）。
        返回 {"name", "scene", "activity", "mood", "mood_desc", "mood_emoji",
              "today_date", "today_log", "weather", "time_str"} 或 None。
        """
        state = self.get_state(use_api=True)
        if not state or "error" in state:
            state = self._read_file_state()
        if not state:
            return None

        ch = self._read_character()
        name = ch.get("basic", {}).get("name", "") if ch else ""

        # 场景
        scene_label = state.get("scene_label", "") or _SCENE_LABELS.get(state.get("current_scene", ""), "")
        scene_raw = state.get("current_scene", "")

        # 活动
        activity = state.get("activity", "") or state.get("current_activity", "")
        today_log = state.get("latest_log", []) or state.get("today_log", [])
        if not activity and today_log:
            last = today_log[-1]
            activity = last.get("event", "") if isinstance(last, dict) else getattr(last, "event", "")

        # 心情
        mood = state.get("mood", 70)
        if mood >= 80:
            mood_desc, mood_emoji = "心情不错", "😊"
        elif mood >= 60:
            mood_desc, mood_emoji = "状态还行", "🙂"
        elif mood >= 40:
            mood_desc, mood_emoji = "有点累", "😐"
        else:
            mood_desc, mood_emoji = "心情不太好", "😔"

        # 日志标准化为 [{"time": ..., "event": ...}]
        log_entries = []
        for entry in today_log:
            if isinstance(entry, dict):
                log_entries.append({
                    "time": entry.get("time", entry.get("timestamp", "")),
                    "event": entry.get("event", entry.get("content", "")),
                })
            elif hasattr(entry, "event"):
                log_entries.append({
                    "time": getattr(entry, "time", ""),
                    "event": entry.event,
                })

        # 天气（兼容 API 新格式和旧格式）
        weather_raw = state.get("weather", "")
        if isinstance(weather_raw, dict):
            weather_str = f"{weather_raw.get('emoji', '')} {weather_raw.get('label', '')}"
            weather_temp = weather_raw.get("temp", "")
            if weather_temp:
                weather_str += f" {weather_temp}°C"
        elif isinstance(weather_raw, str):
            weather_str = weather_raw
        else:
            weather_str = ""

        # 节假日
        holiday = state.get("holiday")

        # 时间标签（API 返回，含节假日标注）
        time_str = state.get("time_label", "") or state.get("current_time", "")

        return {
            "name": name,
            "scene": scene_label,
            "scene_raw": scene_raw,
            "activity": activity,
            "mood": mood,
            "mood_desc": mood_desc,
            "mood_emoji": mood_emoji,
            "today_date": state.get("today_date", ""),
            "today_log": log_entries,
            "weather": weather_str,
            "time_str": time_str,
            "holiday": holiday,
        }
