def get_prompt3_code(regenerate_note, section, base_class):
    section_id = section.id.replace('_', '').title()
    return f"""你是 Manim Community Edition v0.19.0 专家。请根据以下教学脚本生成高质量的 Manim 动画代码。
{regenerate_note}

1. 基本要求：
- 使用提供的 TeachingScene 基类，不要修改
- 每条讲解要点在对应动画出现时改变颜色
- 不要在讲解文字上施加缩放、平移或 Transform 动画

2. 视觉锚点系统（必须使用）：
- 使用 6×6 网格系统精确定位
- 使用 self.place_at_grid(obj, 'B2', scale_factor=0.8) 或 self.place_in_area(obj, 'A1', 'C3', scale_factor=0.7)
- 禁止使用 .to_edge()、.move_to() 手动定位

3. 教学内容：
- 标题：{section.title}
- 讲解要点：{section.lecture_lines}
- 动画描述：{'; '.join(section.animations)}

4. 代码结构（使用注释标记所属讲解要点）：
```python
from manim import *
import numpy as np

{base_class}

class {section_id}Scene(TeachingScene):
    def construct(self):
        self.setup_layout("{section.title}", {section.lecture_lines})

        # === Animation for Lecture Line 1 ===
        ...

        # === Animation for Lecture Line 2 ===
        ...
```

5. 强制约束：
- 颜色：使用浅色十六进制颜色，确保可读性
- 禁止使用 Tex()，全部用 MathTex() 写 LaTeX 公式
- 禁止使用 SVGMobject、ImageMobject
- 确保导入 numpy
- Scene 类名为 {section_id}Scene
- 【关键】所有 MathTex 都必须使用 raw string，如 MathTex(r"x^2 + y^2 = 1")，禁止在公式内使用 $$ 符号
"""
    return prompt


def get_regenerate_note(attempt, MAX_REGENERATE_TRIES):
    return f"""
**重要提示：** 这是第 {attempt}/{MAX_REGENERATE_TRIES} 次尝试生成代码。
之前的尝试运行失败了。请：
1. 只使用基础的、经过验证的 Manim 函数
2. 避免可能导致错误的复杂动画
3. 使用简单、可靠的 Manim 模式
"""
