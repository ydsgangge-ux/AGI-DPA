"""
天气系统 - 天气数据获取 + 缓存 + 场景/心情影响
使用 Open-Meteo 免费 API（无需 API Key）
缓存策略：每 30 分钟更新一次，写入本地 JSON
"""

import json
import urllib.request
import urllib.parse
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional


# ── 天气数据路径 ──────────────────────────────────────

_CACHE_FILE = Path(__file__).parent.parent / "data" / "weather_cache.json"

# ── 城市 → 经纬度映射 ─────────────────────────────────
# Open-Meteo 用经纬度查询，这里内置中国常见城市
_CITY_GEO = {
    "北京": (39.9042, 116.4074),
    "上海": (31.2304, 121.4737),
    "广州": (23.1291, 113.2644),
    "深圳": (22.5431, 114.0579),
    "杭州": (30.2741, 120.1551),
    "成都": (30.5728, 104.0668),
    "重庆": (29.4316, 106.9123),
    "武汉": (30.5928, 114.3055),
    "南京": (32.0603, 118.7969),
    "天津": (39.3434, 117.3616),
    "西安": (34.3416, 108.9398),
    "苏州": (31.2990, 120.5853),
    "长沙": (28.2282, 112.9388),
    "郑州": (34.7466, 113.6254),
    "东莞": (23.0208, 113.7518),
    "青岛": (36.0671, 120.3826),
    "沈阳": (41.8057, 123.4315),
    "宁波": (29.8683, 121.5440),
    "昆明": (25.0389, 102.7183),
    "大连": (38.9140, 121.6147),
    "厦门": (24.4798, 118.0894),
    "福州": (26.0745, 119.2965),
    "哈尔滨": (45.8038, 126.5350),
    "济南": (36.6512, 117.1201),
    "温州": (28.0001, 120.6722),
    "南宁": (22.8170, 108.3665),
    "长春": (43.8171, 125.3235),
    "泉州": (24.8741, 118.6758),
    "贵阳": (26.6470, 106.6302),
    "南昌": (28.6820, 115.8579),
    "金华": (29.0785, 119.6494),
    "常州": (31.8106, 119.9741),
    "惠州": (23.1115, 114.4160),
    "珠海": (22.2710, 113.5767),
    "中山": (22.5154, 113.3926),
    "台州": (28.6563, 121.4207),
    "兰州": (36.0611, 103.8343),
    "绍兴": (30.0300, 120.5800),
    "海口": (20.0440, 110.1999),
    "无锡": (31.4906, 120.3119),
    "佛山": (23.0218, 113.1219),
    "徐州": (34.2044, 117.2858),
    "合肥": (31.8206, 117.2272),
    "乌鲁木齐": (43.8256, 87.6168),
    "太原": (37.8706, 112.5489),
    "石家庄": (38.0428, 114.5149),
    "呼和浩特": (40.8424, 111.7491),
    "拉萨": (29.6500, 91.1000),
    "西宁": (36.6171, 101.7782),
    "银川": (38.4872, 106.2309),
    "香港": (22.3193, 114.1694),
    "澳门": (22.1987, 113.5439),
    "台北": (25.0330, 121.5654),
}


def _geocode_city(city: str) -> Optional[tuple]:
    """
    城市名 → (lat, lon)。
    先查内置表，查不到时用 Open-Meteo Geocoding API（免费）。
    """
    # 标准化：去掉"市"、"区"后缀
    clean = city.rstrip("市区县")
    if clean in _CITY_GEO:
        return _CITY_GEO[clean]

    # 用 Open-Meteo geocoding 查
    try:
        url = f"https://geocoding-api.open-meteo.com/v1/search?name={urllib.parse.quote(city)}&count=1&language=zh"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=5) as r:
            data = json.loads(r.read().decode("utf-8"))
        results = data.get("results", [])
        if results:
            loc = results[0]
            lat, lon = loc["latitude"], loc["longitude"]
            # 缓存到内置表
            _CITY_GEO[clean] = (lat, lon)
            return (lat, lon)
    except Exception:
        pass

    # 模糊匹配：去掉前缀（如"浙江杭州"）
    for key, val in _CITY_GEO.items():
        if key in city or city in key:
            return val

    return None


# ── 天气条件枚举 ──────────────────────────────────────

class WeatherCondition:
    SUNNY = "sunny"         # 晴
    CLEAR = "clear"         # 晴（夜间）
    CLOUDY = "cloudy"       # 多云
    OVERCAST = "overcast"   # 阴
    LIGHT_RAIN = "light_rain"    # 小雨
    MODERATE_RAIN = "moderate_rain"  # 中雨
    HEAVY_RAIN = "heavy_rain"  # 大雨/暴雨
    THUNDER = "thunder"     # 雷暴
    SNOW = "snow"           # 雪
    FOG = "fog"             # 雾
    HAZE = "haze"           # 雾霾


# ── 天气对心情和场景的影响 ────────────────────────────

WEATHER_EFFECTS = {
    WeatherCondition.SUNNY:           {"mood": +5, "scene_hint": None, "commute_modifier": 0},
    WeatherCondition.CLEAR:           {"mood": +3, "scene_hint": None, "commute_modifier": 0},
    WeatherCondition.CLOUDY:          {"mood": 0,  "scene_hint": None, "commute_modifier": 0},
    WeatherCondition.OVERCAST:        {"mood": -3, "scene_hint": None, "commute_modifier": 0},
    WeatherCondition.LIGHT_RAIN:      {"mood": -2, "scene_hint": None, "commute_modifier": 5},
    WeatherCondition.MODERATE_RAIN:   {"mood": -5, "scene_hint": "HOME_EVENING", "commute_modifier": 10},
    WeatherCondition.HEAVY_RAIN:      {"mood": -10, "scene_hint": "HOME_EVENING", "commute_modifier": 20},
    WeatherCondition.THUNDER:         {"mood": -12, "scene_hint": "HOME_EVENING", "commute_modifier": 30},
    WeatherCondition.SNOW:            {"mood": +3, "scene_hint": None, "commute_modifier": 15},
    WeatherCondition.FOG:             {"mood": -3, "scene_hint": None, "commute_modifier": 10},
    WeatherCondition.HAZE:            {"mood": -8, "scene_hint": "HOME_EVENING", "commute_modifier": 0},
}


# ── WMO 天气代码映射 ──────────────────────────────────
# Open-Meteo 使用 WMO 天气代码
_WMO_CODE_MAP = {
    0: WeatherCondition.CLEAR,       # 晴朗
    1: WeatherCondition.CLEAR,       # 晴朗
    2: WeatherCondition.CLOUDY,      # 多云
    3: WeatherCondition.OVERCAST,    # 阴天
    45: WeatherCondition.FOG,        # 雾
    48: WeatherCondition.FOG,        # 雾凇
    51: WeatherCondition.LIGHT_RAIN, # 小毛毛雨
    53: WeatherCondition.LIGHT_RAIN,
    55: WeatherCondition.LIGHT_RAIN,
    56: WeatherCondition.LIGHT_RAIN, # 冻毛毛雨
    57: WeatherCondition.LIGHT_RAIN,
    61: WeatherCondition.LIGHT_RAIN, # 小雨
    63: WeatherCondition.MODERATE_RAIN, # 中雨
    65: WeatherCondition.HEAVY_RAIN,   # 大雨
    66: WeatherCondition.LIGHT_RAIN,   # 冻雨
    67: WeatherCondition.MODERATE_RAIN,
    71: WeatherCondition.LIGHT_RAIN,   # 小雪
    73: WeatherCondition.SNOW,         # 中雪
    75: WeatherCondition.SNOW,         # 大雪
    77: WeatherCondition.SNOW,         # 雪粒
    80: WeatherCondition.LIGHT_RAIN,   # 阵雨
    81: WeatherCondition.MODERATE_RAIN,
    82: WeatherCondition.HEAVY_RAIN,
    85: WeatherCondition.SNOW,         # 阵雪
    86: WeatherCondition.SNOW,
    95: WeatherCondition.THUNDER,      # 雷暴
    96: WeatherCondition.THUNDER,
    99: WeatherCondition.THUNDER,      # 冰雹雷暴
}


def _wmo_to_condition(code: int) -> str:
    """WMO 天气代码 → 内部 WeatherCondition"""
    return _WMO_CODE_MAP.get(code, WeatherCondition.CLOUDY)


# ── 天气中文描述 ──────────────────────────────────────

WEATHER_LABELS = {
    WeatherCondition.SUNNY: "晴",
    WeatherCondition.CLEAR: "晴",
    WeatherCondition.CLOUDY: "多云",
    WeatherCondition.OVERCAST: "阴天",
    WeatherCondition.LIGHT_RAIN: "小雨",
    WeatherCondition.MODERATE_RAIN: "中雨",
    WeatherCondition.HEAVY_RAIN: "大雨",
    WeatherCondition.THUNDER: "雷暴",
    WeatherCondition.SNOW: "雪",
    WeatherCondition.FOG: "雾",
    WeatherCondition.HAZE: "雾霾",
}

WEATHER_EMOJI = {
    WeatherCondition.SUNNY: "☀️",
    WeatherCondition.CLEAR: "🌙",
    WeatherCondition.CLOUDY: "⛅",
    WeatherCondition.OVERCAST: "☁️",
    WeatherCondition.LIGHT_RAIN: "🌦️",
    WeatherCondition.MODERATE_RAIN: "🌧️",
    WeatherCondition.HEAVY_RAIN: "⛈️",
    WeatherCondition.THUNDER: "🌩️",
    WeatherCondition.SNOW: "🌨️",
    WeatherCondition.FOG: "🌫️",
    WeatherCondition.HAZE: "😷",
}


class WeatherService:
    """
    天气服务：获取 + 缓存 + 效果计算
    使用 Open-Meteo 免费 API（无需 API Key），根据城市名自动定位。
    """

    def __init__(self, city: str = "上海"):
        self._city = city or "上海"
        self._geo = _geocode_city(self._city)
        self._cache = self._load_cache()

    def _load_cache(self) -> dict:
        if _CACHE_FILE.exists():
            try:
                with open(_CACHE_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _save_cache(self):
        _CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(self._cache, f, ensure_ascii=False, indent=2)

    def _is_cache_fresh(self) -> bool:
        """缓存是否在 30 分钟内"""
        if not self._cache.get("updated"):
            return False
        try:
            updated = datetime.fromisoformat(self._cache["updated"])
            return (datetime.now() - updated).total_seconds() < 1800
        except Exception:
            return False

    def fetch_weather(self) -> Optional[dict]:
        """从 Open-Meteo API 获取实时天气"""
        if not self._geo:
            # 尝试重新解析城市名
            self._geo = _geocode_city(self._city)
        if not self._geo:
            return None

        try:
            lat, lon = self._geo
            url = (
                f"https://api.open-meteo.com/v1/forecast?"
                f"latitude={lat}&longitude={lon}"
                f"&current=temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m"
                f"&timezone=auto"
            )
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=8) as r:
                data = json.loads(r.read().decode("utf-8"))

            current = data.get("current", {})
            weather_code = current.get("weather_code", 0)
            temp = current.get("temperature_2m", "")
            humidity = current.get("relative_humidity_2m", "")
            wind_speed = current.get("wind_speed_10m", "")

            condition = _wmo_to_condition(weather_code)

            return {
                "condition": condition,
                "temp": f"{temp:.0f}" if temp != "" else "",
                "humidity": f"{humidity}" if humidity != "" else "",
                "wind": f"{wind_speed:.0f} km/h" if wind_speed != "" else "",
                "label": WEATHER_LABELS.get(condition, "多云"),
                "emoji": WEATHER_EMOJI.get(condition, "⛅"),
                "text": WEATHER_LABELS.get(condition, "多云"),
            }
        except Exception:
            return None

    def get_weather(self) -> dict:
        """
        获取当前天气（优先缓存，回退 API，最终回退默认）。
        返回 {"condition": str, "temp": str, "label": str, "emoji": str, "text": str}
        """
        if self._is_cache_fresh():
            return self._cache

        # 尝试 API
        api_data = self.fetch_weather()
        if api_data:
            condition = api_data["condition"]
            result = {
                "condition": condition,
                "temp": api_data.get("temp", ""),
                "humidity": api_data.get("humidity", ""),
                "wind": api_data.get("wind", ""),
                "label": WEATHER_LABELS.get(condition, "多云"),
                "emoji": WEATHER_EMOJI.get(condition, "⛅"),
                "text": api_data.get("text", ""),
                "updated": datetime.now().isoformat(),
            }
            self._cache = result
            self._save_cache()
            return result

        # 缓存过期但 API 失败 → 保留旧缓存
        if self._cache:
            return self._cache

        # 完全无数据 → 根据月份推断
        return self._fallback_weather()

    def _fallback_weather(self) -> dict:
        """无 API 时根据季节返回合理默认值"""
        month = datetime.now().month
        if month in (3, 4, 5):
            condition = WeatherCondition.CLOUDY
        elif month in (6, 7, 8):
            condition = WeatherCondition.LIGHT_RAIN
        elif month in (9, 10, 11):
            condition = WeatherCondition.CLOUDY
        else:
            condition = WeatherCondition.OVERCAST

        return {
            "condition": condition,
            "temp": "",
            "humidity": "",
            "wind": "",
            "label": WEATHER_LABELS.get(condition, "多云"),
            "emoji": WEATHER_EMOJI.get(condition, "⛅"),
            "text": WEATHER_LABELS.get(condition, "多云"),
            "updated": datetime.now().isoformat(),
        }

    def get_mood_delta(self) -> int:
        """天气对心情的影响值"""
        w = self.get_weather()
        effect = WEATHER_EFFECTS.get(w.get("condition", "cloudy"), {})
        return effect.get("mood", 0)

    def get_scene_hint(self) -> Optional[str]:
        """恶劣天气是否建议留在室内（返回场景枚举或 None）"""
        w = self.get_weather()
        effect = WEATHER_EFFECTS.get(w.get("condition", "cloudy"), {})
        return effect.get("scene_hint")

    def get_commute_delay(self) -> int:
        """天气导致的通勤额外延迟（分钟）"""
        w = self.get_weather()
        effect = WEATHER_EFFECTS.get(w.get("condition", "cloudy"), {})
        return effect.get("commute_modifier", 0)

    def get_description(self) -> str:
        """一句话天气描述（用于日志注入）"""
        w = self.get_weather()
        parts = []
        if w.get("label"):
            parts.append(w["label"])
        if w.get("temp"):
            parts.append(f"{w['temp']}°C")
        return "，".join(parts) if parts else "多云"
