from manim import *
import numpy as np

class TeachingScene(Scene):
    def setup_layout(self, title_text, lecture_lines):
        # BASE
        self.camera.background_color = "#000000"
        self.title = Text(title_text, font_size=28, color=WHITE).to_edge(UP)
        self.add(self.title)

        # Left-side lecture content (bullets with "-")
        lecture_texts = [Text(line, font_size=22, color=WHITE) for line in lecture_lines]
        self.lecture = VGroup(*lecture_texts).arrange(DOWN, aligned_edge=LEFT).scale(0.8)
        self.lecture.to_edge(LEFT, buff=0.2)
        self.add(self.lecture)

        # Define fine-grained animation grid (6x6 grid on right side)
        self.grid = {}
        rows = ["A", "B", "C", "D", "E", "F"]
        cols = ["1", "2", "3", "4", "5", "6"]

        for i, row in enumerate(rows):
            for j, col in enumerate(cols):
                x = 0.5 + j * 1
                y = 2.2 - i * 1
                self.grid[f"{row}{col}"] = np.array([x, y, 0])

    def place_at_grid(self, mobject, grid_pos, scale_factor=1.0):
        mobject.scale(scale_factor)
        mobject.move_to(self.grid[grid_pos])
        return mobject

    def place_in_area(self, mobject, top_left, bottom_right, scale_factor=1.0):
        tl_pos = self.grid[top_left]
        br_pos = self.grid[bottom_right]
        center_x = (tl_pos[0] + br_pos[0]) / 2
        center_y = (tl_pos[1] + br_pos[1]) / 2
        center = np.array([center_x, center_y, 0])
        mobject.scale(scale_factor)
        mobject.move_to(center)
        return mobject

class Section4Scene(TeachingScene):
    def construct(self):
        self.setup_layout("第4节：极限的运算法则——简化计算", ['极限四则运算法则', '加法与减法法则', '乘法与除法法则', r'示例：$\lim_{{x\to2}} (x^2+3x-1)$', '分母极限不为零'])

        # === Animation for Lecture Line 1 ===
        self.play(self.lecture[0].animate.set_color(YELLOW))
        self.wait(1)
        self.play(self.lecture[0].animate.set_color(WHITE))

        # === Animation for Lecture Line 2 ===
        self.play(self.lecture[1].animate.set_color(YELLOW))
        self.wait(1)
        self.play(self.lecture[1].animate.set_color(WHITE))

        # === Animation for Lecture Line 3 ===
        self.play(self.lecture[2].animate.set_color(YELLOW))
        self.wait(1)
        self.play(self.lecture[2].animate.set_color(WHITE))

        # === Animation for Lecture Line 4 ===
        self.play(self.lecture[3].animate.set_color(YELLOW))
        limit_expr = MathTex(r"\lim_{{x \to 2}} (x^2 + 3x - 1)", color=WHITE)
        self.place_at_grid(limit_expr, 'B2', scale_factor=0.8)
        self.play(FadeIn(limit_expr))
        self.wait(1)
        self.play(self.lecture[3].animate.set_color(WHITE))

        # Split the expression into parts
        split_expr = MathTex(r"\lim_{{x \to 2}} x^2 + \lim_{{x \to 2}} 3x - \lim_{{x \to 2}} 1", color=BLUE)
        self.place_at_grid(split_expr, 'B2', scale_factor=0.8)
        self.play(TransformMatchingTex(limit_expr, split_expr))
        self.wait(1)

        # Calculate each part
        calc_expr1 = MathTex(r"\lim_{{x \to 2}} x^2 = 4", color=YELLOW)
        self.place_at_grid(calc_expr1, 'D2', scale_factor=0.8)
        self.play(FadeIn(calc_expr1))
        self.wait(1)

        calc_expr2 = MathTex(r"\lim_{{x \to 2}} 3x = 6", color=GREEN)
        self.place_at_grid(calc_expr2, 'E2', scale_factor=0.8)
        self.play(FadeIn(calc_expr2))
        self.wait(1)

        calc_expr3 = MathTex(r"\lim_{{x \to 2}} 1 = 1", color=MAROON)
        self.place_at_grid(calc_expr3, 'F2', scale_factor=0.8)
        self.play(FadeIn(calc_expr3))
        self.wait(1)

        # Combine results
        result_expr1 = MathTex(r"4 + 6 - 1", color=WHITE)
        self.place_at_grid(result_expr1, 'B2', scale_factor=0.8)
        self.play(TransformMatchingTex(split_expr, result_expr1))
        self.wait(1)

        final_result = MathTex(r"9", color=RED)
        self.place_at_grid(final_result, 'B2', scale_factor=0.8)
        self.play(TransformMatchingTex(result_expr1, final_result))
        self.wait(1)

        # === Animation for Lecture Line 5 ===
        self.play(self.lecture[4].animate.set_color(YELLOW))
        warning_text = MathTex(r"\text{除法时，分母极限 } \neq 0", color=GRAY)
        self.place_at_grid(warning_text, 'F4', scale_factor=0.6)
        exclamation_mark = MathTex(r"!", color=YELLOW)
        self.place_at_grid(exclamation_mark, 'F5', scale_factor=0.6)
        self.play(FadeIn(warning_text), FadeIn(exclamation_mark))
        self.play(Blink(exclamation_mark))
        self.wait(1)
        self.play(self.lecture[4].animate.set_color(WHITE))
        self.wait(2)