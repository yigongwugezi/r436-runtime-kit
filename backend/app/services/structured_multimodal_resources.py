"""Safe local templates for structured learning visuals.

The P4 resources are deliberately local: they work when no external model is
available and only use a small, validated Mermaid subset.
"""

from __future__ import annotations

import re
from typing import Any


STRUCTURED_RESOURCE_DEFINITIONS = {
    "knowledge_map": ("知识结构图", "mindmap"),
    "process_flow": ("学习流程图", "mindmap"),
    "concept_diagram": ("概念对比图", "mindmap"),
    "execution_trace": ("执行过程图", "mindmap"),
    "code_trace": ("代码运行轨迹", "case_study"),
}
_RESOURCE_LABELS = {key: value[0] for key, value in STRUCTURED_RESOURCE_DEFINITIONS.items()}
ALLOWED_MERMAID_TYPES = {"flowchart", "graph", "sequenceDiagram", "mindmap", "stateDiagram-v2"}
_DANGEROUS_MERMAID = re.compile(r"%%\{|\b(?:click|style|classDef|linkStyle)\b|<\s*(?:script|iframe|img)\b|javascript:|\bon\w+\s*=", re.I)


def _text(value: Any, limit: int = 96) -> str:
    text = " ".join(str(value or "").replace("\r", "").replace("\n", " ").split())
    return text[:limit]


def _label(value: Any) -> str:
    return _text(value, 56).replace('"', "'").replace("[", "（").replace("]", "）").replace("{", "（").replace("}", "）") or "学习要点"


def normalized_points(items: Any, topic: str) -> list[str]:
    values = items if isinstance(items, list) else []
    points = [_text(item.get("name") if isinstance(item, dict) else item, 48) for item in values]
    points = [point for point in points if point]
    return list(dict.fromkeys(points))[:6] or [_label(topic)]


def normalized_topic(section_title: Any, knowledge_points: Any = None) -> str:
    """Use a short, teachable topic instead of a full task sentence."""
    raw = f"{section_title or ''} {' '.join(normalized_points(knowledge_points, ''))}".lower()
    if any(token in raw for token in ("递归", "recursion", "阶乘", "factorial", "调用栈", "栈帧")):
        return "递归调用栈"
    return _label(section_title)


def normalized_resource_title(section_title: Any, resource_type: str, knowledge_points: Any = None) -> str:
    """Return one user-facing title; IDs and stored bindings stay unchanged."""
    topic = normalized_topic(section_title, knowledge_points)
    if topic == "递归调用栈":
        special = {
            "knowledge_map": "递归调用栈知识结构图",
            "process_flow": "递归调用栈学习流程图",
            "concept_diagram": "递归与迭代概念对比",
            "execution_trace": "阶乘递归执行过程图",
            "code_trace": "阶乘函数代码运行轨迹",
        }
        if resource_type in special:
            return special[resource_type]
    return f"{topic}{_RESOURCE_LABELS.get(resource_type, '')}".strip() or "学习资源"


def sanitize_mermaid(value: Any) -> str:
    """Return a render-safe Mermaid definition or an empty string.

    The validator intentionally supports only the small diagram dialect emitted
    by this module.  Rejecting unknown syntax is safer than forwarding it to
    the browser renderer.
    """
    raw = str(value or "").replace("\r", "").strip()
    fenced = re.search(r"```(?:mermaid)?\s*(.*?)```", raw, re.S | re.I)
    if fenced:
        raw = fenced.group(1).strip()
    lines = [line.rstrip() for line in raw.splitlines()]
    start = next(
        (
            index
            for index, line in enumerate(lines)
            if line.strip() and line.strip().split(maxsplit=1)[0] in ALLOWED_MERMAID_TYPES
        ),
        -1,
    )
    if start < 0:
        return ""
    lines = [line for line in lines[start:] if line.strip()]
    candidate = "\n".join(lines).strip()
    if _DANGEROUS_MERMAID.search(candidate):
        return ""
    header = lines[0].strip().split(maxsplit=1)[0]
    if header not in ALLOWED_MERMAID_TYPES:
        return ""
    if len(candidate) > 8_000:
        return ""

    labels = re.findall(r'\["([^"\n]*)"\]|\(\(([^()\n]*)\)\)|\[([^\]\n]*)\]', candidate)
    label_values = [next((part for part in match if part), "") for match in labels]
    if any(not label.strip() or len(label.strip()) > 120 for label in label_values):
        return ""

    node_labels: dict[str, str] = {}
    for node_id, label in re.findall(r'\b([A-Za-z][\w-]*)\s*\["?([^\]"\n]+)"?\]', candidate):
        previous = node_labels.setdefault(node_id, label.strip())
        if previous != label.strip():
            return ""
    edge_ids = re.findall(r'\b([A-Za-z][\w-]*)\s*(?:-->|---|==>|-.->|->>|-->>)', candidate)
    edge_ids += re.findall(r'(?:-->|---|==>|-.->|->>|-->>)\s*\b([A-Za-z][\w-]*)', candidate)
    if len(set(node_labels).union(edge_ids)) > 40 or len(re.findall(r'-->|---|==>|-.->|->>|-->>', candidate)) > 60:
        return ""
    if header == "mindmap" and not re.search(r'\broot\(\([^()\n]+\)\)', candidate):
        return ""
    return candidate


def _subject_kind(subject: str, topic: str, points: list[str]) -> str:
    text = f"{subject} {topic} {' '.join(points)}".lower()
    if any(token in text for token in ("数学", "微积分", "函数", "极限", "导数", "积分", "方程")):
        return "math"
    if any(token in text for token in ("英语", "语法", "词汇", "阅读", "写作", "english")):
        return "english"
    if any(token in text for token in ("物理", "力学", "电路", "电磁", "运动", "光学")):
        return "physics"
    if any(token in text for token in ("数据结构", "算法", "python", "编程", "递归", "数组", "链表", "代码", "计算机")):
        return "computer"
    return "general"


def _personalization(profile: dict[str, Any] | None) -> dict[str, Any]:
    profile = profile or {}
    context = profile.get("subject_context") if isinstance(profile.get("subject_context"), dict) else {}
    preferences = [str(item) for item in context.get("content_preferences") or [] if str(item).strip()][:3]
    mastery = profile.get("knowledge_mastery") if isinstance(profile.get("knowledge_mastery"), list) else []
    weak = [str(item.get("label") or item.get("knowledge_id") or "") for item in mastery if isinstance(item, dict) and item.get("status") == "weak"]
    return {
        "learner_level": "beginner" if any(word in " ".join(str(item) for item in context.get("prior_experience") or []) for word in ("零基础", "没学过", "基础薄弱", "初学")) else "general",
        "preferences": preferences,
        "weak_points": [item for item in weak if item][:3],
    }


def _flow(topic: str, points: list[str]) -> str:
    lines = ["flowchart TD", f'  ROOT["{_label(topic)}"]']
    for index, point in enumerate((points or [topic])[:4], 1):
        lines.append(f'  ROOT --> N{index}["{_label(point)}"]')
    return sanitize_mermaid("\n".join(lines))


def _recursion_trace(topic: str, points: list[str], resource_type: str, feedback: str = "") -> dict[str, Any]:
    mermaid = sanitize_mermaid(
        """sequenceDiagram
  participant U as 调用者
  participant F4 as factorial(4)
  participant F3 as factorial(3)
  participant F2 as factorial(2)
  participant F1 as factorial(1)
  U->>F4: n=4，创建栈帧
  F4->>F3: 等待 factorial(3)
  F3->>F2: 等待 factorial(2)
  F2->>F1: 到达基例 n=1
  F1-->>F2: 返回 1
  F2-->>F3: 返回 2
  F3-->>F4: 返回 6
  F4-->>U: 返回 24"""
    )
    code = '''def factorial(n):
    if not isinstance(n, int):
        raise TypeError("n 必须是整数")
    if n < 0:
        raise ValueError("n 必须是非负整数")
    return 1 if n <= 1 else n * factorial(n - 1)'''
    common = f"""## {topic}：factorial(4) 执行轨迹

### 调用栈
| 步骤 | 调用 | 参数与局部变量 | 栈深度 | 状态 |
|---|---|---|---:|---|
| 1 | factorial(4) | n=4 | 1 | 等待 factorial(3) |
| 2 | factorial(3) | n=3 | 2 | 等待 factorial(2) |
| 3 | factorial(2) | n=2 | 3 | 等待 factorial(1) |
| 4 | factorial(1) | n=1 | 4 | 命中基例，返回 1 |

### 返回后继续执行
| 栈帧 | 局部变量 | 返回后继续执行 |
|---|---|---|
| factorial(4) | n=4 | 计算 `4 × factorial(3)` 的返回值 |
| factorial(3) | n=3 | 计算 `3 × factorial(2)` 的返回值 |
| factorial(2) | n=2 | 计算 `2 × factorial(1)` 的返回值 |
| factorial(1) | n=1 | 命中终止条件，返回 1 |

### 返回过程
| 返回层 | 返回值 | 计算 |
|---|---:|---|
| factorial(1) | 1 | 基例 |
| factorial(2) | 2 | 2 × 1 |
| factorial(3) | 6 | 3 × 2 |
| factorial(4) | 24 | 4 × 6 |

### 关键点
- 每次调用都会创建一个包含局部变量 `n` 和返回地址的栈帧。
- `n<=1` 是终止条件，因此 `factorial(0)=1`、`factorial(1)=1`。
- 负数会被明确拒绝，避免无终止的递归。
- 时间复杂度为 `O(n)`，调用栈空间复杂度为 `O(n)`。

### 易错点与自测
- 不要遗漏基例，否则递归不会停止。
- 想一想：`factorial(0)` 为什么也应返回 `1`？"""
    if resource_type == "code_trace":
        common = f"## {topic}：安全代码运行轨迹\n\n输入：`factorial(4)`。下方代码只展示一次；调用和返回表说明每层栈帧如何继续执行。\n\n{common.split('### 调用栈', 1)[1]}"
    if feedback == "too_hard":
        mermaid = sanitize_mermaid(
            """sequenceDiagram
  participant U as 调用者
  participant F3 as factorial(3)
  participant F2 as factorial(2)
  participant F1 as factorial(1)
  U->>F3: 从 n=3 开始
  F3->>F2: 等待 factorial(2)
  F2->>F1: 等待 factorial(1)
  F1-->>F2: 返回 1
  F2-->>F3: 返回 2
  F3-->>U: 返回 6"""
        )
        common = f"""## {topic}：从 factorial(3) 开始

先只看三个栈帧：`factorial(3)`、`factorial(2)` 和 `factorial(1)`。每一层只保存自己的 `n`，并等待下一层返回。

### 分步调用表
| 栈帧 | 局部变量 | 正在等待 | 返回后继续执行 |
|---|---|---|---|
| factorial(3) | n=3 | factorial(2) | 计算 `3 × factorial(2)` |
| factorial(2) | n=2 | factorial(1) | 计算 `2 × factorial(1)` |
| factorial(1) | n=1 | 无 | 命中终止条件，返回 1 |

### 逐层返回
1. `factorial(1)` 因为 `n<=1` 返回 1。
2. `factorial(2)` 在原来的返回位置继续，计算 `2 × 1 = 2`。
3. `factorial(3)` 在原来的返回位置继续，计算 `3 × 2 = 6`。

### 先记住这三点
- 终止条件让递归停下来；调用栈保存每层栈帧和局部变量。
- `factorial(0)=1`，`factorial(1)=1`；负数会被拒绝。
- 时间复杂度和调用栈空间复杂度都是 `O(n)`。"""
    elif feedback == "too_easy":
        common += "\n\n### 进阶检查\n- 对比递归与迭代实现的状态保存方式。\n- 解释深度过大时的栈溢出风险。\n- 验证 `factorial(0)=1` 与负数抛出异常的边界。"
    elif feedback == "not_relevant":
        common = common.replace(topic, "递归调用栈") + "\n\n### 主题对齐\n本版仅解释递归、终止条件、调用栈、栈帧与逐层返回。"
    return {"content": common, "mermaid_def": mermaid, "code_blocks": [{"language": "python", "code": code, "explanation": "安全阶乘示例：0 和 1 返回 1，负数被拒绝。"}] if resource_type == "code_trace" else None}


def build_structured_resource(context: dict[str, Any]) -> dict[str, Any]:
    """Build one deterministic, section-scoped visual learning resource."""
    resource_type = str(context.get("resource_type") or context.get("resourceType") or "").strip()
    if resource_type not in STRUCTURED_RESOURCE_DEFINITIONS:
        raise ValueError("unsupported structured resource type")
    section_title = _label(context.get("section_title") or context.get("sectionTitle") or "当前小节")
    points = normalized_points(context.get("knowledge_points") or context.get("knowledgePoints"), section_title)
    title = normalized_topic(section_title, points)
    profile = context.get("profile") if isinstance(context.get("profile"), dict) else {}
    subject_context = profile.get("subject_context") if isinstance(profile.get("subject_context"), dict) else {}
    subject = _label(context.get("subject") or subject_context.get("course_name") or subject_context.get("subject_name") or "")
    kind = _subject_kind(subject, title, points)
    personalization = _personalization(profile)
    feedback = str(context.get("feedback") or "").strip()
    is_recursion = any(token in f"{title} {' '.join(points)}" for token in ("递归", "recursion", "阶乘", "factorial"))

    if resource_type in {"execution_trace", "code_trace"} and is_recursion:
        payload = _recursion_trace(title, points, resource_type, feedback)
    elif resource_type == "knowledge_map" and is_recursion:
        payload = {
            "content": """## 递归调用栈知识结构图

- **递归函数**：函数通过调用自身解决规模更小的同类问题。
- **终止条件**：`n<=1` 时直接返回，防止无限调用。
- **调用栈**：每次调用都会压入一个栈帧，保存局部变量和返回位置。
- **逐层返回**：最深层先返回，上一层从等待位置继续计算。
- **示例**：阶乘和斐波那契都能展示这一过程。""",
            "mermaid_def": sanitize_mermaid("""mindmap
  root((递归调用栈))
    递归函数
      终止条件
      递归关系
    调用栈
      栈帧
      局部变量
      返回位置
    执行过程
      逐层调用
      逐层返回
    示例
      阶乘
      斐波那契"""),
        }
    elif resource_type == "process_flow" and is_recursion:
        steps = ["理解递归函数", "找到终止条件", "确定递归关系", "代入 factorial(4)", "记录每层参数与栈帧", "到达终止条件", "逐层计算返回值", "分析时间和空间复杂度", "完成类似练习"]
        lines = ["flowchart TD", '  S["开始：理解递归函数"]']
        for index, step in enumerate(steps[1:], 1):
            lines.append(f'  P{index - 1 if index > 1 else "S"} --> P{index}["{step}"]' if index > 1 else f'  S --> P1["{step}"]')
        payload = {
            "content": "## 递归调用栈学习流程\n\n" + "\n".join(f"{index}. {step}" for index, step in enumerate(steps, 1)),
            "mermaid_def": sanitize_mermaid("\n".join(lines)),
        }
    elif resource_type == "concept_diagram" and is_recursion:
        rows = [
            ("定义", "函数调用自身解决更小的同类问题", "用循环重复执行步骤"),
            ("执行方式", "通过函数调用推进", "通过循环条件推进"),
            ("状态保存", "调用栈中的栈帧保存每层局部变量", "变量或显式栈保存状态"),
            ("结束条件", "由终止条件结束最深层调用", "由循环条件结束重复执行"),
            ("返回过程", "最深层先返回，上一层在返回位置继续计算", "每轮循环直接更新下一轮所需状态"),
            ("空间开销", "常为 O(n)", "常可优化为 O(1)"),
            ("优点", "结构接近递归定义", "避免深递归的栈开销"),
            ("风险", "深度过大可能栈溢出", "状态更新遗漏会出错"),
            ("适用场景", "树遍历、分治、回溯", "线性重复计算"),
            ("易混淆点", "基例和返回位置", "循环条件和状态更新"),
        ]
        payload = {
            "content": "## 递归与迭代概念对比\n\n| 对比维度 | 递归 | 迭代 |\n|---|---|---|\n" + "\n".join(f"| {a} | {b} | {c} |" for a, b, c in rows),
            "mermaid_def": sanitize_mermaid("""flowchart LR
  T["递归调用栈"] --> R["递归"]
  T --> I["迭代"]
  R --> RS["调用栈保存状态"]
  I --> IS["变量或显式栈保存状态"]"""),
        }
    elif resource_type == "knowledge_map":
        payload = {
            "content": f"## {title} 知识结构\n\n- 中心主题：{title}\n- 核心知识：{'、'.join(points)}\n- 学习顺序：先理解定义与关系，再完成一个对应练习。",
            "mermaid_def": _flow(title, points),
        }
    elif resource_type == "process_flow":
        steps = (points + ["复盘与自测"])[:4]
        lines = ["flowchart TD", '  S["明确本节目标"]']
        previous = "S"
        for index, step in enumerate(steps, 1):
            node = f"P{index}"
            lines.append(f'  {previous} --> {node}["{_label(step)}"]')
            previous = node
        lines.append(f'  {previous} --> E["完成一道自测题"]')
        payload = {
            "content": f"## {title} 学习流程\n\n按“理解概念 → 跟随步骤 → 用例验证 → 自测复盘”的顺序推进。当前知识点：{'、'.join(points)}。",
            "mermaid_def": sanitize_mermaid("\n".join(lines)),
        }
    elif resource_type == "concept_diagram":
        first = points[0]
        second = points[1] if len(points) > 1 else f"{title} 的应用"
        payload = {
            "content": f"## {title} 概念对比\n\n| 维度 | {first} | {second} |\n|---|---|---|\n| 关注点 | 定义、条件与作用 | 使用步骤与结果 |\n| 共同点 | 都服务于 {title} 的理解 | 都需要结合例子验证 |\n| 容易混淆 | 不把名称当作完整理解 | 不跳过适用条件 |\n\n建议先用同一个例子分别说明这两个概念。",
            "mermaid_def": sanitize_mermaid(f'''flowchart LR\n  T["{title}"] --> A["{_label(first)}"]\n  T --> B["{_label(second)}"]\n  A --> C["定义与条件"]\n  B --> D["使用与结果"]'''),
        }
    elif resource_type == "execution_trace":
        steps = (points + ["完成并复盘"])[:4]
        lines = ["flowchart TD", f'  S["开始：{title}"]']
        previous = "S"
        for index, step in enumerate(steps, 1):
            node = f"E{index}"
            lines.append(f'  {previous} --> {node}["{_label(step)}"]')
            previous = node
        payload = {
            "content": f"## {title} 执行过程\n\n| 步骤 | 当前动作 | 检查点 |\n|---|---|---|\n" + "\n".join(f"| {index} | 理解 {point} | 能用自己的话说明 |" for index, point in enumerate(steps, 1)) + "\n\n完成后用一个具体输入检查每一步的变化。",
            "mermaid_def": sanitize_mermaid("\n".join(lines)),
        }
    else:  # code_trace without an executable, trusted algorithm example
        focus = points[0]
        payload = {
            "content": f"## {title} 代码运行轨迹\n\n本资源只展示安全的结构化伪代码，不执行用户代码。\n\n```text\n读取输入 → 检查 {focus} → 记录当前状态 → 输出结论\n```\n\n| 步骤 | 变量状态 | 说明 |\n|---|---|---|\n| 1 | input 已读取 | 明确输入范围 |\n| 2 | current 更新 | 逐步检查 {focus} |\n| 3 | result 输出 | 记录可验证结论 |\n\n示例流程按线性步骤展示，时间复杂度为 `O(n)`，额外空间复杂度为 `O(1)`。",
            "mermaid_def": sanitize_mermaid(f'''flowchart TD\n  I["读取输入"] --> C["检查 {_label(focus)}"]\n  C --> U["更新当前状态"]\n  U --> O["输出结果"]'''),
            "code_blocks": [{"language": "text", "code": "读取输入 → 检查知识点 → 更新状态 → 输出结果", "explanation": "安全伪代码，不执行外部或用户提供的代码。"}],
        }

    label, storage_type = STRUCTURED_RESOURCE_DEFINITIONS[resource_type]
    fallback_note = "已按反馈降低说明门槛。" if feedback == "too_hard" else "已按反馈补充挑战性检查。" if feedback == "too_easy" else ""
    return {
        "type": storage_type,
        "title": normalized_resource_title(section_title, resource_type, points),
        "description": f"基于当前小节与知识点生成的{label}{fallback_note}",
        "content": payload["content"],
        "mermaid_def": payload.get("mermaid_def") or "",
        "code_blocks": payload.get("code_blocks"),
        "format": "code" if resource_type == "code_trace" else "diagram",
        "knowledge_points": points,
        "generation_source": "local_template",
        "generation_mode": "rule_based",
        "personalization": personalization,
        "template_domain": kind,
        "used_fallback": True,
        "used_llm": False,
    }
