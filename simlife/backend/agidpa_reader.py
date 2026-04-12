"""
AGI-DPA 数据读取器 - 只读接口
"""
import json
from pathlib import Path
from datetime import datetime
from typing import Optional


class AGIDPAReader:
    """只读读取 AGI-DPA 的数据文件"""

    def __init__(self, agidpa_data_path: str = ""):
        self.path = Path(agidpa_data_path) if agidpa_data_path else Path(__file__).parent.parent.parent
        self._personality_data = None
        self._load()

    def _load(self):
        """尝试加载人格数据（与 desktop/config.py 保持一致）"""
        import sys, os
        if sys.platform == "win32":
            data_root = Path(os.environ.get("APPDATA", str(Path.home()))) / "AGI-Desktop"
        else:
            data_root = Path.home() / ".agi-desktop"
        personality_file = data_root / "personality.json"

        if personality_file.exists():
            try:
                with open(personality_file, "r", encoding="utf-8") as f:
                    self._personality_data = json.load(f)
            except Exception:
                self._personality_data = None

    def is_available(self) -> bool:
        """AGI-DPA 数据是否可读"""
        return self._personality_data is not None

    def get_character_personality(self) -> dict:
        """读取人格设定"""
        if not self._personality_data:
            return {}

        data = self._personality_data
        return {
            "character_name": data.get("name", ""),
            "personality_traits": data.get("personality_traits", []),
            "speaking_style": data.get("speaking_style", ""),
            "background_story": data.get("background_story", ""),
            "values": data.get("values", []),
            "appearance": data.get("appearance", ""),
        }

    def get_recent_interaction_time(self) -> Optional[datetime]:
        """最近一次用户对话的时间戳"""
        chat_history_path = self.path / "data" / "chat_history.json"
        if not chat_history_path.exists():
            return None
        try:
            with open(chat_history_path, "r", encoding="utf-8") as f:
                history = json.load(f)
            if history:
                last = history[-1] if isinstance(history, list) else history
                ts = last.get("timestamp", "")
                if ts:
                    return datetime.fromisoformat(ts)
        except Exception:
            pass
        return None

    def get_task_queue_length(self) -> int:
        """当前待处理任务数"""
        tasks_path = self.path / "data" / "tasks.json"
        if not tasks_path.exists():
            return 0
        try:
            with open(tasks_path, "r", encoding="utf-8") as f:
                tasks = json.load(f)
            if isinstance(tasks, list):
                return len([t for t in tasks if t.get("status") == "pending"])
        except Exception:
            pass
        return 0

    def recent_interaction_within_hours(self, hours: float) -> bool:
        """最近N小时是否有对话"""
        t = self.get_recent_interaction_time()
        if not t:
            return False
        delta = (datetime.now() - t).total_seconds() / 3600
        return delta <= hours
