"""
人物卡数据模型 (Pydantic)
支持多种工作模式：上班族 / 自由职业 / 学生 等
"""
from pydantic import BaseModel, Field
from typing import Optional, List
from enum import Enum


class SceneEnum(str, Enum):
    # ── 居家 ──
    HOME_SLEEPING = "HOME_SLEEPING"
    HOME_MORNING = "HOME_MORNING"
    HOME_EVENING = "HOME_EVENING"
    HOME_WEEKEND_LAZY = "HOME_WEEKEND_LAZY"
    HOME_WORKING = "HOME_WORKING"          # 在家工作（自由职业）
    # ── 通勤 ──
    COMMUTE_TO_WORK = "COMMUTE_TO_WORK"
    COMMUTE_TO_HOME = "COMMUTE_TO_HOME"
    # ── 办公室 ──
    OFFICE_WORKING = "OFFICE_WORKING"
    OFFICE_MEETING = "OFFICE_MEETING"
    OFFICE_LUNCH = "OFFICE_LUNCH"
    OVERTIME = "OVERTIME"
    # ── 自由职业工作场景 ──
    CAFE_WORKING = "CAFE_WORKING"          # 咖啡馆办公
    OUTDOOR_WORKING = "OUTDOOR_WORKING"    # 户外工作（拍摄/采访）
    STUDIO_WORKING = "STUDIO_WORKING"      # 工作室
    # ── 休闲 ──
    CAFE = "CAFE"
    PARK = "PARK"
    SUPERMARKET = "SUPERMARKET"
    STREET_WANDERING = "STREET_WANDERING"
    FRIEND_HANGOUT = "FRIEND_HANGOUT"


SCENE_LABELS = {
    # 居家
    SceneEnum.HOME_SLEEPING: "睡觉",
    SceneEnum.HOME_MORNING: "晨间准备",
    SceneEnum.HOME_EVENING: "晚间放松",
    SceneEnum.HOME_WEEKEND_LAZY: "周末赖床",
    SceneEnum.HOME_WORKING: "在家工作",
    # 通勤
    SceneEnum.COMMUTE_TO_WORK: "去公司",
    SceneEnum.COMMUTE_TO_HOME: "回家",
    # 办公室
    SceneEnum.OFFICE_WORKING: "工作中",
    SceneEnum.OFFICE_MEETING: "开会",
    SceneEnum.OFFICE_LUNCH: "午休觅食",
    SceneEnum.OVERTIME: "加班",
    # 自由职业
    SceneEnum.CAFE_WORKING: "咖啡馆办公",
    SceneEnum.OUTDOOR_WORKING: "外出工作",
    SceneEnum.STUDIO_WORKING: "工作室",
    # 休闲
    SceneEnum.CAFE: "咖啡馆",
    SceneEnum.PARK: "公园",
    SceneEnum.SUPERMARKET: "超市",
    SceneEnum.STREET_WANDERING: "街头闲逛",
    SceneEnum.FRIEND_HANGOUT: "和朋友在外",
}

# 工作场景集合（用于事件过滤等）
WORK_SCENES = {
    SceneEnum.OFFICE_WORKING, SceneEnum.OFFICE_MEETING, SceneEnum.OVERTIME,
    SceneEnum.HOME_WORKING, SceneEnum.CAFE_WORKING,
    SceneEnum.OUTDOOR_WORKING, SceneEnum.STUDIO_WORKING,
}


class WorkStyle(str, Enum):
    OFFICE = "office"           # 传统上班族，固定地点
    FREELANCE = "freelance"     # 自由职业，地点灵活
    REMOTE = "remote"           # 远程办公（有公司但在家）
    STUDENT = "student"         # 学生


# 工作日工作场景映射（根据 work_style 决定"上班时"在哪个场景）
WORK_STYLE_SCENES = {
    WorkStyle.OFFICE: [SceneEnum.OFFICE_WORKING, SceneEnum.OFFICE_MEETING],
    WorkStyle.FREELANCE: [SceneEnum.HOME_WORKING, SceneEnum.CAFE_WORKING,
                          SceneEnum.OUTDOOR_WORKING, SceneEnum.STUDIO_WORKING],
    WorkStyle.REMOTE: [SceneEnum.HOME_WORKING, SceneEnum.CAFE],
    WorkStyle.STUDENT: [SceneEnum.OFFICE_WORKING, SceneEnum.CAFE, SceneEnum.HOME_WORKING],
}


def detect_work_style(occupation: str) -> WorkStyle:
    """根据职业描述自动推断工作模式"""
    if not occupation:
        return WorkStyle.OFFICE
    occ = occupation.lower()
    freelance_keywords = [
        "自由", "freelance", "独立", "self-employed", "自媒体", "博主",
        "创作者", "up主", "主播", "直播", "网店", "电商", "作家", "写手",
        "摄影师", "摄像", "设计师（自由", "独立开发", "插画", "翻译",
        "内容创作", "自由职业", "个人工作室",
    ]
    remote_keywords = [
        "远程", "remote", "居家办公", "在家办公",
    ]
    student_keywords = [
        "学生", "研究生", "博士生", "大学生", "高中生", "留学生",
        "本科", "硕士", "博士",
    ]
    for kw in student_keywords:
        if kw in occ:
            return WorkStyle.STUDENT
    for kw in freelance_keywords:
        if kw in occ:
            return WorkStyle.FREELANCE
    for kw in remote_keywords:
        if kw in occ:
            return WorkStyle.REMOTE
    return WorkStyle.OFFICE


class LifeGoal(BaseModel):
    """人生目标/长期计划"""
    category: str = "生活"       # 分类：事业/生活/学习/健康/社交/理财
    description: str = ""         # 目标描述，如"粉丝突破10万"
    target_date: str = ""         # 目标截止日期（可选）
    progress: int = 0             # 进度 0-100
    priority: int = 1             # 优先级 1-5


class BasicInfo(BaseModel):
    name: str = ""
    age: int = 24
    birth_date: str = ""          # 格式 "YYYY-MM-DD"，由 birthday_engine 根据性格匹配星座后生成
    zodiac: str = ""              # 星座名称（中文），如 "双鱼座"
    city: str = "上海"
    district: str = "静安区"
    occupation: str = "UI设计师"
    work_style: str = "office"   # office / freelance / remote / student
    company_name: str = ""        # 上班族才有
    company_area: str = ""        # 上班族才有
    # 自由职业的工作偏好（非上班族使用）
    work_location_weights: dict = Field(default_factory=lambda: {
        "home": 50, "cafe": 25, "outdoor": 15, "studio": 10
    })


class HomeInfo(BaseModel):
    type: str = "一室一厅"
    description: str = "老公寓改造，有一个小阳台"
    has_roommate: bool = False
    pets: str = ""


class FamilyInfo(BaseModel):
    parents_location: str = ""
    contact_frequency: str = "每周视频一次"
    notes: str = ""


class DailySchedule(BaseModel):
    wake_up: str = "07:30"
    leave_home: str = "08:45"          # 上班族离家时间（自由职业可忽略）
    arrive_work: str = "09:30"         # 上班族到达时间（自由职业可忽略）
    lunch_break_start: str = "12:00"
    lunch_break_end: str = "13:00"
    leave_work: str = "18:30"          # 上班族离开时间
    arrive_home: str = "19:15"         # 上班族到家时间
    sleep: str = "23:30"
    # 自由职业扩展字段
    work_start: str = "10:00"          # 开始工作（灵活）
    work_end: str = "18:00"            # 结束工作（灵活）


class CommuteInfo(BaseModel):
    method: str = ""                   # 空字符串表示不需要通勤
    line: str = ""
    duration_minutes: int = 0


class LocationsInfo(BaseModel):
    home_address_hint: str = ""
    company_landmark: str = ""         # 上班族
    favorite_cafe: str = ""
    supermarket: str = ""
    park: str = ""
    weekend_hangout: str = ""
    # 自由职业扩展
    frequent_outdoor_spots: str = ""   # 常去的户外工作地点


class HabitsInfo(BaseModel):
    morning_drink: str = "美式咖啡"
    lunch_style: str = "公司附近随机"
    evening_routine: str = "刷手机"
    weekend_morning: str = "睡懒觉到10点"


class PixelAppearance(BaseModel):
    hair_color: str = "#4A3728"
    hair_style: str = "中长发"
    default_outfit_color: str = "#F5F0E8"


class Wardrobe(BaseModel):
    """
    角色衣柜 — 由 LLM 根据人物设定（性别/风格/职业）生成。
    按场景分类，每个场景 2-3 套备选。
    每条记录包含中文描述（用于对话）和英文描述（用于图片生成）。
    """
    home: str = "舒适的家居服"                      # 在家（晨间/晚间/居家办公）
    work: str = "职场正装或商务休闲装"               # 工作中（上班族/学生上课）
    casual: str = "休闲T恤牛仔裤"                    # 日常出门（逛街/咖啡馆/超市）
    outdoor: str = "运动风穿搭，便于活动"             # 户外（公园/外出工作）
    formal: str = "略正式的着装"                      # 正式场合（约会/聚餐/会议）
    sport: str = "运动装"                            # 运动/健身
    sleep: str = "睡衣"                              # 睡觉
    # 英文版（图片生成用）
    home_en: str = "comfortable home clothes"
    work_en: str = "business casual outfit"
    casual_en: str = "casual T-shirt and jeans"
    outdoor_en: str = "sporty outdoor outfit"
    formal_en: str = "smart casual outfit"
    sport_en: str = "athletic wear"
    sleep_en: str = "pajamas"


class CharacterCard(BaseModel):
    basic: BasicInfo = Field(default_factory=BasicInfo)
    home: HomeInfo = Field(default_factory=HomeInfo)
    family: FamilyInfo = Field(default_factory=FamilyInfo)
    daily_schedule: DailySchedule = Field(default_factory=DailySchedule)
    commute: CommuteInfo = Field(default_factory=CommuteInfo)
    locations: LocationsInfo = Field(default_factory=LocationsInfo)
    habits: HabitsInfo = Field(default_factory=HabitsInfo)
    current_context: str = ""
    pixel_appearance: PixelAppearance = Field(default_factory=PixelAppearance)
    # 新增：人生目标
    life_goals: List[LifeGoal] = Field(default_factory=list)
    # 新增：角色衣柜（LLM 根据人物设定生成）
    wardrobe: Wardrobe = Field(default_factory=Wardrobe)


# 锚点表单（用户首次填写）
class AnchorForm(BaseModel):
    character_name: str = ""
    city: str = "上海"
    occupation_hint: str = "UI设计师"
    age: int = 24
    personality_word: str = ""


# NPC 数据卡
class NPCRelation(str, Enum):
    BESTFRIEND = "闺蜜"
    COLLEAGUE = "同事"
    FAMILY = "家人"
    ACQUAINTANCE = "熟人"
    CLIENT = "客户"           # 自由职业者特有
    MENTOR = "导师"           # 自由职业者特有
    COLLABORATOR = "合作者"   # 自由职业者特有


class NPCCard(BaseModel):
    id: str = ""
    relation: str = "同事"
    name: str = ""
    age: int = 25
    birth_date: str = ""          # 格式 "YYYY-MM-DD"
    occupation: str = ""
    personality_word: str = ""
    contact_frequency: str = ""
    appear_scenes: List[str] = Field(default_factory=list)
    event_pool: List[str] = Field(default_factory=list)
    pixel_variant: Optional[str] = None


# 世界状态
class LogEntry(BaseModel):
    time: str = ""
    event: str = ""


class WorldState(BaseModel):
    last_updated: str = ""
    current_scene: str = "HOME_SLEEPING"
    current_activity: str = ""
    mood: int = 70
    active_npcs: List[str] = Field(default_factory=list)
    today_date: str = ""
    today_log: List[LogEntry] = Field(default_factory=list)
    today_events_triggered: List[str] = Field(default_factory=list)
    sleep_mood_penalty: int = 0
