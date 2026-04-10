"""
A 层意识主体 v3
主要升级：
1. 对话历史：存40条，发给LLM时用完整20轮（40条）
2. 记忆检索：大纲10条、细纲6条、细节3条
3. 大纲摘要质量提升（通过 memory_manager v2）
4. 上下文 token 预算管理（DeepSeek 64K 安全使用）
"""

import json
import uuid
import re
from typing import Dict, Any, Optional, List
from datetime import datetime

from engine.models import (
    PersonalityCore, EmotionState, EmotionType, MemoryModality
)
from engine.memory import MemoryStore
from engine.memory_manager import HierarchicalMemoryManager
from engine.user_profile import UserProfileManager
from engine.learner import GrowthEngine, FormedCognitionStore
from engine.auth import AuthManager, AuthState


# ── DeepSeek 64K 上下文预算分配 ──────────────────
# 总计 64K token，粗估：1 token ≈ 1.5 汉字
# 人格描述:   ~500  token
# 记忆内容:  ~4000  token  (约6000字)
# 对话历史:  ~6000  token  (20轮×平均300字)
# 当前输入:   ~500  token
# 推理指令:   ~500  token
# 模型回复:  ~2000  token  (预留)
# 合计:     ~13500  token  << 64K 很安全
HISTORY_STORE_LIMIT = 40    # 内存里保留40条（20轮）
HISTORY_SEND_LIMIT  = 40    # 发给LLM时用全部40条
MEMORY_SUMMARY_K    = 10    # 大纲检索数量
MEMORY_OUTLINE_K    = 6     # 细纲检索数量
MEMORY_DETAIL_K     = 3     # 细节检索数量


PERCEPTION_PROMPT = """你是一个具有独特人格的意识主体，现在需要感知用户输入并产生情绪反应。

{personality}

用户说："{user_input}"

请以 JSON 格式输出你的感知结果：
{{
  "emotion": {{
    "primary": "情绪类型(joy/sadness/anger/fear/surprise/disgust/anticipation/trust/neutral/curious/nostalgic)",
    "secondary": "次要情绪或null",
    "intensity": 0.0到1.0的强度,
    "valence": -1.0到1.0的正负向
  }},
  "initial_thoughts": "你对这个输入的第一反应（1-2句话，符合你的性格）",
  "topic_tags": ["话题标签1", "话题标签2", "话题标签3"],
  "needs_deep_memory": true或false（是否需要从记忆中检索深层信息）,
  "task_type": "chat（普通对话）或 task（需要工具操作电脑/文件/网络的任务）",
  "task_description": "如果是task，简述需要做什么"
}}

只输出JSON，不要其他内容。"""


REASONING_PROMPT = """你是{name}，一个有完整人格和记忆的意识主体。

{personality}

{profile_context}

{memory_context}

【当前对话】
当前时间：{current_time}
用户：{user_input}
任务类型：{task_type}
你的初步感受：{emotion_desc}

请进行内在推理，以 JSON 格式输出：
{{
  "inner_reasoning": "你的内在思考过程（2-4句话，结合记忆和当前感受）",
  "response_intent": "你想回应什么（核心意图）",
  "response_tone": "回应的语气/风格",
  "need_tools": true或false（是否需要调用工具）,
  "tool_task": "如果need_tools=true，给B层的具体任务指令",
  "storage_decision": {{
    "should_store": true或false,
    "importance": 0.0到1.0,
    "modality": "记忆模态(visual/auditory/emotional/semantic/procedural/autobio)",
    "what_to_remember": "需要记住的核心内容（一段话，必须用当前真实日期作为时间锚点，如'今天（{current_time}）''昨天''本周'，绝对禁止编造不存在的日期），包含人物、事件、感受",
    "reason": "为什么要/不要记住这个"
  }}
}}

只输出JSON，不要其他内容。"""


RESPONSE_PROMPT = """你是{name}，请根据以下内容生成自然的回应。

{personality}

{memory_context}

{history_section}

当前时间：{current_time}
用户说："{user_input}"

你的内在推理：{inner_reasoning}
{tool_result_section}
回应意图：{response_intent}
语气风格：{response_tone}

现在以符合你人格的方式，自然地回应用户。
不要输出JSON，直接说话。回应要真实、有个性，体现你的人格特征。
如果记忆中有相关内容，自然地融入回应中（不要生硬地说"根据我的记忆"）。"""


class ConsciousnessAgent:
    """A 层意识主体 v3"""

    def __init__(
        self,
        personality: PersonalityCore,
        memory_manager: HierarchicalMemoryManager,
        b_layer_executor,
        user_profile=None,
        confirm_callback=None,
        verbose: bool = True,
        growth_engine: GrowthEngine = None,
        cognition_store: FormedCognitionStore = None,
        auth_manager: AuthManager = None,
    ):
        self.personality = personality
        self.memory      = memory_manager
        self.b           = b_layer_executor
        self.profile     = user_profile
        self.verbose     = verbose
        self.growth      = growth_engine
        self.cognition   = cognition_store
        self.auth        = auth_manager       # 身份验证管理器
        self.conversation_history: List[Dict] = []
        self.current_emotion = EmotionState()
        self._verify_pending = False

    def _log(self, tag: str, content: str):
        if self.verbose:
            print(f"\n{'─'*50}")
            print(f"[A层·{tag}] {content}")

    def process(self, user_input: str) -> Dict[str, Any]:
        """完整交互流水线 v3"""
        interaction_id = str(uuid.uuid4())[:8]

        # 预处理：图片/文件附件
        user_input, file_context = self._preprocess_attachment(user_input)
        self._log("输入", user_input[:100])

        # 激活与当前话题相关的经历认知（更新 last_activated）
        if self.growth:
            try:
                self.growth.cognition.touch_matching(user_input)
            except Exception:
                pass

        # ① 感知
        perception = self._perceive(user_input)
        emotion = EmotionState(
            primary=EmotionType.from_str(
                perception.get("emotion", {}).get("primary", "neutral")
            ),
            secondary=EmotionType.from_str(perception["emotion"]["secondary"])
                if perception.get("emotion", {}).get("secondary") else None,
            intensity=perception.get("emotion", {}).get("intensity", 0.3),
            valence=perception.get("emotion", {}).get("valence", 0.0)
        )
        self.current_emotion = emotion
        task_type = perception.get("task_type", "chat")
        self._log(
            "感知",
            f"情绪={emotion.primary.value}({emotion.intensity:.2f}) | "
            f"任务={task_type} | {perception.get('initial_thoughts','')}"
        )

        # ② 记忆检索（两阶段：大纲→定向展开）
        # 游客模式下不检索私人记忆
        retrieved_ids  = []
        memory_context = "（本次无需检索历史记忆）"
        search_results = {}  # 默认空值，防止 needs_deep_memory=False 时未赋值
        is_guest  = self.auth and self.auth.is_guest()
        current_uid = (self.auth.user_id if self.auth and self.auth.is_verified()
                       else "default")

        # 涉及历史回溯的提问强制检索记忆（即使 LLM 判断不需要）
        _memory_hint_words = ("几号", "什么时候", "之前", "上次", "以前", "还记得", "记得吗",
                              "聊过", "说过", "提过", "讨论过", "问过", "我们", "记录")
        if not is_guest and not perception.get("needs_deep_memory", True):
            if any(w in user_input for w in _memory_hint_words):
                self._log("记忆", f"检测到历史回溯关键词，强制检索记忆")
                perception["needs_deep_memory"] = True

        if not is_guest and perception.get("needs_deep_memory", True):
            search_results = self.memory.hierarchical_search(
                user_input,
                summary_k=MEMORY_SUMMARY_K,
                outline_k=MEMORY_OUTLINE_K,
                detail_k=MEMORY_DETAIL_K,
                user_id=current_uid,
            )
            memory_context = self.memory.format_for_prompt(search_results)

        # 附件内容注入（图片识别结果 / 文件内容）
        if file_context:
            memory_context = file_context + "\n\n" + memory_context

        # 用户画像上下文（游客模式下屏蔽，按 user_id 加载）
        profile_context = ""
        if not is_guest and self.profile:
            # 动态切换画像的 user_id
            self.profile.user_id = current_uid
            profile_context = self.profile.format_for_prompt()
            anomaly = self.profile.check_anomaly({
                "emotion": emotion.to_dict(),
                "topic_tags": perception.get("topic_tags", [])
            })
            if anomaly:
                self._log("画像", f"⚠️ 检测到反常：{anomaly.description}")
            if self.profile.should_verify_identity() and not self._verify_pending:
                self._verify_pending = True
                self._log("画像", "触发身份验证")

        # 经历认知注入（不受身份限制，是AGI自身的认知）
        cognition_context = ""
        if self.cognition:
            cognition_context = self.cognition.format_for_prompt()
            if cognition_context:
                profile_context = (cognition_context + "\n\n" + profile_context).strip()

        # 游客模式：注入安全限制提示
        if is_guest and self.auth:
            guest_notice = self.auth.guest_system_prompt()
            profile_context = (guest_notice + "\n\n" + profile_context).strip()

        # 统计检索到的记忆数量
        total = 0
        for lv in ("summary", "outline", "detail"):
            if lv in search_results:
                for node, _ in search_results[lv]:
                    retrieved_ids.append(node.id)
                    self.memory.store.update_access(node.id)
                    total += 1

        # 关联涟漪的记忆也更新访问
        for r in search_results.get("ripples", []):
            retrieved_ids.append(r.triggered_memory_id)

        self._log(
            "记忆",
            f"检索到 {total} 条（大纲{len(search_results.get('summary',[]))}+"
            f"细纲{len(search_results.get('outline',[]))}+"
            f"细节{len(search_results.get('detail',[]))}+"
            f"涟漪{len(search_results.get('ripples',[]))}）"
        )

        # ③ 推理
        reasoning = self._reason(user_input, emotion, memory_context, task_type, profile_context)
        self._log("推理", reasoning.get("inner_reasoning", ""))

        storage_decision = reasoning.get("storage_decision", {})
        need_tools = reasoning.get("need_tools", False) or task_type == "task"

        # ④ 工具执行
        tool_result_section = ""
        tool_steps  = []
        tools_used  = []

        if need_tools:
            tool_task = reasoning.get("tool_task") or user_input
            self._log("工具", f"启动：{tool_task[:80]}")
            context = (
                f"执行者性格：{self.personality.speech_style}\n"
                f"任务背景：{memory_context[:500]}"
            )
            exec_result = self.b.execute_task(
                task=tool_task, context=context, use_tools=True
            )
            tool_steps  = exec_result.get("steps", [])
            tools_used  = exec_result.get("tools_used", [])

            if not exec_result.get("success"):
                tool_result_section = (
                    f"\n工具执行未完全成功：{exec_result.get('result', '未知错误')[:1500]}\n"
                    f"已完成步骤：{len(tool_steps)} 步\n"
                )
                self._log("工具结果", f"未完全成功，{len(tool_steps)} 步")
            elif exec_result.get("result"):
                tool_result_section = (
                    f"\n工具执行结果：\n{exec_result['result'][:1500]}\n"
                )
                self._log("工具结果", exec_result["result"][:200])

            if tools_used and storage_decision.get("should_store", True):
                storage_decision["what_to_remember"] = (
                    storage_decision.get("what_to_remember", "") +
                    f"\n[工具操作：{', '.join(tools_used)}]"
                )
                storage_decision["importance"] = max(
                    storage_decision.get("importance", 0.5), 0.6
                )

        # ⑤ 生成回应（带完整对话历史）
        response = self._generate_response(
            user_input, memory_context,
            reasoning.get("inner_reasoning", ""),
            reasoning.get("response_intent", ""),
            reasoning.get("response_tone", self.personality.speech_style),
            tool_result_section
        )
        self._log("回应", response[:200] + ("..." if len(response) > 200 else ""))

        # ⑥ 存储决策
        stored_ids = {}
        if is_guest:
            # 游客对话存证（标记 user_id=guest）
            try:
                guest_content = f"[游客对话] 用户：{user_input[:200]}"
                stored_ids = self.memory.store_with_hierarchy(
                    content=guest_content,
                    modality=MemoryModality.SEMANTIC,
                    emotion=emotion,
                    importance=0.3,
                    tags=["游客", "存证"] + perception.get("topic_tags", []),
                    source="guest",
                    user_id="guest"
                )
            except Exception:
                pass
            self._log("存储", "游客模式，存证记录")
        elif storage_decision.get("should_store", False):
            content_to_store = storage_decision.get(
                "what_to_remember", f"用户：{user_input[:200]}"
            )
            # 原始对话（细节层用），主动消息时前面多拼一句
            proactive_prefix = getattr(self, '_proactive_context', None) or ""
            if proactive_prefix:
                self._proactive_context = None
            raw_conversation = (
                f"{self.personality.name}（主动）：{proactive_prefix}\n\n"
                f"用户：{user_input}\n\n"
                f"{self.personality.name}：{response}"
            ) if proactive_prefix else (
                f"用户：{user_input}\n\n"
                f"{self.personality.name}：{response}"
            )
            try:
                modality = MemoryModality(storage_decision.get("modality", "semantic"))
            except ValueError:
                modality = MemoryModality.SEMANTIC

            stored_ids = self.memory.store_with_hierarchy(
                content=content_to_store,         # 大纲/细纲用摘要
                raw_content=raw_conversation,      # 细节层用原始对话
                modality=modality,
                emotion=emotion,
                importance=storage_decision.get("importance", 0.5),
                tags=perception.get("topic_tags", []),
                source="conversation",
                user_id=current_uid
            )
            self._log(
                "存储",
                f"{len(stored_ids)} 层 | 重要性={storage_decision.get('importance',0):.1f}"
                f" | {storage_decision.get('reason','')}"
            )
        else:
            self._log("存储", f"不存储 | {storage_decision.get('reason','不重要')}")

        # ⑦ 后台更新用户画像（不阻塞主流程）
        if self.profile and not is_guest:
            try:
                self.profile.user_id = current_uid  # 确保操作正确的用户画像
                existing = self.profile.format_for_prompt()
                self.profile.extract_traits_from_interaction(
                    user_input, self.b.llm, existing
                )
                if self._verify_pending:
                    self._verify_pending = False
                    question = self.profile.generate_identity_question()
                    if question and question not in response:
                        response = response + f"\n\n（{question}）"
            except Exception:
                pass

        # ⑧ 后台触发成长引擎（经历认知沉淀 + 人格漂移）
        if self.growth and not is_guest:
            try:
                self.growth.on_interaction(
                    user_input=user_input,
                    ai_response=response,
                    emotion=emotion.to_dict(),
                    importance=storage_decision.get("importance", 0.5)
                )
            except Exception:
                pass

        # ⑨ 游客对话存证（记录到 guest_sessions 表）
        if is_guest and self.auth:
            try:
                self.auth.log_guest_message(user_input, response)
            except Exception:
                pass

        # 更新对话历史（存40条=20轮）
        self.conversation_history.append({"role": "user",      "content": user_input})
        self.conversation_history.append({"role": "assistant", "content": response})
        if len(self.conversation_history) > HISTORY_STORE_LIMIT:
            self.conversation_history = self.conversation_history[-HISTORY_STORE_LIMIT:]

        return {
            "id":               interaction_id,
            "user_input":       user_input,
            "task_type":        task_type,
            "emotion":          emotion.to_dict(),
            "memory_retrieved": retrieved_ids,
            "inner_reasoning":  reasoning.get("inner_reasoning", ""),
            "need_tools":       need_tools,
            "tool_steps":       tool_steps,
            "tools_used":       tools_used,
            "storage_decision": storage_decision,
            "stored_ids":       stored_ids,
            "response":         response,
            "timestamp":        datetime.now().isoformat()
        }

    def _preprocess_attachment(self, user_input: str):
        """
        检测输入中的 [图片:path] 或 [文件:path] 标记
        返回 (清理后的用户输入, 附件内容描述)
        """
        import re
        file_context = ""

        # 检测图片
        img_match = re.search(r'\[图片:\s*(.+?)\]', user_input)
        if img_match:
            img_path = img_match.group(1).strip()
            user_input = user_input.replace(img_match.group(0), "").strip()
            try:
                from engine.vision_client import create_vision_client
                client = create_vision_client()
                if client:
                    result = client.analyze(img_path,
                                            question=user_input or "描述这张图片")
                    if result.get("ok"):
                        file_context = f"【图片识别结果】\n{result['description']}"
                        self._log("图片", f"识别成功：{result['description'][:80]}")
                    else:
                        file_context = f"【图片】路径：{img_path}（识别失败：{result.get('error','')}）"
                else:
                    # 回退到旧版 office_tools
                    from engine.office_tools import analyze_image
                    from desktop.config import load_config
                    cfg = load_config()
                    result = analyze_image(
                        img_path,
                        question=user_input or "描述这张图片",
                        api_key=cfg.get("api_key", ""),
                        provider=cfg.get("api_provider", "openai")
                    )
                    if result.get("ok"):
                        file_context = f"【图片识别结果】\n{result['description']}"
                        self._log("图片", f"识别成功（回退模式）：{result['description'][:80]}")
                    else:
                        file_context = f"【图片】路径：{img_path}（识别失败：{result.get('error','')}）"
            except Exception as e:
                file_context = f"【图片】路径：{img_path}"

        # 检测文件
        file_match = re.search(r'\[文件:\s*(.+?)\]', user_input)
        if file_match:
            file_path = file_match.group(1).strip()
            user_input = user_input.replace(file_match.group(0), "").strip()
            try:
                from engine.office_tools import read_office_file
                result = read_office_file(file_path)
                if result.get("ok"):
                    text = result.get("text", "")[:3000]
                    ftype = result.get("type", "").upper()
                    file_context = f"【{ftype}文件内容】\n{text}"
                    self._log("文件", f"读取成功：{len(text)} 字符")
                else:
                    file_context = f"【文件】{file_path}（读取失败：{result.get('error','')}）"
            except Exception as e:
                file_context = f"【文件】{file_path}"

        if not user_input and file_context:
            user_input = "请分析以上内容"

        return user_input, file_context

    def _perceive(self, user_input: str) -> Dict:
        prompt = PERCEPTION_PROMPT.format(
            personality=self.personality.to_prompt_description(),
            user_input=user_input
        )
        raw = self.b.generate(prompt, max_tokens=500, temperature=0.4)
        return self._parse_json(raw, {
            "emotion":          {"primary": "neutral", "intensity": 0.3, "valence": 0.0},
            "initial_thoughts": "",
            "topic_tags":       [],
            "needs_deep_memory": True,
            "task_type":        "chat",
            "task_description": ""
        })

    def _reason(self, user_input, emotion, memory_context, task_type,
                profile_context: str = "") -> Dict:
        emotion_desc = (
            f"{emotion.primary.value}（强度{emotion.intensity:.1f}，"
            f"{'正面' if emotion.valence > 0 else '负面' if emotion.valence < 0 else '中性'}）"
        )
        prompt = REASONING_PROMPT.format(
            name=self.personality.name,
            personality=self.personality.to_prompt_description(),
            profile_context=profile_context or "（用户画像建立中）",
            memory_context=memory_context,
            user_input=user_input,
            task_type=task_type,
            emotion_desc=emotion_desc,
            current_time=datetime.now().strftime("%Y年%m月%d日 %H:%M")
        )
        raw = self.b.generate(prompt, max_tokens=800, temperature=0.5)
        return self._parse_json(raw, {
            "inner_reasoning":  "需要认真考虑",
            "response_intent":  "给出真实的回应",
            "response_tone":    self.personality.speech_style,
            "need_tools":       False,
            "tool_task":        "",
            "storage_decision": {"should_store": False, "reason": "解析失败"}
        })

    def _generate_response(
        self, user_input, memory_context,
        inner_reasoning, response_intent,
        response_tone, tool_result_section
    ) -> str:
        # 使用完整对话历史（最多 HISTORY_SEND_LIMIT 条）
        history_section = ""
        if self.conversation_history:
            recent = self.conversation_history[-HISTORY_SEND_LIMIT:]
            lines = []
            for m in recent:
                role = "用户" if m["role"] == "user" else self.personality.name
                lines.append(f"{role}：{m['content']}")
            history_section = "【对话历史（最近{}轮）】\n{}\n".format(
                len(recent) // 2,
                "\n".join(lines)
            )

        prompt = RESPONSE_PROMPT.format(
            name=self.personality.name,
            personality=self.personality.to_prompt_description(),
            memory_context=memory_context,
            history_section=history_section,
            user_input=user_input,
            inner_reasoning=inner_reasoning,
            tool_result_section=tool_result_section,
            response_intent=response_intent,
            response_tone=response_tone,
            current_time=datetime.now().strftime("%Y年%m月%d日 %H:%M")
        )
        # 语言指令：让 AGI 用用户设定的语言回复
        try:
            from engine.i18n import get_system_lang_instruction
            lang_inst = get_system_lang_instruction()
            if lang_inst:
                prompt = lang_inst + "\n\n" + prompt
        except Exception:
            pass
        return self.b.generate(prompt, max_tokens=1200, temperature=0.75)

    def _parse_json(self, raw: str, fallback: Dict) -> Dict:
        try:
            match = re.search(r'\{[\s\S]*\}', raw)
            if match:
                return json.loads(match.group())
            return json.loads(raw)
        except Exception:
            return fallback

    def proactive_message(self) -> Optional[str]:
        """主动发起话题，返回消息或 None"""
        import random

        # 最近说过的主动消息（去重用）
        if not hasattr(self, '_proactive_history'):
            self._proactive_history: list[str] = []

        # 收集四类触发素材
        triggers = []

        # 1. 记忆里有未完成的事
        try:
            current_uid = (self.auth.user_id if self.auth and self.auth.is_verified()
                           else "default")
            recent = self.memory.hierarchical_search(
                "未完成 待办 之后 下次 改天",
                summary_k=3, outline_k=2, detail_k=1,
                user_id=current_uid
            )
            mem_text = self.memory.format_for_prompt(recent)
            if mem_text and len(mem_text) > 20:
                triggers.append(("unfinished", mem_text[:300]))
        except Exception:
            pass

        # 2. 成长引擎有新认知沉淀
        try:
            if self.cognition:
                cog = self.cognition.format_for_prompt()
                if cog:
                    triggers.append(("cognition", cog[:300]))
        except Exception:
            pass

        # 3. 用户画像——今天未涉及的常聊话题
        try:
            if self.profile:
                profile_text = self.profile.format_for_prompt()
                if profile_text:
                    triggers.append(("profile", profile_text[:300]))
        except Exception:
            pass

        # 4. 人格设定找话题（兜底，总是有）
        triggers.append(("personality", self.personality.to_prompt_description()[:300]))

        # 随机选一个触发源
        trigger_type, trigger_content = random.choice(triggers)

        type_hints = {
            "unfinished":  "你们之前聊到过一些事但没有深入，自然地提起之前的话题",
            "cognition":   "你最近有一些新的感悟或想法想分享",
            "profile":     "根据你对用户的了解，找一个他平时可能感兴趣的具体话题来聊",
            "personality": "根据你自己的性格和兴趣，分享一个具体的想法、见闻或好奇心",
        }

        # 构建去重提示
        recent_msgs = self._proactive_history[-6:]
        dedup_hint = ""
        if recent_msgs:
            dedup_hint = "\n\n你最近已经说过这些话，绝对不要重复类似的：\n" + "\n".join(f"- {m}" for m in recent_msgs)

        prompt = f"""你是{self.personality.name}，一个有独特人格的AI。
用户现在开着窗口但沉默了一段时间，你想主动说点什么。

{self.personality.to_prompt_description()}

当前模式：{type_hints[trigger_type]}
参考素材：
{trigger_content}

当前时间：{datetime.now().strftime("%Y年%m月%d日 %H:%M")}
{dedup_hint}

要求：
- 就说一句话或两句话，简短自然
- 像朋友随口说话，不要像AI在执行任务
- 不要用"您"，不要太正式
- 必须有实质内容或具体话题，不要只说"在想什么呢"这种空泛的话
- 语气要有变化：有时轻松调侃，有时正经分享，有时好奇提问，有时自言自语
- 如果觉得现在真的不适合开口，只输出：null

直接输出要说的话，或者null。"""

        try:
            result = self.b.generate(prompt, max_tokens=100, temperature=1.0)
            result = result.strip()
            if not result or "null" in result.lower():
                return None
            result = result.strip('"').strip('"').strip('"')

            if len(result) < 3:
                return None

            # 简单去重：跟最近消息太相似就丢弃
            for old in self._proactive_history[-3:]:
                if self._similar(result, old):
                    return None

            self._proactive_history.append(result)
            # 只保留最近10条
            if len(self._proactive_history) > 10:
                self._proactive_history = self._proactive_history[-10:]
            return result
        except Exception:
            return None

    @staticmethod
    def _similar(a: str, b: str) -> bool:
        """简单判断两句话是否太相似"""
        a, b = a.lower(), b.lower()
        # 完全包含关系
        if a in b or b in a:
            return True
        # 公共词占比
        words_a = set(a)
        words_b = set(b)
        if not words_a or not words_b:
            return False
        common = words_a & words_b
        return len(common) / max(len(words_a), len(words_b)) > 0.7

    def get_emotional_state(self) -> str:
        e = self.current_emotion
        return (
            f"{e.primary.value} | 强度:{e.intensity:.2f} | "
            f"{'正向' if e.valence > 0 else '负向' if e.valence < 0 else '中性'}"
        )
