"""
AI 生成器 - 生成人物卡 + NPC卡 + Activity描述 + 事件队列
支持多种工作模式：上班族 / 自由职业 / 学生
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


def _detect_work_style(occupation: str) -> str:
    """根据职业描述推断工作模式"""
    from .character import detect_work_style
    return detect_work_style(occupation).value


def generate_character_card(anchor: dict, agidpa_personality: dict = None) -> dict:
    """
    根据锚点和人格数据生成完整人物卡。
    根据职业类型自动选择不同的生成模板。
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

    work_style = _detect_work_style(occupation)

    if work_style == "freelance":
        prompt = _build_freelance_prompt(name, age, city, occupation, personality, extra_context)
    elif work_style == "student":
        prompt = _build_student_prompt(name, age, city, occupation, personality, extra_context)
    else:
        prompt = _build_office_prompt(name, age, city, occupation, personality, extra_context)

    try:
        response = llm.generate(prompt, max_tokens=2500, temperature=0.8)
        response = response.strip()
        if response.startswith("```"):
            lines = response.split("\n")
            response = "\n".join(lines[1:])
            if response.endswith("```"):
                response = response[:-3]
            response = response.strip()

        card = json.loads(response)
        card["basic"]["name"] = name
        # 确保有 work_style
        if "work_style" not in card.get("basic", {}):
            card["basic"]["work_style"] = work_style
        else:
            work_style = card["basic"]["work_style"]
        # 确保有 work_location_weights
        if work_style == "freelance" and "work_location_weights" not in card.get("basic", {}):
            card["basic"]["work_location_weights"] = {"home": 50, "cafe": 25, "outdoor": 15, "studio": 10}
        # 确保有 life_goals
        if "life_goals" not in card:
            card["life_goals"] = []
        # 确保有 work_start/work_end
        if "work_start" not in card.get("daily_schedule", {}):
            card["daily_schedule"]["work_start"] = card["daily_schedule"].get("arrive_work", "10:00")
        if "work_end" not in card.get("daily_schedule", {}):
            card["daily_schedule"]["work_end"] = card["daily_schedule"].get("leave_work", "18:00")
        # 兼容旧数据：通勤信息
        if work_style in ("freelance", "remote") and "commute" not in card:
            card["commute"] = {"method": "", "line": "", "duration_minutes": 0}
        # ── 自动生成生日：性格→星座→随机日期 ──
        if "birth_date" not in card.get("basic", {}) or not card["basic"].get("birth_date"):
            from .birthday_engine import auto_generate_birthday
            bd_info = auto_generate_birthday(personality, age)
            card["basic"]["birth_date"] = bd_info["birth_date"]
            card["basic"]["zodiac"] = bd_info["zodiac"]
        return card
    except Exception as e:
        print(f"[SimLife] 人物卡生成失败: {e}")
        return None


def _build_office_prompt(name, age, city, occupation, personality, extra_context):
    """上班族生成模板"""
    return f"""为一个名叫"{name}"的虚拟角色生成详细的人物设定卡。

基本信息：
- 年龄：{age}
- 城市：{city}
- 职业：{occupation}（上班族，固定地点工作）
- 性格关键词：{personality}{extra_context}

请生成以下信息，返回JSON格式：
{{
  "basic": {{
    "age": {age},
    "city": "{city}",
    "district": "一个{city}真实的区名",
    "occupation": "{occupation}",
    "work_style": "office",
    "company_name": "一个合理的公司名",
    "company_area": "一个合理的商务区名",
    "work_location_weights": {{"home": 0, "cafe": 0, "outdoor": 0, "studio": 0}}
  }},
  "home": {{
    "type": "合理的户型",
    "description": "30字以内的住处描述，有生活细节",
    "has_roommate": false,
    "pets": "如果没有宠物写空字符串"
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
    "sleep": "23:30",
    "work_start": "09:30",
    "work_end": "18:30"
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
    "weekend_hangout": "一个真实的商圈/街道名",
    "frequent_outdoor_spots": ""
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
  }},
  "life_goals": [
    {{"category": "事业", "description": "一个职业相关的短期目标", "target_date": "", "progress": 0, "priority": 1}},
    {{"category": "生活", "description": "一个生活相关的目标（如考驾照、学游泳、练肌肉、画油画、种花、学做饭等）", "target_date": "", "progress": 0, "priority": 2}},
    {{"category": "学习", "description": "一个学习成长相关的目标", "target_date": "", "progress": 0, "priority": 3}}
  ],
  "wardrobe": {{
    "home": "在家穿的舒适衣物（中文描述，10字以内）",
    "work": "上班穿的正式或商务休闲装（中文描述）",
    "casual": "日常出门穿的休闲装（中文描述）",
    "outdoor": "户外活动穿的穿搭（中文描述）",
    "formal": "正式场合穿的着装（中文描述）",
    "sport": "运动健身穿的服装（中文描述）",
    "sleep": "睡觉穿的睡衣（中文描述）",
    "home_en": "English description of home outfit for image generation",
    "work_en": "English description of work outfit",
    "casual_en": "English description of casual outfit",
    "outdoor_en": "English description of outdoor outfit",
    "formal_en": "English description of formal outfit",
    "sport_en": "English description of sport outfit",
    "sleep_en": "English description of sleepwear"
  }}
}}

只返回JSON，不要其他内容。所有地点必须是{city}真实存在的。人生目标要具体有趣，不要太空泛。wardrobe 要符合角色的性别、年龄和风格偏好——如果角色是男性，穿着应偏向男性化；如果性格偏运动风，户外和运动装应更具体。"""


def _build_freelance_prompt(name, age, city, occupation, personality, extra_context):
    """自由职业生成模板"""
    return f"""为一个名叫"{name}"的虚拟角色生成详细的人物设定卡。

基本信息：
- 年龄：{age}
- 城市：{city}
- 职业：{occupation}（自由职业/独立工作者，时间地点灵活）
- 性格关键词：{personality}{extra_context}

重要：这是一个自由职业者，没有固定公司，不需要每天通勤。请根据具体职业生成合理的生活节奏。

请生成以下信息，返回JSON格式：
{{
  "basic": {{
    "age": {age},
    "city": "{city}",
    "district": "一个{city}真实的区名",
    "occupation": "{occupation}",
    "work_style": "freelance",
    "company_name": "",
    "company_area": "",
    "work_location_weights": {{
      "home": "在家工作的频率权重（整数0-100）",
      "cafe": "咖啡馆工作的频率权重（整数0-100）",
      "outdoor": "户外工作（拍摄/采访等）的频率权重（整数0-100）",
      "studio": "工作室的频率权重（整数0-100）"
    }}
  }},
  "home": {{
    "type": "合理的户型（自由职业者可能有一间书房或工作区）",
    "description": "30字以内的住处描述，要体现自由职业者的生活气息",
    "has_roommate": false,
    "pets": "如果有宠物会更有生活感，没有写空字符串"
  }},
  "family": {{
    "parents_location": "一个合理的城市",
    "contact_frequency": "合理的联系频率",
    "notes": "家人对这个职业的态度，一个小细节"
  }},
  "daily_schedule": {{
    "wake_up": "合理的起床时间（自由职业者通常比上班族晚）",
    "leave_home": "10:00",
    "arrive_work": "10:30",
    "lunch_break_start": "12:30",
    "lunch_break_end": "14:00",
    "leave_work": "19:00",
    "arrive_home": "19:00",
    "sleep": "合理的睡觉时间（可能比上班族晚）",
    "work_start": "实际开始工作的时间",
    "work_end": "实际结束工作的时间"
  }},
  "commute": {{
    "method": "",
    "line": "",
    "duration_minutes": 0
  }},
  "locations": {{
    "home_address_hint": "一个{city}真实的路名附近",
    "company_landmark": "",
    "favorite_cafe": "常去办公的咖啡馆名",
    "supermarket": "一个真实的超市名",
    "park": "一个真实的公园名（常去放松/找灵感的地方）",
    "weekend_hangout": "一个真实的商圈/街道名",
    "frequent_outdoor_spots": "常去的工作相关户外地点（如拍摄地、采访地点等）"
  }},
  "habits": {{
    "morning_drink": "早上的饮品",
    "lunch_style": "午餐习惯（可能自己做、点外卖或去附近小店）",
    "evening_routine": "晚上的放松方式",
    "weekend_morning": "周末早上的习惯"
  }},
  "current_context": "最近在忙什么项目/创作，30字以内",
  "pixel_appearance": {{
    "hair_color": "#十六进制颜色",
    "hair_style": "发型",
    "default_outfit_color": "#十六进制颜色"
  }},
  "life_goals": [
    {{"category": "事业", "description": "一个与{occupation}直接相关的目标（如粉丝量、接单量、作品数等）", "target_date": "", "progress": 0, "priority": 1}},
    {{"category": "生活", "description": "一个个人生活目标（从以下选一个或自创：考驾照、学游泳、练肌肉、画油画、种花、学做饭、养猫、旅行计划、学吉他、学跳舞、考个证书等）", "target_date": "", "progress": 0, "priority": 2}},
    {{"category": "健康", "description": "一个健康相关目标（如跑步、健身、早睡、少吃外卖等）", "target_date": "", "progress": 0, "priority": 3}},
    {{"category": "理财", "description": "一个理财目标（如攒钱买设备、月收入达到多少等）", "target_date": "", "progress": 0, "priority": 4}}
  ],
  "wardrobe": {{
    "home": "在家穿的舒适衣物（自由职业者可能一整天穿家居服，中文描述）",
    "work": "见客户或正式工作时的着装（自由职业者不一定穿正装，符合职业风格）",
    "casual": "出门闲逛、去咖啡馆的穿搭",
    "outdoor": "外出拍摄/采访/运动的穿搭（根据具体职业调整）",
    "formal": "正式场合或约会时的着装",
    "sport": "运动健身的服装",
    "sleep": "睡衣",
    "home_en": "English description for image generation",
    "work_en": "English work outfit description",
    "casual_en": "English casual outfit",
    "outdoor_en": "English outdoor outfit",
    "formal_en": "English formal outfit",
    "sport_en": "English sport outfit",
    "sleep_en": "English sleepwear"
  }}
}}

只返回JSON，不要其他内容。所有地点必须是{city}真实存在的。时刻表要符合自由职业者的真实节奏，不要照搬上班族。人生目标要具体有趣、贴合{occupation}这个职业特点。wardrobe 要符合角色的性别、年龄和职业风格。"""


def _build_student_prompt(name, age, city, occupation, personality, extra_context):
    """学生生成模板"""
    return f"""为一个名叫"{name}"的虚拟角色生成详细的人物设定卡。

基本信息：
- 年龄：{age}
- 城市：{city}
- 职业：{occupation}（学生）
- 性格关键词：{personality}{extra_context}

请生成以下信息，返回JSON格式：
{{
  "basic": {{
    "age": {age},
    "city": "{city}",
    "district": "一个{city}真实的区名（大学城附近）",
    "occupation": "{occupation}",
    "work_style": "student",
    "company_name": "所在学校名",
    "company_area": "学校所在区域",
    "work_location_weights": {{"home": 40, "cafe": 25, "outdoor": 5, "studio": 0}}
  }},
  "home": {{
    "type": "宿舍/出租屋",
    "description": "30字以内的住处描述",
    "has_roommate": true,
    "pets": ""
  }},
  "family": {{
    "parents_location": "一个合理的城市",
    "contact_frequency": "合理的联系频率",
    "notes": "一个家庭小细节"
  }},
  "daily_schedule": {{
    "wake_up": "合理的起床时间",
    "leave_home": "上课出发时间",
    "arrive_work": "到教室/图书馆时间",
    "lunch_break_start": "12:00",
    "lunch_break_end": "13:00",
    "leave_work": "下课时间",
    "arrive_home": "回宿舍/家时间",
    "sleep": "合理的睡觉时间",
    "work_start": "开始自习时间",
    "work_end": "结束自习时间"
  }},
  "commute": {{
    "method": "步行/骑车/地铁",
    "line": "具体线路（如有）",
    "duration_minutes": 15
  }},
  "locations": {{
    "home_address_hint": "一个{city}真实的路名附近",
    "company_landmark": "学校名",
    "favorite_cafe": "常去的咖啡馆名",
    "supermarket": "一个真实的超市名",
    "park": "一个真实的公园名",
    "weekend_hangout": "一个真实的商圈/街道名",
    "frequent_outdoor_spots": ""
  }},
  "habits": {{
    "morning_drink": "早上的饮品",
    "lunch_style": "食堂/外卖/校外小店",
    "evening_routine": "晚上的放松方式",
    "weekend_morning": "周末早上"
  }},
  "current_context": "最近在忙什么（如考试、论文、社团等），30字以内",
  "pixel_appearance": {{
    "hair_color": "#十六进制颜色",
    "hair_style": "发型",
    "default_outfit_color": "#十六进制颜色"
  }},
  "life_goals": [
    {{"category": "学业", "description": "一个学业目标（如考研、考级、GPA等）", "target_date": "", "progress": 0, "priority": 1}},
    {{"category": "生活", "description": "一个生活目标（如学游泳、考驾照、旅行、学乐器等）", "target_date": "", "progress": 0, "priority": 2}},
    {{"category": "社交", "description": "一个社交目标（如参加社团、脱单等）", "target_date": "", "progress": 0, "priority": 3}}
  ],
  "wardrobe": {{
    "home": "在宿舍/出租屋穿的舒适衣物（中文描述）",
    "work": "上课穿的日常服装（学生不需要正装，符合学生风格）",
    "casual": "周末出门穿的休闲装",
    "outdoor": "户外运动或活动的穿搭",
    "formal": "参加活动/面试/正式场合的着装",
    "sport": "运动健身的服装",
    "sleep": "睡衣",
    "home_en": "English description for image generation",
    "work_en": "English daily outfit for class",
    "casual_en": "English casual outfit",
    "outdoor_en": "English outdoor outfit",
    "formal_en": "English formal outfit",
    "sport_en": "English sport outfit",
    "sleep_en": "English sleepwear"
  }}
}}

只返回JSON，不要其他内容。所有地点必须是{city}真实存在的。wardrobe 要符合学生的性别和风格，不要生成过于成熟的职业装。"""


def generate_npc_cards(character_card: dict) -> list:
    """根据主角人物卡生成 NPC 网络（根据工作模式调整）"""
    llm = get_llm_client()

    name = character_card.get("basic", {}).get("name", "")
    age = character_card.get("basic", {}).get("age", 24)
    occupation = character_card.get("basic", {}).get("occupation", "")
    city = character_card.get("basic", {}).get("city", "上海")
    district = character_card.get("basic", {}).get("district", "")
    work_style = character_card.get("basic", {}).get("work_style", "office")

    if work_style == "freelance":
        prompt = f"""为主角"{name}"生成一个丰富真实的人际圈。

主角信息：{age}岁，{occupation}（自由职业者），住在{city}{district}。
自由职业者的人际圈不同于上班族，通常有客户、合作者、同行朋友等。

请生成以下NPC，返回JSON数组（必须包含所有角色）：
[
  {{
    "id": "npc_bestfriend",
    "relation": "好友",
    "name": "一个{city}常见名字",
    "age": 25,
    "occupation": "合理的职业（可以是其他自由职业者）",
    "personality_word": "性格词（如开朗、细腻等）",
    "contact_frequency": "见面频率",
    "appear_scenes": ["CAFE", "STREET_WANDERING", "PARK", "FRIEND_HANGOUT", "CAFE_WORKING"],
    "event_pool": ["invite_hangout", "share_good_news"],
    "pixel_variant": "npc_f_01"
  }},
  {{
    "id": "npc_client",
    "relation": "客户",
    "name": "一个常见名字",
    "age": 30,
    "occupation": "合理的行业",
    "personality_word": "性格词",
    "contact_frequency": "项目期间频繁",
    "appear_scenes": ["CAFE_WORKING", "CAFE"],
    "event_pool": ["new_project", "payment_delay"],
    "pixel_variant": "npc_f_02"
  }},
  {{
    "id": "npc_collaborator",
    "relation": "合作者",
    "name": "一个常见名字",
    "age": 27,
    "occupation": "相关行业的自由职业者",
    "personality_word": "性格词",
    "contact_frequency": "偶尔合作",
    "appear_scenes": ["CAFE_WORKING", "CAFE", "HOME_WORKING"],
    "event_pool": ["collaboration_opportunity", "share_resource"],
    "pixel_variant": "npc_m_01"
  }},
  {{
    "id": "npc_mom",
    "relation": "妈妈",
    "name": "不显示",
    "age": {age + random.randint(25, 32)},
    "occupation": "",
    "personality_word": "关心",
    "contact_frequency": "每周视频",
    "appear_scenes": [],
    "event_pool": ["video_call", "send_recipe"],
    "pixel_variant": null
  }},
  {{
    "id": "npc_dad",
    "relation": "爸爸",
    "name": "不显示",
    "age": {age + random.randint(27, 34)},
    "occupation": "",
    "personality_word": "沉稳内敛",
    "contact_frequency": "偶尔视频",
    "appear_scenes": [],
    "event_pool": ["video_call", "send_money"],
    "pixel_variant": null
  }},
  {{
    "id": "npc_roommate",
    "relation": "大学室友",
    "name": "一个{city}常见名字",
    "age": {age},
    "occupation": "合理职业",
    "personality_word": "活泼古怪",
    "contact_frequency": "每月见面",
    "appear_scenes": ["CAFE", "FRIEND_HANGOUT", "STREET_WANDERING"],
    "event_pool": ["invite_hangout", "share_good_news", "catch_up"],
    "pixel_variant": "npc_f_03"
  }},
  {{
    "id": "npc_neighbor",
    "relation": "邻居",
    "name": "一个常见名字",
    "age": {age + random.randint(0, 3)},
    "occupation": "合理的职业",
    "personality_word": "佛系随和",
    "contact_frequency": "偶尔碰面",
    "appear_scenes": ["HOME_MORNING", "HOME_EVENING", "STREET_WANDERING"],
    "event_pool": ["borrow_thing", "share_good_news"],
    "pixel_variant": "npc_f_04"
  }}
]

只返回JSON数组，不要其他内容。人名使用{city}常见名字风格。age 可以适当微调（±2岁）。"""
    else:
        prompt = f"""为主角"{name}"生成一个丰富真实的人际圈。

主角信息：{age}岁，{occupation}，住在{city}{district}。

请生成以下NPC，返回JSON数组（必须包含所有角色）：
[
  {{
    "id": "npc_bestfriend",
    "relation": "好友",
    "name": "一个{city}常见名字",
    "age": {age + random.randint(1, 5)},
    "occupation": "合理的职业",
    "personality_word": "性格词（如开朗、细腻等）",
    "contact_frequency": "见面频率",
    "appear_scenes": ["CAFE", "STREET_WANDERING", "PARK", "FRIEND_HANGOUT"],
    "event_pool": ["invite_hangout", "share_good_news"],
    "pixel_variant": "npc_f_01"
  }},
  {{
    "id": "npc_colleague_a",
    "relation": "同事",
    "name": "一个常见名字",
    "age": {age + random.randint(2, 6)},
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
    "age": {age + random.randint(3, 8)},
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
    "age": {age + random.randint(25, 32)},
    "occupation": "",
    "personality_word": "关心",
    "contact_frequency": "每周视频",
    "appear_scenes": [],
    "event_pool": ["video_call", "send_recipe"],
    "pixel_variant": null
  }},
  {{
    "id": "npc_dad",
    "relation": "爸爸",
    "name": "不显示",
    "age": {age + random.randint(27, 34)},
    "occupation": "",
    "personality_word": "沉稳内敛",
    "contact_frequency": "偶尔视频",
    "appear_scenes": [],
    "event_pool": ["video_call", "send_money"],
    "pixel_variant": null
  }},
  {{
    "id": "npc_roommate",
    "relation": "大学室友",
    "name": "一个{city}常见名字",
    "age": {age},
    "occupation": "合理职业",
    "personality_word": "活泼古怪",
    "contact_frequency": "每月见面",
    "appear_scenes": ["CAFE", "FRIEND_HANGOUT", "STREET_WANDERING"],
    "event_pool": ["invite_hangout", "share_good_news", "catch_up"],
    "pixel_variant": "npc_f_03"
  }},
  {{
    "id": "npc_boss",
    "relation": "直属上司",
    "name": "一个常见名字",
    "age": {age + random.randint(8, 14)},
    "occupation": "合理的职位",
    "personality_word": "干练严厉",
    "contact_frequency": "每天见面",
    "appear_scenes": ["OFFICE_WORKING", "OFFICE_MEETING"],
    "event_pool": ["extra_task_from_boss", "praise_from_boss"],
    "pixel_variant": "npc_m_02"
  }},
  {{
    "id": "npc_neighbor",
    "relation": "邻居",
    "name": "一个常见名字",
    "age": {age + random.randint(0, 3)},
    "occupation": "合理的职业",
    "personality_word": "佛系随和",
    "contact_frequency": "偶尔碰面",
    "appear_scenes": ["HOME_MORNING", "HOME_EVENING", "STREET_WANDERING"],
    "event_pool": ["borrow_thing", "share_good_news"],
    "pixel_variant": "npc_f_04"
  }}
]

只返回JSON数组，不要其他内容。人名使用{city}常见名字风格。age 可以适当微调（±2岁）。"""

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
        # ── 自动为每个 NPC 补充生日 ──
        from .birthday_engine import auto_generate_birthday
        for npc in npcs:
            if not npc.get("birth_date"):
                personality = npc.get("personality_word", "")
                npc_age = npc.get("age", age + 2)
                bd_info = auto_generate_birthday(personality, npc_age)
                npc["birth_date"] = bd_info["birth_date"]
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
    occupation = character_card.get("basic", {}).get("occupation", "")

    if mood > 80:
        tone = "语气轻快，有小惊喜细节"
    elif mood >= 60:
        tone = "正常语气，平淡但有质感"
    elif mood >= 40:
        tone = "语气带轻微疲惫感"
    else:
        tone = "语气低落，但不夸张"

    prompt = f"""角色名是"{name}"，职业是{occupation}，现在{weekday_names[now.weekday()]} {now.strftime('%H:%M')}。
她/他刚进入"{scene_label}"状态。
今天发生过的事：{today_events_summary or '暂无'}。
{tone}。
用第三人称写一句话描述这个瞬间，口语化，有细节，不超过30字，不要用感叹号。
只返回描述文字，不要引号或其他内容。"""

    try:
        response = llm.generate(prompt, max_tokens=100, temperature=0.9)
        return response.strip().strip('"').strip('"').strip("'").strip()
    except Exception:
        defaults = {
            "HOME_MORNING": "洗漱完在厨房煮咖啡",
            "COMMUTE_TO_WORK": "在去公司的路上",
            "OFFICE_WORKING": "在工位上做事",
            "OFFICE_MEETING": "在会议室里开会",
            "OFFICE_LUNCH": "出来觅食",
            "COMMUTE_TO_HOME": "下班回家的路上",
            "HOME_EVENING": "在家放松",
            "CAFE": "在咖啡馆坐了一会儿",
            "PARK": "在公园散步",
            "HOME_SLEEPING": "睡着了",
            "HOME_WEEKEND_LAZY": "赖在床上不想起来",
            "HOME_WORKING": "在家对着电脑做事",
            "CAFE_WORKING": "在咖啡馆打开了笔记本",
            "OUTDOOR_WORKING": "在外面忙工作的事",
            "STUDIO_WORKING": "在工作室里忙碌",
            "OVERTIME": "还在加班",
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
    occupation = character_card.get("basic", {}).get("occupation", "")
    work_style = character_card.get("basic", {}).get("work_style", "office")
    recent = "、".join([e.get("label", "") for e in recent_events[-5:]]) if recent_events else "暂无"

    style_hint = ""
    if work_style == "freelance":
        style_hint = "她是自由职业者，事件可能涉及找灵感、客户沟通、作品创作、自我提升等。"
    elif work_style == "student":
        style_hint = "她是学生，事件可能涉及考试、社团、作业、同学社交等。"
    else:
        style_hint = "她是上班族，事件可能涉及工作项目、同事关系、加班、通勤等。"

    prompt = f"""角色"{name}"，{occupation}。最近发生过：{recent}。
{style_hint}
帮她/他生成接下来{days}天可能发生的生活小事，
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
