"""Profile dimension normalization utilities.

维度分为两类：
- 通用维度：所有课程都需要
- 科目专属维度：只在特定科目分类下激活（如 coding_ability 仅 CS 课程）
"""

from __future__ import annotations

from typing import Any

# ── 科目分类 ──────────────────────────────────────────────
# 设计思路：所有科目默认只用通用维度，额外维度仅在匹配时激活。
# 学微积分 → 通用维度（无编程能力）
# 学英语 → 通用维度（无编程能力）
# 学数据结构 → 通用维度 + coding_ability
# 新增科目无需改代码，关键词自动匹配，未匹配到的科目安全fallback到 general。
COURSE_CATEGORIES: dict[str, dict[str, Any]] = {
    "cs": {
        "label": "计算机科学",
        "extra_dimensions": ["coding_ability"],
        "keywords": [
            "编程", "代码", "Python", "C语言", "C++", "Java", "JavaScript",
            "数据结构", "算法", "计算机", "软件工程", "人工智能", "机器学习",
            "深度学习", "神经网络", "操作系统", "编译原理", "计算机网络", "数据库",
            "前端", "后端", "全栈", "嵌入式", "信息工程", "自动化", "数据科学",
            "爬虫", "Linux", "Git", "Docker", "云计算", "大数据",
        ],
    },
    "math": {
        "label": "数学与统计",
        "extra_dimensions": [],  # 未来可加 math_basis
        "keywords": [
            "微积分", "高等数学", "线性代数", "概率论", "数理统计",
            "离散数学", "数学分析", "复变函数", "常微分方程", "偏微分方程",
            "数值分析", "优化理论", "拓扑学", "几何学", "抽象代数",
            "数学", "统计学", "概率", "函数", "积分", "微分",
        ],
    },
    "language": {
        "label": "语言学习",
        "extra_dimensions": [],  # 未来可加 language_level, vocabulary_size
        "keywords": [
            "英语", "日语", "韩语", "法语", "德语", "西班牙语",
            "四六级", "六级", "四级", "托福", "雅思", "GRE", "GMAT",
            "考研英语", "高考英语", "口语", "听力", "阅读", "写作", "翻译",
            "词汇", "语法", "发音", "N1", "N2", "N3", "JLPT",
            "English", "TOEFL", "IELTS",
        ],
    },
    "science": {
        "label": "自然科学",
        "extra_dimensions": [],  # 未来可加 experiment_ability
        "keywords": [
            "物理", "化学", "生物", "地理", "天文", "力学",
            "电磁", "量子", "有机化学", "分子生物学", "遗传学",
        ],
    },
    "engineering": {
        "label": "工程技术",
        "extra_dimensions": [],  # 未来可加 experiment_ability, design_ability
        "keywords": [
            "电子", "电路", "信号", "通信", "机械", "土木", "材料",
            "控制", "电气", "自动化", "工程制图", "单片机", "FPGA",
        ],
    },
    "humanities": {
        "label": "人文社科",
        "extra_dimensions": [],
        "keywords": [
            "历史", "哲学", "政治", "经济", "管理", "心理", "社会",
            "法律", "教育", "文学", "艺术", "音乐", "美术",
            "考研政治", "马原", "毛概",
        ],
    },
    "general": {
        "label": "通用",
        "extra_dimensions": [],
        "keywords": [],
    },
}

# ── 通用维度（所有课程都激活）──────────────────────────
UNIVERSAL_DIMENSIONS = [
    "major_background",
    "learning_history",
    "knowledge_base",
    "learning_goal",
    "cognitive_style",
    "error_patterns",
    "learning_progress",
    "interest_direction",
    "learning_rhythm",
]

PROFILE_DIMENSION_ORDER = UNIVERSAL_DIMENSIONS + ["coding_ability"]

PROFILE_DIMENSION_LABELS: dict[str, str] = {
    "major_background": "专业背景",
    "learning_history": "学习历史",
    "knowledge_base": "知识基础",
    "learning_goal": "学习目标",
    "cognitive_style": "认知风格",
    "error_patterns": "易错模式",
    "coding_ability": "编程能力",
    "learning_progress": "学习进度",
    "interest_direction": "兴趣方向",
    "learning_rhythm": "学习节奏",
}

OLD_TO_NEW_KEYS: dict[str, str] = {
    "weak_points": "error_patterns",
    "programming_ability": "coding_ability",
    "interests": "interest_direction",
}

DEFAULT_DIMENSIONS: dict[str, dict[str, Any]] = {
    key: {
        "label": label,
        "value": "待补充",
        "score": 50,
        "confidence": 0.35,
        "explanation": "当前对话中还缺少足够信息，后续可继续补充。",
        "evidence": "",
        "source": "rule_based_fallback",
    }
    for key, label in PROFILE_DIMENSION_LABELS.items()
}


def clamp_score(value: Any, default: int = 50) -> int:
    try:
        number = int(round(float(value)))
    except (TypeError, ValueError):
        return default
    return max(0, min(100, number))


def clamp_confidence(value: Any, default: float = 0.5) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return max(0.0, min(1.0, number))


def normalize_profile_dimensions(
    dimensions: list[dict[str, Any]] | dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Normalize dimensions to the stable 10-dimension schema."""
    if dimensions is None:
        dimensions = []

    if isinstance(dimensions, dict):
        dims_list: list[dict[str, Any]] = []
        for key, value in dimensions.items():
            if isinstance(value, dict):
                dims_list.append({"key": key, **value})
            else:
                dims_list.append({"key": key, "value": str(value)})
        dimensions = dims_list
    elif not isinstance(dimensions, list):
        return []

    by_key: dict[str, dict[str, Any]] = {}
    for dim in dimensions:
        if not isinstance(dim, dict):
            continue
        old_key = str(dim.get("key", "")).strip()
        new_key = OLD_TO_NEW_KEYS.get(old_key, old_key)
        if new_key not in PROFILE_DIMENSION_LABELS:
            continue

        default = DEFAULT_DIMENSIONS[new_key]
        value_text = str(dim.get("value", default["value"])).strip() or default["value"]
        explanation = str(dim.get("explanation", "")).strip() or value_text
        evidence = str(dim.get("evidence", "")).strip()
        source = str(dim.get("source", default["source"])).strip() or default["source"]

        by_key[new_key] = {
            "key": new_key,
            "label": str(dim.get("label", default["label"])) or default["label"],
            "value": value_text,
            "score": clamp_score(dim.get("score"), default["score"]),
            "confidence": clamp_confidence(dim.get("confidence"), default["confidence"]),
            "explanation": explanation,
            "description": explanation,
            "evidence": evidence,
            "source": source,
        }

    normalized: list[dict[str, Any]] = []
    for key in PROFILE_DIMENSION_ORDER:
        if key in by_key:
            normalized.append(by_key[key])
            continue
        normalized.append(
            {
                "key": key,
                "description": DEFAULT_DIMENSIONS[key]["explanation"],
                **DEFAULT_DIMENSIONS[key],
            }
        )
    return normalized


# ── 科目感知维度 ───────────────────────────────────────────


def detect_course_category(course_context: dict[str, Any] | None) -> str:
    """从课程上下文中检测科目分类。

    优先级：course.json 中的 category 字段 > 关键词自动检测 > 'general'
    """
    if not course_context or not isinstance(course_context, dict):
        return "general"

    # 1. 明确声明的 category
    explicit = str(course_context.get("category", "")).strip().lower()
    if explicit in COURSE_CATEGORIES:
        return explicit

    # 2. 关键词自动检测
    text_parts = [
        str(course_context.get("course_name", "")),
        str(course_context.get("course_id", "")),
        str(course_context.get("description", "")),
        " ".join(str(s) for s in course_context.get("target_students", [])),
    ]
    combined = " ".join(text_parts)

    # 按关键词密度排序，得分最高者胜出
    scores: dict[str, int] = {}
    for cat_key, cat_def in COURSE_CATEGORIES.items():
        if cat_key == "general":
            continue
        score = sum(1 for kw in cat_def.get("keywords", []) if kw in combined)
        if score > 0:
            scores[cat_key] = score

    if scores:
        return max(scores, key=scores.get)  # type: ignore[arg-type]

    return "general"


def get_active_dimensions(course_context: dict[str, Any] | None = None) -> list[str]:
    """返回当前课程上下文中应激活的画像维度列表。

    通用维度始终包含；科目专属维度（如 coding_ability）仅在匹配时添加。
    """
    category = detect_course_category(course_context)
    extra = COURSE_CATEGORIES.get(category, {}).get("extra_dimensions", [])
    return UNIVERSAL_DIMENSIONS + extra


def get_active_dimension_labels(course_context: dict[str, Any] | None = None) -> dict[str, str]:
    """返回当前课程上下文中应激活的维度标签映射。"""
    active = get_active_dimensions(course_context)
    return {key: PROFILE_DIMENSION_LABELS[key] for key in active if key in PROFILE_DIMENSION_LABELS}
