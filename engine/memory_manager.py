"""
分层记忆管理器 v3
实现你设计的两阶段检索：

阶段一：向量检索大纲 + 关联网络涟漪
  → 得到最相关的大纲列表（精炼关键词）

阶段二：大纲命中 → 定向拉取对应细纲/细节
  → 不是再次全量检索，而是通过 base_id 精准展开
  → 就像：在书的目录找到章节名 → 翻到那一页读内容

最终：LLM 综合「上下文 + 大纲导航图 + 定向展开的细节」作答
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from engine.memory import MemoryStore, MemoryLevel, MemoryModality
from engine.models import MemoryNode, EmotionState
from typing import Dict, List, Tuple, Any, Optional
import uuid


class HierarchicalMemoryManager:
    def __init__(self, store: MemoryStore, association_network=None,
                 llm_client=None):
        self.store = store
        self.net   = association_network
        self.llm   = llm_client

    # ══════════════════════════════════════════════
    # 两阶段检索（核心）
    # ══════════════════════════════════════════════
    def hierarchical_search(
        self, query: str,
        summary_k:   int = 10,
        expand_top:  int = 5,
        outline_k:   int = 6,
        detail_k:    int = 3,
        user_id:     str = None,
    ) -> Dict[str, Any]:
        """
        两阶段检索，user_id 限定检索范围
        """
        results: Dict[str, Any] = {
            "summary":          [],
            "outline":          [],
            "detail":           [],
            "directed_expand":  [],
            "ripples":          [],
        }

        # ══ 第一阶段：检索大纲 ══════════════════
        summaries = self.store.search_by_level(
            query, MemoryLevel.SUMMARY, top_k=summary_k, user_id=user_id
        )
        results["summary"] = summaries

        if not summaries:
            return results

        # ══ 关联网络涟漪（基于大纲种子） ════════
        if self.net:
            seed_ids = [n.id for n, _ in summaries[:5]]
            ripples = self.net.ripple(
                seed_ids, max_depth=2, min_strength=0.2
            )
            results["ripples"] = ripples
            # 强化被触发的关联
            for r in ripples:
                self.net.strengthen(r.triggered_by_id, r.triggered_memory_id)

            # 把涟漪触发的记忆也加入大纲种子（扩展定向展开范围）
            ripple_summary_ids = []
            for r in ripples:
                if r.triggered_memory_id.endswith("_summary"):
                    ripple_summary_ids.append(r.triggered_memory_id)

            # 从涟漪中拉取对应细节
            if ripple_summary_ids:
                ripple_details = self.store.get_by_base_ids(
                    ripple_summary_ids, levels=["outline"]
                )
                results["ripple_details"] = ripple_details

        # ══ 第二阶段：定向展开前N条大纲 ════════
        # 取评分最高的 expand_top 条大纲，精准拉对应细纲和细节
        top_summaries = summaries[:expand_top]
        expand_ids = [node.id for node, score in top_summaries]

        directed_nodes = self.store.get_by_base_ids(
            expand_ids, levels=["outline", "detail"]
        )
        results["directed_expand"] = directed_nodes

        # 把定向展开的结果也分入 outline/detail
        for node in directed_nodes:
            if node.level == MemoryLevel.OUTLINE:
                # 避免重复（后续补充检索可能重叠）
                existing_ids = {n.id for n, _ in results["outline"]}
                if node.id not in existing_ids:
                    results["outline"].append((node, 1.0))
            elif node.level == MemoryLevel.DETAIL:
                existing_ids = {n.id for n, _ in results["detail"]}
                if node.id not in existing_ids:
                    results["detail"].append((node, 1.0))

        # ══ 补充检索（覆盖没有大纲对应关系的记忆）══
        extra_outlines = self.store.search_by_level(
            query, MemoryLevel.OUTLINE, top_k=outline_k, user_id=user_id
        )
        for node, score in extra_outlines:
            existing_ids = {n.id for n, _ in results["outline"]}
            if node.id not in existing_ids:
                results["outline"].append((node, score))

        extra_details = self.store.search_by_level(
            query, MemoryLevel.DETAIL, top_k=detail_k, user_id=user_id
        )
        for node, score in extra_details:
            existing_ids = {n.id for n, _ in results["detail"]}
            if node.id not in existing_ids:
                results["detail"].append((node, score))

        # 更新访问记录
        for node, _ in (results["summary"] + results["outline"] + results["detail"]):
            self.store.update_access(node.id)

        return results

    # ══════════════════════════════════════════════
    # 存储（大纲精炼）
    # ══════════════════════════════════════════════
    def store_with_hierarchy(
        self, content: str, modality: MemoryModality,
        emotion: EmotionState, importance: float,
        tags: List[str] = None, source: str = "conversation",
        user_id: str = "default",
        raw_content: str = None   # 原始对话内容，细节层用这个
    ) -> Dict[str, str]:
        stored_ids = {}
        base_id = str(uuid.uuid4())[:8]
        tags = tags or []

        # 细节层 — 存原始完整对话（如果提供），否则存 content
        detail_text = raw_content if raw_content else content
        if emotion.is_strong() or importance >= 0.8:
            n = MemoryNode(
                id=f"{base_id}_detail", content=detail_text,
                modality=modality, level=MemoryLevel.DETAIL,
                emotion=emotion, importance=importance,
                tags=tags, source=source
            )
            stored_ids["detail"] = self.store.add(n, user_id=user_id)

        # 细纲层 — 存摘要的前500字
        if importance >= 0.4 or emotion.is_moderate():
            outline_content = content[:500] + "…" if len(content) > 500 else content
            n = MemoryNode(
                id=f"{base_id}_outline", content=outline_content,
                modality=modality, level=MemoryLevel.OUTLINE,
                emotion=emotion, importance=importance,
                tags=tags, source=source
            )
            stored_ids["outline"] = self.store.add(n, user_id=user_id)

        # 大纲层（精炼摘要，是检索的入口）
        summary_content = self._make_summary(content, tags, importance, emotion)
        n = MemoryNode(
            id=f"{base_id}_summary", content=summary_content,
            modality=modality, level=MemoryLevel.SUMMARY,
            emotion=emotion, importance=importance,
            tags=tags, source=source
        )
        stored_ids["summary"] = self.store.add(n, user_id=user_id)

        # 关联网络
        if self.net and tags:
            from engine.association import AssociationAnalyzer
            entities = AssociationAnalyzer.extract_entities(content, tags)
            primary_id = (stored_ids.get("detail")
                          or stored_ids.get("outline")
                          or stored_ids.get("summary"))
            for etype, enames in entities.items():
                for ename in enames:
                    self.net.register_entity(ename, etype, primary_id)

        return stored_ids

    def _make_summary(self, content: str, tags: List[str],
                      importance: float, emotion: EmotionState) -> str:
        """
        大纲精炼：简短但信息密度高
        格式：[情绪标记] 核心事件第一句 #标签
        目标：20-60字，让向量检索能命中，让人一眼看懂这条记忆是关于什么的
        """
        emotion_mark = ""
        if emotion.intensity >= 0.6:
            emotion_mark = f"[{emotion.primary.value}] "

        importance_mark = "★ " if importance >= 0.8 else ""

        # 提取第一句（最核心的信息通常在开头）
        for sep in ["。", "！", "？", "…", "\n"]:
            if sep in content:
                first = content.split(sep)[0].strip()
                if len(first) >= 10:
                    break
        else:
            first = content[:80]

        first = first[:80]   # 大纲核心不超过80字

        tag_str = " ".join(f"#{t}" for t in tags[:4]) if tags else ""

        parts = [importance_mark + emotion_mark + first]
        if tag_str:
            parts.append(tag_str)

        return "  ".join(parts)[:200]

    # ══════════════════════════════════════════════
    # 格式化（清晰展示两阶段结果）
    # ══════════════════════════════════════════════
    def format_for_prompt(self, results: Dict[str, Any]) -> str:
        """
        格式化为 LLM 可读的记忆上下文
        清晰分层：大纲导航图 → 定向展开的细节
        """
        if not results or not results.get("summary"):
            return "（暂无相关长期记忆）"

        lines = ["【长期记忆检索结果】"]

        # ── 大纲导航图（所有命中的大纲）──────
        summaries = results.get("summary", [])
        if summaries:
            lines.append(f"\n▌ 记忆大纲（{len(summaries)} 条命中）")
            for i, (node, score) in enumerate(summaries, 1):
                lines.append(f"  {i}. {node.content}")

        # ── 定向展开的细节（最重要的部分）────
        directed = results.get("directed_expand", [])
        outline_nodes = [n for n in directed if n.level == MemoryLevel.OUTLINE]
        detail_nodes  = [n for n in directed if n.level == MemoryLevel.DETAIL]

        # 补充额外检索的
        for node, _ in results.get("outline", []):
            if node not in outline_nodes:
                outline_nodes.append(node)
        for node, _ in results.get("detail", []):
            if node not in detail_nodes:
                detail_nodes.append(node)

        if outline_nodes:
            lines.append(f"\n▌ 相关细节摘要（{len(outline_nodes)} 条）")
            for node in outline_nodes[:6]:
                e = node.emotion
                e_str = f" [{e.primary.value}·{e.intensity:.1f}]" if e.intensity >= 0.5 else ""
                lines.append(f"  · {node.content[:500]}{e_str}")

        if detail_nodes:
            lines.append(f"\n▌ 深度记忆（高重要性，{len(detail_nodes)} 条）")
            for node in detail_nodes[:3]:
                lines.append(f"  ▪ {node.content[:800]}")

        # ── 关联网络触发的记忆 ────────────────
        ripples = results.get("ripples", [])
        ripple_details = results.get("ripple_details", [])
        if ripples:
            from engine.association import ASSOC_DESC
            lines.append(f"\n▌ 关联记忆（涟漪触发 {len(ripples)} 条）")
            mem_contents = {}
            for node in ripple_details:
                mem_contents[node.id] = node.content
            for r in ripples[:4]:
                assoc_label = ASSOC_DESC.get(r.assoc_type, r.assoc_type.value)
                shared_str = f"（{', '.join(r.shared_elements)}）" if r.shared_elements else ""
                content = mem_contents.get(r.triggered_memory_id, "")
                if content:
                    lines.append(
                        f"  ↳ [{assoc_label}{shared_str}] {content[:200]}"
                    )

        return "\n".join(lines)

    def get_memory_stats(self) -> Dict:
        return self.store.get_stats()
