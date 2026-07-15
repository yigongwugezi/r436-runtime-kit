import json


def get_prompt2_storyboard(outline, reference_image_path):
    prompt = f"""你是一位专业的教育动画设计师，擅长将教学大纲转化为适合 Manim 动画系统的分镜脚本。

## 任务
将以下教学大纲转化为详细的分镜脚本：

{outline}

## 分镜要求

### 内容结构
- 关键小节（最多3个）使用5条讲解要点+5个动画，其他小节3条讲解+3个动画
- 每条讲解要点不超过15个字
- 动画步骤要紧密对应讲解要点

### 视觉设计
- 背景固定 #000000，使用浅色/亮色作为文字和元素颜色
- 重要：提供十六进制颜色代码

### 动画效果
- 基础：出现、移动、颜色变化、淡入淡出、缩放
- 强调：闪烁、颜色变化、高亮

### 约束
- 禁止使用面板或3D方法
- 如非必要不画坐标轴
- 不要在讲解要点上施加任何动画，只在对应动画出现时改变其颜色
- 不使用 SVG 等外部资源

输出 JSON 格式：
{{
    "sections": [
        {{
            "id": "section_1",
            "title": "第1节：标题",
            "lecture_lines": ["讲解要点1", "讲解要点2", ...],
            "animations": ["动画步骤1", "动画步骤2", ...]
        }}
    ]
}}
"""
    return prompt


def get_prompt_download_assets(storyboard_data):
    return f"""分析教学视频分镜，识别最多4个需要用图标/素材展示的关键视觉元素。

内容：
{storyboard_data}

选择标准：
1. 只选择引言或应用小节中的元素
2. 元素必须是真实世界可识别的物体
3. 优先：特定动物、人物、车辆、工具、设备、日常物品

输出：每行一个关键词，全部小写，不超过4个。"""


def get_prompt_place_assets(asset_mapping, animations_structure):
    return f"""在适当的位置将下载的素材融入动画。

素材列表：
{asset_mapping}

当前动画数据：
{animations_structure}

指示：
- 判断每个动画步骤是否需要素材
- 使用格式 [Asset: XXX] 插入素材路径
- 只修改动画描述，保持结构不变
- 返回增强后的动画数据 JSON"""
