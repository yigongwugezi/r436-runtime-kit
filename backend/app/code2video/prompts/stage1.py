def get_prompt1_outline(knowledge_point, duration=5, reference_image_path=None):
    prompt = f"""你是一位优秀的教学设计专家，请为以下知识点设计一个逻辑清晰、循序渐进、实例驱动的教学大纲。

知识点：{knowledge_point}

请用中文输出 JSON 格式的教学大纲：
{{
    "topic": "主题名称",
    "target_audience": "目标受众",
    "sections": [
        {{
            "id": "section_1",
            "title": "小节标题",
            "content": "小节内容描述",
            "example": "示例说明"
        }}
    ]
}}

要求：
1. 总时长控制在 {duration} 分钟左右
2. 小节之间要有逻辑递进关系
3. 重点突出核心概念和关键知识点
4. 数学概念尽量结合图形化展示
5. 大纲要适合动画和可视化呈现
6. 复杂概念要先引入必要的前置知识
"""
    return prompt
