"""
用户画像系统
像认识一个人一样逐步了解用户：
- 从对话中提炼性格特征（逐步累积，不是一次性判断）
- 识别反常行为（这次不像平时的他/她）
- 主动提问确认身份（安全机制）
- 为未来的摄像头识别预留接口
"""

import json
import sqlite3
from engine.db_guard import guarded_connect
import uuid
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field


# ══════════════════════════════════════════════
# 数据结构
# ══════════════════════════════════════════════

@dataclass
class PersonalityTrait:
    """单个性格特征的置信度"""
    name:         str           # 特征名，如「喜欢AGI研究」「说话简洁」
    category:     str           # 分类：interest/style/value/habit/emotion
    confidence:   float         # 置信度 0~1（观察越多越高）
    evidence_count: int = 0     # 观察到的次数
    first_seen:   str = ""
    last_seen:    str = ""
    examples:     List[str] = field(default_factory=list)  # 支撑例子（最多3条）

    def to_dict(self) -> dict:
        return {
            "name":           self.name,
            "category":       self.category,
            "confidence":     round(self.confidence, 3),
            "evidence_count": self.evidence_count,
            "first_seen":     self.first_seen,
            "last_seen":      self.last_seen,
            "examples":       self.examples[-3:]
        }


@dataclass
class AnomalyRecord:
    """反常行为记录"""
    timestamp:   str
    description: str            # 反常的描述
    normal_pattern: str         # 正常模式是什么
    severity:    float          # 0~1 严重程度
    resolved:    bool = False   # 是否已确认/解释

    def to_dict(self) -> dict:
        return {
            "timestamp":      self.timestamp,
            "description":    self.description,
            "normal_pattern": self.normal_pattern,
            "severity":       self.severity,
            "resolved":       self.resolved
        }


# ══════════════════════════════════════════════
# 用户画像管理器
# ══════════════════════════════════════════════

class UserProfileManager:
    """
    用户画像管理器
    核心理念：不预设，通过观察逐步建立
    """

    # 性格确认阈值（观察N次后认为「已确认」）
    CONFIRMED_THRESHOLD = 5

    # 反常检测阈值（与已知模式偏差超过此值触发）
    ANOMALY_THRESHOLD = 0.65

    # 身份验证问题模板
    IDENTITY_QUESTIONS = [
        "我记得你之前提到过{topic}，你还记得那次是怎么说的吗？",
        "你上次和我聊{topic}的时候，你的看法是什么？",
        "有件事想确认一下：你之前说过{quote}，这是你说的吗？",
    ]

    def __init__(self, db_path: str, user_id: str = "default"):
        self.db_path = db_path
        self.user_id = user_id
        self._init_db()
        self._profile_cache: Optional[Dict] = None

    def _init_db(self):
        with guarded_connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS user_profile (
                    user_id TEXT NOT NULL DEFAULT 'default',
                    key TEXT NOT NULL,
                    value TEXT NOT NULL,
                    updated_at TEXT,
                    PRIMARY KEY (user_id, key)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS personality_traits (
                    user_id TEXT NOT NULL DEFAULT 'default',
                    name TEXT NOT NULL,
                    data_json TEXT NOT NULL,
                    updated_at TEXT,
                    PRIMARY KEY (user_id, name)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS anomaly_records (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL DEFAULT 'default',
                    data_json TEXT NOT NULL,
                    timestamp TEXT
                )
            """)
            conn.commit()
        # 迁移旧数据库
        with guarded_connect(self.db_path) as conn:
            for table, col in [("user_profile","user_id"),("personality_traits","user_id"),("anomaly_records","user_id")]:
                cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]
                if col not in cols:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} TEXT DEFAULT \'default\'")
            conn.commit()

    # ── 画像读写 ──────────────────────────────

    def get_profile(self) -> Dict:
        with guarded_connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT key, value FROM user_profile WHERE user_id=?", (self.user_id,)
            ).fetchall()
        return {r[0]: json.loads(r[1]) for r in rows}

    def update_profile(self, key: str, value: Any):
        with guarded_connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO user_profile (user_id, key, value, updated_at) VALUES (?,?,?,?)",
                (self.user_id, key, json.dumps(value, ensure_ascii=False), datetime.now().isoformat())
            )
            conn.commit()

    # ── 性格特征 ──────────────────────────────

    def get_traits(self) -> List[PersonalityTrait]:
        with guarded_connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT data_json FROM personality_traits WHERE user_id=? "
                "ORDER BY json_extract(data_json,'$.confidence') DESC",
                (self.user_id,)
            ).fetchall()
        return [PersonalityTrait(**json.loads(r[0])) for r in rows]

    def add_or_reinforce_trait(self, name: str, category: str,
                                example: str = "", confidence_boost: float = 0.1):
        now = datetime.now().isoformat()
        with guarded_connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT data_json FROM personality_traits WHERE user_id=? AND name=?",
                (self.user_id, name)
            ).fetchone()
        if row:
            t = PersonalityTrait(**json.loads(row[0]))
            t.evidence_count += 1
            t.confidence = min(1.0, t.confidence + confidence_boost)
            t.last_seen = now
            if example and example not in t.examples:
                t.examples.append(example)
                if len(t.examples) > 3:
                    t.examples = t.examples[-3:]
        else:
            t = PersonalityTrait(name=name, category=category, confidence=confidence_boost,
                                  evidence_count=1, first_seen=now, last_seen=now,
                                  examples=[example] if example else [])
        with guarded_connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO personality_traits (user_id, name, data_json, updated_at) VALUES (?,?,?,?)",
                (self.user_id, name, json.dumps(t.to_dict(), ensure_ascii=False), now)
            )
            conn.commit()

    def get_confirmed_traits(self) -> List[PersonalityTrait]:
        return [t for t in self.get_traits() if t.evidence_count >= self.CONFIRMED_THRESHOLD]

    def get_emerging_traits(self) -> List[PersonalityTrait]:
        return [t for t in self.get_traits() if t.evidence_count < self.CONFIRMED_THRESHOLD]

    # ── 反常检测 ──────────────────────────────

    def check_anomaly(self, current_behavior: Dict) -> Optional[AnomalyRecord]:
        traits = self.get_confirmed_traits()
        if not traits:
            return None
        anomalies = []
        emotion = current_behavior.get("emotion", {})
        if emotion.get("valence", 0) < -0.5:
            positive_trait = next(
                (t for t in traits if "积极" in t.name or "乐观" in t.name), None)
            if positive_trait and positive_trait.confidence > 0.7:
                anomalies.append(AnomalyRecord(
                    timestamp=datetime.now().isoformat(),
                    description=f"情绪明显消极（valence={emotion.get('valence',0):.2f}），与平时不符",
                    normal_pattern=f"通常：{positive_trait.name}（置信度{positive_trait.confidence:.0%}）",
                    severity=0.6
                ))
        if anomalies:
            most_severe = max(anomalies, key=lambda a: a.severity)
            if most_severe.severity >= self.ANOMALY_THRESHOLD:
                self._save_anomaly(most_severe)
                return most_severe
        return None

    def _save_anomaly(self, anomaly: AnomalyRecord):
        with guarded_connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO anomaly_records (id, user_id, data_json, timestamp) VALUES (?,?,?,?)",
                (str(uuid.uuid4())[:8], self.user_id,
                 json.dumps(anomaly.to_dict(), ensure_ascii=False), anomaly.timestamp)
            )
            conn.commit()

    def get_recent_anomalies(self, limit: int = 5) -> List[AnomalyRecord]:
        with guarded_connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT data_json FROM anomaly_records WHERE user_id=? "
                "ORDER BY timestamp DESC LIMIT ?", (self.user_id, limit)
            ).fetchall()
        return [AnomalyRecord(**json.loads(r[0])) for r in rows]

    # ── 身份验证 ──────────────────────────────

    def generate_identity_question(self, memory_store=None) -> Optional[str]:
        traits = self.get_confirmed_traits()
        if not traits:
            return None
        import random
        trait = random.choice([t for t in traits if t.examples and t.confidence > 0.7] or traits[:1])
        return f"我想确认一下你的身份。你之前提到过{trait.name}，能简单说说是怎么回事吗？"

    def should_verify_identity(self) -> bool:
        unresolved = [a for a in self.get_recent_anomalies(limit=3) if not a.resolved]
        return len(unresolved) >= 2

    # ── LLM 提取特征（从对话中自动更新画像）────

    def extract_traits_from_interaction(
        self, user_input: str, llm_client, existing_summary: str = ""
    ):
        """
        让 LLM 从当前对话中提取用户特征，更新画像
        轻量调用，不影响主流程速度
        """
        if not llm_client:
            return

        prompt = f"""从以下对话中提取用户的性格特征、兴趣爱好、行为习惯、价值观等信息。

用户说的话："{user_input}"

已知用户特征（供参考，不要重复）：
{existing_summary[:300] if existing_summary else "暂无"}

请以 JSON 格式输出发现的新特征（没有则返回空列表）：
{{
  "traits": [
    {{
      "name": "特征描述（10字以内，如：喜欢AGI研究、说话简洁直接）",
      "category": "interest/style/value/habit/emotion之一",
      "example": "支撑这个判断的原文片段（20字以内）",
      "confidence_boost": 0.1到0.3之间（这条证据的置信度贡献）
    }}
  ]
}}

重要：
- 只提取有明确证据支撑的特征，不要猜测
- 一次最多提取3个特征
- 只输出JSON"""

        try:
            raw = llm_client.generate(prompt, max_tokens=300, temperature=0.3)
            import re
            m = re.search(r'\{[\s\S]*\}', raw)
            if not m:
                return
            data = json.loads(m.group())
            for t in data.get("traits", [])[:3]:
                if t.get("name") and t.get("category"):
                    self.add_or_reinforce_trait(
                        name=t["name"],
                        category=t["category"],
                        example=t.get("example", ""),
                        confidence_boost=float(t.get("confidence_boost", 0.1))
                    )
        except Exception:
            pass  # 画像更新失败不影响主流程

    # ── 画像摘要（注入 prompt）─────────────────

    def format_for_prompt(self) -> str:
        """
        格式化用户画像为 prompt 可用的文本
        始终注入，不需要检索
        """
        traits = self.get_traits()
        if not traits:
            return "【用户画像】尚在建立中，暂无确定性格特征。"

        confirmed = [t for t in traits if t.evidence_count >= self.CONFIRMED_THRESHOLD]
        emerging  = [t for t in traits if t.evidence_count < self.CONFIRMED_THRESHOLD]

        lines = ["【用户画像（逐步累积）】"]

        if confirmed:
            lines.append("▌ 已确认特征：")
            for t in confirmed[:8]:
                conf_bar = "█" * int(t.confidence * 5) + "░" * (5 - int(t.confidence * 5))
                lines.append(
                    f"  {conf_bar} {t.name}"
                    f"（{t.category}，观察{t.evidence_count}次）"
                )

        if emerging:
            lines.append("▌ 初步观察（待确认）：")
            for t in emerging[:5]:
                lines.append(f"  · {t.name}（{t.evidence_count}次观察）")

        anomalies = self.get_recent_anomalies(limit=2)
        unresolved = [a for a in anomalies if not a.resolved]
        if unresolved:
            lines.append("▌ ⚠️ 近期反常行为：")
            for a in unresolved:
                lines.append(f"  · {a.description}")

        return "\n".join(lines)
