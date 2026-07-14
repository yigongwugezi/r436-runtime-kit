from manim import *
import numpy as np

class EduScene(Scene):
    def construct(self):
        # /
        self.camera.background_color = BLACK
        
        # 
        title = Text("1.1 ", font_size=36, color=GOLD).to_edge(UP)
        subtitle = Text("", font_size=28, color=GRAY).next_to(title, DOWN, buff=0.2)
        self.play(Write(title), Write(subtitle))
        self.wait(1)
        
        # ...
        greeting = Text("\n\n\n", font_size=32, line_spacing=1.4, t2c={"": GOLD})
        self.play(FadeOut(title), FadeOut(subtitle), FadeIn(greeting))
        self.wait(3)
        
        # ...
        self.play(FadeOut(greeting))
        phone_vs_nasa = VGroup(
            ImageMobject("phone_icon.png").scale(0.5).set_opacity(0.8),
            Text("  ", font_size=28).rotate(PI/2).next_to(ORIGIN, RIGHT, buff=0.3),
            ImageMobject("apollo_computer.png").scale(0.4).set_opacity(0.8).next_to(ORIGIN, RIGHT, buff=1.2)
        ).move_to(ORIGIN)
        nasa_label = Text("NASA ", font_size=24, color=BLUE).next_to(phone_vs_nasa[2], DOWN, buff=0.3)
        phone_label = Text("", font_size=24, color=GOLD).next_to(phone_vs_nasa[0], DOWN, buff=0.3)
        
        # 
        phone_sim = RoundedRectangle(height=2.2, width=1.2, corner_radius=0.2, fill_color=GRAY_E, fill_opacity=0.9, stroke_color=WHITE).set_z_index(2)
        nasa_sim = Rectangle(height=1.8, width=2.6, fill_color=DARK_BLUE, fill_opacity=0.7, stroke_color=BLUE).set_z_index(1)
        arrow = Arrow(start=LEFT*1.5, end=RIGHT*1.5, stroke_width=6, color=GOLD, buff=0)
        compare_group = VGroup(phone_sim, arrow, nasa_sim).arrange(RIGHT, buff=0.8).move_to(ORIGIN)
        phone_label2 = Text("", font_size=24, color=GOLD).next_to(phone_sim, DOWN, buff=0.3)
        nasa_label2 = Text("NASA ", font_size=24, color=BLUE).next_to(nasa_sim, DOWN, buff=0.3)
        
        self.play(FadeIn(compare_group), FadeIn(phone_label2), FadeIn(nasa_label2))
        self.wait(3)
        
        # ...
        self.play(FadeOut(compare_group), FadeOut(phone_label2), FadeOut(nasa_label2))
        timeline_title = Text("", font_size=32, color=GOLD).to_edge(UP)
        self.play(Write(timeline_title))
        self.wait(1)
        
        # 
        axis = NumberLine(
            x_range=[1940, 2025, 10],
            length=12,
            color=GRAY_C,
            include_numbers=True,
            label_direction=DOWN,
            numbers_to_include=[1945, 1955, 1965, 1975, 2000, 2020],
            font_size=20
        ).shift(DOWN*1.5)
        
        # 1940s1955
        gen1 = RoundedRectangle(height=1.6, width=2.0, corner_radius=0.3, fill_color=RED_E, fill_opacity=0.8)
        gen1_label = Text("\n", font_size=22, color=RED).next_to(gen1, UP, buff=0.2)
        gen1_period = Text("1940s-1955", font_size=18, color=GRAY).next_to(gen1, DOWN, buff=0.2)
        gen1_group = VGroup(gen1, gen1_label, gen1_period).move_to(axis.n2p(1948))
        
        # 19551965
        gen2 = RoundedRectangle(height=1.4, width=1.8, corner_radius=0.3, fill_color=ORANGE_E, fill_opacity=0.8)
        gen2_label = Text("\n", font_size=22, color=ORANGE).next_to(gen2, UP, buff=0.2)
        gen2_period = Text("1955-1965", font_size=18, color=GRAY).next_to(gen2, DOWN, buff=0.2)
        gen2_group = VGroup(gen2, gen2_label, gen2_period).move_to(axis.n2p(1960))
        
        # 19651975
        gen3 = RoundedRectangle(height=1.2, width=1.6, corner_radius=0.3, fill_color=GOLD_E, fill_opacity=0.8)
        gen3_label = Text("\n", font_size=22, color=GOLD).next_to(gen3, UP, buff=0.2)
        gen3_period = Text("1965-1975", font_size=18, color=GRAY).next_to(gen3, DOWN, buff=0.2)
        gen3_group = VGroup(gen3, gen3_label, gen3_period).move_to(axis.n2p(1970))
        
        # 1975
        gen4 = RoundedRectangle(height=1.0, width=2.4, corner_radius=0.3, fill_color=GREEN_E, fill_opacity=0.8)
        gen4_label = Text("\n", font_size=22, color=GREEN).next_to(gen4, UP, buff=0.2)
        gen4_period = Text("1975-present", font_size=18, color=GRAY).next_to(gen4, DOWN, buff=0.2)
        gen4_group = VGroup(gen4, gen4_label, gen4_period).move_to(axis.n2p(1995))
        
        self.play(Create(axis))
        self.wait(0.5)
        self.play(FadeIn(gen1_group))
        self.wait(2)
        self.play(FadeIn(gen2_group))
        self.wait(2)
        self.play(FadeIn(gen3_group))
        self.wait(2)
        self.play(FadeIn(gen4_group))
        self.wait(2)
        
        # ...
        self.play(FadeOut(timeline_title), FadeOut(axis), FadeOut(gen2_group), FadeOut(gen3_group), FadeOut(gen4_group))
        self.play(gen1_group.animate.shift(UP*2))
        
        tube_icon = SVGMobject("vacuum_tube.svg").scale(0.8).set_color(RED).move_to(LEFT*4 + UP*0.5)
        room_icon = SVGMobject("building.svg").scale(0.6).set_color(GRAY).move_to(RIGHT*3 + UP*0.5)
        
        #  SVG Manim CE 
        # 
        tube_sim = Circle(radius=0.4, color=RED, fill_opacity=0.6).move_to(LEFT*4 + UP*0.5)
        tube_text = Text("", font_size=20, color=RED).next_to(tube_sim, DOWN, buff=0.2)
        
        room_sim = Rectangle(height=2.0, width=2.8, fill_color=GRAY_D, fill_opacity=0.4, stroke_color=GRAY).move_to(RIGHT*3 + UP*0.5)
        room_text = Text("", font_size=20, color=GRAY).next_to(room_sim, DOWN, buff=0.2)
        
        preheat = Text("30", font_size=22, color=YELLOW).move_to(UP*2.5)
        feasibility = Text(" ", font_size=24, color=GOLD).move_to(DOWN*2)
        
        self.play(FadeIn(tube_sim), FadeIn(tube_text), FadeIn(room_sim), FadeIn(room_text), Write(preheat), Write(feasibility))
        self.wait(3)
        
        # ...
        self.play(FadeOut(tube_sim), FadeOut(tube_text), FadeOut(room_sim), FadeOut(room_text), FadeOut(preheat), FadeOut(feasibility))
        
        transistor = Dot(color=ORANGE, radius=0.3).move_to(LEFT*4)
        trans_text = Text("\n", font_size=22, color=ORANGE).next_to(transistor, RIGHT, buff=0.5)
        
        ic_chip = Square(side_length=1.2, color=GOLD, fill_opacity=0.3).move_to(RIGHT*3)
        ic_text = Text("\n/", font_size=22, color=GOLD).next_to(ic_chip, RIGHT, buff=0.5)
        
        self.play(FadeIn(transistor), Write(trans_text))
        self.wait(2)
        self.play(FadeIn(ic_chip), Write(ic_text))
        self.wait(2)
        
        # ...
        self.play(FadeOut(transistor), FadeOut(trans_text), FadeOut(ic_chip), FadeOut(ic_text))
        
        classify_title = Text("", font_size=30, color=GOLD).to_edge(UP)
        self.play(Write(classify_title))
        self.wait(1)
        
        # 
        supercomp = RoundedRectangle(height=1.8, width=2.6, corner_radius=0.2, fill_color=BLUE_E, fill_opacity=0.7)
        supercomp_label = Text("\n", font_size=22, color=BLUE).move_to(supercomp.get_center())
        supercomp_task = Text("\n", font_size=18, color=BLUE_A).next_to(supercomp, DOWN, buff=0.2)
        
        mainframe = RoundedRectangle(height=1.8, width=2.6, corner_radius=0.2, fill_color=PURPLE_E, fill_opacity=0.7)
        mainframe_label = Text("", font_size=22, color=PURPLE).move_to(mainframe.get_center())
        mainframe_task = Text("\n", font_size=18, color=PURPLE_A).next_to(mainframe, DOWN, buff=0.2)
        
        micro = RoundedRectangle(height=1.8, width=2.6, corner_radius=0.2, fill_color=GREEN_E, fill_opacity=0.7)
        micro_label = Text("", font_size=22, color=GREEN).move_to(micro.get_center())
        micro_task = Text("\n", font_size=18, color=GREEN_A).next_to(micro, DOWN, buff=0.2)
        
        embedded = RoundedRectangle(height=1.8, width=2.6, corner_radius=0.2, fill_color=TEAL_E, fill_opacity=0.7)
        embedded_label = Text("", font_size=22, color=TEAL).move_to(embedded.get_center())
        embedded_task = Text("ECU", font_size=18, color=TEAL_A).next_to(embedded, DOWN, buff=0.2)
        
        group = VGroup(supercomp, mainframe, micro, embedded).arrange_in_grid(rows=1, cols=4, buff=0.8).move_to(ORIGIN)
        labels = VGroup(supercomp_label, mainframe_label, micro_label, embedded_label)
        tasks = VGroup(supercomp_task, mainframe_task, micro_task, embedded_task)
        
        self.play(FadeIn(group))
        self.wait(1)
        self.play(FadeIn(labels))
        self.wait(1)
        self.play(FadeIn(tasks))
        self.wait(3)
        
        # ...
        self.play(FadeOut(classify_title), FadeOut(group), FadeOut(labels), FadeOut(tasks))
        
        example_title = Text("  ", font_size=30, color=GOLD).to_edge(UP)
        self.play(Write(example_title))
        self.wait(1)
        
        cashier = ImageMobject("cashier.png").scale(0.4).move_to(LEFT*4 + DOWN*0.5)
        weather = ImageMobject("weather_map.png").scale(0.4).move_to(RIGHT*4 + DOWN*0.5)
        
        # 
        cashier_sim = RoundedRectangle(height=1.6, width=1.2, corner_radius=0.2, fill_color=GREEN_C, fill_opacity=0.6).move_to(LEFT*4 + DOWN*0.5)
        weather_sim = RoundedRectangle(height=1.6, width=1.2, corner_radius=0.2, fill_color=BLUE_C, fill_opacity=0.6).move_to(RIGHT*4 + DOWN*0.5)
        
        cashier_label = Text("\n+\n", font_size=20, color=GREEN).next_to(cashier_sim, DOWN, buff=0.2)
        weather_label = Text("\n\n1", font_size=20, color=BLUE).next_to(weather_sim, DOWN, buff=0.2)
        
        self.play(FadeIn(cashier_sim), FadeIn(weather_sim))
        self.wait(1)
        self.play(FadeIn(cashier_label), FadeIn(weather_label))
        self.wait(3)
        
        # ...
        self.play(FadeOut(example_title), FadeOut(cashier_sim), FadeOut(weather_sim), FadeOut(cashier_label), FadeOut(weather_label))
        
        core_principle = Text("\n\n\n \n \n \n ", font_size=2