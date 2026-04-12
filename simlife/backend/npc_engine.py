"""
NPC 引擎 - NPC 激活与交互逻辑
"""
import json
from pathlib import Path
from typing import List, Optional


NPC_CARDS_PATH = Path(__file__).parent.parent / "data" / "npc_cards.json"


def load_npc_cards() -> List[dict]:
    """加载所有 NPC 数据卡"""
    if NPC_CARDS_PATH.exists():
        with open(NPC_CARDS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def save_npc_cards(cards: List[dict]):
    """保存 NPC 数据卡"""
    NPC_CARDS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(NPC_CARDS_PATH, "w", encoding="utf-8") as f:
        json.dump(cards, f, ensure_ascii=False, indent=2)


def get_active_npcs(
    current_scene: str,
    today_events: list,
    npc_cards: Optional[List[dict]] = None,
) -> List[dict]:
    """
    根据当前场景和今日事件，返回应该出现在画面中的 NPC 列表。
    today_events 可以是 List[str]（事件ID）或 List[dict]（事件对象）。
    """
    if npc_cards is None:
        npc_cards = load_npc_cards()

    active = []

    # 场景匹配
    for npc in npc_cards:
        appear = npc.get("appear_scenes", [])
        if current_scene in appear:
            active.append(npc)

    # 事件覆盖
    for event in today_events:
        evt_id = event.get("id", "") if isinstance(event, dict) else event
        if "friend" in evt_id and "hangout" in evt_id:
            # 找闺蜜/好友
            for npc in npc_cards:
                if npc.get("relation") == "闺蜜" and npc not in active:
                    active.append(npc)
                    break
        if "lunch_together" in evt_id:
            for npc in npc_cards:
                if npc.get("relation") == "同事" and npc not in active:
                    active.append(npc)
                    break

    return active


def get_npc_event_pool(npc_id: str, npc_cards: Optional[List[dict]] = None) -> List[str]:
    """获取 NPC 的事件池"""
    if npc_cards is None:
        npc_cards = load_npc_cards()
    for npc in npc_cards:
        if npc.get("id") == npc_id:
            return npc.get("event_pool", [])
    return []


def get_npc_by_id(npc_id: str, npc_cards: Optional[List[dict]] = None) -> Optional[dict]:
    """通过 ID 获取 NPC"""
    if npc_cards is None:
        npc_cards = load_npc_cards()
    for npc in npc_cards:
        if npc.get("id") == npc_id:
            return npc
    return None


def get_background_npc_count(scene: str) -> int:
    """获取背景层 NPC 数量（纯氛围装饰）"""
    counts = {
        "COMMUTE_TO_WORK": 6,
        "COMMUTE_TO_HOME": 4,
        "OFFICE_WORKING": 3,
        "OFFICE_LUNCH": 5,
        "STREET_WANDERING": 4,
        "CAFE": 3,
        "PARK": 3,
        "SUPERMARKET": 5,
    }
    return counts.get(scene, 2)
