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

class Section3Scene(TeachingScene):
    def construct(self):
        self.setup_layout("第3节：核心概念：导数的定义式", ["导数定义：f'(x₀)=lim_{h→0} [f(x₀+h)-f(x₀)]/h", 'h是自变量增量，分子是函数增量', '极限表示瞬时变化率', '代入f(x)=x²，x₀=1', '化简得极限为2'])
        
        # === Animation for Lecture Line 1 ===
        derivative_def = MathTex(r"f'(x_0) = \lim_{{h \to 0}} \frac{f(x_0 + h) - f(x_0)}{h}", color=BLACK)
        derivative_def.set_color_by_tex(r"\lim_{{h \to 0}}", BLUE)
        derivative_def.set_color_by_tex(r"h \to 0", BLUE)
        derivative_def.set_color_by_tex(r"f(x_0 + h) - f(x_0)", YELLOW)
        derivative_def.set_color_by_tex(r"h", ORANGE)
        self.place_at_grid(derivative_def, 'B2', scale_factor=0.8)
        self.play(FadeIn(derivative_def))
        self.wait(1)
        self.lecture[0].set_color(GREEN)
        self.wait(1)

        # === Animation for Lecture Line 2 ===
        self.lecture[1].set_color(GREEN)
        self.wait(1)

        # === Animation for Lecture Line 3 ===
        instantaneous_rate = Text("瞬时变化率", font_size=22, color="#87CEEB")
        self.place_at_grid(instantaneous_rate, 'D2', scale_factor=0.8)
        self.play(FadeIn(instantaneous_rate))
        self.play(Blink(instantaneous_rate), run_time=2)
        self.lecture[2].set_color(GREEN)
        self.wait(1)

        # === Animation for Lecture Line 4 ===
        substitution = MathTex(r"f(1 + h) - f(1) = (1 + h)^2 - 1^2 = 2h + h^2", color=BLACK)
        self.place_at_grid(substitution, 'F2', scale_factor=0.8)
        self.play(FadeIn(substitution))
        self.lecture[3].set_color(GREEN)
        self.wait(1)

        # === Animation for Lecture Line 5 ===
        simplified_limit = MathTex(r"\lim_{{h \to 0}} (2 + h) = 2", color=BLACK)
        self.place_at_grid(simplified_limit, 'F4', scale_factor=0.8)
        self.play(FadeIn(simplified_limit))
        final_result = MathTex(r"2", color="#FFD700").scale(1.5)
        self.place_at_grid(final_result, 'F5', scale_factor=0.8)
        self.play(FadeIn(final_result))
        self.lecture[4].set_color(GREEN)
        self.wait(1)