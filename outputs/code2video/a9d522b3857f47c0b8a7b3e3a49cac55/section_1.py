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

class Section1Scene(TeachingScene):
    def construct(self):
        self.setup_layout("第1节：为什么需要极限？——从“趋近”说起", 
                          ['函数 f(x)=x² 在 x=2 附近', 
                           'x 从左侧靠近 2', 
                           'x 从右侧靠近 2', 
                           'y 值趋近于 4', 
                           '极限描述趋势，而非到达'])

        # === Animation for Lecture Line 1 ===
        func_graph = FunctionGraph(lambda x: x**2, x_range=[-1, 3], color="#00FFFF")
        point_2_4 = Dot(point=[2, 4, 0], color="#FFFF00")
        label_2_4 = MathTex(r"(2, 4)").next_to(point_2_4, RIGHT, buff=0.1).set_color("#FFFF00")
        graph_group = VGroup(func_graph, point_2_4, label_2_4)
        self.play(Create(graph_group))
        self.lecture[0].set_color(YELLOW)
        self.wait(2)

        # === Animation for Lecture Line 2 ===
        left_point = Dot(point=[1.9, 1.9**2, 0], color="#FF5555")
        left_label_x = MathTex(r"x = 1.9").next_to(left_point, DOWN, buff=0.1).set_color(BLACK)
        left_label_y = MathTex(r"y = 3.61").next_to(left_point, UP, buff=0.1).set_color(BLACK)
        left_labels = VGroup(left_label_x, left_label_y)
        self.play(Create(left_point), Write(left_labels))
        self.lecture[1].set_color(YELLOW)
        self.wait(1)

        left_path = VMobject()
        left_path.set_points_as_corners([left_point.get_center(), *[np.array([x, x**2, 0]) for x in np.linspace(1.9, 2, 100)]])
        left_path.set_color("#FF5555")
        self.play(MoveAlongPath(left_point, left_path), 
                  TransformMatchingTex(left_label_x, MathTex(r"x = 2.0").next_to(left_point, DOWN, buff=0.1).set_color(BLACK)),
                  TransformMatchingTex(left_label_y, MathTex(r"y = 4.0").next_to(left_point, UP, buff=0.1).set_color(BLACK)))
        self.wait(1)

        # === Animation for Lecture Line 3 ===
        right_point = Dot(point=[2.1, 2.1**2, 0], color="#5555FF")
        right_label_x = MathTex(r"x = 2.1").next_to(right_point, DOWN, buff=0.1).set_color(BLACK)
        right_label_y = MathTex(r"y = 4.41").next_to(right_point, UP, buff=0.1).set_color(BLACK)
        right_labels = VGroup(right_label_x, right_label_y)
        self.play(Create(right_point), Write(right_labels))
        self.lecture[2].set_color(YELLOW)
        self.wait(1)

        right_path = VMobject()
        right_path.set_points_as_corners([right_point.get_center(), *[np.array([x, x**2, 0]) for x in np.linspace(2.1, 2, 100)]])
        right_path.set_color("#5555FF")
        self.play(MoveAlongPath(right_point, right_path), 
                  TransformMatchingTex(right_label_x, MathTex(r"x = 2.0").next_to(right_point, DOWN, buff=0.1).set_color(BLACK)),
                  TransformMatchingTex(right_label_y, MathTex(r"y = 4.0").next_to(right_point, UP, buff=0.1).set_color(BLACK)))
        self.wait(1)

        # === Animation for Lecture Line 4 ===
        final_y_label = MathTex(r"y = 4.00").next_to(point_2_4, UP, buff=0.1).set_color("#00FF00")
        self.play(TransformMatchingTex(left_label_y, final_y_label), TransformMatchingTex(right_label_y, final_y_label))
        self.play(Indicate(final_y_label, color="#00FF00"))  # Use Indicate instead of flash
        self.lecture[3].set_color(YELLOW)
        self.wait(2)

        # === Animation for Lecture Line 5 ===
        limit_line = DashedLine(start=[-1, 4, 0], end=[3, 4, 0], color="#FF00FF")
        x_to_2 = MathTex(r"x \to 2").to_edge(RIGHT, buff=0.5).set_color(BLACK)
        self.play(Create(limit_line), Write(x_to_2))
        self.play(left_point.animate.move_to([2 - 0.05, 4, 0]), right_point.animate.move_to([2 + 0.05, 4, 0]))
        trend_text = Text("趋势", font_size=24, color=BLACK).to_edge(DOWN)
        self.play(FadeIn(trend_text))
        self.lecture[4].set_color(YELLOW)
        self.wait(2)