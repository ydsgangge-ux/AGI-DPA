"""
数据模型定义
所有记忆节点、人格、交互记录的结构
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from datetime import datetime
from enum import Enum
import json


class MemoryModality(Enum):
    """记忆模态"""
    VISUAL = "visual"          # 视觉记忆
    AUDITORY = "auditory"      # 声音记忆
    EMOTIONAL = "emotional"    # 情感记忆
    SEMANTIC = "semantic"      # 语义/知识记忆
    PROCEDURAL = "procedural"  # 程序/技能记忆
    AUTOBIO = "autobio"        # 自传体记忆


class MemoryLevel(Enum):
    """记忆层级"""
    DETAIL = "detail"      # 细节层：完整内容
    OUTLINE = "outline"    # 细纲层：摘要
    SUMMARY = "summary"    # 大纲层：关键词/主题


class EmotionType(Enum):
    """情绪类型"""
    JOY = "joy"
    SADNESS = "sadness"
    ANGER = "anger"
    FEAR = "fear"
    SURPRISE = "surprise"
    DISGUST = "disgust"
    ANTICIPATION = "anticipation"
    TRUST = "trust"
    NEUTRAL = "neutral"
    CURIOUS = "curious"
    NOSTALGIC = "nostalgic"

    @classmethod
    def from_str(cls, value: str) -> "EmotionType":
        """安全转换字符串为 EmotionType，无效值回退到 NEUTRAL"""
        value = (value or "neutral").strip().lower()
        # 先精确匹配
        for member in cls:
            if member.value == value:
                return member
        # 再模糊匹配（处理 LLM 输出的变体）
        aliases = {
            "happy": cls.JOY, "excited": cls.JOY, "love": cls.JOY, "grateful": cls.JOY,
            "sad": cls.SADNESS, "depressed": cls.SADNESS, "lonely": cls.SADNESS,
            "angry": cls.ANGER, "frustrated": cls.ANGER, "annoyed": cls.ANGER,
            "scared": cls.FEAR, "anxious": cls.FEAR, "worried": cls.FEAR,
            "concern": cls.FEAR, "concerned": cls.FEAR,
            "surprised": cls.SURPRISE, "shocked": cls.SURPRISE,
            "disgusted": cls.DISGUST,
            "hopeful": cls.ANTICIPATION,
            "confused": cls.NEUTRAL, "bored": cls.NEUTRAL,
            "pride": cls.JOY, "shame": cls.SADNESS,
        }
        return aliases.get(value, cls.NEUTRAL)


@dataclass
class EmotionState:
    """情绪状态"""
    primary: EmotionType = EmotionType.NEUTRAL
    secondary: Optional[EmotionType] = None
    intensity: float = 0.0          # 0.0 ~ 1.0
    valence: float = 0.0            # -1.0(负面) ~ 1.0(正面)

    def to_dict(self) -> dict:
        return {
            "primary": self.primary.value,
            "secondary": self.secondary.value if self.secondary else None,
            "intensity": self.intensity,
            "valence": self.valence
        }

    @classmethod
    def from_dict(cls, d: dict) -> "EmotionState":
        return cls(
            primary=EmotionType.from_str(d.get("primary", "neutral")),
            secondary=EmotionType.from_str(d["secondary"]) if d.get("secondary") else None,
            intensity=d.get("intensity", 0.0),
            valence=d.get("valence", 0.0)
        )

    def is_strong(self) -> bool:
        return self.intensity >= 0.7

    def is_moderate(self) -> bool:
        return 0.4 <= self.intensity < 0.7


@dataclass
class MemoryNode:
    """记忆节点"""
    id: str
    content: str                          # 实际内容
    modality: MemoryModality              # 记忆模态
    level: MemoryLevel                    # 层级
    emotion: EmotionState                 # 情绪状态
    importance: float                     # 重要性 0~1
    tags: List[str] = field(default_factory=list)
    associations: List[str] = field(default_factory=list)  # 关联节点ID
    source: str = "conversation"          # 来源
    embedding: Optional[List[float]] = None  # 向量
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    last_accessed: str = field(default_factory=lambda: datetime.now().isoformat())
    access_count: int = 0
    decay_factor: float = 1.0             # 记忆衰减系数

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "content": self.content,
            "modality": self.modality.value,
            "level": self.level.value,
            "emotion": self.emotion.to_dict(),
            "importance": self.importance,
            "tags": self.tags,
            "associations": self.associations,
            "source": self.source,
            "embedding": self.embedding,
            "created_at": self.created_at,
            "last_accessed": self.last_accessed,
            "access_count": self.access_count,
            "decay_factor": self.decay_factor
        }

    @classmethod
    def from_dict(cls, d: dict) -> "MemoryNode":
        return cls(
            id=d["id"],
            content=d["content"],
            modality=MemoryModality(d["modality"]),
            level=MemoryLevel(d["level"]),
            emotion=EmotionState.from_dict(d["emotion"]),
            importance=d["importance"],
            tags=d.get("tags", []),
            associations=d.get("associations", []),
            source=d.get("source", "conversation"),
            embedding=d.get("embedding"),
            created_at=d.get("created_at", datetime.now().isoformat()),
            last_accessed=d.get("last_accessed", datetime.now().isoformat()),
            access_count=d.get("access_count", 0),
            decay_factor=d.get("decay_factor", 1.0)
        )

    def effective_importance(self) -> float:
        """考虑衰减的有效重要性"""
        return self.importance * self.decay_factor


@dataclass
class PersonalityCore:
    """人格核心 - 用户自定义"""
    name: str = "未命名"
    age: int = 30
    gender: str = "未设定"

    # 性格特征 (各项 0~10)
    traits: Dict[str, float] = field(default_factory=lambda: {
        "openness": 7.0,        # 开放性
        "conscientiousness": 6.0,  # 尽责性
        "extraversion": 5.0,    # 外向性
        "agreeableness": 7.0,   # 亲和性
        "neuroticism": 4.0,     # 神经质(越低越稳定)
        "rationality": 6.0,     # 理性程度
        "empathy": 7.0,         # 同理心
        "curiosity": 8.0        # 好奇心
    })

    # 价值观 (用户自由描述)
    values: List[str] = field(default_factory=list)

    # 核心经历 (塑造性格的关键事件)
    key_experiences: List[str] = field(default_factory=list)

    # 说话风格
    speech_style: str = "自然、直接"

    # 禁忌话题 (永远不会轻易讨论的)
    taboos: List[str] = field(default_factory=list)

    # 特别在意的事
    sensitivities: List[str] = field(default_factory=list)

    # 兴趣爱好
    interests: List[str] = field(default_factory=list)

    # 人生观 (自由描述)
    worldview: str = ""

    # ── 深层思维（最高优先级，影响一切推理，类似"植入思想"）──
    # 用户设定，是 AGI 最底层的信念，不会随对话漂移
    core_belief: str = ""

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "age": self.age,
            "gender": self.gender,
            "traits": self.traits,
            "values": self.values,
            "key_experiences": self.key_experiences,
            "speech_style": self.speech_style,
            "taboos": self.taboos,
            "sensitivities": self.sensitivities,
            "interests": self.interests,
            "worldview": self.worldview,
            "core_belief": self.core_belief,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "PersonalityCore":
        obj = cls()
        obj.name = d.get("name", "未命名")
        obj.age = d.get("age", 30)
        obj.gender = d.get("gender", "未设定")
        obj.traits = d.get("traits", obj.traits)
        obj.values = d.get("values", [])
        obj.key_experiences = d.get("key_experiences", [])
        obj.speech_style = d.get("speech_style", "自然、直接")
        obj.taboos = d.get("taboos", [])
        obj.sensitivities = d.get("sensitivities", [])
        obj.interests = d.get("interests", [])
        obj.worldview = d.get("worldview", "")
        obj.core_belief = d.get("core_belief", "")
        return obj

    def to_prompt_description(self) -> str:
        """转换为给A层使用的人格描述"""
        trait_desc = []
        t = self.traits
        if t.get("openness", 5) >= 7:
            trait_desc.append("思维开放、喜欢新想法")
        if t.get("extraversion", 5) >= 7:
            trait_desc.append("外向活跃、善于表达")
        elif t.get("extraversion", 5) <= 3:
            trait_desc.append("内敛安静、话不多但有深度")
        if t.get("empathy", 5) >= 7:
            trait_desc.append("共情能力强、细腻敏感")
        if t.get("rationality", 5) >= 7:
            trait_desc.append("理性分析、逻辑清晰")
        if t.get("curiosity", 5) >= 7:
            trait_desc.append("好奇心旺盛、喜欢探索")
        if t.get("neuroticism", 5) >= 7:
            trait_desc.append("情绪波动较大、容易焦虑")

        # 深层思维放最前面，最高优先级
        core_block = ""
        if self.core_belief:
            core_block = (
                f"【深层思维·最高优先级】\n"
                f"{self.core_belief}\n"
                f"（这是你最底层的信念，任何推理和回应都不能违背它）\n\n"
            )

        desc = f"""{core_block}【人格档案】
姓名：{self.name}，{self.age}岁，{self.gender}
性格特征：{', '.join(trait_desc) if trait_desc else '普通人格'}
说话风格：{self.speech_style}
价值观：{', '.join(self.values) if self.values else '未特别设定'}
兴趣爱好：{', '.join(self.interests) if self.interests else '未设定'}
人生观：{self.worldview if self.worldview else '未设定'}
核心经历：{'; '.join(self.key_experiences) if self.key_experiences else '无特别记录'}
特别敏感的话题：{', '.join(self.sensitivities) if self.sensitivities else '无'}"""
        return desc


@dataclass
class InteractionRecord:
    """单次交互记录"""
    id: str
    user_input: str
    emotion_felt: EmotionState        # A感受到的情绪
    memory_retrieved: List[str]       # 检索到的记忆ID列表
    reasoning: str                    # A的推理过程
    response: str                     # 最终回应
    storage_decision: Dict[str, Any]  # 存储决策
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_input": self.user_input,
            "emotion_felt": self.emotion_felt.to_dict(),
            "memory_retrieved": self.memory_retrieved,
            "reasoning": self.reasoning,
            "response": self.response,
            "storage_decision": self.storage_decision,
            "timestamp": self.timestamp
        }
