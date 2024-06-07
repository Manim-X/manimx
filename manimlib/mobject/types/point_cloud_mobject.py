from __future__ import annotations

import numpy as np

from manimlib.mobject.mobject import Mobject
from manimlib.utils.color import color_gradient
from manimlib.utils.color import color_to_rgba
from manimlib.utils.iterables import resize_with_interpolation

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Callable
    from manimlib.typing import ManimColor, Vect3, Vect3Array, Vect4Array, Self


class PMobject(Mobject):
    def set_points(self, points: Vect3Array):
        if len(points) == 0:
            points = np.zeros((0, 3))
        super().set_points(points)
        self.resize_points(len(points))
        return self

    def add_points(
        self,
        points: Vect3Array,
        rgbas: Vect4Array | None = None,
        color: ManimColor | None = None,
        opacity: float | None = None
    ) -> Self:
        """
        points must be a Nx3 numpy array, as must rgbas if it is not None
        """
        self.append_points(points)
        # rgbas array will have been resized with points
        if color is not None:
            if opacity is None:
                opacity = self.data["rgba"][-1, 3]
            rgbas = np.repeat(
                [color_to_rgba(color, opacity)],
                len(points),
                axis=0
            )
        if rgbas is not None:
            self.data["rgba"][-len(rgbas):] = rgbas
        return self

    def add_point(self, point: Vect3, rgba=None, color=None, opacity=None) -> Self:
        rgbas = None if rgba is None else [rgba]
        self.add_points([point], rgbas, color, opacity)
        return self

    @Mobject.affects_data
    def set_color_by_gradient(self, *colors: ManimColor) -> Self:
        self.data["rgba"][:] = np.array(list(map(
            color_to_rgba,
            color_gradient(colors, self.get_num_points())
        )))
        return self

    @Mobject.affects_data
    def match_colors(self, pmobject: PMobject) -> Self:
        self.data["rgba"][:] = resize_with_interpolation(
            pmobject.data["rgba"], self.get_num_points()
        )
        return self

    @Mobject.affects_data
    def filter_out(self, condition: Callable[[np.ndarray], bool]) -> Self:
        for mob in self.family_members_with_points():
            mob.data = mob.data[~np.apply_along_axis(condition, 1, mob.get_points())]
        return self

    @Mobject.affects_data
    def sort_points(self, function: Callable[[Vect3], None] = lambda p: p[0]) -> Self:
        """
        function is any map from R^3 to R
        """
        for mob in self.family_members_with_points():
            indices = np.argsort(
                np.apply_along_axis(function, 1, mob.get_points())
            )
            mob.data[:] = mob.data[indices]
        return self

    @Mobject.affects_data
    def ingest_submobjects(self) -> Self:
        self.data = np.vstack([
            sm.data for sm in self.get_family()
        ])
        return self

    def point_from_proportion(self, alpha: float) -> np.ndarray:
        index = alpha * (self.get_num_points() - 1)
        return self.get_points()[int(index)]

    @Mobject.affects_data
    def pointwise_become_partial(self, pmobject: PMobject, a: float, b: float) -> Self:
        lower_index = int(a * pmobject.get_num_points())
        upper_index = int(b * pmobject.get_num_points())
        self.data = pmobject.data[lower_index:upper_index].copy()
        return self


class PGroup(PMobject):
    def __init__(self, *pmobs: PMobject, **kwargs):
        if not all([isinstance(m, PMobject) for m in pmobs]):
            raise Exception("All submobjects must be of type PMobject")
        super().__init__(**kwargs)
        self.add(*pmobs)
