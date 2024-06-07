from __future__ import annotations

import numpy as np

from manimlib.constants import BLUE, BLUE_E, GREEN_E, GREY_B, GREY_D, MAROON_B, YELLOW
from manimlib.constants import DOWN, LEFT, RIGHT, UP
from manimlib.constants import MED_LARGE_BUFF, MED_SMALL_BUFF, SMALL_BUFF
from manimlib.mobject.geometry import Line
from manimlib.mobject.geometry import Rectangle
from manimlib.mobject.mobject import Mobject
from manimlib.mobject.svg.brace import Brace
from manimlib.mobject.svg.tex_mobject import Tex
from manimlib.mobject.svg.tex_mobject import TexText
from manimlib.mobject.types.vectorized_mobject import VGroup
from manimlib.utils.color import color_gradient
from manimlib.utils.iterables import listify

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Iterable
    from manimlib.typing import ManimColor


EPSILON = 0.0001


class SampleSpace(Rectangle):
    def __init__(
        self,
        width: float = 3,
        height: float = 3,
        fill_color: ManimColor = GREY_D,
        fill_opacity: float = 1,
        stroke_width: float = 0.5,
        stroke_color: ManimColor = GREY_B,
        default_label_scale_val: float = 1,
        **kwargs,
    ):
        super().__init__(
            width, height,
            fill_color=fill_color,
            fill_opacity=fill_opacity,
            stroke_width=stroke_width,
            stroke_color=stroke_color,
        )
        self.default_label_scale_val = default_label_scale_val

    def add_title(
        self,
        title: str = "Sample space",
        buff: float = MED_SMALL_BUFF
    ) -> None:
        # TODO, should this really exist in SampleSpaceScene
        title_mob = TexText(title)
        if title_mob.get_width() > self.get_width():
            title_mob.set_width(self.get_width())
        title_mob.next_to(self, UP, buff=buff)
        self.title = title_mob
        self.add(title_mob)

    def add_label(self, label: str) -> None:
        self.label = label

    def complete_p_list(self, p_list: list[float]) -> list[float]:
        new_p_list = listify(p_list)
        remainder = 1.0 - sum(new_p_list)
        if abs(remainder) > EPSILON:
            new_p_list.append(remainder)
        return new_p_list

    def get_division_along_dimension(
        self,
        p_list: list[float],
        dim: int,
        colors: Iterable[ManimColor],
        vect: np.ndarray
    ) -> VGroup:
        p_list = self.complete_p_list(p_list)
        colors = color_gradient(colors, len(p_list))

        last_point = self.get_edge_center(-vect)
        parts = VGroup()
        for factor, color in zip(p_list, colors):
            part = SampleSpace()
            part.set_fill(color, 1)
            part.replace(self, stretch=True)
            part.stretch(factor, dim)
            part.move_to(last_point, -vect)
            last_point = part.get_edge_center(vect)
            parts.add(part)
        return parts

    def get_horizontal_division(
        self,
        p_list: list[float],
        colors: Iterable[ManimColor] = [GREEN_E, BLUE_E],
        vect: np.ndarray = DOWN
    ) -> VGroup:
        return self.get_division_along_dimension(p_list, 1, colors, vect)

    def get_vertical_division(
        self,
        p_list: list[float],
        colors: Iterable[ManimColor] = [MAROON_B, YELLOW],
        vect: np.ndarray = RIGHT
    ) -> VGroup:
        return self.get_division_along_dimension(p_list, 0, colors, vect)

    def divide_horizontally(self, *args, **kwargs) -> None:
        self.horizontal_parts = self.get_horizontal_division(*args, **kwargs)
        self.add(self.horizontal_parts)

    def divide_vertically(self, *args, **kwargs) -> None:
        self.vertical_parts = self.get_vertical_division(*args, **kwargs)
        self.add(self.vertical_parts)

    def get_subdivision_braces_and_labels(
        self,
        parts: VGroup,
        labels: str,
        direction: np.ndarray,
        buff: float = SMALL_BUFF,
    ) -> VGroup:
        label_mobs = VGroup()
        braces = VGroup()
        for label, part in zip(labels, parts):
            brace = Brace(
                part, direction,
                buff=buff
            )
            if isinstance(label, Mobject):
                label_mob = label
            else:
                label_mob = Tex(label)
                label_mob.scale(self.default_label_scale_val)
            label_mob.next_to(brace, direction, buff)

            braces.add(brace)
            label_mobs.add(label_mob)
        parts.braces = braces
        parts.labels = label_mobs
        parts.label_kwargs = {
            "labels": label_mobs.copy(),
            "direction": direction,
            "buff": buff,
        }
        return VGroup(parts.braces, parts.labels)

    def get_side_braces_and_labels(
        self,
        labels: str,
        direction: np.ndarray = LEFT,
        **kwargs
    ) -> VGroup:
        assert(hasattr(self, "horizontal_parts"))
        parts = self.horizontal_parts
        return self.get_subdivision_braces_and_labels(parts, labels, direction, **kwargs)

    def get_top_braces_and_labels(
        self,
        labels: str,
        **kwargs
    ) -> VGroup:
        assert(hasattr(self, "vertical_parts"))
        parts = self.vertical_parts
        return self.get_subdivision_braces_and_labels(parts, labels, UP, **kwargs)

    def get_bottom_braces_and_labels(
        self,
        labels: str,
        **kwargs
    ) -> VGroup:
        assert(hasattr(self, "vertical_parts"))
        parts = self.vertical_parts
        return self.get_subdivision_braces_and_labels(parts, labels, DOWN, **kwargs)

    def add_braces_and_labels(self) -> None:
        for attr in "horizontal_parts", "vertical_parts":
            if not hasattr(self, attr):
                continue
            parts = getattr(self, attr)
            for subattr in "braces", "labels":
                if hasattr(parts, subattr):
                    self.add(getattr(parts, subattr))

    def __getitem__(self, index: int | slice) -> VGroup:
        if hasattr(self, "horizontal_parts"):
            return self.horizontal_parts[index]
        elif hasattr(self, "vertical_parts"):
            return self.vertical_parts[index]
        return self.split()[index]


class BarChart(VGroup):
    def __init__(
        self,
        values: Iterable[float],
        height: float = 4,
        width: float = 6,
        n_ticks: int = 4,
        include_x_ticks: bool = False,
        tick_width: float = 0.2,
        tick_height: float = 0.15,
        label_y_axis: bool = True,
        y_axis_label_height: float = 0.25,
        max_value: float = 1,
        bar_colors: list[ManimColor] = [BLUE, YELLOW],
        bar_fill_opacity: float = 0.8,
        bar_stroke_width: float = 3,
        bar_names: list[str] = [],
        bar_label_scale_val: float = 0.75,
        **kwargs
    ):
        super().__init__(**kwargs)
        self.height = height
        self.width = width
        self.n_ticks = n_ticks
        self.include_x_ticks = include_x_ticks
        self.tick_width = tick_width
        self.tick_height = tick_height
        self.label_y_axis = label_y_axis
        self.y_axis_label_height = y_axis_label_height
        self.max_value = max_value
        self.bar_colors = bar_colors
        self.bar_fill_opacity = bar_fill_opacity
        self.bar_stroke_width = bar_stroke_width
        self.bar_names = bar_names
        self.bar_label_scale_val = bar_label_scale_val

        if self.max_value is None:
            self.max_value = max(values)

        self.n_ticks_x = len(values)
        self.add_axes()
        self.add_bars(values)
        self.center()

    def add_axes(self) -> None:
        x_axis = Line(self.tick_width * LEFT / 2, self.width * RIGHT)
        y_axis = Line(MED_LARGE_BUFF * DOWN, self.height * UP)
        y_ticks = VGroup()
        heights = np.linspace(0, self.height, self.n_ticks + 1)
        values = np.linspace(0, self.max_value, self.n_ticks + 1)
        for y, value in zip(heights, values):
            y_tick = Line(LEFT, RIGHT)
            y_tick.set_width(self.tick_width)
            y_tick.move_to(y * UP)
            y_ticks.add(y_tick)
        y_axis.add(y_ticks)

        if self.include_x_ticks == True:
            x_ticks = VGroup()
            widths = np.linspace(0, self.width, self.n_ticks_x + 1)
            label_values = np.linspace(0, len(self.bar_names), self.n_ticks_x + 1)
            for x, value in zip(widths, label_values):
                x_tick = Line(UP, DOWN)
                x_tick.set_height(self.tick_height)
                x_tick.move_to(x * RIGHT)
                x_ticks.add(x_tick)
            x_axis.add(x_ticks)

        self.add(x_axis, y_axis)
        self.x_axis, self.y_axis = x_axis, y_axis

        if self.label_y_axis:
            labels = VGroup()
            for y_tick, value in zip(y_ticks, values):
                label = Tex(str(np.round(value, 2)))
                label.set_height(self.y_axis_label_height)
                label.next_to(y_tick, LEFT, SMALL_BUFF)
                labels.add(label)
            self.y_axis_labels = labels
            self.add(labels)

    def add_bars(self, values: Iterable[float]) -> None:
        buff = float(self.width) / (2 * len(values))
        bars = VGroup()
        for i, value in enumerate(values):
            bar = Rectangle(
                height=(value / self.max_value) * self.height,
                width=buff,
                stroke_width=self.bar_stroke_width,
                fill_opacity=self.bar_fill_opacity,
            )
            bar.move_to((2 * i + 0.5) * buff * RIGHT, DOWN + LEFT * 5)
            bars.add(bar)
        bars.set_color_by_gradient(*self.bar_colors)

        bar_labels = VGroup()
        for bar, name in zip(bars, self.bar_names):
            label = Tex(str(name))
            label.scale(self.bar_label_scale_val)
            label.next_to(bar, DOWN, SMALL_BUFF)
            bar_labels.add(label)

        self.add(bars, bar_labels)
        self.bars = bars
        self.bar_labels = bar_labels

    def change_bar_values(self, values: Iterable[float]) -> None:
        for bar, value in zip(self.bars, values):
            bar_bottom = bar.get_bottom()
            bar.stretch_to_fit_height(
                (value / self.max_value) * self.height
            )
            bar.move_to(bar_bottom, DOWN)
