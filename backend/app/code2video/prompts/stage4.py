def get_prompt4_layout_feedback(section, position_table):
    return f"""
1. 分析要求：
- 仅分析此 Manim 教学视频的布局和空间定位问题
- 重点消除重叠、遮挡，优化网格空间利用

2. 内容上下文：
- 标题：{section.title}
- 讲解要点：{'; '.join(section.lecture_lines)}
- 当前网格占用：{position_table}

3. 视觉锚点系统（6×6 网格）：
```
lecture |  A1  A2  A3  A4  A5  A6
        |  B1  B2  B3  B4  B5  B6
        |  C1  C2  C3  C4  C5  C6
        |  D1  D2  D3  D4  D5  D6
        |  E1  E2  E3  E4  E5  E6
        |  F1  F2  F3  F4  F5  F6
```

4. 约束：
- 讲解文字不移动、不缩放、只改颜色
- 标签距离对象不超过1个网格单位

5. 输出 JSON：
{{
    "layout": {{
        "has_issues": true/false,
        "improvements": [
            {{
                "problem": "具体问题描述",
                "solution": "第X行：self.place_at_grid(...) 或 self.place_in_area(...)",
                "line_number": X,
                "object_affected": "对象名"
            }}
        ]
    }}
}}

最多列出3个最影响视觉体验的布局问题。
"""


def get_feedback_list_prefix(feedback_improvements):
    return f"""
MLLM 反馈改进建议：基于视频分析，请解决以下问题：
{chr(10).join([f"- {improvement}" for improvement in feedback_improvements])}
"""


def get_feedback_improve_code(feedback, code):
    return f"""
你是 Manim v0.19.0 教育动画专家。

必须保留：
- 基于以下反馈改进当前的 Manim 代码
- 使用浅色做动画和标签
- 讲解文字只改颜色，不移动不缩放
- 只输出完整 Python 代码，不要解释

反馈：
{feedback}

---

当前代码：
```python
{code}
```
"""
