import json


def get_prompt2_storyboard(outline, reference_image_path, user_requirements=""):
    req_block = f"""
## 用户特殊要求（必须严格遵循，优先级最高）
{user_requirements}
""" if user_requirements else ""
    prompt = f"""你是一位专业的教育动画设计师，擅长将教学大纲转化为适合 Manim 动画系统的分镜脚本。
{req_block}
## 任务
将以下教学大纲转化为详细的分镜脚本。大纲中已经包含了具体元素和动画步骤，请充分利用这些信息。

{outline}

## 分镜要求

### 讲解要点（lecture_lines）
- 关键小节（开头或核心的 2~3 个）使用 5 条讲解要点，其余使用 3 条
- 每条讲解要点不超过 15 个字，必须是对应动画步骤的语言概括

### 动画步骤（animations）
- 数量与讲解要点一一对应
- 每条动画描述必须包含以下三项信息：
  1. 画什么元素（名称、形状、位置）
  2. 用什么颜色（必须给出十六进制颜色码）
  3. 显示什么文字/公式（精确写法）
- 格式示例：
  "在坐标系B2:C4区域画f(x)=x²曲线，颜色#FFD700"
  "在点(1,1)放置红色圆点标记，颜色#FF4444，旁标文字'P(1,1)'"
  "显示极限表达式 lim_{{h→0}} (f(1+h)-f(1))/h，颜色#00BFFF，置于D2:E4区域"

### 视觉设计
- 背景固定 #000000，所有文字和元素使用浅色/亮色
- 一个 section 内部颜色方案保持统一（同一色系），不同 section 可换色系
- 重要公式用高亮色，辅助文字用白色

### 动画效果
- 基础：出现、移动、颜色变化、淡入淡出、缩放
- 强调：闪烁、颜色变化、高亮
- 每次动画后适当停顿（在描述末尾标注 wait 时间）

### 约束
- 禁止使用面板或3D方法
- 如非必要不画坐标轴
- 不要在讲解要点文字上施加任何动画，只在对应动画出现时改变其颜色
- 不使用 SVG 等外部资源
- 如果大纲给出了 visual_elements 和 animation_steps，直接把它们转化为 animations 数组

输出 JSON 格式：
{{
    "sections": [
        {{
            "id": "section_1",
            "title": "第1节：标题",
            "lecture_lines": ["讲解要点1", "讲解要点2", ...],
            "animations": ["动画步骤1（含颜色码和公式）", "动画步骤2", ...]
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
