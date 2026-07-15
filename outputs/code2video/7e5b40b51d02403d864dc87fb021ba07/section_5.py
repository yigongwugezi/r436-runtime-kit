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

class Section5Scene(TeachingScene):
    def construct(self):
        self.setup_layout("第5节：常见误区与注意事项", ['导数是极限，不是割线斜率', 'h趋近0但不等于0', '可导必连续，连续不一定可导', '反例：|x|在x=0处不可导'])

        # === Animation for Lecture Line 1 ===
        derivative_text = Text("导数 ≠ 割线斜率", font_size=24, color="#DDDDDD")
        strike_through = Line(start=derivative_text.get_left(), end=derivative_text.get_right(), color=RED)
        self.play(Write(derivative_text))
        self.place_at_grid(derivative_text, 'B2', scale_factor=0.8)
        self.play(Create(strike_through))
        self.lecture[0].set_color(GREEN)
        self.wait(1)

        # === Animation for Lecture Line 2 ===
        h_limit_text = MathTex(r"h \to 0", color="#DDDDDD")
        self.place_at_grid(h_limit_text, 'B4', scale_factor=0.8)
        self.play(Write(h_limit_text))
        h_note_text = MathTex(r"h \neq 0", color=YELLOW)
        self.place_at_grid(h_note_text, 'B5', scale_factor=0.8)
        self.play(Write(h_note_text))
        self.lecture[1].set_color(GREEN)
        self.wait(1)

        # === Animation for Lecture Line 3 ===
        self.lecture[2].set_color(GREEN)
        self.wait(1)

        # === Animation for Lecture Line 4 ===
        abs_func_graph = FunctionGraph(lambda x: abs(x), x_range=[-2, 2], color=LIGHT_GRAY)
        self.place_in_area(abs_func_graph, 'A1', 'F6', scale_factor=0.7)
        self.play(Create(abs_func_graph))
        sharp_point = Dot(point=abs_func_graph.get_points()[len(abs_func_graph.get_points()) // 2], color=RED)
        self.play(Create(sharp_point))
        left_tangent = Line(start=np.array([-1, 1, 0]), end=np.array([0, 0, 0]), color=RED)
        right_tangent = Line(start=np.array([0, 0, 0]), end=np.array([1, 1, 0]), color=BLUE)
        self.play(Create(left_tangent), Create(right_tangent))
        left_derivative_text = Text("左导数 ≠ 右导数", font_size=24, color="#DDDDDD")
        self.place_at_grid(left_derivative_text, 'E2', scale_factor=0.8)
        self.play(Write(left_derivative_text))
        not_differentiable_text = Text("导数不存在", font_size=24, color="#DDDDDD")
        self.place_at_grid(not_differentiable_text, 'E4', scale_factor=0.8)
        self.play(Write(not_differentiable_text))
        self.lecture[3].set_color(GREEN)
        self.wait(1)