"""
事件系统 - 预设事件库 + 调度 + 触发 + 连锁
"""
import json
import random
from datetime import datetime, date
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple


EVENT_LIB_PATH = Path(__file__).parent.parent / "data" / "event_library.json"
SCHEDULED_PATH = Path(__file__).parent.parent / "data" / "scheduled_events.json"
HISTORY_PATH = Path(__file__).parent.parent / "data" / "event_history.json"


def load_event_library() -> List[dict]:
    """加载预设事件库"""
    if EVENT_LIB_PATH.exists():
        with open(EVENT_LIB_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def load_scheduled_events() -> List[dict]:
    """加载待触发事件队列"""
    if SCHEDULED_PATH.exists():
        with open(SCHEDULED_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def save_scheduled_events(events: List[dict]):
    """保存待触发事件队列"""
    SCHEDULED_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(SCHEDULED_PATH, "w", encoding="utf-8") as f:
        json.dump(events, f, ensure_ascii=False, indent=2)


def load_event_history() -> List[dict]:
    """加载历史事件"""
    if HISTORY_PATH.exists():
        with open(HISTORY_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def save_event_history(history: List[dict]):
    """保存历史事件"""
    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(HISTORY_PATH, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def _build_micro_templates() -> dict:
    """构建完整的微事件模板库（覆盖所有 15 个场景）"""
    return {
        # ── 通勤去公司 ──
        "COMMUTE_TO_WORK": [
            {"id": "micro_commute_a", "label": "地铁很挤，站了一路", "mood_delta": -3},
            {"id": "micro_commute_b", "label": "今天地铁刚好有座", "mood_delta": +3},
            {"id": "micro_commute_c", "label": "换乘的时候人太多，挤了三趟才上去", "mood_delta": -5},
            {"id": "micro_commute_d", "label": "在地铁上不小心踩到了别人的脚", "mood_delta": -2},
            {"id": "micro_commute_e", "label": "耳机里随机播放到一首很好听的歌", "mood_delta": +4},
            {"id": "micro_commute_f", "label": "地铁上看到有人在读一本自己也想看的书", "mood_delta": +2},
            {"id": "micro_commute_g", "label": "出站的时候发现公交卡没电了，手机刷才过去", "mood_delta": -2},
            {"id": "micro_commute_h", "label": "今天骑车上班，风吹着还挺舒服的", "mood_delta": +5},
            {"id": "micro_commute_i", "label": "路上堵车，比平时晚了十分钟", "mood_delta": -4},
            {"id": "micro_commute_j", "label": "在便利店买了个三明治当早餐", "mood_delta": 0},
            {"id": "micro_commute_k", "label": "看到路边花店新到了一批花，随手拍了张照", "mood_delta": +3},
            {"id": "micro_commute_l", "label": "差点迟到，最后小跑着进了公司", "mood_delta": -3},
            {"id": "micro_commute_m", "label": "遇到一个穿得特别好看的人，多看了两眼", "mood_delta": +2},
        ],
        # ── 通勤回家 ──
        "COMMUTE_TO_HOME": [
            {"id": "micro_home_a", "label": "下班路上经过面包店，买了明天的早饭", "mood_delta": +3},
            {"id": "micro_home_b", "label": "地铁上刷手机看了一会儿短视频", "mood_delta": 0},
            {"id": "micro_home_c", "label": "到家发现电梯坏了，爬了六层楼", "mood_delta": -5},
            {"id": "micro_home_d", "label": "看到夕阳很好看，在路边站了一会儿", "mood_delta": +4},
            {"id": "micro_home_e", "label": "路上遇到有人在遛一只很可爱的柯基", "mood_delta": +5},
            {"id": "micro_home_f", "label": "便利店买了杯酸奶，边走边喝", "mood_delta": +2},
            {"id": "micro_home_g", "label": "想起来一件忘记买的东西，绕路去了一趟超市", "mood_delta": -2},
            {"id": "micro_home_h", "label": "今天下班早，路上人不多", "mood_delta": +3},
            {"id": "micro_home_i", "label": "在地铁上被旁边的人的香水呛到了", "mood_delta": -2},
            {"id": "micro_home_j", "label": "路过水果摊，买了点草莓回去", "mood_delta": +4},
        ],
        # ── 工作中 ──
        "OFFICE_WORKING": [
            {"id": "micro_work_a", "label": "上午一直在开会", "mood_delta": -2},
            {"id": "micro_work_b", "label": "今天效率还不错", "mood_delta": +5},
            {"id": "micro_work_c", "label": "同事带了好吃的零食", "mood_delta": +3},
            {"id": "micro_work_d", "label": "方案改了第四版，终于可以交了", "mood_delta": +8},
            {"id": "micro_work_e", "label": "电脑卡了一下，还好没丢文件", "mood_delta": -3},
            {"id": "micro_work_f", "label": "摸鱼的时候被领导看见了，赶紧切回工作界面", "mood_delta": -5},
            {"id": "micro_work_g", "label": "和同事讨论了一个新想法，大家都挺兴奋的", "mood_delta": +6},
            {"id": "micro_work_h", "label": "打印机又卡纸了，修了半天", "mood_delta": -4},
            {"id": "micro_work_i", "label": "接到一个客户的表扬电话", "mood_delta": +10},
            {"id": "micro_work_j", "label": "在工位上偷偷做了二十分钟拉伸", "mood_delta": +2},
            {"id": "micro_work_k", "label": "咖啡续命第三杯，手有点抖", "mood_delta": -2},
            {"id": "micro_work_l", "label": "下午犯困，去茶水间洗了把脸", "mood_delta": 0},
            {"id": "micro_work_m", "label": "发现了一个可以提升效率的小工具", "mood_delta": +5},
            {"id": "micro_work_n", "label": "领导突然走过来看了一眼屏幕，心跳加速", "mood_delta": -3},
            {"id": "micro_work_o", "label": "完成了这周最头疼的一项任务", "mood_delta": +12},
        ],
        # ── 开会 ──
        "OFFICE_MEETING": [
            {"id": "micro_meeting_a", "label": "开会的时候不小心走神了，被点名才回过神来", "mood_delta": -4},
            {"id": "micro_meeting_b", "label": "自己的方案被夸了，暗自开心", "mood_delta": +8},
            {"id": "micro_meeting_c", "label": "会议拖了半小时还没结束，脚都坐麻了", "mood_delta": -5},
            {"id": "micro_meeting_d", "label": "在笔记本上偷偷画了几个小人", "mood_delta": +1},
            {"id": "micro_meeting_e", "label": "会上提了个建议，被采纳了", "mood_delta": +10},
            {"id": "micro_meeting_f", "label": "旁边的人在微信聊天，偷偷看了一眼", "mood_delta": 0},
            {"id": "micro_meeting_g", "label": "会上说的方案和之前完全不一样，一脸懵", "mood_delta": -3},
            {"id": "micro_meeting_h", "label": "终于散会了，感觉重新活过来了", "mood_delta": +5},
        ],
        # ── 午休觅食 ──
        "OFFICE_LUNCH": [
            {"id": "micro_lunch_a", "label": "午饭排队太长，随便找了个地方", "mood_delta": -2},
            {"id": "micro_lunch_b", "label": "发现了一家不错的新店", "mood_delta": +5},
            {"id": "micro_lunch_c", "label": "和同事一起吃饭，聊了会儿八卦", "mood_delta": +4},
            {"id": "micro_lunch_d", "label": "点了个外卖，送来的时候凉了", "mood_delta": -3},
            {"id": "micro_lunch_e", "label": "吃了顿好的，下午有动力了", "mood_delta": +5},
            {"id": "micro_lunch_f", "label": "在便利店随便买了个饭团凑合", "mood_delta": -1},
            {"id": "micro_lunch_g", "label": "排队的时候前面的人点了超久", "mood_delta": -3},
            {"id": "micro_lunch_h", "label": "食堂今天的菜出奇的好吃", "mood_delta": +6},
            {"id": "micro_lunch_i", "label": "吃完饭在公司楼下转了一圈消食", "mood_delta": +3},
            {"id": "micro_lunch_j", "label": "点了杯奶茶犒劳自己", "mood_delta": +4},
            {"id": "micro_lunch_k", "label": "一个人吃饭，边吃边刷手机", "mood_delta": 0},
            {"id": "micro_lunch_l", "label": "试了家新开的麻辣烫，辣到冒汗但好爽", "mood_delta": +5},
        ],
        # ── 晨间准备 ──
        "HOME_MORNING": [
            {"id": "micro_morning_a", "label": "闹钟响了三次才起来", "mood_delta": -3},
            {"id": "micro_morning_b", "label": "今天起得挺早，从容地吃了顿早餐", "mood_delta": +5},
            {"id": "micro_morning_c", "label": "找了好久才找到想穿的那件衣服", "mood_delta": -2},
            {"id": "micro_morning_d", "label": "煮了杯咖啡，闻着香味心情好了", "mood_delta": +3},
            {"id": "micro_morning_e", "label": "洗完澡发现没毛巾了，光着身子去拿", "mood_delta": -2},
            {"id": "micro_morning_f", "label": "照镜子发现自己今天状态不错", "mood_delta": +4},
            {"id": "micro_morning_g", "label": "昨晚忘了充电，手机只剩12%", "mood_delta": -3},
            {"id": "micro_morning_h", "label": "边刷牙边想今天的工作安排", "mood_delta": -1},
            {"id": "micro_morning_i", "label": "窗外的鸟叫声有点吵但也没办法", "mood_delta": -1},
            {"id": "micro_morning_j", "label": "匆匆忙忙化了个淡妆出门", "mood_delta": 0},
        ],
        # ── 晚间放松 ──
        "HOME_EVENING": [
            {"id": "micro_evening_a", "label": "刷手机刷到停不下来", "mood_delta": 0},
            {"id": "micro_evening_b", "label": "追了两集剧", "mood_delta": +3},
            {"id": "micro_evening_c", "label": "猫把耳机线咬断了", "mood_delta": -5},
            {"id": "micro_evening_d", "label": "泡了个热水澡，浑身放松", "mood_delta": +8},
            {"id": "micro_evening_e", "label": "做了一顿简单的晚饭", "mood_delta": +4},
            {"id": "micro_evening_f", "label": "翻了翻相册，看到了以前的照片", "mood_delta": +2},
            {"id": "micro_evening_g", "label": "和闺蜜打了个语音电话", "mood_delta": +6},
            {"id": "micro_evening_h", "label": "懒得做饭，点了外卖", "mood_delta": -1},
            {"id": "micro_evening_i", "label": "练了半小时瑜伽", "mood_delta": +5},
            {"id": "micro_evening_j", "label": "收拾了一下房间，心情好了不少", "mood_delta": +4},
            {"id": "micro_evening_k", "label": "敷了个面膜，躺在床上什么都不想", "mood_delta": +3},
            {"id": "micro_evening_l", "label": "写了一页日记", "mood_delta": +2},
            {"id": "micro_evening_m", "label": "看了会儿书，翻了两页就困了", "mood_delta": +2},
            {"id": "micro_evening_n", "label": "切了个水果当夜宵", "mood_delta": +3},
            {"id": "micro_evening_o", "label": "在群里和朋友聊了一会儿天", "mood_delta": +3},
            {"id": "micro_evening_p", "label": "把明天要穿的衣服提前找好了", "mood_delta": +1},
            {"id": "micro_evening_q", "label": "听了会儿音乐，随便哼了两句", "mood_delta": +4},
            {"id": "micro_evening_r", "label": "突然想学点什么，打开B站搜了个教程", "mood_delta": +3},
        ],
        # ── 周末赖床 ──
        "HOME_WEEKEND_LAZY": [
            {"id": "micro_lazy_a", "label": "翻了个身继续睡", "mood_delta": +5},
            {"id": "micro_lazy_b", "label": "在被窝里刷了半小时手机", "mood_delta": +3},
            {"id": "micro_lazy_c", "label": "终于起来了，做了份 brunch", "mood_delta": +5},
            {"id": "micro_lazy_d", "label": "窗外的阳光很好，拉了条毯子在阳台坐了一会儿", "mood_delta": +7},
            {"id": "micro_lazy_e", "label": "睡到中午才起，有点愧疚", "mood_delta": -2},
            {"id": "micro_lazy_f", "label": "刷到一个超长的视频，一看就是一个多小时", "mood_delta": 0},
            {"id": "micro_lazy_g", "label": "打开了存了好久的剧准备刷", "mood_delta": +4},
            {"id": "micro_lazy_h", "label": "给植物浇了水", "mood_delta": +2},
        ],
        # ── 咖啡馆 ──
        "CAFE": [
            {"id": "micro_cafe_a", "label": "点了杯拿铁，在角落坐下", "mood_delta": +5},
            {"id": "micro_cafe_b", "label": "旁边桌的人在聊一个有趣的话题", "mood_delta": +2},
            {"id": "micro_cafe_c", "label": "今天这家店的音乐品味不错", "mood_delta": +3},
            {"id": "micro_cafe_d", "label": "看到有人在画画，默默地观察了一会儿", "mood_delta": +3},
            {"id": "micro_cafe_e", "label": "点单的时候店员笑着说了一句夸奖的话", "mood_delta": +5},
            {"id": "micro_cafe_f", "label": "拿铁上拉了一个很好看的拉花", "mood_delta": +4},
            {"id": "micro_cafe_g", "label": "翻了一会儿书，但心思完全不在上面", "mood_delta": 0},
            {"id": "micro_cafe_h", "label": "遇到一个特别适合拍照的光线，拍了好几张", "mood_delta": +4},
            {"id": "micro_cafe_i", "label": "WiFi不太好，信号断断续续的", "mood_delta": -2},
            {"id": "micro_cafe_j", "label": "发呆看了好久窗外来来往往的人", "mood_delta": +2},
        ],
        # ── 公园 ──
        "PARK": [
            {"id": "micro_park_a", "label": "在长椅上坐了一会儿，阳光暖暖的", "mood_delta": +6},
            {"id": "micro_park_b", "label": "看到一群大爷在打太极，还挺整齐的", "mood_delta": +3},
            {"id": "micro_park_c", "label": "有人在不远处弹吉他，声音挺好听", "mood_delta": +5},
            {"id": "micro_park_d", "label": "湖边的鸭子游来游去的，看了好一会儿", "mood_delta": +4},
            {"id": "micro_park_e", "label": "走路的时候踩到一坨不明物体……", "mood_delta": -5},
            {"id": "micro_park_f", "label": "发现了一条没走过的小路", "mood_delta": +3},
            {"id": "micro_park_g", "label": "风吹过来带着花草的味道", "mood_delta": +5},
            {"id": "micro_park_h", "label": "手机突然没电了，干脆不看手机了", "mood_delta": +2},
            {"id": "micro_park_i", "label": "拍了张花草的照片发了条朋友圈", "mood_delta": +3},
        ],
        # ── 超市 ──
        "SUPERMARKET": [
            {"id": "micro_market_a", "label": "本来只想买一瓶牛奶，出来的时候拎了两大袋", "mood_delta": -2},
            {"id": "micro_market_b", "label": "打折区的车厘子看起来不错，买了一盒", "mood_delta": +4},
            {"id": "micro_market_c", "label": "排队结账排了快十分钟", "mood_delta": -3},
            {"id": "micro_market_d", "label": "试吃了一种新品小蛋糕，意外地好吃", "mood_delta": +5},
            {"id": "micro_market_e", "label": "在调料区站了好久，不知道选哪个", "mood_delta": -1},
            {"id": "micro_market_f", "label": "看到冰淇淋打折，买了两个口味", "mood_delta": +4},
            {"id": "micro_market_g", "label": "买了一些水果和蔬菜，打算这周多吃点健康的", "mood_delta": +3},
            {"id": "micro_market_h", "label": "结账的时候发现忘带袋子了", "mood_delta": -2},
        ],
        # ── 街头闲逛 ──
        "STREET_WANDERING": [
            {"id": "micro_street_a", "label": "漫无目的地走了一会儿，感觉挺放松的", "mood_delta": +4},
            {"id": "micro_street_b", "label": "路过一家小店，橱窗里的一条裙子很好看", "mood_delta": +3},
            {"id": "micro_street_c", "label": "有人发传单，接了一份看了看就扔了", "mood_delta": 0},
            {"id": "micro_street_d", "label": "在路边看到一个街头艺人，停下来听了一会儿", "mood_delta": +5},
            {"id": "micro_street_e", "label": "走累了，找了个台阶坐下来歇了歇", "mood_delta": +1},
            {"id": "micro_street_f", "label": "被一个推销员缠住了，好不容易才脱身", "mood_delta": -4},
            {"id": "micro_street_g", "label": "发现了一条新开的美食街", "mood_delta": +4},
            {"id": "micro_street_h", "label": "在文具店逛了好久，买了一个好看的笔记本", "mood_delta": +3},
            {"id": "micro_street_i", "label": "天色渐暗，路灯亮起来的时候还挺好看的", "mood_delta": +5},
            {"id": "micro_street_j", "label": "走了一个多小时，微信步数涨了不少", "mood_delta": +2},
        ],
        # ── 和朋友在外 ──
        "FRIEND_HANGOUT": [
            {"id": "micro_hangout_a", "label": "和朋友逛了一家新开的店", "mood_delta": +6},
            {"id": "micro_hangout_b", "label": "聊了好多有的没的，笑到肚子疼", "mood_delta": +8},
            {"id": "micro_hangout_c", "label": "一起拍了好多自拍", "mood_delta": +5},
            {"id": "micro_hangout_d", "label": "闺蜜说了一个八卦，听得津津有味", "mood_delta": +4},
            {"id": "micro_hangout_e", "label": "逛到脚酸，找了个地方坐下来喝东西", "mood_delta": +3},
            {"id": "micro_hangout_f", "label": "AA付款的时候发现手机没信号，尴尬了一下", "mood_delta": -2},
            {"id": "micro_hangout_g", "label": "分手的时候约好了下次见面的时间", "mood_delta": +5},
            {"id": "micro_hangout_h", "label": "朋友推荐了一个很好吃的地方，下次一定要来", "mood_delta": +4},
            {"id": "micro_hangout_i", "label": "逛到商场快关门了，恋恋不舍地出来了", "mood_delta": +2},
        ],
        # ── 加班 ──
        "OVERTIME": [
            {"id": "micro_overtime_a", "label": "办公室里只剩下自己了，好安静", "mood_delta": -5},
            {"id": "micro_overtime_b", "label": "终于搞定了，伸了个大大的懒腰", "mood_delta": +6},
            {"id": "micro_overtime_c", "label": "肚子咕咕叫，点了份外卖在工位上吃", "mood_delta": -3},
            {"id": "micro_overtime_d", "label": "看了看表，已经九点多了", "mood_delta": -6},
            {"id": "micro_overtime_e", "label": "窗外看到别人都下班回家了，有点羡慕", "mood_delta": -5},
            {"id": "micro_overtime_f", "label": "泡了杯浓茶续命", "mood_delta": -2},
            {"id": "micro_overtime_g", "label": "给家里发了条消息说今天要晚点回去", "mood_delta": -3},
            {"id": "micro_overtime_h", "label": "加班到很晚，走的时候整栋楼都黑了", "mood_delta": -8},
        ],
        # ── 睡觉 ──
        "HOME_SLEEPING": [
            {"id": "micro_sleep_a", "label": "做了一个奇怪的梦，醒来就忘了", "mood_delta": 0},
            {"id": "micro_sleep_b", "label": "半夜醒了一次，翻了个身又睡着了", "mood_delta": -1},
            {"id": "micro_sleep_c", "label": "被子有点薄，有点冷", "mood_delta": -2},
            {"id": "micro_sleep_d", "label": "窗外的雨声反而助眠了", "mood_delta": +1},
        ],
        # ── 在家工作（自由职业） ──
        "HOME_WORKING": [
            {"id": "micro_hwork_a", "label": "在家对着电脑做了一上午", "mood_delta": +3},
            {"id": "micro_hwork_b", "label": "穿着睡衣办公，效率出奇的高", "mood_delta": +5},
            {"id": "micro_hwork_c", "label": "在家工作容易被猫打断，但它太可爱了", "mood_delta": +4},
            {"id": "micro_hwork_d", "label": "不知不觉就下午两点了，都没吃午饭", "mood_delta": -2},
            {"id": "micro_hwork_e", "label": "在家工作到一半，突然来了灵感", "mood_delta": +10},
            {"id": "micro_hwork_f", "label": "煮了壶茶，边喝边想方案", "mood_delta": +3},
            {"id": "micro_hwork_g", "label": "在家办公三天没出门，感觉自己快发霉了", "mood_delta": -5},
            {"id": "micro_hwork_h", "label": "窗外阳光很好，但强迫自己坐在电脑前", "mood_delta": -2},
            {"id": "micro_hwork_i", "label": "翻看了一下去年的作品，觉得自己进步了不少", "mood_delta": +6},
            {"id": "micro_hwork_j", "label": "一口气完成了好几个任务，满足感爆棚", "mood_delta": +12},
            {"id": "micro_hwork_k", "label": "在家办公的缺点是工作和生活的界限没了", "mood_delta": -3},
            {"id": "micro_hwork_l", "label": "做了会儿拉伸，继续干活", "mood_delta": +1},
        ],
        # ── 咖啡馆办公（自由职业） ──
        "CAFE_WORKING": [
            {"id": "micro_cwork_a", "label": "在咖啡馆打开笔记本，点了杯冰美式", "mood_delta": +5},
            {"id": "micro_cwork_b", "label": "咖啡馆的白噪音反而让人更专注", "mood_delta": +6},
            {"id": "micro_cwork_c", "label": "旁边桌在聊创业，偷偷听了一会儿", "mood_delta": +2},
            {"id": "micro_cwork_d", "label": "WiFi不太稳定，论文档保存了好几次", "mood_delta": -3},
            {"id": "micro_cwork_e", "label": "坐了三小时才喝完一杯咖啡，店员没赶人", "mood_delta": +3},
            {"id": "micro_cwork_f", "label": "灵感来了，一口气写了好几段", "mood_delta": +10},
            {"id": "micro_cwork_g", "label": "换了个咖啡馆，环境更好，人也少", "mood_delta": +4},
            {"id": "micro_cwork_h", "label": "认识了另一个常来的自由职业者", "mood_delta": +5},
            {"id": "micro_cwork_i", "label": "被一杯拿铁的价格吓到了，还是自己做咖啡吧", "mood_delta": -3},
            {"id": "micro_cwork_j", "label": "午后的阳光透过落地窗洒在键盘上", "mood_delta": +7},
        ],
        # ── 户外工作（自由职业） ──
        "OUTDOOR_WORKING": [
            {"id": "micro_owork_a", "label": "今天光线正好，拍了不少好素材", "mood_delta": +10},
            {"id": "micro_owork_b", "label": "出门忘了带充电宝，手机快没电了", "mood_delta": -4},
            {"id": "micro_owork_c", "label": "在户外拍了一整天，腿都走酸了", "mood_delta": -2},
            {"id": "micro_owork_d", "label": "拍到了一个很棒的瞬间，激动了好久", "mood_delta": +15},
            {"id": "micro_owork_e", "label": "被路过的狗吓了一跳，差点摔了相机", "mood_delta": -5},
            {"id": "micro_owork_f", "label": "和一个受访者聊了很久，收获很大", "mood_delta": +8},
            {"id": "micro_owork_g", "label": "天突然变了，赶紧收拾东西找地方躲雨", "mood_delta": -3},
            {"id": "micro_owork_h", "label": "在一个新地方发现了很多创作灵感", "mood_delta": +8},
        ],
        # ── 工作室（自由职业） ──
        "STUDIO_WORKING": [
            {"id": "micro_studio_a", "label": "在工作室里调了半天设备", "mood_delta": +2},
            {"id": "micro_studio_b", "label": "今天的录音效果特别好", "mood_delta": +8},
            {"id": "micro_studio_c", "label": "一个人在工作室有点安静，放了点背景音乐", "mood_delta": +3},
            {"id": "micro_studio_d", "label": "整理了一下工作室，扔了好多杂物", "mood_delta": +4},
            {"id": "micro_studio_e", "label": "器材又出了点小问题，修了半天", "mood_delta": -5},
            {"id": "micro_studio_f", "label": "完成了这周最重要的一个作品", "mood_delta": +12},
        ],
    }


# 预构建，避免每次调用都重新创建
_MICRO_TEMPLATES = _build_micro_templates()


def check_daily_micro_events(
    character_card: dict,
    scene: str,
    today_seed: int,
    already_triggered: List[str],
) -> Optional[dict]:
    """
    层一：日常微变化。根据当天种子决定是否触发微小事件。
    每次调用只返回0-1个事件（或不返回）。
    覆盖全部 15 个场景，每个场景 4-18 条模板。
    """
    now = datetime.now()
    hour = now.hour
    rng = random.Random(today_seed + hash(scene) + hour * 7)

    if rng.random() > 0.35:
        return None  # 65% 什么都不发生

    templates = _MICRO_TEMPLATES.get(scene, [])
    if not templates:
        return None

    evt = rng.choice(templates).copy()
    evt_id = evt["id"]
    if evt_id in already_triggered:
        return None

    return evt


def check_random_events(
    character_card: dict,
    scene: str,
    today_seed: int,
    already_triggered: List[str],
    now: Optional[datetime] = None,
    weekday_only: bool = True,
) -> Optional[dict]:
    """
    层三：随机突发事件。低概率，影响大。
    加入时间因素作为种子的一部分，避免启动时一次性全部触发。
    """
    library = load_event_library()
    now = now or datetime.now()
    is_weekday = now.weekday() < 5

    eligible = []
    for evt in library:
        # 检查是否已经触发过
        if evt["id"] in already_triggered:
            continue
        # 检查触发条件
        cond = evt.get("trigger_condition", "")
        if "weekday" in cond and not is_weekday:
            continue
        if "commute_to_work" in cond and scene != "COMMUTE_TO_WORK":
            continue
        eligible.append(evt)

    if not eligible:
        return None

    # 种子包含日期+小时+分钟，不同时间触发不同事件，不会一次性全触发
    time_salt = now.hour * 60 + now.minute
    rng = random.Random(today_seed + time_salt)
    for evt in eligible:
        prob = evt.get("probability_per_day", 0.02)
        if rng.random() < prob:
            # 从日志模板中随机选一条
            templates = evt.get("log_templates", [evt.get("label", "")])
            result = {
                "id": evt["id"],
                "label": rng.choice(templates),
                "mood_delta": evt.get("mood_delta", 0),
                "consequences": evt.get("consequences", []),
                "source": "random",
            }
            return result

    return None


def check_scheduled_events(
    scheduled: List[dict],
    now: Optional[datetime] = None,
) -> Tuple[List[dict], List[dict]]:
    """
    检查待触发队列中是否有到期事件。
    返回 (触发的, 仍待触发的)。
    """
    now = now or datetime.now()
    triggered = []
    remaining = []

    for evt in scheduled:
        evt_date = evt.get("scheduled_date", "")
        evt_range = evt.get("scheduled_time_range", "00:00-23:59")
        if not evt_date:
            remaining.append(evt)
            continue

        # 检查日期
        try:
            target_date = date.fromisoformat(evt_date)
        except ValueError:
            remaining.append(evt)
            continue

        if target_date > now.date():
            remaining.append(evt)
            continue

        # 检查时间范围
        if target_date == now.date():
            parts = evt_range.split("-")
            if len(parts) == 2:
                h1, m1 = parts[0].split(":")
                h2, m2 = parts[1].split(":")
                start_min = int(h1) * 60 + int(m1)
                end_min = int(h2) * 60 + int(m2)
                now_min = now.hour * 60 + now.minute
                if now_min < start_min:
                    remaining.append(evt)
                    continue

        # 触发
        library = load_event_library()
        lib_evt = next((e for e in library if e["id"] == evt["event_id"]), None)
        label = evt.get("label", "")
        mood = evt.get("mood_delta", 0)
        if lib_evt:
            label = label or lib_evt.get("label", "")
            mood = mood or lib_evt.get("mood_delta", 0)
            templates = lib_evt.get("log_templates", [label])
            if templates and label in templates:
                import random as _r
                label = _r.choice(templates)

        triggered.append({
            "id": evt.get("event_id", ""),
            "label": label,
            "mood_delta": mood,
            "consequences": evt.get("consequences", []),
            "source": evt.get("source", "scheduled"),
        })

    return triggered, remaining


def apply_event_consequences(event_id: str, mood_delta: int) -> dict:
    """
    返回事件对时刻表和后续场景的影响。
    返回 {"schedule_overrides": {...}, "scene_hint": "...", "extra_mood": int}
    """
    result = {
        "schedule_overrides": {},
        "scene_hint": None,
        "extra_mood": 0,
        "block_positive": False,
    }

    rng = random.Random()

    if "subway_delay" in event_id:
        delay = rng.randint(30, 50)
        result["schedule_overrides"]["arrive_work"] = 9 * 60 + 30 + delay
        result["extra_mood"] = mood_delta
        if rng.random() < 0.4:
            result["scene_hint"] = "CAFE"

    elif "design_approved" in event_id or "task_done" in event_id:
        early = rng.randint(30, 60)
        result["schedule_overrides"]["leave_work"] = 18 * 60 + 30 - early
        result["extra_mood"] = mood_delta
        if rng.random() < 0.6:
            result["scene_hint"] = rng.choice(["PARK", "STREET_WANDERING"])

    elif "pet_sick" in event_id:
        result["schedule_overrides"]["arrive_home"] = 19 * 60 + 15 + rng.randint(90, 120)
        result["extra_mood"] = mood_delta
        result["block_positive"] = True

    elif "extra_task" in event_id:
        overtime = rng.randint(90, 180)
        result["schedule_overrides"]["leave_work"] = 18 * 60 + 30 + overtime
        result["extra_mood"] = mood_delta
        result["scene_hint"] = "OVERTIME"

    elif "friend_conflict" in event_id:
        result["extra_mood"] = mood_delta

    elif "parcel" in event_id or "surprise" in event_id:
        result["extra_mood"] = mood_delta

    else:
        result["extra_mood"] = mood_delta

    return result


def add_scheduled_events(new_events: List[dict]):
    """向队列追加新事件"""
    scheduled = load_scheduled_events()
    scheduled.extend(new_events)
    save_scheduled_events(scheduled)


def record_triggered_event(event: dict):
    """将已触发事件存入历史"""
    history = load_event_history()
    history.append({
        **event,
        "triggered_at": datetime.now().isoformat(),
    })
    # 只保留最近100条
    history = history[-100:]
    save_event_history(history)
