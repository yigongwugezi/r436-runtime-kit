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

class Section2Scene(TeachingScene):
    def construct(self):
        self.setup_layout("第2节：图形化理解：割线斜率到切线斜率", ['将速度转为函数斜率问题', '两点连线为割线，斜率=平均变化率', '两点无限接近，割线变切线', '切线斜率=瞬时变化率', '观察h→0时斜率趋近2'])

        # Function definition
        def f(x):
            return x**2

        # Plot the parabola
        parabola = ParametricFunction(lambda t: np.array([t, f(t), 0]), t_range=[-2, 2], color="#CCCCCC")
        self.play(Create(parabola))
        self.wait()

        # Red point at x=1
        red_point = Dot(color="#FF3333").move_to(np.array([1, f(1), 0]))
        self.play(Create(red_point))
        self.wait()

        # Blue point at x=1+h
        h = ValueTracker(1)
        blue_point = always_redraw(lambda: Dot(color="#3399FF").move_to(np.array([1 + h.get_value(), f(1 + h.get_value()), 0])))
        self.play(Create(blue_point))
        self.wait()

        # Secant line
        secant_line = always_redraw(lambda: Line(start=red_point.get_center(), end=blue_point.get_center(), color=BLACK))
        self.play(Create(secant_line))
        self.wait()

        # Slope formula
        slope_formula = MathTex(r"k = \frac{f(1+h)-f(1)}{h}", color=BLACK).scale(0.7)
        self.place_at_grid(slope_formula, 'B4')
        self.play(FadeIn(slope_formula))
        self.wait()

        # Highlight the point of tangency
        tangent_point_label = Text("切点", font_size=20, color=BLACK).next_to(red_point, UP, buff=0.1)
        tangent_point_arrow = Arrow(tangent_point_label.get_bottom(), red_point.get_top(), color=BLACK, buff=0.1)
        self.play(Create(tangent_point_label), Create(tangent_point_arrow))
        self.wait()

        # === Animation for Lecture Line 1 ===
        self.lecture[0].set_color(YELLOW)
        self.wait(2)

        # === Animation for Lecture Line 2 ===
        self.lecture[1].set_color(YELLOW)
        self.wait(2)

        # Move blue point towards red point
        self.lecture[2].set_color(YELLOW)
        self.play(h.animate.set_value(0.1), run_time=5)
        self.wait()

        # Change secant to tangent
        self.lecture[3].set_color(YELLOW)
        self.play(
            h.animate.set_value(0),
            secant_line.animate.set_color("#FFA500"),
            run_time=3
        )
        self.wait()

        # Final tangent line and slope value
        self.lecture[4].set_color(YELLOW)
        final_slope_value = MathTex(r"2", color="#FFD700").scale(0.7)
        self.place_at_grid(final_slope_value, 'B5')
        self.play(TransformMatchingTex(slope_formula, final_slope_value))
        self.wait(2)

        # Clean up
        self.play(FadeOut(red_point), FadeOut(blue_point), FadeOut(secant_line), FadeOut(final_slope_value), FadeOut(tangent_point_label), FadeOut(tangent_point_arrow))
        self.wait()