"""High-quality Manim CE templates for common math topics.

Each template takes topic-specific parameters and returns a complete,
renderable Manim Python script.  LLM only fills in the blanks — no
code generation hallucination possible.
"""

from __future__ import annotations

from typing import Any

# ── Template base ──────────────────────────────────────────────────────────

TEMPLATE_HEADER = '''"""Auto-generated Manim education animation."""
from manim import *

class EduScene(Scene):
    def construct(self):
        # ── Style ──
        self.camera.background_color = "#1a1a2e"
        title_color = GOLD
        text_color = WHITE
        highlight_color = BLUE
'''

TEMPLATE_FOOTER = '''
        self.wait(2.5)
'''


def _render(code: str) -> str:
    return TEMPLATE_HEADER + code + TEMPLATE_FOOTER


# ── Template 1: Function Graph ─────────────────────────────────────────────

FUNCTION_GRAPH = _render('''
        # ── Title ──
        title = Text("{title}", color=title_color, font_size=42)
        subtitle = Text("{subtitle}", color=text_color, font_size=28)
        title.to_edge(UP)
        subtitle.next_to(title, DOWN, buff=0.3)
        self.play(Write(title), run_time=1.2)
        self.wait(1.5)
        self.play(FadeIn(subtitle, shift=DOWN), run_time=0.6)

        # ── Axes ──
        axes = Axes(
            x_range=[{x_min}, {x_max}, {x_step}],
            y_range=[{y_min}, {y_max}, {y_step}],
            x_length={axis_length},
            y_length={axis_length * 0.75},
            axis_config={{"color": text_color, "include_tip": True}},
            x_axis_config={{"numbers_to_include": np.arange({x_min}, {x_max} + 1, 1)}},
            y_axis_config={{"numbers_to_include": np.arange({y_min}, {y_max} + 1, 1)}},
        )
        labels = axes.get_axis_labels(
            Tex("{x_label}", color=text_color),
            Tex("{y_label}", color=text_color),
        )
        self.play(Create(axes), Write(labels), run_time=1.2)

        # ── Graph ──
        graph = axes.plot(
            lambda x: {expression},
            color=highlight_color,
            stroke_width=3,
        )
        label = MathTex(r"{formula}", color=highlight_color, font_size=30)
        label.next_to(graph.get_end(), RIGHT, buff=0.3)
        self.play(Create(graph), Write(label), run_time=1.5)

        # ── Key point ──
        {key_point_code}

        # ── Summary ──
        summary_text = Text("{summary}", color=text_color, font_size=24)
        summary.to_edge(DOWN, buff=0.5)
        self.play(FadeIn(summary, shift=UP), run_time=1.0)
''')


# ── Template 2: Derivative (Tangent Line) ──────────────────────────────────

DERIVATIVE = _render('''
        # ── Title ──
        title = Text("{title}", color=title_color, font_size=42)
        subtitle = Text("{subtitle}", color=text_color, font_size=28)
        title.to_edge(UP)
        subtitle.next_to(title, DOWN, buff=0.3)
        self.play(Write(title), run_time=1.2)
        self.wait(1.5)
        self.play(FadeIn(subtitle, shift=DOWN), run_time=0.6)

        # ── Axes ──
        axes = Axes(
            x_range=[{x_min}, {x_max}, {x_step}],
            y_range=[{y_min}, {y_max}, {y_step}],
            axis_config={{"color": text_color, "include_tip": True}},
        )
        self.play(Create(axes), run_time=1.0)

        # ── Function curve ──
        curve = axes.plot(lambda x: {expression}, color=highlight_color, stroke_width=3)
        curve_label = MathTex(r"{formula}", color=highlight_color, font_size=26)
        curve_label.to_corner(UR)
        self.play(Create(curve), Write(curve_label), run_time=1.2)

        # ── Point marker ──
        dot = Dot(axes.c2p({point_x}, {point_y}), color=GOLD, radius=0.08)
        self.play(FadeIn(dot), run_time=0.5)

        # ── Tangent line animation ──
        slope = {slope_val}
        tangent = axes.plot(
            lambda x: slope * (x - {point_x}) + {point_y},
            color=GOLD, stroke_width=2.5,
            x_range=[{point_x} - 1.5, {point_x} + 1.5],
        )
        tangent_label = MathTex(
            r"f'({point_x_text}) = {slope_text}",
            color=GOLD, font_size=28,
        )
        tangent_label.next_to(tangent.get_center(), UP, buff=0.5)
        self.play(Create(tangent), Write(tangent_label), run_time=1.5)

        # ── Move the point ──
        tracker = ValueTracker({point_x})
        moving_dot = always_redraw(lambda: Dot(axes.c2p(tracker.get_value(), {point_y_at_x}), color=GOLD, radius=0.06))
        self.add(moving_dot)
        self.remove(dot)
        self.play(tracker.animate.set_value({end_x}), run_time=2.0, rate_func=smooth)

        # ── Summary ──
        summary_text = Text("{summary}", color=text_color, font_size=24)
        summary.to_edge(DOWN, buff=0.5)
        self.play(FadeIn(summary, shift=UP), run_time=1.0)
''')


# ── Template 3: Limit Definition ───────────────────────────────────────────

LIMIT = _render('''
        # ── Title ──
        title = Tex("{title}", color=title_color, font_size=42)
        title.to_edge(UP)
        self.play(Write(title), run_time=1.2)
        self.wait(1.5)

        # ── Formal definition ──
        definition = MathTex(
            r"{definition_formula}",
            color=text_color, font_size=32,
        )
        self.play(Write(definition), run_time=1.0)

        # ── Explanation ──
        explanation = Tex("{explanation}", color=text_color, font_size=26)
        explanation.next_to(definition, DOWN, buff=0.6)
        self.play(FadeIn(explanation, shift=UP), run_time=0.8)

        # ── Graph visualization ──
        axes = Axes(
            x_range=[{x_min}, {x_max}, 1],
            y_range=[{y_min}, {y_max}, 1],
            axis_config={{"color": text_color, "include_tip": True}},
            x_length=7, y_length=4,
        )
        axes.next_to(explanation, DOWN, buff=0.8)
        self.play(Create(axes), run_time=0.8)

        # ── Function ──
        graph = axes.plot(lambda x: {expression}, color=highlight_color, stroke_width=3)
        self.play(Create(graph), run_time=1.0)

        # ── Epsilon band ──
        eps = {epsilon}
        L = {limit_val}
        a = {point_a}
        upper = axes.plot(lambda x: L + eps, color=GOLD, stroke_width=1.5, stroke_opacity=0.5,
                          x_range=[{x_min} + 0.1, {x_max} - 0.1])
        lower = axes.plot(lambda x: L - eps, color=GOLD, stroke_width=1.5, stroke_opacity=0.5,
                          x_range=[{x_min} + 0.1, {x_max} - 0.1])
        self.play(Create(upper), Create(lower), run_time=0.8)

        # ── Point a ──
        dot = Dot(axes.c2p(a, {f_a}), color=GOLD, radius=0.06)
        self.play(FadeIn(dot), run_time=0.5)

        # ── Summary ──
        summary_text = Text("{summary}", color=text_color, font_size=24)
        summary.to_edge(DOWN, buff=0.4)
        self.play(FadeIn(summary, shift=UP), run_time=1.0)
''')


# ── Template 4: Integral (Area Under Curve) ────────────────────────────────

INTEGRAL = _render('''
        # ── Title ──
        title = Tex("{title}", color=title_color, font_size=42)
        subtitle = MathTex(r"{formula}", color=highlight_color, font_size=32)
        title.to_edge(UP)
        subtitle.next_to(title, DOWN, buff=0.3)
        self.play(Write(title), run_time=1.2)
        self.wait(1.5)
        self.play(FadeIn(subtitle, shift=DOWN), run_time=0.6)

        # ── Axes ──
        axes = Axes(
            x_range=[{x_min}, {x_max}, {x_step}],
            y_range=[{y_min}, {y_max}, {y_step}],
            axis_config={{"color": text_color, "include_tip": True}},
        )
        self.play(Create(axes), run_time=1.0)

        # ── Function ──
        graph = axes.plot(lambda x: {expression}, color=highlight_color, stroke_width=3)
        formula = MathTex(r"{formula}", color=highlight_color, font_size=26)
        formula.to_corner(UR)
        self.play(Create(graph), Write(formula), run_time=1.0)

        # ── Riemann rectangles ──
        rects = axes.get_riemann_rectangles(
            graph=graph,
            x_range=[{rect_a}, {rect_b}],
            dx={dx},
            fill_opacity=0.4,
            stroke_width=1,
            stroke_color=highlight_color,
        )
        self.play(Create(rects), run_time=2.0)

        # ── Area label ──
        area_label = MathTex(
            r"\\int_{{{a}}}^{{{b}}} f(x)\\,dx \\approx {approx_value:.2f}",
            color=GOLD, font_size=28,
        )
        area_label.next_to(rects, DOWN, buff=0.6)
        self.play(Write(area_label), run_time=1.0)

        # ── Refinement: more rectangles ──
        finer_rects = axes.get_riemann_rectangles(
            graph=graph,
            x_range=[{rect_a}, {rect_b}],
            dx={dx} / 2,
            fill_opacity=0.5,
            stroke_width=0.5,
            stroke_color=highlight_color,
        )
        self.play(Transform(rects, finer_rects), run_time=2.5)
        self.play(FadeOut(area_label))

        area_label2 = MathTex(
            r"\\int_{{{a}}}^{{{b}}} f(x)\\,dx \\xrightarrow{{n\\to\\infty}} {exact_int}",
            color=GOLD, font_size=28,
        )
        area_label2.next_to(rects, DOWN, buff=0.6)
        self.play(Write(area_label2), run_time=1.0)

        # ── Summary ──
        summary_text = Text("{summary}", color=text_color, font_size=24)
        summary.to_edge(DOWN, buff=0.4)
        self.play(FadeIn(summary, shift=UP), run_time=1.0)
''')


# ── Template 5: Concept Comparison ─────────────────────────────────────────

CONCEPT_COMPARISON = _render('''
        # ── Title ──
        title = Tex("{title}", color=title_color, font_size=42)
        title.to_edge(UP)
        self.play(Write(title), run_time=1.2)
        self.wait(1.5)

        # ── Left concept ──
        left_box = RoundedRectangle(
            width=4, height=3, color=BLUE, corner_radius=0.2,
            fill_opacity=0.15,
        ).shift(LEFT * 3.5)
        left_title = Tex("{left_title}", color=BLUE, font_size=28)
        left_title.next_to(left_box, UP, buff=0.15)
        left_content = Tex("{left_content}", color=text_color, font_size=22)
        left_content.move_to(left_box)
        self.play(
            FadeIn(left_box), Write(left_title), FadeIn(left_content),
            run_time=1.5,
        )

        # ── Right concept ──
        right_box = RoundedRectangle(
            width=4, height=3, color=GOLD, corner_radius=0.2,
            fill_opacity=0.15,
        ).shift(RIGHT * 3.5)
        right_title = Tex("{right_title}", color=GOLD, font_size=28)
        right_title.next_to(right_box, UP, buff=0.15)
        right_content = Tex("{right_content}", color=text_color, font_size=22)
        right_content.move_to(right_box)
        self.play(
            FadeIn(right_box), Write(right_title), FadeIn(right_content),
            run_time=1.5,
        )

        # ── VS label ──
        vs = Tex("VS", color=RED, font_size=36, weight=BOLD)
        self.play(Write(vs), run_time=0.5)

        # ── Key difference ──
        difference = Tex("{difference}", color=text_color, font_size=24)
        difference.to_edge(DOWN, buff=0.8)
        self.play(FadeIn(difference, shift=UP), run_time=1.0)
''')


# ── Template selector ──────────────────────────────────────────────────────

TEMPLATES = {
    "function_graph": {
        "name": "函数图像",
        "template": FUNCTION_GRAPH,
        "params": [
            "title", "subtitle",
            "x_min", "x_max", "x_step",
            "y_min", "y_max", "y_step",
            "axis_length",
            "x_label", "y_label",
            "expression", "formula",
            "key_point_code",
            "summary",
        ],
    },
    "derivative": {
        "name": "导数可视化",
        "template": DERIVATIVE,
        "params": [
            "title", "subtitle",
            "x_min", "x_max", "x_step",
            "y_min", "y_max", "y_step",
            "expression", "formula",
            "point_x", "point_y", "point_x_text",
            "slope_val", "slope_text",
            "point_y_at_x", "end_x",
            "summary",
        ],
    },
    "limit": {
        "name": "极限定义",
        "template": LIMIT,
        "params": [
            "title", "definition_formula", "explanation",
            "x_min", "x_max", "y_min", "y_max",
            "expression", "epsilon", "limit_val", "point_a", "f_a",
            "summary",
        ],
    },
    "integral": {
        "name": "定积分演示",
        "template": INTEGRAL,
        "params": [
            "title", "formula",
            "x_min", "x_max", "x_step",
            "y_min", "y_max", "y_step",
            "expression",
            "rect_a", "rect_b", "dx",
            "approx_value", "exact_int",
            "summary",
        ],
    },
    "concept_comparison": {
        "name": "概念对比",
        "template": CONCEPT_COMPARISON,
        "params": [
            "title",
            "left_title", "left_content",
            "right_title", "right_content",
            "difference",
        ],
    },
}


def match_template(topic: str, subject: str) -> str | None:
    """Return the best matching template key for a topic, or None."""
    text = f"{subject} {topic}".lower()
    # Derivative patterns
    if any(w in text for w in ["导数", "微分", "切线", "切线方程", "变化率", "导数定义", "求导"]):
        return "derivative"
    # Integral patterns
    if any(w in text for w in ["积分", "定积分", "不定积分", "面积", "原函数", "黎曼"]):
        return "integral"
    # Limit patterns
    if any(w in text for w in ["极限", "趋近", "收敛", "无穷小", "无穷大", "夹逼"]):
        return "limit"
    # Function graph patterns
    if any(w in text for w in ["函数", "图像", "图象", "曲线", "方程", "参数", "坐标系"]):
        return "function_graph"
    # Comparison patterns
    if any(w in text for w in ["对比", "区别", "比较", "vs", "区别", "异同"]):
        return "concept_comparison"
    return None


def fill_template(llm, template_key: str, topic: str, subject: str, kb_context: str) -> str | None:
    """Use LLM to fill template parameters from topic context."""
    template_info = TEMPLATES.get(template_key)
    if not template_info:
        return None

    params_desc = "\n".join(f"  {p}: ..." for p in template_info["params"])

    kb_block = f"\n\n知识点参考资料：\n{kb_context}" if kb_context else ""

    prompt = f"""请根据以下教学主题，为 Manim 动画模板填充参数。

## 模板类型
{template_info["name"]}

## 教学主题
课程: {subject}
节: {topic}
{kb_block}

## 需要填充的参数
{params_desc}

## 规则
- 数值参数填具体数字（如 x_min=-3, x_max=3）
- 文字参数用中文（如 title="函数的定义与基本性质"）
- expression 填 Python lambda 表达式（如 "x**2"）
- formula 填 LaTeX 公式（如 "f(x)=x^2"）
- 确保所有数值合理（坐标范围内函数有意义）
- key_point_code 填 Manim 代码，标注图像上的关键点（如最值点、零点），如果不需可留空
- summary 填一句 15 字以内的中文总结

只输出 JSON：
{{"title": "...", "subtitle": "...", ...（所有模板参数）}}"""

    try:
        raw = llm.chat(messages=[
            {"role": "system", "content": "你是数学教育动画专家。只输出 JSON 参数。"},
            {"role": "user", "content": prompt},
        ], temperature=0.2, max_tokens=1500)
        raw = raw.strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```\w*\n", "", raw)
            raw = re.sub(r"\n```$", "", raw)
        params = json.loads(raw)
        # Fill the template with defaults for unfilled params
        script = template_info["template"]
        for key in template_info["params"]:
            value = params.get(key, "")
            if not value:
                # Provide sensible defaults for unfilled params
                value = {
                    "x_min": "-5", "x_max": "5", "x_step": "1",
                    "y_min": "-3", "y_max": "3", "y_step": "1",
                    "axis_length": "7",
                    "x_label": "x", "y_label": "y",
                    "summary": "理解核心概念，掌握基本方法",
                    "key_point_code": "",
                    "subtitle": "",
                    "point_x_text": "a", "point_y_at_x": "0",
                }.get(key, "")
            script = script.replace("{" + key + "}", str(value))
        # Fix double-brace escapes (leftover from f-string format)
        script = script.replace("{{", "{").replace("}}", "}")
        script = script.replace("summary_text", "summary")
        # Convert Tex() to Text() for Chinese compatibility, keep MathTex for formulas
        import re as _re
        script = _re.sub(r'(?<!Math)Tex\(', 'Text(', script)
        return script
    except Exception as e:
        logger.warning("Template fill failed: %s", e)
        return None


import json
import logging
import re

logger = logging.getLogger(__name__)
