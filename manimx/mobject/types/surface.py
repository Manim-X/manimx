from __future__ import annotations

import moderngl
import numpy as np

from manimx.constants import GREY
from manimx.constants import OUT
from manimx.mobject.mobject import Mobject
from manimx.utils.bezier import integer_interpolate
from manimx.utils.bezier import interpolate
from manimx.utils.images import get_full_raster_image_path
from manimx.utils.iterables import listify
from manimx.utils.iterables import resize_with_interpolation
from manimx.utils.space_ops import normalize_along_axis
from manimx.utils.space_ops import cross

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Callable, Iterable, Sequence, Tuple

    from manimx.camera.camera import Camera
    from manimx.typing import ManimColor, Vect3, Vect3Array, Self


class Surface(Mobject):
    render_primitive: int = moderngl.TRIANGLES
    shader_folder: str = "surface"
    shader_dtype: np.dtype = np.dtype([
        ('point', np.float32, (3,)),
        ('normal', np.float32, (3,)),
        ('rgba', np.float32, (4,)),
    ])

    def __init__(
        self,
        color: ManimColor = GREY,
        shading: Tuple[float, float, float] = (0.3, 0.2, 0.4),
        depth_test: bool = True,
        u_range: Tuple[float, float] = (0.0, 1.0),
        v_range: Tuple[float, float] = (0.0, 1.0),
        # Resolution counts number of points sampled, which for
        # each coordinate is one more than the the number of
        # rows/columns of approximating squares
        resolution: Tuple[int, int] = (101, 101),
        prefered_creation_axis: int = 1,
        # For du and dv steps.  Much smaller and numerical error
        # can crop up in the shaders.
        epsilon: float = 1e-5,
        **kwargs
    ):
        self.u_range = u_range
        self.v_range = v_range
        self.resolution = resolution
        self.prefered_creation_axis = prefered_creation_axis
        self.epsilon = epsilon

        super().__init__(
            **kwargs,
            color=color,
            shading=shading,
            depth_test=depth_test,
        )
        self.compute_triangle_indices()

    def init_uniforms(self):
        super().init_uniforms()
        self.uniforms["clip_plane"] = np.zeros(4)

    def uv_func(self, u: float, v: float) -> tuple[float, float, float]:
        # To be implemented in subclasses
        return (u, v, 0.0)

    @Mobject.affects_data
    def init_points(self):
        dim = self.dim
        nu, nv = self.resolution
        u_range = np.linspace(*self.u_range, nu)
        v_range = np.linspace(*self.v_range, nv)

        # Get three lists:
        # - Points generated by pure uv values
        # - Those generated by values nudged by du
        # - Those generated by values nudged by dv
        uv_grid = np.array([[[u, v] for v in v_range] for u in u_range])
        uv_plus_du = uv_grid.copy()
        uv_plus_du[:, :, 0] += self.epsilon
        uv_plus_dv = uv_grid.copy()
        uv_plus_dv[:, :, 1] += self.epsilon

        points, du_points, dv_points = [
            np.apply_along_axis(
                lambda p: self.uv_func(*p), 2, grid
            ).reshape((nu * nv, dim))
            for grid in (uv_grid, uv_plus_du, uv_plus_dv)
        ]
        self.set_points(points)
        self.data["normal"] = normalize_along_axis(cross(
            (du_points - points) / self.epsilon,
            (dv_points - points) / self.epsilon,
        ), 1)

    def apply_points_function(self, *args, **kwargs) -> Self:
        super().apply_points_function(*args, **kwargs)
        self.get_unit_normals()
        return self

    def compute_triangle_indices(self) -> np.ndarray:
        # TODO, if there is an event which changes
        # the resolution of the surface, make sure
        # this is called.
        nu, nv = self.resolution
        if nu == 0 or nv == 0:
            self.triangle_indices = np.zeros(0, dtype=int)
            return self.triangle_indices
        index_grid = np.arange(nu * nv).reshape((nu, nv))
        indices = np.zeros(6 * (nu - 1) * (nv - 1), dtype=int)
        indices[0::6] = index_grid[:-1, :-1].flatten()  # Top left
        indices[1::6] = index_grid[+1:, :-1].flatten()  # Bottom left
        indices[2::6] = index_grid[:-1, +1:].flatten()  # Top right
        indices[3::6] = index_grid[:-1, +1:].flatten()  # Top right
        indices[4::6] = index_grid[+1:, :-1].flatten()  # Bottom left
        indices[5::6] = index_grid[+1:, +1:].flatten()  # Bottom right
        self.triangle_indices = indices
        return self.triangle_indices

    def get_triangle_indices(self) -> np.ndarray:
        return self.triangle_indices

    def get_unit_normals(self) -> Vect3Array:
        nu, nv = self.resolution
        indices = np.arange(nu * nv)
        if len(indices) == 0:
            return np.zeros((3, 0))

        # For each point, find two adjacent points at indices
        # step1 and step2, such that crossing points[step1] - points
        # with points[step1] - points gives a normal vector
        step1 = indices + 1
        step2 = indices + nu

        # Right edge
        step1[nu - 1::nu] = indices[nu - 1::nu] + nu
        step2[nu - 1::nu] = indices[nu - 1::nu] - 1

        # Bottom edge
        step1[-nu:] = indices[-nu:] - nu
        step2[-nu:] = indices[-nu:] + 1

        # Lower right point
        step1[-1] = indices[-1] - 1
        step2[-1] = indices[-1] - nu

        points = self.get_points()
        crosses = cross(
            points[step1] - points,
            points[step2] - points,
        )
        self.data["normal"] = normalize_along_axis(crosses, 1)
        return self.data["normal"]

    @Mobject.affects_data
    def pointwise_become_partial(
        self,
        smobject: "Surface",
        a: float,
        b: float,
        axis: int | None = None
    ) -> Self:
        assert(isinstance(smobject, Surface))
        if axis is None:
            axis = self.prefered_creation_axis
        if a <= 0 and b >= 1:
            self.match_points(smobject)
            return self

        nu, nv = smobject.resolution
        self.data['point'][:] = self.get_partial_points_array(
            smobject.data['point'], a, b,
            (nu, nv, 3),
            axis=axis
        )
        return self

    def get_partial_points_array(
        self,
        points: Vect3Array,
        a: float,
        b: float,
        resolution: Sequence[int],
        axis: int
    ) -> Vect3Array:
        if len(points) == 0:
            return points
        nu, nv = resolution[:2]
        points = points.reshape(resolution).copy()
        max_index = resolution[axis] - 1
        lower_index, lower_residue = integer_interpolate(0, max_index, a)
        upper_index, upper_residue = integer_interpolate(0, max_index, b)
        if axis == 0:
            points[:lower_index] = interpolate(
                points[lower_index],
                points[lower_index + 1],
                lower_residue
            )
            points[upper_index + 1:] = interpolate(
                points[upper_index],
                points[upper_index + 1],
                upper_residue
            )
        else:
            shape = (nu, 1, resolution[2])
            points[:, :lower_index] = interpolate(
                points[:, lower_index],
                points[:, lower_index + 1],
                lower_residue
            ).reshape(shape)
            points[:, upper_index + 1:] = interpolate(
                points[:, upper_index],
                points[:, upper_index + 1],
                upper_residue
            ).reshape(shape)
        return points.reshape((nu * nv, *resolution[2:]))

    @Mobject.affects_data
    def sort_faces_back_to_front(self, vect: Vect3 = OUT) -> Self:
        tri_is = self.triangle_indices
        points = self.get_points()

        dots = (points[tri_is[::3]] * vect).sum(1)
        indices = np.argsort(dots)
        for k in range(3):
            tri_is[k::3] = tri_is[k::3][indices]
        return self

    def always_sort_to_camera(self, camera: Camera) -> Self:
        def updater(surface: Surface):
            vect = camera.get_location() - surface.get_center()
            surface.sort_faces_back_to_front(vect)
        self.add_updater(updater)
        return self

    def set_clip_plane(
        self,
        vect: Vect3 | None = None,
        threshold: float | None = None
    ) -> Self:
        if vect is not None:
            self.uniforms["clip_plane"][:3] = vect
        if threshold is not None:
            self.uniforms["clip_plane"][3] = threshold
        return self

    def deactivate_clip_plane(self) -> Self:
        self.uniforms["clip_plane"][:] = 0
        return self

    def get_shader_vert_indices(self) -> np.ndarray:
        return self.get_triangle_indices()


class ParametricSurface(Surface):
    def __init__(
        self,
        uv_func: Callable[[float, float], Iterable[float]],
        u_range: tuple[float, float] = (0, 1),
        v_range: tuple[float, float] = (0, 1),
        **kwargs
    ):
        self.passed_uv_func = uv_func
        super().__init__(u_range=u_range, v_range=v_range, **kwargs)

    def uv_func(self, u, v):
        return self.passed_uv_func(u, v)


class SGroup(Surface):
    def __init__(
        self,
        *parametric_surfaces: Surface,
        **kwargs
    ):
        super().__init__(resolution=(0, 0), **kwargs)
        self.add(*parametric_surfaces)

    def init_points(self):
        pass  # Needed?


class TexturedSurface(Surface):
    shader_folder: str = "textured_surface"
    shader_dtype: Sequence[Tuple[str, type, Tuple[int]]] = [
        ('point', np.float32, (3,)),
        ('normal', np.float32, (3,)),
        ('im_coords', np.float32, (2,)),
        ('opacity', np.float32, (1,)),
    ]

    def __init__(
        self,
        uv_surface: Surface,
        image_file: str,
        dark_image_file: str | None = None,
        **kwargs
    ):
        if not isinstance(uv_surface, Surface):
            raise Exception("uv_surface must be of type Surface")
        # Set texture information
        if dark_image_file is None:
            dark_image_file = image_file
            self.num_textures = 1
        else:
            self.num_textures = 2

        texture_paths = {
            "LightTexture": get_full_raster_image_path(image_file),
            "DarkTexture": get_full_raster_image_path(dark_image_file),
        }

        self.uv_surface = uv_surface
        self.uv_func = uv_surface.uv_func
        self.u_range: Tuple[float, float] = uv_surface.u_range
        self.v_range: Tuple[float, float] = uv_surface.v_range
        self.resolution: Tuple[int, int] = uv_surface.resolution
        super().__init__(
            texture_paths=texture_paths,
            shading=tuple(uv_surface.shading),
            **kwargs
        )

    @Mobject.affects_data
    def init_points(self):
        surf = self.uv_surface
        nu, nv = surf.resolution
        self.resize_points(surf.get_num_points())
        self.resolution = surf.resolution
        self.data['point'][:] = surf.data['point']
        self.data['normal'][:] = surf.data['normal']
        self.data['opacity'][:, 0] = surf.data["rgba"][:, 3]
        self.data["im_coords"] = np.array([
            [u, v]
            for u in np.linspace(0, 1, nu)
            for v in np.linspace(1, 0, nv)  # Reverse y-direction
        ])

    def init_uniforms(self):
        super().init_uniforms()
        self.uniforms["num_textures"] = self.num_textures

    @Mobject.affects_data
    def set_opacity(self, opacity: float | Iterable[float]) -> Self:
        op_arr = np.array(listify(opacity))
        self.data["opacity"][:, 0] = resize_with_interpolation(op_arr, len(self.data))
        return self

    def set_color(
        self,
        color: ManimColor | Iterable[ManimColor] | None,
        opacity: float | Iterable[float] | None = None,
        recurse: bool = True
    ) -> Self:
        if opacity is not None:
            self.set_opacity(opacity)
        return self

    def pointwise_become_partial(
        self,
        tsmobject: "TexturedSurface",
        a: float,
        b: float,
        axis: int = 1
    ) -> Self:
        super().pointwise_become_partial(tsmobject, a, b, axis)
        im_coords = self.data["im_coords"]
        im_coords[:] = tsmobject.data["im_coords"]
        if a <= 0 and b >= 1:
            return self
        nu, nv = tsmobject.resolution
        im_coords[:] = self.get_partial_points_array(
            im_coords, a, b, (nu, nv, 2), axis
        )
        return self