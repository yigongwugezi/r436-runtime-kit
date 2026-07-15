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
        self.setup_layout("第2节：极限的直观定义——左右逼近与唯一值", ['左极限与右极限概念', '分段函数 f(x) 示例', '从左侧趋近 x=1', '从右侧趋近 x=1', '左右不等，极限不存在'])

        # === Animation for Lecture Line 1 ===
        self.play(self.lecture[0].animate.set_color("#00FFFF"))
        self.wait(1)

        # === Animation for Lecture Line 2 ===
        self.play(self.lecture[1].animate.set_color("#00FFFF"))
        # Draw the piecewise function
        left_line = Line(start=np.array([-1, 0, 0]), end=np.array([1, 2, 0]), color="#00FFFF")
        right_line = Line(start=np.array([1, 1, 0]), end=np.array([3, 3, 0]), color="#00FFFF")
        isolated_point = Dot(point=np.array([1, 2, 0]), color="#FFFF00", radius=0.05)
        vertical_line = DashedLine(start=np.array([1, -1, 0]), end=np.array([1, 3, 0]), color="#AAAAAA")

        self.play(Create(left_line), Create(right_line), Create(isolated_point), Create(vertical_line))
        self.wait(1)

        # === Animation for Lecture Line 3 ===
        self.play(self.lecture[2].animate.set_color("#00FFFF"))
        left_dot = Dot(point=np.array([0.8, 1.8, 0]), color="#FF5555", radius=0.05)
        self.play(Create(left_dot))
        self.play(MoveAlongPath(left_dot, left_line), run_time=2)
        self.play(left_dot.animate.set_color("#FF0000"))
        self.wait(1)

        # === Animation for Lecture Line 4 ===
        self.play(self.lecture[3].animate.set_color("#00FFFF"))
        right_dot = Dot(point=np.array([1.2, 1.2, 0]), color="#5555FF", radius=0.05)
        self.play(Create(right_dot))
        self.play(MoveAlongPath(right_dot, right_line), run_time=2)
        self.play(right_dot.animate.set_color("#0000FF"))
        self.wait(1)

        # === Animation for Lecture Line 5 ===
        self.play(self.lecture[4].animate.set_color("#00FFFF"))
        # Flash the y-values
        flash1 = Flash(left_dot, color="#FF0000")
        flash2 = Flash(right_dot, color="#0000FF")
        self.play(flash1, flash2)
        # Display the 'X' and '极限不存在'
        x_mark = MathTex("X", color="#FF0000").scale(2)
        limit_not_exist = Text("极限不存在", font_size=36, color="#000000")
        self.place_at_grid(x_mark, 'B2', scale_factor=0.8)
        self.place_at_grid(limit_not_exist, 'D2', scale_factor=0.8)
        self.play(FadeIn(x_mark), FadeIn(limit_not_exist))
        self.wait(2)