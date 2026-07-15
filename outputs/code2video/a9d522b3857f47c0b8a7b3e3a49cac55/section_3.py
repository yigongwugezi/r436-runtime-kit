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
        self.setup_layout("第3节：极限的严谨定义——ε-δ 语言入门", ['任意小的正数 $\epsilon$', '存在正数 $\delta$', '$x$ 与 $a$ 距离小于 $\delta$', '$f(x)$ 与 $L$ 距离小于 $\epsilon$', '$\epsilon$ 带与 $\delta$ 带的关系'])

        # Define constants
        a, L = 2, 3
        epsilon = 0.5
        delta = 1.5

        # Create the function graph
        axes = Axes(
            x_range=[0, 4, 1],
            y_range=[0, 5, 1],
            axis_config={"color": BLACK},
            tips=False,
        )
        curve = axes.plot(lambda x: 0.5 * (x - 2)**2 + 3, color="#00FFFF", x_range=[0, 4])
        point_a_L = Dot(axes.c2p(a, L), color="#FFFF00")

        # Create epsilon bands
        epsilon_band_lower = DashedLine(start=axes.c2p(0, L - epsilon), end=axes.c2p(4, L - epsilon), color="#FF00FF", stroke_width=2)
        epsilon_band_upper = DashedLine(start=axes.c2p(0, L + epsilon), end=axes.c2p(4, L + epsilon), color="#FF00FF", stroke_width=2)
        epsilon_region = Rectangle(
            width=axes.x_range[1] - axes.x_range[0],
            height=2 * epsilon,
            fill_color="#FF00FF",
            fill_opacity=0.2,
            stroke_width=0,
        ).move_to(epsilon_band_lower.get_center() + UP * epsilon)

        # Create delta bands
        delta_band_lower = DashedLine(start=axes.c2p(a - delta, 0), end=axes.c2p(a - delta, 5), color="#00FF00", stroke_width=2)
        delta_band_upper = DashedLine(start=axes.c2p(a + delta, 0), end=axes.c2p(a + delta, 5), color="#00FF00", stroke_width=2)
        delta_region = Rectangle(
            width=2 * delta,
            height=axes.y_range[1] - axes.y_range[0],
            fill_color="#00FF00",
            fill_opacity=0.2,
            stroke_width=0,
        ).move_to(delta_band_lower.get_center() + RIGHT * delta)

        # Place objects on the grid
        self.place_in_area(axes, 'A1', 'F6', scale_factor=0.8)
        self.place_at_grid(point_a_L, 'C3', scale_factor=0.8)

        # Animation for Lecture Line 1
        self.play(Create(curve), Create(point_a_L))
        self.wait(1)
        self.lecture[0].set_color(YELLOW)
        self.play(Create(epsilon_band_lower), Create(epsilon_band_upper), Create(epsilon_region))
        self.wait(1)

        # Animation for Lecture Line 2
        self.lecture[1].set_color(YELLOW)
        self.play(Create(delta_band_lower), Create(delta_band_upper), Create(delta_region))
        self.wait(1)

        # Animation for Lecture Line 3
        self.lecture[2].set_color(YELLOW)
        self.wait(1)

        # Animation for Lecture Line 4
        self.lecture[3].set_color(YELLOW)
        self.wait(1)

        # Animation for Lecture Line 5
        self.lecture[4].set_color(YELLOW)
        self.play(FadeOut(delta_band_lower), FadeOut(delta_band_upper), FadeOut(delta_region))

        # Dynamic shrinking of delta band
        for new_delta in np.linspace(1.5, 0.5, 10):
            new_delta_band_lower = DashedLine(start=axes.c2p(a - new_delta, 0), end=axes.c2p(a - new_delta, 5), color="#00FF00", stroke_width=2)
            new_delta_band_upper = DashedLine(start=axes.c2p(a + new_delta, 0), end=axes.c2p(a + new_delta, 5), color="#00FF00", stroke_width=2)
            new_delta_region = Rectangle(
                width=2 * new_delta,
                height=axes.y_range[1] - axes.y_range[0],
                fill_color="#00FF00",
                fill_opacity=0.2,
                stroke_width=0,
            ).move_to(new_delta_band_lower.get_center() + RIGHT * new_delta)
            self.play(Transform(delta_band_lower, new_delta_band_lower), Transform(delta_band_upper, new_delta_band_upper), Transform(delta_region, new_delta_region), run_time=0.2)

        # Highlight the part of the curve within the epsilon band
        t_min, t_max = curve.t_min, curve.t_max
        curve_within_epsilon = curve.copy().set_color(BLACK)
        curve_within_epsilon = curve_within_epsilon.get_subcurve(t_min, t_max)
        curve_within_epsilon = curve_within_epsilon.apply_function(
            lambda p: p if L - epsilon <= axes.point_to_coords(p)[1] <= L + epsilon else np.array([float('inf'), float('inf'), 0])
        )
        self.play(Transform(curve, curve_within_epsilon))
        self.play(Flash(curve_within_epsilon, flash_radius=0.2, line_length=0.2, num_lines=30, color=BLACK))
        self.wait(1)