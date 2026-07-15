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
        self.setup_layout("第1节：引入：从平均速度到瞬时速度", ['汽车行驶，求t=2秒瞬时速度', '平均速度 = 位移 / 时间', '缩短时间间隔：2→2.1秒', '继续缩短：2→2.01秒', '数值趋近固定值，即极限'])

        # === Animation for Lecture Line 1 ===
        car = Arrow(start=LEFT*3, end=RIGHT*3, color="#FFFFFF", max_tip_length_to_length_ratio=0.1)
        car_label = Text("t=2秒", font_size=22, color="#FF3333").next_to(car.get_end(), UP)
        self.play(Create(car), Write(car_label))
        self.wait(1)
        self.lecture[0].set_color("#FFFF00")
        self.wait(1)

        # === Animation for Lecture Line 2 ===
        avg_speed_formula = MathTex(r"v_{\text{avg}} = \frac{\Delta s}{\Delta t}", color="#FFFFFF")
        self.place_at_grid(avg_speed_formula, 'B2', scale_factor=0.8)
        self.play(Write(avg_speed_formula))
        self.wait(1)
        self.lecture[1].set_color("#FFFF00")
        self.wait(1)

        # === Animation for Lecture Line 3 ===
        point_t2 = Dot(point=car.get_end(), color="#FF3333")
        point_t2_1 = Dot(point=car.get_end() + RIGHT*0.1, color="#3399FF")
        line_t2_t2_1 = Line(start=point_t2.get_center(), end=point_t2_1.get_center(), color="#3399FF")
        avg_speed_value_1 = Text("平均速度: 18.0", font_size=22, color="#FFFFFF").next_to(line_t2_t2_1, UP)
        self.play(Create(point_t2), Create(point_t2_1), Create(line_t2_t2_1), Write(avg_speed_value_1))
        self.wait(1)
        self.lecture[2].set_color("#FFFF00")
        self.wait(1)

        # === Animation for Lecture Line 4 ===
        point_t2_01 = Dot(point=car.get_end() + RIGHT*0.01, color="#3399FF")
        line_t2_t2_01 = Line(start=point_t2.get_center(), end=point_t2_01.get_center(), color="#3399FF")
        avg_speed_value_2 = Text("平均速度: 19.4", font_size=22, color="#FFFFFF").next_to(line_t2_t2_01, UP)
        self.play(Transform(point_t2_1, point_t2_01), Transform(line_t2_t2_1, line_t2_t2_01), Transform(avg_speed_value_1, avg_speed_value_2))
        self.wait(1)
        self.lecture[3].set_color("#FFFF00")
        self.wait(1)

        # === Animation for Lecture Line 5 ===
        point_t2_001 = Dot(point=car.get_end() + RIGHT*0.001, color="#3399FF")
        line_t2_t2_001 = Line(start=point_t2.get_center(), end=point_t2_001.get_center(), color="#3399FF")
        avg_speed_value_3 = Text("平均速度: 19.6", font_size=22, color="#FFFFFF").next_to(line_t2_t2_001, UP)
        self.play(Transform(point_t2_01, point_t2_001), Transform(line_t2_t2_01, line_t2_t2_001), Transform(avg_speed_value_2, avg_speed_value_3))
        self.wait(1)
        self.play(Blink(avg_speed_value_3))
        instant_speed_label = Text("瞬时速度", font_size=22, color="#FFFF00").next_to(avg_speed_value_3, DOWN)
        self.play(Write(instant_speed_label))
        self.lecture[4].set_color("#FFFF00")
        self.wait(2)