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
        self.setup_layout("第5节：极限的应用——连续性与导数", ['极限是微积分基石', '连续性：极限等于函数值', '导数定义：增量比的极限', '割线斜率逼近切线斜率', '切线斜率即导数'])

        # Define the curve function
        def func(x):
            return np.sin(x) * 2 + 2

        # Create the curve
        curve = ParametricFunction(lambda t: np.array([t, func(t), 0]), t_range=[-2, 4], color="#00FFFF")

        # Point P and its label
        p = Dot(point=np.array([1, func(1), 0]), color="#FFFF00")
        p_label = MathTex("P", color="#FFFF00").next_to(p, UP, buff=0.1)

        # Function value at P and limit value L
        f_a = MathTex("f(a)", color="#00FF00").next_to(p, RIGHT, buff=0.1)
        l = MathTex("L", color="#FF00FF").next_to(p, RIGHT, buff=0.1)
        continuous_symbol = MathTex("=", color="#000000").next_to(p, RIGHT, buff=0.1)

        # Point Q and its label
        q = Dot(point=np.array([2, func(2), 0]), color="#FF5555")
        q_label = MathTex("Q", color="#FF5555").next_to(q, UP, buff=0.1)

        # Secant line and its slope
        secant_line = Line(start=p.get_center(), end=q.get_center(), color="#FF5555")
        slope_value = MathTex(r"\text{slope} = \frac{f(Q) - f(P)}{Q-P}", color="#FF5555").next_to(secant_line, RIGHT, buff=0.1)

        # Tangent line and its slope
        tangent_line = Line(start=p.get_center(), end=p.get_center() + np.array([0.1, 0.1 * np.cos(1), 0]), color="#5555FF")
        derivative_value = MathTex(r"\text{derivative} = \lim_{{Q \to P}} \text{slope}", color="#000000").next_to(tangent_line, RIGHT, buff=0.1)

        # Place objects on the grid
        self.place_in_area(curve, 'A1', 'F6', scale_factor=0.8)
        self.place_at_grid(p, 'C3', scale_factor=0.5)
        self.place_at_grid(p_label, 'C4', scale_factor=0.5)
        self.place_at_grid(f_a, 'C5', scale_factor=0.5)
        self.place_at_grid(l, 'C5', scale_factor=0.5)
        self.place_at_grid(continuous_symbol, 'C5', scale_factor=0.5)
        self.place_at_grid(q, 'D4', scale_factor=0.5)
        self.place_at_grid(q_label, 'D5', scale_factor=0.5)
        self.place_at_grid(secant_line, 'C3', scale_factor=0.8)
        self.place_at_grid(slope_value, 'E4', scale_factor=0.5)
        self.place_at_grid(tangent_line, 'C3', scale_factor=0.8)
        self.place_at_grid(derivative_value, 'E4', scale_factor=0.5)

        # Initial display
        self.play(Create(curve))
        self.play(FadeIn(p), Write(p_label))
        self.play(Write(f_a))
        self.wait(1)

        # === Animation for Lecture Line 1 ===
        self.play(self.lecture[0].animate.set_color("#FFD700"))
        self.wait(1)
        self.play(self.lecture[0].animate.set_color("#000000"))

        # === Animation for Lecture Line 2 ===
        self.play(self.lecture[1].animate.set_color("#FFD700"))
        self.play(TransformMatchingShapes(f_a, l))
        self.play(TransformMatchingShapes(l, continuous_symbol))
        self.wait(1)
        self.play(self.lecture[1].animate.set_color("#000000"))

        # === Animation for Lecture Line 3 ===
        self.play(self.lecture[2].animate.set_color("#FFD700"))
        self.play(FadeIn(q), Write(q_label))
        self.play(Create(secant_line), Write(slope_value))
        self.wait(1)
        self.play(self.lecture[2].animate.set_color("#000000"))

        # === Animation for Lecture Line 4 ===
        self.play(self.lecture[3].animate.set_color("#FFD700"))
        
        # Add trajectory for point Q
        q_trajectory = DashedLine(start=q.get_center(), end=p.get_center(), color="#FF5555")
        self.play(Create(q_trajectory))
        
        def update_secant(mob):
            x = mob.get_start()[0]
            y = func(x)
            q_new = Dot(point=np.array([x + 0.5, func(x + 0.5), 0]), color="#FF5555")
            q_label_new = MathTex("Q", color="#FF5555").next_to(q_new, UP, buff=0.1)
            new_secant_line = Line(start=mob.get_start(), end=q_new.get_center(), color="#FF5555")
            new_slope_value = MathTex(r"\text{slope} = \frac{f(Q) - f(P)}{Q-P}", color="#FF5555").next_to(new_secant_line, RIGHT, buff=0.1)
            mob.become(new_secant_line)
            q.become(q_new)
            q_label.become(q_label_new)
            slope_value.become(new_slope_value)

        secant_updater = UpdateFromFunc(secant_line, update_secant)
        self.play(MoveAlongPath(q, q_trajectory), run_time=5, rate_func=there_and_back, updater=secant_updater)
        self.wait(1)
        self.play(self.lecture[3].animate.set_color("#000000"))

        # === Animation for Lecture Line 5 ===
        self.play(self.lecture[4].animate.set_color("#FFD700"))
        self.play(TransformMatchingShapes(secant_line, tangent_line), TransformMatchingShapes(slope_value, derivative_value))
        self.wait(1)
        self.play(self.lecture[4].animate.set_color("#000000"))

        self.wait(2)