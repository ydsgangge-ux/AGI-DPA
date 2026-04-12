"""
人物卡数据模型 (Pydantic)
"""
from pydantic import BaseModel, Field
from typing import Optional, List
from enum import Enum


class SceneEnum(str, Enum):
    HOME_SLEEPING = "HOME_SLEEPING"
    HOME_MORNING = "HOME_MORNING"
    HOME_EVENING = "HOME_EVENING"
    HOME_WEEKEND_LAZY = "HOME_WEEKEND_LAZY"
    COMMUTE_TO_WORK = "COMMUTE_TO_WORK"
    COMMUTE_TO_HOME = "COMMUTE_TO_HOME"
    OFFICE_WORKING = "OFFICE_WORKING"
    OFFICE_MEETING = "OFFICE_MEETING"
    OFFICE_LUNCH = "OFFICE_LUNCH"
    CAFE = "CAFE"
    PARK = "PARK"
    SUPERMARKET = "SUPERMARKET"
    STREET_WANDERING = "STREET_WANDERING"
    FRIEND_HANGOUT = "FRIEND_HANGOUT"
    OVERTIME = "OVERTIME"


SCENE_LABELS = {
    SceneEnum.HOME_SLEEPING: "睡觉",
    SceneEnum.HOME_MORNING: "晨间准备",
    SceneEnum.HOME_EVENING: "晚间放松",
    SceneEnum.HOME_WEEKEND_LAZY: "周末赖床",
    SceneEnum.COMMUTE_TO_WORK: "去公司",
    SceneEnum.COMMUTE_TO_HOME: "回家",
    SceneEnum.OFFICE_WORKING: "工作中",
    SceneEnum.OFFICE_MEETING: "开会",
    SceneEnum.OFFICE_LUNCH: "午休觅食",
    SceneEnum.CAFE: "咖啡馆",
    SceneEnum.PARK: "公园",
    SceneEnum.SUPERMARKET: "超市",
    SceneEnum.STREET_WANDERING: "街头闲逛",
    SceneEnum.FRIEND_HANGOUT: "和朋友在外",
    SceneEnum.OVERTIME: "加班",
}


class BasicInfo(BaseModel):
    name: str = ""
    age: int = 24
    city: str = "上海"
    district: str = "静安区"
    occupation: str = "UI设计师"
    company_name: str = "某互联网公司"
    company_area: str = "长宁区"


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
    leave_home: str = "08:45"
    arrive_work: str = "09:30"
    lunch_break_start: str = "12:00"
    lunch_break_end: str = "13:00"
    leave_work: str = "18:30"
    arrive_home: str = "19:15"
    sleep: str = "23:30"


class CommuteInfo(BaseModel):
    method: str = "地铁"
    line: str = "2号线"
    duration_minutes: int = 35


class LocationsInfo(BaseModel):
    home_address_hint: str = ""
    company_landmark: str = ""
    favorite_cafe: str = ""
    supermarket: str = ""
    park: str = ""
    weekend_hangout: str = ""


class HabitsInfo(BaseModel):
    morning_drink: str = "美式咖啡"
    lunch_style: str = "公司附近随机"
    evening_routine: str = "刷手机"
    weekend_morning: str = "睡懒觉到10点"


class PixelAppearance(BaseModel):
    hair_color: str = "#4A3728"
    hair_style: str = "中长发"
    default_outfit_color: str = "#F5F0E8"


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


class NPCCard(BaseModel):
    id: str = ""
    relation: str = "同事"
    name: str = ""
    age: int = 25
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
