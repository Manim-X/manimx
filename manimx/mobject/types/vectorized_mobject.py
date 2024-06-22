from __future__ import annotations

from functools import wraps

import moderngl
import numpy as np

from manimx.constants import GREY_A, GREY_C, GREY_E
from manimx.constants import BLACK
from manimx.constants import DEFAULT_STROKE_WIDTH
from manimx.constants import DEGREES
from manimx.constants import JOINT_TYPE_MAP
from manimx.constants import ORIGIN, OUT
from manimx.constants import TAU
from manimx.mobject.mobject import Mobject
from manimx.mobject.mobject import Group
from manimx.mobject.mobject import Point
from manimx.utils.bezier import bezier
from manimx.utils.bezier import get_quadratic_approximation_of_cubic
from manimx.utils.bezier import approx_smooth_quadratic_bezier_handles
from manimx.utils.bezier import smooth_quadratic_path
from manimx.utils.bezier import interpolate
from manimx.utils.bezier import integer_interpolate
from manimx.utils.bezier import inverse_interpolate
from manimx.utils.bezier import find_intersection
from manimx.utils.bezier import outer_interpolate
from manimx.utils.bezier import partial_quadratic_bezier_points
from manimx.utils.bezier import quadratic_bezier_points_for_arc
from manimx.utils.color import color_gradient
from manimx.utils.color import rgb_to_hex
from manimx.utils.iterables import make_even
from manimx.utils.iterables import resize_array
from manimx.utils.iterables import resize_with_interpolation
from manimx.utils.iterables import resize_preserving_order
from manimx.utils.iterables import arrays_match
from manimx.utils.space_ops import angle_between_vectors
from manimx.utils.space_ops import cross
from manimx.utils.space_ops import cross2d
from manimx.utils.space_ops import earclip_triangulation
from manimx.utils.space_ops import get_norm
from manimx.utils.space_ops import get_unit_normal
from manimx.utils.space_ops import line_intersects_path
from manimx.utils.space_ops import midpoint
from manimx.utils.space_ops import rotation_between_vectors
from manimx.utils.space_ops import poly_line_length
from manimx.utils.space_ops import z_to_vector
from manimx.shader_wrapper import ShaderWrapper
from manimx.shader_wrapper import FillShaderWrapper

from typing import TYPE_CHECKING
from typing import Generic, TypeVar, Iterable
SubVmobjectType = TypeVar('SubVmobjectType', bound='VMobject')

if TYPE_CHECKING:
    from typing import Callable, Tuple, Any
    from manimx.typing import ManimColor, Vect3, Vect4, Vect3Array, Vect4Array, Self
    from moderngl.context import Context

DEFAULT_STROKE_COLOR = GREY_A
DEFAULT_FILL_COLOR = GREY_C


class VMobject(Mobject):
    fill_shader_folder: str = "quadratic_bezier_fill"
    stroke_shader_folder: str = "quadratic_bezier_stroke"
    shader_dtype: np.dtype = np.dtype([
        ('point', np.float32, (3,)),
        ('stroke_rgba', np.float32, (4,)),
        ('stroke_width', np.float32, (1,)),
        ('joint_product', np.float32, (4,)),
        ('fill_rgba', np.float32, (4,)),
        ('base_point', np.float32, (3,)),
        ('unit_normal', np.float32, (3,)),
        ('fill_border_width', np.float32, (1,)),
    ])
    fill_data_names = ['point', 'fill_rgba', 'base_point', 'unit_normal']
    stroke_data_names = ['point', 'stroke_rgba', 'stroke_width', 'joint_product']

    fill_render_primitive: int = moderngl.TRIANGLES
    stroke_render_primitive: int = moderngl.TRIANGLES

    pre_function_handle_to_anchor_scale_factor: float = 0.01
    make_smooth_after_applying_functions: bool = False
    # TODO, do we care about accounting for varying zoom levels?
    tolerance_for_point_equality: float = 1e-8

    def __init__(
        self,
        color: ManimColor = None,  # If set, this will override stroke_color and fill_color
        fill_color: ManimColor = None,
        fill_opacity: float | Iterable[float] | None = 0.0,
        stroke_color: ManimColor = None,
        stroke_opacity: float | Iterable[float] | None = 1.0,
        stroke_width: float | Iterable[float] | None = DEFAULT_STROKE_WIDTH,
        stroke_behind: bool = False,
        background_image_file: str | None = None,
        long_lines: bool = False,
        # Could also be "no_joint", "bevel", "miter"
        joint_type: str = "auto",
        flat_stroke: bool = True,
        use_simple_quadratic_approx: bool = False,
        # Measured in pixel widths
        anti_alias_width: float = 1.0,
        fill_border_width: float = 0.5,
        use_winding_fill: bool = True,
        **kwargs
    ):
        self.fill_color = fill_color or color or DEFAULT_FILL_COLOR
        self.fill_opacity = fill_opacity
        self.stroke_color = stroke_color or color or DEFAULT_STROKE_COLOR
        self.stroke_opacity = stroke_opacity
        self.stroke_width = stroke_width
        self.stroke_behind = stroke_behind
        self.background_image_file = background_image_file
        self.long_lines = long_lines
        self.joint_type = joint_type
        self.flat_stroke = flat_stroke
        self.use_simple_quadratic_approx = use_simple_quadratic_approx
        self.anti_alias_width = anti_alias_width
        self.fill_border_width = fill_border_width
        self._use_winding_fill = use_winding_fill
        self._has_fill = False
        self._has_stroke = False

        self.needs_new_triangulation = True
        self.triangulation = np.zeros(0, dtype='i4')
        self.needs_new_joint_products = True
        self.outer_vert_indices = np.zeros(0, dtype='i4')

        super().__init__(**kwargs)

    def get_group_class(self):
        return VGroup

    def init_uniforms(self):
        super().init_uniforms()
        self.uniforms["anti_alias_width"] = self.anti_alias_width
        self.uniforms["joint_type"] = JOINT_TYPE_MAP[self.joint_type]
        self.uniforms["flat_stroke"] = float(self.flat_stroke)

    def add(self, *vmobjects: VMobject) -> Self:
        if not all((isinstance(m, VMobject) for m in vmobjects)):
            raise Exception("All submobjects must be of type VMobject")
        return super().add(*vmobjects)

    # Colors
    def note_changed_fill(self) -> Self:
        for submob in self.get_family():
            submob._has_fill = submob.has_fill()
        return self

    def note_changed_stroke(self) -> Self:
        for submob in self.get_family():
            submob._has_stroke = submob.has_stroke()
        return self

    def init_colors(self):
        self.set_fill(
            color=self.fill_color,
            opacity=self.fill_opacity,
            border_width=self.fill_border_width,
        )
        self.set_stroke(
            color=self.stroke_color,
            width=self.stroke_width,
            opacity=self.stroke_opacity,
            background=self.stroke_behind,
        )
        self.set_shading(*self.shading)
        self.set_flat_stroke(self.flat_stroke)
        self.color = self.get_color()
        return self

    def set_rgba_array(
        self,
        rgba_array: Vect4Array,
        name: str = "stroke_rgba",
        recurse: bool = False
    ) -> Self:
        super().set_rgba_array(rgba_array, name, recurse)
        self.note_changed_fill()
        self.note_changed_stroke()
        return self

    def set_fill(
        self,
        color: ManimColor | Iterable[ManimColor] = None,
        opacity: float | Iterable[float] | None = None,
        border_width: float | None = None,
        recurse: bool = True
    ) -> Self:
        self.set_rgba_array_by_color(color, opacity, 'fill_rgba', recurse)
        if border_width is not None:
            for mob in self.get_family(recurse):
                mob.data["fill_border_width"] = border_width
        self.note_changed_fill()
        return self

    def set_stroke(
        self,
        color: ManimColor | Iterable[ManimColor] = None,
        width: float | Iterable[float] | None = None,
        opacity: float | Iterable[float] | None = None,
        background: bool | None = None,
        recurse: bool = True
    ) -> Self:
        self.set_rgba_array_by_color(color, opacity, 'stroke_rgba', recurse)

        if width is not None:
            for mob in self.get_family(recurse):
                data = mob.data if mob.get_num_points() > 0 else mob._data_defaults
                if isinstance(width, (float, int)):
                    data['stroke_width'][:, 0] = width
                else:
                    data['stroke_width'][:, 0] = resize_with_interpolation(
                        np.array(width), len(data)
                    ).flatten()

        if background is not None:
            for mob in self.get_family(recurse):
                mob.stroke_behind = background

        self.note_changed_stroke()
        return self

    def set_backstroke(
        self,
        color: ManimColor | Iterable[ManimColor] = BLACK,
        width: float | Iterable[float] = 3,
        background: bool = True
    ) -> Self:
        self.set_stroke(color, width, background=background)
        return self

    @Mobject.affects_family_data
    def set_style(
        self,
        fill_color: ManimColor | Iterable[ManimColor] | None = None,
        fill_opacity: float | Iterable[float] | None = None,
        fill_rgba: Vect4 | None = None,
        stroke_color: ManimColor | Iterable[ManimColor] | None = None,
        stroke_opacity: float | Iterable[float] | None = None,
        stroke_rgba: Vect4 | None = None,
        stroke_width: float | Iterable[float] | None = None,
        stroke_background: bool = False,
        shading: Tuple[float, float, float] | None = None,
        recurse: bool = True
    ) -> Self:
        for mob in self.get_family(recurse):
            if fill_rgba is not None:
                mob.data['fill_rgba'][:] = resize_with_interpolation(fill_rgba, len(mob.data['fill_rgba']))
            else:
                mob.set_fill(
                    color=fill_color,
                    opacity=fill_opacity,
                    recurse=False
                )

            if stroke_rgba is not None:
                mob.data['stroke_rgba'][:] = resize_with_interpolation(stroke_rgba, len(mob.data['stroke_rgba']))
                mob.set_stroke(
                    width=stroke_width,
                    background=stroke_background,
                    recurse=False,
                )
            else:
                mob.set_stroke(
                    color=stroke_color,
                    width=stroke_width,
                    opacity=stroke_opacity,
                    recurse=False,
                    background=stroke_background,
                )

            if shading is not None:
                mob.set_shading(*shading, recurse=False)
        self.note_changed_fill()
        self.note_changed_stroke()
        return self

    def get_style(self) -> dict[str, Any]:
        data = self.data if self.get_num_points() > 0 else self._data_defaults
        return {
            "fill_rgba": data['fill_rgba'].copy(),
            "stroke_rgba": data['stroke_rgba'].copy(),
            "stroke_width": data['stroke_width'].copy(),
            "stroke_background": self.stroke_behind,
            "shading": self.get_shading(),
        }

    def match_style(self, vmobject: VMobject, recurse: bool = True) -> Self:
        self.set_style(**vmobject.get_style(), recurse=False)
        if recurse:
            # Does its best to match up submobject lists, and
            # match styles accordingly
            submobs1, submobs2 = self.submobjects, vmobject.submobjects
            if len(submobs1) == 0:
                return self
            elif len(submobs2) == 0:
                submobs2 = [vmobject]
            for sm1, sm2 in zip(*make_even(submobs1, submobs2)):
                sm1.match_style(sm2)
        return self

    def set_color(
        self,
        color: ManimColor | Iterable[ManimColor] | None,
        opacity: float | Iterable[float] | None = None,
        recurse: bool = True
    ) -> Self:
        self.set_fill(color, opacity=opacity, recurse=recurse)
        self.set_stroke(color, opacity=opacity, recurse=recurse)
        return self

    def set_opacity(
        self,
        opacity: float | Iterable[float] | None,
        recurse: bool = True
    ) -> Self:
        self.set_fill(opacity=opacity, recurse=recurse)
        self.set_stroke(opacity=opacity, recurse=recurse)
        return self

    def set_anti_alias_width(self, anti_alias_width: float, recurse: bool = True) -> Self:
        self.set_uniform(recurse, anti_alias_width=anti_alias_width)
        return self

    def fade(self, darkness: float = 0.5, recurse: bool = True) -> Self:
        mobs = self.get_family() if recurse else [self]
        for mob in mobs:
            factor = 1.0 - darkness
            mob.set_fill(
                opacity=factor * mob.get_fill_opacity(),
                recurse=False,
            )
            mob.set_stroke(
                opacity=factor * mob.get_stroke_opacity(),
                recurse=False,
            )
        return self

    def get_fill_colors(self) -> list[str]:
        return [
            rgb_to_hex(rgba[:3])
            for rgba in self.data['fill_rgba']
        ]

    def get_fill_opacities(self) -> np.ndarray:
        return self.data['fill_rgba'][:, 3]

    def get_stroke_colors(self) -> list[str]:
        return [
            rgb_to_hex(rgba[:3])
            for rgba in self.data['stroke_rgba']
        ]

    def get_stroke_opacities(self) -> np.ndarray:
        return self.data['stroke_rgba'][:, 3]

    def get_stroke_widths(self) -> np.ndarray:
        return self.data['stroke_width'][:, 0]

    # TODO, it's weird for these to return the first of various lists
    # rather than the full information
    def get_fill_color(self) -> str:
        """
        If there are multiple colors (for gradient)
        this returns the first one
        """
        data = self.data if self.has_points() else self._data_defaults
        return rgb_to_hex(data["fill_rgba"][0, :3])

    def get_fill_opacity(self) -> float:
        """
        If there are multiple opacities, this returns the
        first
        """
        data = self.data if self.has_points() else self._data_defaults
        return data["fill_rgba"][0, 3]

    def get_stroke_color(self) -> str:
        data = self.data if self.has_points() else self._data_defaults
        return rgb_to_hex(data["stroke_rgba"][0, :3])

    def get_stroke_width(self) -> float:
        data = self.data if self.has_points() else self._data_defaults
        return data["stroke_width"][0, 0]

    def get_stroke_opacity(self) -> float:
        data = self.data if self.has_points() else self._data_defaults
        return data["stroke_rgba"][0, 3]

    def get_color(self) -> str:
        if self.has_fill():
            return self.get_fill_color()
        return self.get_stroke_color()

    def get_anti_alias_width(self):
        return self.uniforms["anti_alias_width"]

    def has_stroke(self) -> bool:
        data = self.data if len(self.data) > 0 else self._data_defaults
        return any(data['stroke_width']) and any(data['stroke_rgba'][:, 3])

    def has_fill(self) -> bool:
        data = self.data if len(self.data) > 0 else self._data_defaults
        return any(data['fill_rgba'][:, 3])

    def get_opacity(self) -> float:
        if self.has_fill():
            return self.get_fill_opacity()
        return self.get_stroke_opacity()

    def set_flat_stroke(self, flat_stroke: bool = True, recurse: bool = True) -> Self:
        for mob in self.get_family(recurse):
            mob.uniforms["flat_stroke"] = float(flat_stroke)
        return self

    def get_flat_stroke(self) -> bool:
        return self.uniforms["flat_stroke"] == 1.0

    def set_joint_type(self, joint_type: str, recurse: bool = True) -> Self:
        for mob in self.get_family(recurse):
            mob.uniforms["joint_type"] = JOINT_TYPE_MAP[joint_type]
        return self

    def get_joint_type(self) -> float:
        return self.uniforms["joint_type"]

    def apply_depth_test(
        self,
        anti_alias_width: float = 0,
        fill_border_width: float = 0,
        recurse: bool = True
    ) -> Self:
        super().apply_depth_test(recurse)
        self.set_anti_alias_width(anti_alias_width)
        self.set_fill(border_width=fill_border_width)
        return self

    def deactivate_depth_test(
        self,
        anti_alias_width: float = 1.0,
        fill_border_width: float = 0.5,
        recurse: bool = True
    ) -> Self:
        super().deactivate_depth_test(recurse)
        self.set_anti_alias_width(anti_alias_width)
        self.set_fill(border_width=fill_border_width)
        return self

    @Mobject.affects_family_data
    def use_winding_fill(self, value: bool = True, recurse: bool = True) -> Self:
        for submob in self.get_family(recurse):
            submob._use_winding_fill = value
            if not value and submob.has_points():
                submob.subdivide_intersections()
        return self

    # Points
    def set_anchors_and_handles(
        self,
        anchors: Vect3Array,
        handles: Vect3Array,
    ) -> Self:
        if len(anchors) == 0:
            self.clear_points()
            return self
        assert(len(anchors) == len(handles) + 1)
        points = resize_array(self.get_points(), 2 * len(anchors) - 1)
        points[0::2] = anchors
        points[1::2] = handles
        self.set_points(points)
        return self

    def start_new_path(self, point: Vect3) -> Self:
        # Path ends are signaled by a handle point sitting directly
        # on top of the previous anchor
        if self.has_points():
            self.append_points([self.get_last_point(), point])
        else:
            self.set_points([point])
        return self

    def add_cubic_bezier_curve(
        self,
        anchor1: Vect3,
        handle1: Vect3,
        handle2: Vect3,
        anchor2: Vect3
    ) -> Self:
        self.start_new_path(anchor1)
        self.add_cubic_bezier_curve_to(handle1, handle2, anchor2)
        return self

    def add_cubic_bezier_curve_to(
        self,
        handle1: Vect3,
        handle2: Vect3,
        anchor: Vect3,
    ) -> Self:
        """
        Add cubic bezier curve to the path.
        """
        self.throw_error_if_no_points()
        last = self.get_last_point()
        # Note, this assumes all points are on the xy-plane
        v1 = handle1 - last
        v2 = anchor - handle2
        angle = angle_between_vectors(v1, v2)
        if self.use_simple_quadratic_approx and angle < 45 * DEGREES:
            quad_approx = [last, find_intersection(last, v1, anchor, -v2), anchor]
        else:
            quad_approx = get_quadratic_approximation_of_cubic(
                last, handle1, handle2, anchor
            )
        if self.consider_points_equal(quad_approx[1], last):
            # This is to prevent subpaths from accidentally being marked closed
            quad_approx[1] = midpoint(*quad_approx[1:3])
        self.append_points(quad_approx[1:])
        return self

    def add_quadratic_bezier_curve_to(self, handle: Vect3, anchor: Vect3) -> Self:
        self.throw_error_if_no_points()
        last_point = self.get_last_point()
        if self.consider_points_equal(handle, last_point):
            # This is to prevent subpaths from accidentally being marked closed
            handle = midpoint(handle, anchor)
        self.append_points([handle, anchor])
        return self

    def add_line_to(self, point: Vect3) -> Self:
        self.throw_error_if_no_points()
        last_point = self.get_last_point()
        alphas = np.linspace(0, 1, 5 if self.long_lines else 3)
        self.append_points(outer_interpolate(last_point, point, alphas[1:]))
        return self

    def add_smooth_curve_to(self, point: Vect3) -> Self:
        if self.has_new_path_started():
            self.add_line_to(point)
        else:
            self.throw_error_if_no_points()
            new_handle = self.get_reflection_of_last_handle()
            self.add_quadratic_bezier_curve_to(new_handle, point)
        return self

    def add_smooth_cubic_curve_to(self, handle: Vect3, point: Vect3) -> Self:
        self.throw_error_if_no_points()
        if self.get_num_points() == 1:
            new_handle = handle
        else:
            new_handle = self.get_reflection_of_last_handle()
        self.add_cubic_bezier_curve_to(new_handle, handle, point)
        return self

    def add_arc_to(self, point: Vect3, angle: float, n_components: int | None = None, threshold: float = 1e-3) -> Self:
        self.throw_error_if_no_points()
        if abs(angle) < threshold:
            self.add_line_to(point)
            return self

        # Assign default value for n_components
        if n_components is None:
            n_components = int(np.ceil(8 * abs(angle) / TAU))

        arc_points = quadratic_bezier_points_for_arc(angle, n_components)
        target_vect = point - self.get_end()
        curr_vect = arc_points[-1] - arc_points[0]

        arc_points = arc_points @ rotation_between_vectors(curr_vect, target_vect).T
        arc_points *= get_norm(target_vect) / get_norm(curr_vect)
        arc_points += (self.get_end() - arc_points[0])
        self.append_points(arc_points[1:])
        return self

    def has_new_path_started(self) -> bool:
        points = self.get_points()
        if len(points) == 0:
            return False
        elif len(points) == 1:
            return True
        return self.consider_points_equal(points[-3], points[-2])

    def get_last_point(self) -> Vect3:
        return self.get_points()[-1]

    def get_reflection_of_last_handle(self) -> Vect3:
        points = self.get_points()
        return 2 * points[-1] - points[-2]

    def close_path(self, smooth: bool = False) -> Self:
        if self.is_closed():
            return self
        last_path_start = self.get_subpaths()[-1][0]
        if smooth:
            self.add_smooth_curve_to(last_path_start)
        else:
            self.add_line_to(last_path_start)
        return self

    def is_closed(self) -> bool:
        points = self.get_points()
        return self.consider_points_equal(points[0], points[-1])

    def subdivide_curves_by_condition(
        self,
        tuple_to_subdivisions: Callable,
        recurse: bool = True
    ) -> Self:
        for vmob in self.get_family(recurse):
            if not vmob.has_points():
                continue
            new_points = [vmob.get_points()[0]]
            for tup in vmob.get_bezier_tuples():
                n_divisions = tuple_to_subdivisions(*tup)
                if n_divisions > 0:
                    alphas = np.linspace(0, 1, n_divisions + 2)
                    new_points.extend([
                        partial_quadratic_bezier_points(tup, a1, a2)[1:]
                        for a1, a2 in zip(alphas, alphas[1:])
                    ])
                else:
                    new_points.append(tup[1:])
            vmob.set_points(np.vstack(new_points))
        return self

    def subdivide_sharp_curves(
        self,
        angle_threshold: float = 30 * DEGREES,
        recurse: bool = True
    ) -> Self:
        def tuple_to_subdivisions(b0, b1, b2):
            angle = angle_between_vectors(b1 - b0, b2 - b1)
            return int(angle / angle_threshold)

        self.subdivide_curves_by_condition(tuple_to_subdivisions, recurse)
        return self

    def subdivide_intersections(self, recurse: bool = True, n_subdivisions: int = 1) -> Self:
        path = self.get_anchors()
        def tuple_to_subdivisions(b0, b1, b2):
            if line_intersects_path(b0, b1, path):
                return n_subdivisions
            return 0

        self.subdivide_curves_by_condition(tuple_to_subdivisions, recurse)
        return self

    def add_points_as_corners(self, points: Iterable[Vect3]) -> Self:
        for point in points:
            self.add_line_to(point)
        return self

    def set_points_as_corners(self, points: Iterable[Vect3]) -> Self:
        anchors = np.array(points)
        handles = 0.5 * (anchors[:-1] + anchors[1:])
        self.set_anchors_and_handles(anchors, handles)
        return self

    def set_points_smoothly(
        self,
        points: Iterable[Vect3],
        approx: bool = True
    ) -> Self:
        self.set_points_as_corners(points)
        self.make_smooth(approx=approx)
        return self

    def is_smooth(self) -> bool:
        dots = self.get_joint_products()[::2, 3]
        return bool((dots > 1 - 1e-3).all())

    def change_anchor_mode(self, mode: str) -> Self:
        assert(mode in ("jagged", "approx_smooth", "true_smooth"))
        if self.get_num_points() == 0:
            return self
        subpaths = self.get_subpaths()
        self.clear_points()
        for subpath in subpaths:
            anchors = subpath[::2]
            new_subpath = np.array(subpath)
            if mode == "jagged":
                new_subpath[1::2] = 0.5 * (anchors[:-1] + anchors[1:])
            elif mode == "approx_smooth":
                new_subpath[1::2] = approx_smooth_quadratic_bezier_handles(anchors)
            elif mode == "true_smooth":
                new_subpath = smooth_quadratic_path(anchors)
            # Shift any handles which ended up on top of
            # the previous anchor
            a0 = new_subpath[0:-1:2]
            h = new_subpath[1::2]
            a1 = new_subpath[2::2]
            false_ends = np.equal(a0, h).all(1)
            h[false_ends] = 0.5 * (a0[false_ends] + a1[false_ends])
            self.add_subpath(new_subpath)
        return self

    def make_smooth(self, approx=False, recurse=True) -> Self:
        """
        Edits the path so as to pass smoothly through all
        the current anchor points.

        If approx is False, this may increase the total
        number of points.
        """
        mode = "approx_smooth" if approx else "true_smooth"
        for submob in self.get_family(recurse):
            if submob.is_smooth():
                continue
            submob.change_anchor_mode(mode)
        return self

    def make_approximately_smooth(self, recurse=True) -> Self:
        self.make_smooth(approx=True, recurse=recurse)
        return self

    def make_jagged(self, recurse=True) -> Self:
        for submob in self.get_family(recurse):
            submob.change_anchor_mode("jagged")
        return self

    def add_subpath(self, points: Vect3Array) -> Self:
        assert(len(points) % 2 == 1 or len(points) == 0)
        if not self.has_points():
            self.set_points(points)
            return self
        if not self.consider_points_equal(points[0], self.get_points()[-1]):
            self.start_new_path(points[0])
        self.append_points(points[1:])
        return self

    def append_vectorized_mobject(self, vmobject: VMobject) -> Self:
        self.add_subpath(vmobject.get_points())
        n = vmobject.get_num_points()
        self.data[-n:] = vmobject.data
        return self

    #
    def consider_points_equal(self, p0: Vect3, p1: Vect3) -> bool:
        return get_norm(p1 - p0) < self.tolerance_for_point_equality

    # Information about the curve
    def get_bezier_tuples_from_points(self, points: Vect3Array) -> Iterable[Vect3Array]:
        n_curves = (len(points) - 1) // 2
        return (points[2 * i : 2 * i + 3] for i in range(n_curves))

    def get_bezier_tuples(self) -> Iterable[Vect3Array]:
        return self.get_bezier_tuples_from_points(self.get_points())

    def get_subpath_end_indices_from_points(self, points: Vect3Array) -> np.ndarray:
        atol = self.tolerance_for_point_equality
        a0, h, a1 = points[0:-1:2], points[1::2], points[2::2]
        # An anchor point is considered the end of a path
        # if its following handle is sitting on top of it.
        # To disambiguate this from cases with many null
        # curves in a row, we also check that the following
        # anchor is genuinely distinct
        is_end = np.empty(len(points) // 2 + 1, dtype=bool)
        is_end[:-1] = (a0 == h).all(1) & (abs(h - a1) > atol).any(1)
        is_end[-1] = True
        # If the curve immediately after an end marker is also an
        # end marker, don't mark the second one
        is_end[:-1] = is_end[:-1] & ~is_end[1:]
        return np.array([2 * n for n, end in enumerate(is_end) if end])

    def get_subpath_end_indices(self) -> np.ndarray:
        return self.get_subpath_end_indices_from_points(self.get_points())

    def get_subpaths_from_points(self, points: Vect3Array) -> list[Vect3Array]:
        if len(points) == 0:
            return []
        end_indices = self.get_subpath_end_indices_from_points(points)
        start_indices = [0, *(end_indices[:-1] + 2)]
        return [points[i1:i2 + 1] for i1, i2 in zip(start_indices, end_indices)]

    def get_subpaths(self) -> list[Vect3Array]:
        return self.get_subpaths_from_points(self.get_points())

    def get_nth_curve_points(self, n: int) -> Vect3Array:
        assert n < self.get_num_curves()
        return self.get_points()[2 * n:2 * n + 3]

    def get_nth_curve_function(self, n: int) -> Callable[[float], Vect3]:
        return bezier(self.get_nth_curve_points(n))

    def get_num_curves(self) -> int:
        return self.get_num_points() // 2

    def quick_point_from_proportion(self, alpha: float) -> Vect3:
        # Assumes all curves have the same length, so is inaccurate
        num_curves = self.get_num_curves()
        n, residue = integer_interpolate(0, num_curves, alpha)
        curve_func = self.get_nth_curve_function(n)
        return curve_func(residue)

    def curve_and_prop_of_partial_point(self, alpha) -> Tuple[int, float]:
        """
        If you want a point a proportion alpha along the curve, this
        gives you the index of the appropriate bezier curve, together
        with the proportion along that curve you'd need to travel
        """
        if alpha == 0:
            return (0, 0.0)
        partials: list[float] = [0]
        for tup in self.get_bezier_tuples():
            if self.consider_points_equal(tup[0], tup[1]):
                # Don't consider null curves
                arclen = 0
            else:
                # Approximate length with straight line from start to end
                arclen = get_norm(tup[2] - tup[0])
            partials.append(partials[-1] + arclen)
        full = partials[-1]
        if full == 0:
            return len(partials), 1.0
        # First index where the partial length is more than alpha times the full length
        index = next(
            (i for i, x in enumerate(partials) if x >= full * alpha),
            len(partials) - 1  # Default
        )
        residue = float(inverse_interpolate(
            partials[index - 1] / full, partials[index] / full, alpha
        ))
        return index - 1, residue

    def point_from_proportion(self, alpha: float) -> Vect3:
        if alpha <= 0:
            return self.get_start()
        elif alpha >= 1:
            return self.get_end()
        index, residue = self.curve_and_prop_of_partial_point(alpha)
        return self.get_nth_curve_function(index)(residue)

    def get_anchors_and_handles(self) -> list[Vect3]:
        """
        returns anchors1, handles, anchors2,
        where (anchors1[i], handles[i], anchors2[i])
        will be three points defining a quadratic bezier curve
        for any i in range(0, len(anchors1))
        """
        points = self.get_points()
        return [points[0:-1:2], points[1::2], points[2::2]]

    def get_start_anchors(self) -> Vect3Array:
        return self.get_points()[0:-1:2]

    def get_end_anchors(self) -> Vect3:
        return self.get_points()[2::2]

    def get_anchors(self) -> Vect3Array:
        return self.get_points()[::2]

    def get_points_without_null_curves(self, atol: float = 1e-9) -> Vect3Array:
        new_points = [self.get_points()[0]]
        for tup in self.get_bezier_tuples():
            if get_norm(tup[1] - tup[0]) > atol or get_norm(tup[2] - tup[0]) > atol:
                new_points.append(tup[1:])
        return np.vstack(new_points)

    def get_arc_length(self, n_sample_points: int | None = None) -> float:
        if n_sample_points is not None:
            points = np.array([
                self.quick_point_from_proportion(a)
                for a in np.linspace(0, 1, n_sample_points)
            ])
            return poly_line_length(points)
        points = self.get_points()
        inner_len = poly_line_length(points[::2])
        outer_len = poly_line_length(points)
        return interpolate(inner_len, outer_len, 1 / 3)

    def get_area_vector(self) -> Vect3:
        # Returns a vector whose length is the area bound by
        # the polygon formed by the anchor points, pointing
        # in a direction perpendicular to the polygon according
        # to the right hand rule.
        if not self.has_points():
            return np.zeros(3)

        p0 = self.get_anchors()
        p1 = np.vstack([p0[1:], p0[0]])

        # Each term goes through all edges [(x0, y0, z0), (x1, y1, z1)]
        sums = p0 + p1
        diffs = p1 - p0
        return 0.5 * np.array([
            (sums[:, 1] * diffs[:, 2]).sum(),  # Add up (y0 + y1)*(z1 - z0)
            (sums[:, 2] * diffs[:, 0]).sum(),  # Add up (z0 + z1)*(x1 - x0)
            (sums[:, 0] * diffs[:, 1]).sum(),  # Add up (x0 + x1)*(y1 - y0)
        ])

    def get_unit_normal(self) -> Vect3:
        if self.get_num_points() < 3:
            return OUT

        area_vect = self.get_area_vector()
        area = get_norm(area_vect)
        if area > 0:
            normal = area_vect / area
        else:
            points = self.get_points()
            normal = get_unit_normal(
                points[1] - points[0],
                points[2] - points[1],
            )
        self.data["unit_normal"][:] = normal
        return normal

    def refresh_unit_normal(self) -> Self:
        self.get_unit_normal()
        return self

    def rotate(
        self,
        angle: float,
        axis: Vect3 = OUT,
        about_point: Vect3 | None = None,
        **kwargs
    ) -> Self:
        super().rotate(angle, axis, about_point, **kwargs)
        for mob in self.get_family():
            mob.refresh_unit_normal()
        return self

    def ensure_positive_orientation(self, recurse=True) -> Self:
        for mob in self.get_family(recurse):
            if mob.get_unit_normal()[2] < 0:
                mob.reverse_points()
        return self

    # Alignment
    def align_points(self, vmobject: VMobject) -> Self:
        winding = self._use_winding_fill and vmobject._use_winding_fill
        if winding != self._use_winding_fill:
            self.use_winding_fill(winding)
        if winding != vmobject._use_winding_fill:
            vmobject.use_winding_fill(winding)
        if self.get_num_points() == len(vmobject.get_points()):
            # If both have fill, and they have the same shape, just
            # give them the same triangulation so that it's not recalculated
            # needlessly throughout an animation
            match_tris = not self._use_winding_fill and \
                         self.has_fill() and \
                         vmobject.has_fill() and \
                         self.has_same_shape_as(vmobject)
            if match_tris:
                vmobject.triangulation = self.triangulation
            for mob in [self, vmobject]:
                mob.get_joint_products()
            return self

        for mob in self, vmobject:
            # If there are no points, add one to
            # where the "center" is
            if not mob.has_points():
                mob.start_new_path(mob.get_center())

        # Figure out what the subpaths are, and align
        subpaths1 = self.get_subpaths()
        subpaths2 = vmobject.get_subpaths()
        for subpaths in [subpaths1, subpaths2]:
            subpaths.sort(key=lambda sp: -sum(
                get_norm(p2 - p1)
                for p1, p2 in zip(sp, sp[1:])
            ))
        n_subpaths = max(len(subpaths1), len(subpaths2))

        # Start building new ones
        new_subpaths1 = []
        new_subpaths2 = []

        def get_nth_subpath(path_list, n):
            if n >= len(path_list):
                return np.vstack([path_list[0][:-1], path_list[0][::-1]])
            return path_list[n]

        for n in range(n_subpaths):
            sp1 = get_nth_subpath(subpaths1, n)
            sp2 = get_nth_subpath(subpaths2, n)
            diff1 = max(0, (len(sp2) - len(sp1)) // 2)
            diff2 = max(0, (len(sp1) - len(sp2)) // 2)
            sp1 = self.insert_n_curves_to_point_list(diff1, sp1)
            sp2 = self.insert_n_curves_to_point_list(diff2, sp2)
            if n > 0:
                # Add intermediate anchor to mark path end
                new_subpaths1.append(new_subpaths1[-1][-1])
                new_subpaths2.append(new_subpaths2[-1][-1])
            new_subpaths1.append(sp1)
            new_subpaths2.append(sp2)

        for mob, paths in [(self, new_subpaths1), (vmobject, new_subpaths2)]:
            new_points = np.vstack(paths)
            mob.resize_points(len(new_points), resize_func=resize_preserving_order)
            mob.set_points(new_points)
            mob.get_joint_products()
        return self

    def insert_n_curves(self, n: int, recurse: bool = True) -> Self:
        for mob in self.get_family(recurse):
            if mob.get_num_curves() > 0:
                new_points = mob.insert_n_curves_to_point_list(n, mob.get_points())
                mob.set_points(new_points)
        return self

    def insert_n_curves_to_point_list(self, n: int, points: Vect3Array) -> Vect3Array:
        if len(points) == 1:
            return np.repeat(points, 2 * n + 1, 0)

        bezier_tuples = list(self.get_bezier_tuples_from_points(points))
        atol = self.tolerance_for_point_equality
        norms = [
            0 if get_norm(tup[1] - tup[0]) < atol else get_norm(tup[2] - tup[0])
            for tup in bezier_tuples
        ]
        # Calculate insertions per curve (ipc)
        ipc = np.zeros(len(bezier_tuples), dtype=int)
        for _ in range(n):
            index = np.argmax(norms)
            ipc[index] += 1
            norms[index] *= ipc[index] / (ipc[index] + 1)

        new_points = [points[0]]
        for tup, n_inserts in zip(bezier_tuples, ipc):
            # What was once a single quadratic curve defined
            # by "tup" will now be broken into n_inserts + 1
            # smaller quadratic curves
            alphas = np.linspace(0, 1, n_inserts + 2)
            for a1, a2 in zip(alphas, alphas[1:]):
                new_points.extend(partial_quadratic_bezier_points(tup, a1, a2)[1:])
        return np.vstack(new_points)

    def interpolate(
        self,
        mobject1: VMobject,
        mobject2: VMobject,
        alpha: float,
        *args, **kwargs
    ) -> Self:
        super().interpolate(mobject1, mobject2, alpha, *args, **kwargs)

        self._has_stroke = mobject1._has_stroke or mobject2._has_stroke
        self._has_fill = mobject1._has_fill or mobject2._has_fill

        if self._has_fill and not self._use_winding_fill:
            tri1 = mobject1.get_triangulation()
            tri2 = mobject2.get_triangulation()
            if not arrays_match(tri1, tri2):
                self.refresh_triangulation()
        return self

    def pointwise_become_partial(self, vmobject: VMobject, a: float, b: float) -> Self:
        assert(isinstance(vmobject, VMobject))
        vm_points = vmobject.get_points()
        self.data["joint_product"] = vmobject.data["joint_product"]
        if a <= 0 and b >= 1:
            self.set_points(vm_points, refresh_joints=False)
            return self
        num_curves = vmobject.get_num_curves()

        # Partial curve includes three portions:
        # - A start, which is some ending portion of an inner quadratic
        # - A middle section, which matches the curve exactly
        # - An end, which is the starting portion of a later inner quadratic

        lower_index, lower_residue = integer_interpolate(0, num_curves, a)
        upper_index, upper_residue = integer_interpolate(0, num_curves, b)
        i1 = 2 * lower_index
        i2 = 2 * lower_index + 3
        i3 = 2 * upper_index
        i4 = 2 * upper_index + 3

        new_points = vm_points.copy()
        if num_curves == 0:
            new_points[:] = 0
            return self
        if lower_index == upper_index:
            tup = partial_quadratic_bezier_points(vm_points[i1:i2], lower_residue, upper_residue)
            new_points[:i1] = tup[0]
            new_points[i1:i4] = tup
            new_points[i4:] = tup[2]
        else:
            low_tup = partial_quadratic_bezier_points(vm_points[i1:i2], lower_residue, 1)
            high_tup = partial_quadratic_bezier_points(vm_points[i3:i4], 0, upper_residue)
            new_points[0:i1] = low_tup[0]
            new_points[i1:i2] = low_tup
            # Keep new_points i2:i3 as they are
            new_points[i3:i4] = high_tup
            new_points[i4:] = high_tup[2]
        self.data["joint_product"][:i1] = [0, 0, 0, 1]
        self.data["joint_product"][i4:] = [0, 0, 0, 1]
        self.set_points(new_points, refresh_joints=False)
        return self

    def get_subcurve(self, a: float, b: float) -> Self:
        vmob = self.copy()
        vmob.pointwise_become_partial(self, a, b)
        return vmob

    def resize_points(
        self,
        new_length: int,
        resize_func: Callable[[np.ndarray, int], np.ndarray] = resize_array
    ) -> Self:
        super().resize_points(new_length, resize_func)

        n_curves = self.get_num_curves()
        # Creates the pattern (0, 1, 2, 2, 3, 4, 4, 5, 6, ...)
        self.outer_vert_indices = (np.arange(1, 3 * n_curves + 1) * 2) // 3
        return self

    def get_outer_vert_indices(self) -> np.ndarray:
        """
        Returns the pattern (0, 1, 2, 2, 3, 4, 4, 5, 6, ...)
        """
        return self.outer_vert_indices

    # Data for shaders that may need refreshing

    def refresh_triangulation(self) -> Self:
        for mob in self.get_family():
            mob.needs_new_triangulation = True
        return self

    def get_triangulation(self) -> np.ndarray:
        # Figure out how to triangulate the interior to know
        # how to send the points as to the vertex shader.
        # First triangles come directly from the points
        if not self.needs_new_triangulation:
            return self.triangulation

        points = self.get_points()

        if len(points) <= 1:
            self.triangulation = np.zeros(0, dtype='i4')
            self.needs_new_triangulation = False
            return self.triangulation

        normal_vector = self.get_unit_normal()

        # Rotate points such that unit normal vector is OUT
        if not np.isclose(normal_vector, OUT).all():
            points = np.dot(points, z_to_vector(normal_vector))


        v01s = points[1::2] - points[0:-1:2]
        v12s = points[2::2] - points[1::2]
        curve_orientations = np.sign(cross2d(v01s, v12s))

        concave_parts = curve_orientations < 0

        # These are the vertices to which we'll apply a polygon triangulation
        indices = np.arange(len(points), dtype=int)
        inner_vert_indices = np.hstack([
            indices[0::2],
            indices[1::2][concave_parts],
        ])
        inner_vert_indices.sort()
        # Even indices correspond to anchors, and `end_indices // 2`
        # shows which anchors are considered end points
        end_indices = self.get_subpath_end_indices()
        counts = np.arange(1, len(inner_vert_indices) + 1)
        rings = counts[inner_vert_indices % 2 == 0][end_indices // 2]

        # Triangulate
        inner_verts = points[inner_vert_indices]
        inner_tri_indices = inner_vert_indices[
            earclip_triangulation(inner_verts, rings)
        ]
        # Remove null triangles, coming from adjascent points
        iti = inner_tri_indices
        null1 = (iti[0::3] + 1 == iti[1::3]) & (iti[0::3] + 2 == iti[2::3])
        null2 = (iti[0::3] - 1 == iti[1::3]) & (iti[0::3] - 2 == iti[2::3])
        inner_tri_indices = iti[~(null1 | null2).repeat(3)]

        ovi = self.get_outer_vert_indices()
        tri_indices = np.hstack([ovi, inner_tri_indices])
        self.triangulation = tri_indices
        self.needs_new_triangulation = False
        return tri_indices

    def refresh_joint_products(self) -> Self:
        for mob in self.get_family():
            mob.needs_new_joint_products = True
        return self

    def get_joint_products(self, refresh: bool = False) -> np.ndarray:
        """
        The 'joint product' is a 4-vector holding the cross and dot
        product between tangent vectors at a joint
        """
        if not self.needs_new_joint_products and not refresh:
            return self.data["joint_product"]

        if "joint_product" in self.locked_data_keys:
            return self.data["joint_product"]

        self.needs_new_joint_products = False
        self._data_has_changed = True

        points = self.get_points()

        if(len(points) < 3):
            return self.data["joint_product"]

        # Find all the unit tangent vectors at each joint
        a0, h, a1 = points[0:-1:2], points[1::2], points[2::2]
        a0_to_h = h - a0
        h_to_a1 = a1 - h

        vect_to_vert = np.zeros(points.shape)
        vect_from_vert = np.zeros(points.shape)

        vect_to_vert[1::2] = a0_to_h
        vect_to_vert[2::2] = h_to_a1
        vect_from_vert[0:-1:2] = a0_to_h
        vect_from_vert[1::2] = h_to_a1

        # Joint up closed loops, or mark unclosed paths as such
        ends = self.get_subpath_end_indices()
        starts = [0, *(e + 2 for e in ends[:-1])]
        for start, end in zip(starts, ends):
            if self.consider_points_equal(points[start], points[end]):
                vect_to_vert[start] = vect_from_vert[end - 1]
                vect_from_vert[end] = vect_to_vert[start + 1]
            else:
                vect_to_vert[start] = vect_from_vert[start]
                vect_from_vert[end] = vect_to_vert[end]

        # Compute dot and cross products
        cross(
            vect_to_vert, vect_from_vert,
            out=self.data["joint_product"][:, :3]
        )
        self.data["joint_product"][:, 3] = (vect_to_vert * vect_from_vert).sum(1)
        return self.data["joint_product"]

    def lock_matching_data(self, vmobject1: VMobject, vmobject2: VMobject) -> Self:
        for mob in [self, vmobject1, vmobject2]:
            mob.get_joint_products()
        super().lock_matching_data(vmobject1, vmobject2)
        return self

    def triggers_refreshed_triangulation(func: Callable):
        @wraps(func)
        def wrapper(self, *args, refresh=True, **kwargs):
            func(self, *args, **kwargs)
            if refresh:
                self.refresh_triangulation()
                self.refresh_joint_products()
            return self
        return wrapper

    def set_points(self, points: Vect3Array, refresh_joints: bool = True) -> Self:
        assert(len(points) == 0 or len(points) % 2 == 1)
        super().set_points(points)
        self.refresh_triangulation()
        if refresh_joints:
            self.get_joint_products(refresh=True)
            self.get_unit_normal()
        return self

    @triggers_refreshed_triangulation
    def append_points(self, points: Vect3Array) -> Self:
        assert(len(points) % 2 == 0)
        super().append_points(points)
        return self

    @triggers_refreshed_triangulation
    def reverse_points(self, recurse: bool = True) -> Self:
        # This will reset which anchors are
        # considered path ends
        for mob in self.get_family(recurse):
            if not mob.has_points():
                continue
            inner_ends = mob.get_subpath_end_indices()[:-1]
            mob.data["point"][inner_ends + 1] = mob.data["point"][inner_ends + 2]
            mob.data["unit_normal"] *= -1
        super().reverse_points()
        return self

    @triggers_refreshed_triangulation
    def set_data(self, data: np.ndarray) -> Self:
        super().set_data(data)
        self.note_changed_fill()
        self.note_changed_stroke()
        return self

    # TODO, how to be smart about tangents here?
    @triggers_refreshed_triangulation
    def apply_function(
        self,
        function: Callable[[Vect3], Vect3],
        make_smooth: bool = False,
        **kwargs
    ) -> Self:
        super().apply_function(function, **kwargs)
        if self.make_smooth_after_applying_functions or make_smooth:
            self.make_smooth(approx=True)
        return self

    def apply_points_function(self, *args, **kwargs) -> Self:
        super().apply_points_function(*args, **kwargs)
        self.refresh_joint_products()
        return self

    def set_animating_status(self, is_animating: bool, recurse: bool = True):
        super().set_animating_status(is_animating, recurse)
        for submob in self.get_family(recurse):
            submob.get_joint_products(refresh=True)
            if not submob._use_winding_fill:
                submob.get_triangulation()
        return self

    # For shaders
    def init_shader_data(self, ctx: Context):
        dtype = self.shader_dtype
        fill_dtype, stroke_dtype = (
            np.dtype([
                (name, dtype[name].base, dtype[name].shape)
                for name in names
            ])
            for names in [self.fill_data_names, self.stroke_data_names]
        )
        fill_data = np.zeros(0, dtype=fill_dtype)
        stroke_data = np.zeros(0, dtype=stroke_dtype)
        self.fill_shader_wrapper = FillShaderWrapper(
            ctx=ctx,
            vert_data=fill_data,
            mobject_uniforms=self.uniforms,
            shader_folder=self.fill_shader_folder,
            render_primitive=self.fill_render_primitive,
        )
        self.stroke_shader_wrapper = ShaderWrapper(
            ctx=ctx,
            vert_data=stroke_data,
            mobject_uniforms=self.uniforms,
            shader_folder=self.stroke_shader_folder,
            render_primitive=self.stroke_render_primitive,
        )
        self.back_stroke_shader_wrapper = self.stroke_shader_wrapper.copy()
        self.shader_wrappers = [
            self.back_stroke_shader_wrapper,
            self.fill_shader_wrapper,
            self.stroke_shader_wrapper,
        ]
        for sw in self.shader_wrappers:
            family = self.family_members_with_points()
            rep = family[0] if family else self
            for old, new in rep.shader_code_replacements.items():
                sw.replace_code(old, new)

    def refresh_shader_wrapper_id(self) -> Self:
        if not self._shaders_initialized:
            return self
        for wrapper in self.shader_wrappers:
            wrapper.refresh_id()
        return self

    def get_shader_wrapper_list(self, ctx: Context) -> list[ShaderWrapper]:
        if not self._shaders_initialized:
            self.init_shader_data(ctx)
            self._shaders_initialized = True

        family = self.family_members_with_points()
        if not family:
            return []
        fill_names = self.fill_data_names
        stroke_names = self.stroke_data_names

        fill_family = (sm for sm in family if sm._has_fill)
        stroke_family = (sm for sm in family if sm._has_stroke)

        # Build up fill data lists
        fill_datas = []
        fill_indices = []
        fill_border_datas = []
        for submob in fill_family:
            indices = submob.get_outer_vert_indices()
            if submob._use_winding_fill:
                data = submob.data[fill_names]
                data["base_point"][:] = data["point"][0]
                fill_datas.append(data[indices])
            else:
                fill_datas.append(submob.data[fill_names])
                fill_indices.append(submob.get_triangulation())
            if (not submob._has_stroke) or submob.stroke_behind:
                # Add fill border
                submob.get_joint_products()
                names = list(stroke_names)
                names[names.index('stroke_rgba')] = 'fill_rgba'
                names[names.index('stroke_width')] = 'fill_border_width'
                border_stroke_data = submob.data[names].astype(
                    self.stroke_shader_wrapper.vert_data.dtype
                )
                fill_border_datas.append(border_stroke_data[indices])

        # Build up stroke data lists
        stroke_datas = []
        back_stroke_datas = []
        for submob in stroke_family:
            submob.get_joint_products()
            indices = submob.get_outer_vert_indices()
            if submob.stroke_behind:
                back_stroke_datas.append(submob.data[stroke_names][indices])
            else:
                stroke_datas.append(submob.data[stroke_names][indices])

        shader_wrappers = [
            self.back_stroke_shader_wrapper.read_in([*back_stroke_datas, *fill_border_datas]),
            self.fill_shader_wrapper.read_in(fill_datas, fill_indices or None),
            self.stroke_shader_wrapper.read_in(stroke_datas),
        ]
        for sw in shader_wrappers:
            rep = family[0]  # Representative family member
            sw.bind_to_mobject_uniforms(rep.get_uniforms())
            sw.depth_test = rep.depth_test
        return [sw for sw in shader_wrappers if len(sw.vert_data) > 0]


class VGroup(Group, VMobject, Generic[SubVmobjectType]):
    def __init__(self, *vmobjects: SubVmobjectType | Iterable[SubVmobjectType], **kwargs):
        super().__init__(**kwargs)
        if any(isinstance(vmob, Mobject) and not isinstance(vmob, VMobject) for vmob in vmobjects):
            raise Exception("Only VMobjects can be passed into VGroup")
        self._ingest_args(*vmobjects)
        if self.submobjects:
            self.uniforms.update(self.submobjects[0].uniforms)

    def __add__(self, other: VMobject) -> Self:
        assert isinstance(other, VMobject)
        return self.add(other)

    # This is just here to make linters happy with references to things like VGroup(...)[0]
    def __getitem__(self, index) -> SubVmobjectType:
        return super().__getitem__(index)


class VectorizedPoint(Point, VMobject):
    def __init__(
        self,
        location: np.ndarray = ORIGIN,
        color: ManimColor = BLACK,
        fill_opacity: float = 0.0,
        stroke_width: float = 0.0,
        **kwargs
    ):
        Point.__init__(self, location, **kwargs)
        VMobject.__init__(
            self,
            color=color,
            fill_opacity=fill_opacity,
            stroke_width=stroke_width,
            **kwargs
        )
        self.set_points(np.array([location]))


class CurvesAsSubmobjects(VGroup):
    def __init__(self, vmobject: VMobject, **kwargs):
        super().__init__(**kwargs)
        for tup in vmobject.get_bezier_tuples():
            part = VMobject()
            part.set_points(tup)
            part.match_style(vmobject)
            self.add(part)


class DashedVMobject(VMobject):
    def __init__(
        self,
        vmobject: VMobject,
        num_dashes: int = 15,
        positive_space_ratio: float = 0.5,
        **kwargs
    ):
        super().__init__(**kwargs)

        if num_dashes > 0:
            # End points of the unit interval for division
            alphas = np.linspace(0, 1, num_dashes + 1)

            # This determines the length of each "dash"
            full_d_alpha = (1.0 / num_dashes)
            partial_d_alpha = full_d_alpha * positive_space_ratio

            # Rescale so that the last point of vmobject will
            # be the end of the last dash
            alphas /= (1 - full_d_alpha + partial_d_alpha)

            self.add(*[
                vmobject.get_subcurve(alpha, alpha + partial_d_alpha)
                for alpha in alphas[:-1]
            ])
        # Family is already taken care of by get_subcurve
        # implementation
        self.match_style(vmobject, recurse=False)


class VHighlight(VGroup):
    def __init__(
        self,
        vmobject: VMobject,
        n_layers: int = 5,
        color_bounds: Tuple[ManimColor] = (GREY_C, GREY_E),
        max_stroke_addition: float = 5.0,
    ):
        outline = vmobject.replicate(n_layers)
        outline.set_fill(opacity=0)
        added_widths = np.linspace(0, max_stroke_addition, n_layers + 1)[1:]
        colors = color_gradient(color_bounds, n_layers)
        for part, added_width, color in zip(reversed(outline), added_widths, colors):
            for sm in part.family_members_with_points():
                sm.set_stroke(
                    width=sm.get_stroke_width() + added_width,
                    color=color,
                )
        super().__init__(*outline)
