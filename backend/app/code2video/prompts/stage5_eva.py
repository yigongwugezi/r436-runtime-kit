import json


def get_prompt_aes(knowledge_point):
    return f"""
你是教育内容评估专家。请评估此教学视频的质量。

知识点：{knowledge_point}

**评估维度：**

1. 布局 (20分)：空间安排、可读性、平衡
2. 吸引力 (20分)：配色、视觉设计、动画效果
3. 逻辑流程 (20分)：内容递进、过渡、节奏
4. 准确性与深度 (20分)：内容正确性、深度、覆盖面
5. 视觉一致性 (20分)：风格统一、配色一致

**输出 JSON：**
{{
    "layout": {{"score": 0-20, "feedback": "..."}},
    "attractiveness": {{"score": 0-20, "feedback": "..."}},
    "logic_flow": {{"score": 0-20, "feedback": "..."}},
    "accuracy_depth": {{"score": 0-20, "feedback": "..."}},
    "visual_consistency": {{"score": 0-20, "feedback": "..."}},
    "overall_score": 0-100,
    "summary": "总体评价",
    "strengths": ["优点"],
    "improvements": ["改进建议"]
}}
"""
