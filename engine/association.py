"""
记忆关联网络
实现人类记忆中「触景生情」「睹物思人」的关联机制

核心思想：
  每条记忆不是孤立节点，而是网络中的一个点。
  节点之间的边有类型（感官/情绪/空间/时间）和强度。
  检索时不只返回直接匹配，还沿关联边「涟漪扩散」，
  就像真实的人类记忆一样被触发。
"""

import sqlite3
from engine.db_guard import guarded_connect
import json
import uuid
from typing import List, Dict, Tuple, Optional, Set
from dataclasses import dataclass, field
from enum import Enum


class AssociationType(Enum):
    """关联类型 - 两条记忆之间的连接原因"""
    SENSORY   = "sensory"    # 感官触发：同一种味道/气味/声音
    SPATIAL   = "spatial"    # 空间触发：同一个地点
    TEMPORAL  = "temporal"   # 时间触发：同一时期/季节
    EMOTIONAL = "emotional"  # 情绪触发：相同的情绪体验
    PERSON    = "person"     # 人物触发：同一个人
    SEMANTIC  = "semantic"   # 语义触发：相关概念/话题
    CAUSAL    = "causal"     # 因果触发：前因后果


# 关联类型的中文描述（用于生成「想起了」的说明）
ASSOC_DESC = {
    AssociationType.SENSORY:   "感官触发",
    AssociationType.SPATIAL:   "地点触发",
    AssociationType.TEMPORAL:  "时间触发",
    AssociationType.EMOTIONAL: "情绪共鸣",
    AssociationType.PERSON:    "人物联想",
    AssociationType.SEMANTIC:  "话题关联",
    AssociationType.CAUSAL:    "因果联想",
}


@dataclass
class MemoryEdge:
    """记忆关联边"""
    source_id: str               # 触发节点
    target_id: str               # 被联想到的节点
    assoc_type: AssociationType  # 关联类型
    strength: float              # 关联强度 0~1（越强越容易被触发）
    shared_elements: List[str]   # 共同元素（如：「红烧肉」「那家餐厅」）
    edge_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])

    def to_dict(self) -> dict:
        return {
            "edge_id": self.edge_id,
            "source_id": self.source_id,
            "target_id": self.target_id,
            "assoc_type": self.assoc_type.value,
            "strength": self.strength,
            "shared_elements": self.shared_elements
        }


@dataclass
class AssociationRipple:
    """一次关联涟漪的结果"""
    triggered_memory_id: str     # 被触发的记忆ID
    triggered_by_id: str         # 谁触发了它
    assoc_type: AssociationType  # 触发类型
    strength: float              # 触发强度
    depth: int                   # 涟漪深度（1=直接关联，2=间接）
    shared_elements: List[str]   # 共同元素
    chain: List[str]             # 完整的触发链路


class MemoryAssociationNetwork:
    """
    记忆关联网络
    基于 SQLite 的有向加权图，支持涟漪式扩散检索
    """

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_tables()

    def _init_tables(self):
        with guarded_connect(self.db_path) as conn:
            # 关联边表
            conn.execute("""
                CREATE TABLE IF NOT EXISTS memory_edges (
                    edge_id     TEXT PRIMARY KEY,
                    source_id   TEXT NOT NULL,
                    target_id   TEXT NOT NULL,
                    assoc_type  TEXT NOT NULL,
                    strength    REAL NOT NULL,
                    shared_json TEXT,
                    created_at  TEXT DEFAULT (datetime('now'))
                )
            """)
            # 索引：快速查找某节点的所有出边/入边
            conn.execute("CREATE INDEX IF NOT EXISTS idx_src ON memory_edges(source_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_tgt ON memory_edges(target_id)")

            # 实体表：追踪「人物」「地点」「感官元素」
            conn.execute("""
                CREATE TABLE IF NOT EXISTS memory_entities (
                    entity_id   TEXT PRIMARY KEY,
                    name        TEXT NOT NULL,
                    entity_type TEXT NOT NULL,
                    memory_ids  TEXT NOT NULL
                )
            """)
            conn.commit()

    # ── 建立关联 ──────────────────────────────────────

    def link(
        self,
        source_id: str,
        target_id: str,
        assoc_type: AssociationType,
        strength: float,
        shared_elements: List[str] = None
    ) -> str:
        """建立两条记忆之间的关联"""
        edge = MemoryEdge(
            source_id=source_id,
            target_id=target_id,
            assoc_type=assoc_type,
            strength=min(1.0, max(0.0, strength)),
            shared_elements=shared_elements or []
        )
        with guarded_connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO memory_edges VALUES (?,?,?,?,?,?,datetime('now'))",
                (edge.edge_id, source_id, target_id,
                 assoc_type.value, edge.strength,
                 json.dumps(edge.shared_elements))
            )
            conn.commit()
        return edge.edge_id

    def link_bidirectional(
        self,
        id_a: str,
        id_b: str,
        assoc_type: AssociationType,
        strength: float,
        shared_elements: List[str] = None
    ):
        """双向关联（两者互相触发）"""
        self.link(id_a, id_b, assoc_type, strength, shared_elements)
        self.link(id_b, id_a, assoc_type, strength, shared_elements)

    def register_entity(
        self,
        name: str,
        entity_type: str,   # person / place / object / sensation
        memory_id: str
    ):
        """
        注册实体（人物/地点/感官元素）并关联到记忆
        同一实体出现在多条记忆中，自动建立关联
        """
        entity_id = f"{entity_type}:{name}"

        with guarded_connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT memory_ids FROM memory_entities WHERE entity_id=?",
                (entity_id,)
            ).fetchone()

            if row:
                existing_ids = json.loads(row[0])
                if memory_id not in existing_ids:
                    # 与已有记忆建立关联
                    for existing_id in existing_ids:
                        atype = self._entity_type_to_assoc(entity_type)
                        # 强度：同一重要实体，关联强
                        self.link_bidirectional(
                            memory_id, existing_id, atype,
                            strength=0.75,
                            shared_elements=[name]
                        )
                    existing_ids.append(memory_id)
                    conn.execute(
                        "UPDATE memory_entities SET memory_ids=? WHERE entity_id=?",
                        (json.dumps(existing_ids), entity_id)
                    )
            else:
                conn.execute(
                    "INSERT INTO memory_entities VALUES (?,?,?,?)",
                    (entity_id, name, entity_type, json.dumps([memory_id]))
                )
            conn.commit()

    # ── 涟漪扩散检索 ─────────────────────────────────

    def ripple(
        self,
        seed_memory_ids: List[str],
        max_depth: int = 2,
        min_strength: float = 0.3,
        max_results: int = 8
    ) -> List[AssociationRipple]:
        """
        从种子记忆出发，沿关联边扩散，找到所有可能被触发的记忆。
        
        就像水面的涟漪：
          深度1 = 直接关联（吃到红烧肉 → 想起那家餐厅）
          深度2 = 间接关联（那家餐厅 → 想起喜欢的那个人）
        """
        ripples: List[AssociationRipple] = []
        visited: Set[str] = set(seed_memory_ids)
        current_wave = [(mid, None, None, 1.0, [mid]) for mid in seed_memory_ids]
        # (memory_id, triggered_by, edge, cumulative_strength, chain)

        for depth in range(1, max_depth + 1):
            next_wave = []

            for src_id, parent_id, parent_edge, parent_strength, chain in current_wave:
                # 查找从 src_id 出发的所有边
                edges = self._get_outgoing_edges(src_id, min_strength)

                for edge in edges:
                    tgt_id = edge["target_id"]
                    if tgt_id in visited:
                        continue

                    # 累积强度（随深度衰减）
                    cumulative = parent_strength * edge["strength"] * (0.8 ** (depth - 1))
                    if cumulative < min_strength * 0.5:
                        continue

                    visited.add(tgt_id)
                    new_chain = chain + [tgt_id]

                    ripple = AssociationRipple(
                        triggered_memory_id=tgt_id,
                        triggered_by_id=src_id,
                        assoc_type=AssociationType(edge["assoc_type"]),
                        strength=cumulative,
                        depth=depth,
                        shared_elements=edge["shared_elements"],
                        chain=new_chain
                    )
                    ripples.append(ripple)
                    next_wave.append((tgt_id, src_id, edge, cumulative, new_chain))

            current_wave = next_wave
            if not current_wave:
                break

        # 按强度排序
        ripples.sort(key=lambda r: r.strength, reverse=True)
        return ripples[:max_results]

    def get_associations(self, memory_id: str) -> List[Dict]:
        """获取某条记忆的所有直接关联"""
        return self._get_outgoing_edges(memory_id, min_strength=0.0)

    def strengthen(self, source_id: str, target_id: str, delta: float = 0.05):
        """强化两条记忆之间的关联（每次被触发都会加强）"""
        with guarded_connect(self.db_path) as conn:
            conn.execute("""
                UPDATE memory_edges
                SET strength = MIN(1.0, strength + ?)
                WHERE source_id=? AND target_id=?
            """, (delta, source_id, target_id))
            conn.commit()

    def get_stats(self) -> Dict:
        with guarded_connect(self.db_path) as conn:
            edges = conn.execute("SELECT COUNT(*) FROM memory_edges").fetchone()[0]
            entities = conn.execute("SELECT COUNT(*) FROM memory_entities").fetchone()[0]
            by_type = conn.execute(
                "SELECT assoc_type, COUNT(*) FROM memory_edges GROUP BY assoc_type"
            ).fetchall()
        return {
            "total_edges": edges,
            "total_entities": entities,
            "by_type": dict(by_type)
        }

    # ── 内部工具 ──────────────────────────────────────

    def _get_outgoing_edges(self, memory_id: str, min_strength: float) -> List[Dict]:
        with guarded_connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT target_id, assoc_type, strength, shared_json "
                "FROM memory_edges WHERE source_id=? AND strength>=? ORDER BY strength DESC",
                (memory_id, min_strength)
            ).fetchall()
        return [
            {
                "target_id": r[0],
                "assoc_type": r[1],
                "strength": r[2],
                "shared_elements": json.loads(r[3] or "[]")
            }
            for r in rows
        ]

    def _entity_type_to_assoc(self, entity_type: str) -> AssociationType:
        return {
            "person":    AssociationType.PERSON,
            "place":     AssociationType.SPATIAL,
            "object":    AssociationType.SENSORY,
            "sensation": AssociationType.SENSORY,
            "time":      AssociationType.TEMPORAL,
        }.get(entity_type, AssociationType.SEMANTIC)


# ── 关联分析器：从记忆内容自动提取实体和关联 ─────────────

class AssociationAnalyzer:
    """
    分析两条记忆之间应该建立什么类型的关联
    在存储新记忆时调用，自动建立关联网络
    """

    # 感官词库
    SENSORY_WORDS = {
        "味道", "气味", "声音", "触感", "颜色", "光线",
        "温度", "味", "香", "臭", "甜", "苦", "酸", "咸",
        "辣", "软", "硬", "冷", "热", "暖", "凉"
    }

    # 地点词库
    PLACE_WORDS = {
        "餐厅", "咖啡馆", "公园", "学校", "家", "公司",
        "医院", "商场", "街道", "海边", "山上", "车站",
        "机场", "图书馆", "电影院", "宿舍", "城市"
    }

    @classmethod
    def extract_entities(cls, content: str, tags: List[str]) -> Dict[str, List[str]]:
        """
        从内容和标签中提取实体
        返回 {entity_type: [entity_names]}
        """
        entities: Dict[str, List[str]] = {
            "person": [],
            "place": [],
            "sensation": [],
            "time": []
        }

        # 从标签中提取
        for tag in tags:
            tag_lower = tag.lower()
            if any(w in tag for w in cls.PLACE_WORDS):
                entities["place"].append(tag)
            elif any(w in tag for w in cls.SENSORY_WORDS):
                entities["sensation"].append(tag)
            elif tag.startswith("@") or "人" in tag:
                entities["person"].append(tag)
            elif any(w in tag for w in ["年", "月", "季", "春", "夏", "秋", "冬"]):
                entities["time"].append(tag)

        return entities

    @classmethod
    def infer_association_type(
        cls,
        content_a: str,
        content_b: str,
        tags_a: List[str],
        tags_b: List[str]
    ) -> Tuple[AssociationType, float, List[str]]:
        """
        推断两条记忆之间最合适的关联类型和强度
        返回 (关联类型, 强度, 共同元素)
        """
        shared = set(tags_a) & set(tags_b)
        shared_list = list(shared)

        if not shared:
            return AssociationType.SEMANTIC, 0.2, []

        # 有共同人物标签
        person_shared = [t for t in shared if t.startswith("@")]
        if person_shared:
            return AssociationType.PERSON, 0.85, person_shared

        # 有共同地点
        place_shared = [t for t in shared if any(w in t for w in cls.PLACE_WORDS)]
        if place_shared:
            return AssociationType.SPATIAL, 0.8, place_shared

        # 有共同感官元素
        sensation_shared = [t for t in shared if any(w in t for w in cls.SENSORY_WORDS)]
        if sensation_shared:
            return AssociationType.SENSORY, 0.75, sensation_shared

        # 其他共同标签
        strength = min(0.7, 0.3 + len(shared_list) * 0.15)
        return AssociationType.SEMANTIC, strength, shared_list


def format_ripple_for_prompt(
    ripples: List[AssociationRipple],
    memory_contents: Dict[str, str]  # memory_id -> content
) -> str:
    """
    将涟漪结果格式化为 A 层可用的 prompt 片段
    描述「这让我想起了...」的过程
    """
    if not ripples:
        return ""

    lines = ["\n【关联记忆 · 被触发的联想】"]

    for r in ripples[:4]:
        content = memory_contents.get(r.triggered_memory_id, "")
        if not content:
            continue

        assoc_label = ASSOC_DESC.get(r.assoc_type, r.assoc_type.value)
        shared_str = f"（共同：{', '.join(r.shared_elements)}）" if r.shared_elements else ""

        depth_str = "直接联想" if r.depth == 1 else f"深层联想(第{r.depth}层)"
        strength_str = f"{r.strength:.0%}"

        lines.append(
            f"  [{depth_str} · {assoc_label} · {strength_str}] {shared_str}\n"
            f"  → {content[:120]}{'...' if len(content) > 120 else ''}"
        )

    return "\n".join(lines)
