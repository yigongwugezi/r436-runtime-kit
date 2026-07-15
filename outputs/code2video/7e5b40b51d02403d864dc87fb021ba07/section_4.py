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
        self.setup_layout("第4节：几何与物理意义总结", ['几何意义：曲线切线斜率', '物理意义：瞬时变化率', '切线斜率=导数值'])

        # === Animation for Lecture Line 1 ===
        lecture_line_1 = self.lecture[0]
        lecture_line_1.set_color("#FF6600")
        self.wait(1)

        # Draw the sine curve f(x) = sin(x) in light gray
        sine_curve = FunctionGraph(lambda x: np.sin(x), x_range=[-2*PI, 2*PI], color="#CCCCCC")
        self.play(Create(sine_curve))
        self.wait(1)

        # Mark the point at x = π/2 with a red dot
        point = Dot(point=sine_curve.get_point_from_function(np.pi/2), color="#FF3333")
        self.play(Create(point))
        self.wait(1)

        # Highlight the point with an arrow
        arrow = Arrow(start=point.get_center() + UP*0.5, end=point.get_center(), color="#FF6600", buff=0.1)
        self.play(GrowArrow(arrow))
        self.wait(1)

        # === Animation for Lecture Line 2 ===
        lecture_line_2 = self.lecture[1]
        lecture_line_2.set_color("#FF6600")
        self.wait(1)

        # Draw a horizontal tangent line at the point (x = π/2) in bright green
        tangent_line = Line(start=sine_curve.get_point_from_function(np.pi/2) + LEFT*2,
                            end=sine_curve.get_point_from_function(np.pi/2) + RIGHT*2,
                            color="#00FF00")
        self.play(Create(tangent_line))
        self.wait(1)

        # === Animation for Lecture Line 3 ===
        lecture_line_3 = self.lecture[2]
        lecture_line_3.set_color("#FF6600")
        self.wait(1)

        # Display the derivative value cos(π/2) = 0 next to the tangent line
        derivative_value = MathTex(r"\cos\left(\frac{\pi}{2}\right) = 0").scale(0.8).set_color("#333333")
        self.place_at_grid(derivative_value, 'D3')
        self.play(FadeIn(derivative_value))
        self.wait(1)

        # Highlight the number 0 in red
        zero_highlight = MathTex(r"0").set_color("#FF3333").scale(0.8).set_color("#333333")
        self.place_at_grid(zero_highlight, 'D3')
        zero_highlight.shift(RIGHT*1.5)  # Adjust position to highlight the zero
        self.play(TransformMatchingTex(derivative_value, zero_highlight))
        self.wait(1)

        # Display the text "峰值点，变化率为零"
        peak_text = Text("峰值点，变化率为零", font_size=22, color="#333333")
        self.place_at_grid(peak_text, 'E3')
        self.play(FadeIn(peak_text))
        self.wait(2)

        # Reset colors of lecture lines
        lecture_line_1.set_color("#333333")
        lecture_line_2.set_color("#333333")
        lecture_line_3.set_color("#333333")
        self.wait(1)