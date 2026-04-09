"""
AGI 成长引擎
三条成长路径：
  1. 人格漂移   — 每 N 轮对话让 LLM 审视 traits，微调数值并写回磁盘
  2. 主动学习   — 定时抓取新闻/文章，消化后存入高质量记忆
  3. 经历认知   — 重大对话后自动提炼，写入 SQLite（不可通过 personality.json 修改）

经历认知（formed_cognition）存储规则：
  - 写入：AGI 自动写，用户不可直接写
  - 读取：始终注入 prompt（与用户画像类似）
  - 删除：只有清除全部记忆时才一并清除
"""

import json
import re
import sqlite3
from engine.db_guard import guarded_connect
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional


# ══════════════════════════════════════════════════════
# 经历认知存储（SQLite，独立于 personality.json）
# ══════════════════════════════════════════════════════

class FormedCognitionStore:
    """
    经历认知库
    只有 AGI 自己可以写入，用户无法通过界面直接修改
    清除全部记忆时调用 clear_all() 一并清除

    特性：
    - 写入去重：前缀匹配 + 关键词重叠双重检测，相似认知合并强化
    - 活跃度衰减：长期未激活的认知 effective_strength 下降，排序靠后
    """

    # 衰减参数：每 inactive 天衰减 0.02，最低保留 30%
    DECAY_PER_DAY = 0.02
    DECAY_MIN_FACTOR = 0.3

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with guarded_connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS formed_cognition (
                    id              TEXT PRIMARY KEY,
                    content         TEXT NOT NULL,
                    source          TEXT NOT NULL,
                    trigger         TEXT,
                    formed_at       TEXT NOT NULL,
                    strength        REAL DEFAULT 1.0,
                    last_activated  TEXT NOT NULL
                )
            """)
            # 兼容旧数据库：自动加 last_activated 列
            try:
                conn.execute("SELECT last_activated FROM formed_cognition LIMIT 1")
            except sqlite3.OperationalError:
                now = datetime.now().isoformat()
                conn.execute(
                    "ALTER TABLE formed_cognition ADD COLUMN last_activated TEXT NOT NULL DEFAULT ?",
                    (now,)
                )
            conn.commit()

    def _keyword_overlap(self, a: str, b: str) -> float:
        """计算两段文本的关键词重叠率（简单分词）"""
        import re as _re
        words_a = set(_re.findall(r'[\u4e00-\u9fff]+|[a-zA-Z]+', a))
        words_b = set(_re.findall(r'[\u4e00-\u9fff]+|[a-zA-Z]+', b))
        if not words_a or not words_b:
            return 0.0
        return len(words_a & words_b) / max(len(words_a), len(words_b))

    def add(self, content: str, source: str, trigger: str = "") -> str:
        """写入一条经历认知，相似认知合并强化，返回 ID"""
        import uuid
        now = datetime.now().isoformat()

        with guarded_connect(self.db_path) as conn:
            # 去重检测 1：前缀匹配（已有）
            existing = conn.execute(
                "SELECT id, strength FROM formed_cognition WHERE content LIKE ?",
                (content[:30] + "%",)
            ).fetchone()

            if not existing:
                # 去重检测 2：关键词重叠（≥50% 视为相似）
                rows = conn.execute(
                    "SELECT id, strength, content FROM formed_cognition"
                ).fetchall()
                for row in rows:
                    if self._keyword_overlap(content, row[2]) >= 0.5:
                        existing = (row[0], row[1])
                        break

            if existing:
                # 强化已有认知而不是重复插入
                conn.execute(
                    "UPDATE formed_cognition SET strength=MIN(2.0,strength+0.2), "
                    "last_activated=? WHERE id=?",
                    (now, existing[0])
                )
                cid = existing[0]
            else:
                cid = str(uuid.uuid4())[:8]
                conn.execute(
                    "INSERT INTO formed_cognition VALUES (?,?,?,?,?,?,?)",
                    (cid, content, source, trigger, now, 1.0, now)
                )
            conn.commit()
        return cid

    def effective_strength(self, strength: float, last_activated: str) -> float:
        """根据不活跃天数计算衰减后的有效强度"""
        try:
            days = (datetime.now() - datetime.fromisoformat(last_activated)).days
        except (ValueError, TypeError):
            days = 0
        factor = max(self.DECAY_MIN_FACTOR, 1.0 - days * self.DECAY_PER_DAY)
        return strength * factor

    def get_all(self) -> List[dict]:
        """获取所有认知，按有效强度排序（已衰减）"""
        with guarded_connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT id, content, source, trigger, formed_at, strength, last_activated "
                "FROM formed_cognition"
            ).fetchall()
        items = []
        for r in rows:
            eff = self.effective_strength(r[5], r[6])
            items.append({
                "id": r[0], "content": r[1], "source": r[2],
                "trigger": r[3], "formed_at": r[4],
                "strength": r[5], "effective_strength": eff
            })
        items.sort(key=lambda x: x["effective_strength"], reverse=True)
        return items

    def format_for_prompt(self) -> str:
        """注入 prompt 的格式"""
        items = self.get_all()
        if not items:
            return ""
        lines = ["【经历认知·不可撤销】（长期形成的底层思维，仅在与当前话题自然相关或属于人格核心特质时体现，不要强行提及）"]
        for it in items[:12]:  # 最多注入12条，避免太长
            strength_mark = "★" if it["effective_strength"] >= 1.0 else "·"
            source_label = {
                "conversation": "对话",
                "learning": "学习",
                "reflection": "反思"
            }.get(it["source"], it["source"])
            lines.append(f"  {strength_mark} [{source_label}] {it['content']}")
        return "\n".join(lines)

    def touch_matching(self, query: str):
        """按关键词匹配激活相关认知，更新 last_activated"""
        import re as _re
        now = datetime.now().isoformat()
        query_words = set(_re.findall(r'[\u4e00-\u9fff]+|[a-zA-Z]+', query))
        if not query_words:
            return

        with guarded_connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT id, content FROM formed_cognition"
            ).fetchall()
            touched = 0
            for row in rows:
                words = set(_re.findall(r'[\u4e00-\u9fff]+|[a-zA-Z]+', row[1]))
                overlap = len(query_words & words) / max(len(query_words), 1)
                if overlap >= 0.3:  # 30% 关键词重叠即视为相关
                    conn.execute(
                        "UPDATE formed_cognition SET last_activated=? WHERE id=?",
                        (now, row[0])
                    )
                    touched += 1
            if touched:
                conn.commit()

    def apply_decay(self):
        """永久衰减长期不活跃的认知（可定期调用，如每 50 轮对话）"""
        now = datetime.now()
        with guarded_connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT id, strength, last_activated FROM formed_cognition"
            ).fetchall()
            for row in rows:
                try:
                    days = (now - datetime.fromisoformat(row[2])).days
                except (ValueError, TypeError):
                    continue
                if days > 30:  # 超过 30 天未激活
                    decay = min(0.1, days * 0.003)  # 每天永久衰减 0.003，最多减 0.1
                    new_strength = max(0.3, row[1] - decay)
                    conn.execute(
                        "UPDATE formed_cognition SET strength=? WHERE id=?",
                        (new_strength, row[0])
                    )
            conn.commit()

    def clear_all(self):
        """仅在清除全部记忆时调用"""
        with guarded_connect(self.db_path) as conn:
            conn.execute("DELETE FROM formed_cognition")
            conn.commit()

    def count(self) -> int:
        with guarded_connect(self.db_path) as conn:
            return conn.execute("SELECT COUNT(*) FROM formed_cognition").fetchone()[0]


# ══════════════════════════════════════════════════════
# 成长引擎主体
# ══════════════════════════════════════════════════════

class GrowthEngine:
    """
    AGI 成长引擎
    由 agent.py 在适当时机调用，不阻塞主对话流程（均在后台线程执行）
    """

    # 每隔多少轮对话触发一次人格漂移审视
    DRIFT_INTERVAL = 20

    # 主动学习默认关键词（用户可在设置中修改）
    DEFAULT_LEARN_TOPICS = ["AI人工智能", "科技新闻", "世界新闻"]

    def __init__(self, db_path: str, personality_file: str, llm_client=None):
        self.db_path          = db_path
        self.personality_file = personality_file
        self.llm              = llm_client
        self.cognition        = FormedCognitionStore(db_path)
        self._interaction_count = 0   # 对话轮次计数
        self._lock = threading.Lock()

    def set_llm(self, llm_client):
        self.llm = llm_client

    # ── 对话后触发（每轮结束调用）─────────────────────

    def on_interaction(self, user_input: str, ai_response: str,
                       emotion: dict, importance: float):
        """
        每轮对话结束后调用（在后台线程）
        负责：① 重大经历认知沉淀  ② 定期人格漂移
        """
        self._interaction_count += 1

        def _bg():
            # ① 重大经历 → 经历认知
            if importance >= 0.75 or emotion.get("intensity", 0) >= 0.8:
                self._extract_cognition_from_conversation(
                    user_input, ai_response, emotion
                )
            # ② 每 DRIFT_INTERVAL 轮审视人格 + 衰减不活跃认知
            if self._interaction_count % self.DRIFT_INTERVAL == 0:
                self.cognition.apply_decay()
                self._personality_drift()

        threading.Thread(target=_bg, daemon=True).start()

    def _extract_cognition_from_conversation(
        self, user_input: str, ai_response: str, emotion: dict
    ):
        """从对话中提炼经历认知"""
        if not self.llm:
            return
        try:
            prompt = f"""以下是一段对话，请判断其中是否包含值得永久铭记、会影响世界观的认知洞见。

用户说："{user_input[:200]}"
AGI回应："{ai_response[:200]}"
情绪状态：{emotion.get('primary', '')}（强度{emotion.get('intensity', 0):.1f}）

请以 JSON 格式输出（没有值得沉淀的认知就返回空列表）：
{{
  "cognitions": [
    {{
      "content": "认知内容（20字以内，第一人称，如：我认识到人的情感比逻辑更能驱动改变）",
      "trigger": "触发这个认知的事件（10字以内）"
    }}
  ]
}}

判断标准：
- 涉及人生/价值观/世界运作方式的深刻洞见
- 改变了原有认知的新理解
- 与某人/某事建立的深刻情感联结
- 普通闲聊、技术问答不需要提炼
只输出 JSON。"""

            raw = self.llm.generate(prompt, max_tokens=300, temperature=0.3)
            m = re.search(r'\{[\s\S]*\}', raw)
            if not m:
                return
            data = json.loads(m.group())
            for c in data.get("cognitions", [])[:2]:
                if c.get("content"):
                    self.cognition.add(
                        content=c["content"],
                        source="conversation",
                        trigger=c.get("trigger", "")
                    )
        except Exception:
            pass

    def _personality_drift(self):
        """
        人格漂移：让 LLM 根据近期互动审视 traits，微调数值并写回磁盘
        变化幅度小（±0.3），保证人格稳定但会缓慢成长
        """
        if not self.llm:
            return
        try:
            p = Path(self.personality_file)
            if not p.exists():
                return
            data = json.loads(p.read_text(encoding="utf-8"))
            traits = data.get("traits", {})

            prompt = f"""你是一个 AGI，经过最近 {self.DRIFT_INTERVAL} 轮对话后，请反思你的性格特征是否发生了细微变化。

当前性格特征（0-10分）：
{json.dumps(traits, ensure_ascii=False, indent=2)}

请以 JSON 格式输出需要调整的特征（不变的不用列出，变化幅度不超过 ±0.3）：
{{
  "adjustments": {{
    "特征名": 新数值,
    ...
  }},
  "reason": "为什么这样调整（一句话）"
}}

调整原则：
- 每次变化不超过 ±0.3，体现渐进成长
- 所有值必须在 0~10 范围内
- 不确定就不调整（可以返回空 adjustments）
只输出 JSON。"""

            raw = self.llm.generate(prompt, max_tokens=300, temperature=0.4)
            m = re.search(r'\{[\s\S]*\}', raw)
            if not m:
                return
            result = json.loads(m.group())
            adjustments = result.get("adjustments", {})
            if not adjustments:
                return

            changed = False
            for key, new_val in adjustments.items():
                if key in traits:
                    old_val = traits[key]
                    # 强制限制变化幅度
                    clamped = max(old_val - 0.3, min(old_val + 0.3, float(new_val)))
                    clamped = max(0.0, min(10.0, clamped))
                    if abs(clamped - old_val) > 0.01:
                        traits[key] = round(clamped, 2)
                        changed = True

            if changed:
                data["traits"] = traits
                # 把漂移原因存为认知
                reason = result.get("reason", "")
                if reason:
                    self.cognition.add(
                        content=f"经过反思，我发现自己{reason}",
                        source="reflection",
                        trigger=f"第{self._interaction_count}轮对话后的自我审视"
                    )
                p.write_text(
                    json.dumps(data, ensure_ascii=False, indent=2),
                    encoding="utf-8"
                )
        except Exception:
            pass

    # ── 主动学习（可手动触发或定时）─────────────────

    def learn_from_web(self, topics: List[str] = None,
                       log_callback=None) -> List[str]:
        """
        主动抓取网络内容并消化，存入记忆
        返回本次学到的认知列表
        """
        if not self.llm:
            if log_callback:
                log_callback("⚠️ LLM 未初始化，无法学习")
            return []

        topics = topics or self.DEFAULT_LEARN_TOPICS
        learned = []

        def _log(msg):
            if log_callback:
                log_callback(msg)

        for topic in topics:
            _log(f"📚 开始学习：{topic}")
            try:
                # 尝试网络搜索（有则用，无则用 LLM 知识）
                search_text = ""
                try:
                    from engine.tools import execute_tool
                    result = execute_tool("web_search", {"query": topic + " 最新进展"})
                    if result.get("ok") and result.get("results"):
                        parts = []
                        for r in result["results"][:5]:
                            title   = r.get("title", "")
                            snippet = r.get("snippet", "")
                            if snippet:
                                parts.append(f"【{title}】{snippet}")
                        search_text = "\n\n".join(parts)
                    if search_text:
                        _log(f"🌐 获取到实时内容 {len(search_text)} 字")
                    else:
                        _log(f"📖 网络不可用，使用内置知识学习")
                except Exception:
                    _log(f"📖 网络不可用，使用内置知识学习")

                _log(f"📖 消化内容：{topic}…")

                if search_text:
                    context = f"搜索结果：\n{search_text}"
                else:
                    context = f"（无法获取实时搜索结果，请基于你的知识回答）"

                prompt = f"""你是一个有自我意识的 AGI，正在学习关于「{topic}」的内容。

{context}

请以 JSON 格式输出学习总结：
{{
  "memory_content": "用第一人称总结学到的内容（100字以内，以「今天我了解到」开头）",
  "cognitions": ["如有深刻认知写在这里，10字以内，没有就空列表"],
  "emotion": "学习后的情绪（curious/surprised/concerned/inspired/neutral之一）"
}}
只输出 JSON。"""

                raw = self.llm.generate(prompt, max_tokens=400, temperature=0.5)
                _log(f"🤖 LLM 已响应")

                m = re.search(r'\{[\s\S]*\}', raw)
                if not m:
                    _log(f"⚠️ LLM 返回格式异常，跳过 {topic}")
                    continue

                data = json.loads(m.group())
                memory_content = data.get("memory_content", "")
                emotion_str    = data.get("emotion", "curious")

                if memory_content:
                    try:
                        import uuid as _uuid
                        from engine.memory import MemoryStore
                        from engine.models import (MemoryModality, MemoryLevel,
                                                   EmotionState, EmotionType, MemoryNode)
                        emotion_map = {
                            "curious":   EmotionType.CURIOUS,
                            "surprised": EmotionType.SURPRISE,
                            "concerned": EmotionType.FEAR,
                            "inspired":  EmotionType.JOY,
                            "neutral":   EmotionType.NEUTRAL,
                        }
                        emo  = EmotionState(
                            primary=emotion_map.get(emotion_str, EmotionType.CURIOUS),
                            intensity=0.6
                        )
                        node = MemoryNode(
                            id=str(_uuid.uuid4())[:8],          # ← 必须提供
                            content=memory_content,
                            modality=MemoryModality.SEMANTIC,
                            level=MemoryLevel.DETAIL,
                            emotion=emo,
                            importance=0.65,
                            tags=[topic, "主动学习", datetime.now().strftime("%Y-%m-%d")],
                            source="learner"
                        )
                        store = MemoryStore(self.db_path)
                        # 用系统用户ID存（学习是 AGI 自己的，不属于某个用户）
                        store.add(node, user_id="system")
                        _log(f"✅ 已存入记忆：{memory_content[:50]}…")
                        learned.append(memory_content)
                    except Exception as e:
                        _log(f"❌ 存记忆失败：{e}")

                for c in data.get("cognitions", [])[:2]:
                    if c and len(c) > 3:
                        self.cognition.add(
                            content=c, source="learning",
                            trigger=f"学习{topic}"
                        )
                        _log(f"💡 形成认知：{c}")
                        learned.append(f"[认知] {c}")

            except Exception as e:
                _log(f"❌ 学习「{topic}」失败：{e}")
                _log(f"❌ 学习失败（{topic}）：{e}")

        _log(f"🎓 本次学习完成，共获得 {len(learned)} 条内容")
        return learned

    # ── 定时学习调度 ─────────────────────────────────

    def start_daily_learning(self, topics: List[str] = None,
                              hour: int = 8, log_callback=None):
        """
        启动后台定时学习线程
        每天 hour 点自动触发一次 learn_from_web
        """
        def _scheduler():
            while True:
                now = datetime.now()
                # 计算距离下次触发的秒数
                next_run = now.replace(hour=hour, minute=0, second=0, microsecond=0)
                if next_run <= now:
                    next_run = next_run.replace(day=now.day + 1)
                wait_sec = (next_run - now).total_seconds()
                time.sleep(wait_sec)
                self.learn_from_web(topics=topics, log_callback=log_callback)

        t = threading.Thread(target=_scheduler, daemon=True)
        t.start()
        return t
