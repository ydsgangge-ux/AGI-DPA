"""
AI 生成器 - 生成人物卡 + NPC卡 + Activity描述 + 事件队列
"""
import json
import sys
from pathlib import Path

# 复用主项目的 LLM 客户端
_PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from engine.llm_client import create_client


def get_llm_client(config: dict = None):
    """获取 LLM 客户端实例（从 SimLife 配置或主项目配置）"""
    if config is None:
        config_path = Path(__file__).parent.parent / "data" / "simlife_config.json"
        if config_path.exists():
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
        else:
            config = {}

    # 优先从主项目配置读取（与 desktop/config.py 保持一致）
    import os
    if sys.platform == "win32":
        _cfg_dir = Path(os.environ.get("APPDATA", str(Path.home()))) / "AGI-Desktop"
    else:
        _cfg_dir = Path.home() / ".agi-desktop"
    main_config_path = _cfg_dir / "config.json"
    main_cfg = {}
    if main_config_path.exists():
        with open(main_config_path, "r", encoding="utf-8") as f:
            main_cfg = json.load(f)

    provider = config.get("llm_provider", "") or main_cfg.get("api_provider", "deepseek")
    api_key = config.get("llm_api_key", "") or main_cfg.get("api_key", "")
    model = config.get("llm_model", None) or main_cfg.get("llm_model", None)

    return create_client(api_key=api_key, provider=provider, model=model)


def generate_character_card(anchor: dict, agidpa_personality: dict = None) -> dict:
    """
    根据锚点和人格数据生成完整人物卡。
    返回 CharacterCard dict（不含 basic.name，需后续填充）。
    """
    llm = get_llm_client()

    name = anchor.get("character_name", "小AI")
    city = anchor.get("city", "上海")
    occupation = anchor.get("occupation_hint", "UI设计师")
    age = anchor.get("age", 24)
    personality = anchor.get("personality_word", "温柔")

    extra_context = ""
    if agidpa_personality:
        traits = agidpa_personality.get("personality_traits", [])
        style = agidpa_personality.get("speaking_style", "")
        bg = agidpa_personality.get("background_story", "")
        if traits:
            extra_context += f"\n性格标签：{', '.join(traits)}"
        if style:
            extra_context += f"\n说话风格：{style}"
        if bg:
            extra_context += f"\n背景故事：{bg[:100]}"

    prompt = f"""为一个名叫"{name}"的虚拟角色生成详细的人物设定卡。

基本信息：
- 年龄：{age}
- 城市：{city}
- 职业：{occupation}
- 性格关键词：{personality}{extra_context}

请生成以下信息，返回JSON格式：
{{
  "basic": {{
    "age": {age},
    "city": "{city}",
    "district": "一个{city}真实的区名",
    "occupation": "{occupation}",
    "company_name": "一个合理的公司名",
    "company_area": "一个合理的商务区名"
  }},
  "home": {{
    "type": "合理的户型",
    "description": "30字以内的住处描述，有生活细节",
    "has_roommate": false,
    "pets": "如果没有宠物写空字符串，有的话写宠物描述"
  }},
  "family": {{
    "parents_location": "一个合理的城市",
    "contact_frequency": "合理的联系频率",
    "notes": "一个家庭小细节"
  }},
  "daily_schedule": {{
    "wake_up": "07:30",
    "leave_home": "08:45",
    "arrive_work": "09:30",
    "lunch_break_start": "12:00",
    "lunch_break_end": "13:00",
    "leave_work": "18:30",
    "arrive_home": "19:15",
    "sleep": "23:30"
  }},
  "commute": {{
    "method": "地铁/公交/骑车",
    "line": "具体线路",
    "duration_minutes": 30
  }},
  "locations": {{
    "home_address_hint": "一个{city}真实的路名附近",
    "company_landmark": "一个{city}真实的地标",
    "favorite_cafe": "一个真实的咖啡馆名",
    "supermarket": "一个真实的超市名",
    "park": "一个真实的公园名",
    "weekend_hangout": "一个真实的商圈/街道名"
  }},
  "habits": {{
    "morning_drink": "早上的饮品",
    "lunch_style": "午餐习惯",
    "evening_routine": "晚上做什么",
    "weekend_morning": "周末早上"
  }},
  "current_context": "最近在忙什么，30字以内",
  "pixel_appearance": {{
    "hair_color": "#十六进制颜色",
    "hair_style": "发型",
    "default_outfit_color": "#十六进制颜色"
  }}
}}

只返回JSON，不要其他内容。所有地点必须是{city}真实存在的。"""

    try:
        response = llm.generate(prompt, max_tokens=2000, temperature=0.8)
        # 清理 markdown 代码块
        response = response.strip()
        if response.startswith("```"):
            lines = response.split("\n")
            response = "\n".join(lines[1:])
            if response.endswith("```"):
                response = response[:-3]
            response = response.strip()

        card = json.loads(response)
        card["basic"]["name"] = name
        return card
    except Exception as e:
        print(f"[SimLife] 人物卡生成失败: {e}")
        return None


def generate_npc_cards(character_card: dict) -> list:
    """根据主角人物卡生成 NPC 网络"""
    llm = get_llm_client()

    name = character_card.get("basic", {}).get("name", "")
    age = character_card.get("basic", {}).get("age", 24)
    occupation = character_card.get("basic", {}).get("occupation", "")
    city = character_card.get("basic", {}).get("city", "上海")
    district = character_card.get("basic", {}).get("district", "")
    personality = "见人格设定"

    prompt = f"""为主角"{name}"生成一个真实的人际圈。

主角信息：{age}岁，{occupation}，住在{city}{district}。

请生成以下NPC，返回JSON数组：
[
  {{
    "id": "npc_bestfriend",
    "relation": "闺蜜",
    "name": "一个{city}常见名字",
    "age": 25,
    "occupation": "合理的职业",
    "personality_word": "性格词",
    "contact_frequency": "见面频率",
    "appear_scenes": ["CAFE", "STREET_WANDERING", "PARK", "FRIEND_HANGOUT"],
    "event_pool": ["invite_hangout", "share_good_news"],
    "pixel_variant": "npc_f_01"
  }},
  {{
    "id": "npc_colleague_a",
    "relation": "同事",
    "name": "一个常见名字",
    "age": 26,
    "occupation": "同公司",
    "personality_word": "性格词",
    "contact_frequency": "每天见面",
    "appear_scenes": ["OFFICE_WORKING", "OFFICE_LUNCH"],
    "event_pool": ["lunch_together", "complain_about_work"],
    "pixel_variant": "npc_f_02"
  }},
  {{
    "id": "npc_colleague_b",
    "relation": "同事",
    "name": "一个常见名字",
    "age": 28,
    "occupation": "同公司",
    "personality_word": "性格词",
    "contact_frequency": "每天见面",
    "appear_scenes": ["OFFICE_WORKING"],
    "event_pool": ["extra_task_from_boss"],
    "pixel_variant": "npc_m_01"
  }},
  {{
    "id": "npc_mom",
    "relation": "妈妈",
    "name": "不显示",
    "age": 52,
    "occupation": "",
    "personality_word": "关心",
    "contact_frequency": "每周视频",
    "appear_scenes": [],
    "event_pool": ["video_call", "send_recipe"],
    "pixel_variant": null
  }}
]

只返回JSON数组，不要其他内容。人名使用{city}常见名字风格。"""

    try:
        response = llm.generate(prompt, max_tokens=1500, temperature=0.8)
        response = response.strip()
        if response.startswith("```"):
            lines = response.split("\n")
            response = "\n".join(lines[1:])
            if response.endswith("```"):
                response = response[:-3]
            response = response.strip()
        npcs = json.loads(response)
        return npcs
    except Exception as e:
        print(f"[SimLife] NPC生成失败: {e}")
        return None


def generate_activity_description(
    character_card: dict,
    scene: str,
    scene_label: str,
    today_events_summary: str = "",
    mood: int = 70,
) -> str:
    """生成一条口语化的活动描述"""
    llm = get_llm_client()

    from datetime import datetime
    now = datetime.now()
    weekday_names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]

    name = character_card.get("basic", {}).get("name", "")
    personality = character_card.get("habits", {}).get("evening_routine", "普通")

    # 语气控制
    if mood > 80:
        tone = "语气轻快，有小惊喜细节"
    elif mood >= 60:
        tone = "正常语气，平淡但有质感"
    elif mood >= 40:
        tone = "语气带轻微疲惫感"
    else:
        tone = "语气低落，但不夸张"

    prompt = f"""角色名是"{name}"，现在{weekday_names[now.weekday()]} {now.strftime('%H:%M')}。
她/他刚进入"{scene_label}"状态。
今天发生过的事：{today_events_summary or '暂无'}。
{tone}。
用第三人称写一句话描述这个瞬间，口语化，有细节，不超过30字，不要用感叹号。
只返回描述文字，不要引号或其他内容。"""

    try:
        response = llm.generate(prompt, max_tokens=100, temperature=0.9)
        return response.strip().strip('"').strip('"').strip("'").strip()
    except Exception:
        # 降级：返回场景的默认描述
        defaults = {
            "HOME_MORNING": "洗漱完在厨房煮咖啡",
            "COMMUTE_TO_WORK": "在去公司的路上",
            "OFFICE_WORKING": "在工位上做事",
            "OFFICE_LUNCH": "出来觅食",
            "COMMUTE_TO_HOME": "下班回家的路上",
            "HOME_EVENING": "在家放松",
            "CAFE": "在咖啡馆坐了一会儿",
            "PARK": "在公园散步",
            "HOME_SLEEPING": "睡着了",
            "HOME_WEEKEND_LAZY": "赖在床上不想起来",
        }
        return defaults.get(scene, "在忙自己的事")


def generate_future_events(
    character_card: dict,
    recent_events: list,
    days: int = 3,
) -> list:
    """生成未来N天的随机事件队列"""
    llm = get_llm_client()

    name = character_card.get("basic", {}).get("name", "")
    personality = character_card.get("habits", {}).get("evening_routine", "普通")
    recent = "、".join([e.get("label", "") for e in recent_events[-5:]]) if recent_events else "暂无"

    prompt = f"""角色"{name}"，最近发生过：{recent}。
帮她/他生成接下来{days}天可能发生的生活小事，
从以下类型中选择：工作/社交/生活意外/个人情绪。
每天0-2条，带发生时间段（如"19:00-20:00"）和心情影响值（-30到+30）。
返回JSON数组格式：
[
  {{"event_id": "自定义英文id", "label": "事件描述", "scheduled_date": "YYYY-MM-DD", "scheduled_time_range": "HH:MM-HH:MM", "mood_delta": 10, "source": "llm_generated"}}
]
从明天开始。只返回JSON数组。"""

    try:
        from datetime import datetime, timedelta
        response = llm.generate(prompt, max_tokens=1000, temperature=0.8)
        response = response.strip()
        if response.startswith("```"):
            lines = response.split("\n")
            response = "\n".join(lines[1:])
            if response.endswith("```"):
                response = response[:-3]
            response = response.strip()
        events = json.loads(response)

        # 确保日期从明天开始
        tomorrow = (datetime.now() + timedelta(days=1)).date()
        for i, evt in enumerate(events):
            date_str = evt.get("scheduled_date", "")
            try:
                d = __import__("datetime").date.fromisoformat(date_str)
            except Exception:
                d = tomorrow + timedelta(days=i // 2)

        return events
    except Exception as e:
        print(f"[SimLife] 未来事件生成失败: {e}")
        return []
