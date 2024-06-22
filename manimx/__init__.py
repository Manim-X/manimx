import pkg_resources

__version__ = pkg_resources.get_distribution("manimx").version

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from manimx.typing import *

from manimx.constants import *

from manimx.window import *

from manimx.animation.animation import *
from manimx.animation.composition import *
from manimx.animation.creation import *
from manimx.animation.fading import *
from manimx.animation.growing import *
from manimx.animation.indication import *
from manimx.animation.movement import *
from manimx.animation.numbers import *
from manimx.animation.rotation import *
from manimx.animation.specialized import *
from manimx.animation.transform import *
from manimx.animation.transform_matching_parts import *
from manimx.animation.update import *

from manimx.camera.camera import *

from manimx.mobject.boolean_ops import *
from manimx.mobject.changing import *
from manimx.mobject.coordinate_systems import *
from manimx.mobject.frame import *
from manimx.mobject.functions import *
from manimx.mobject.geometry import *
from manimx.mobject.interactive import *
from manimx.mobject.matrix import *
from manimx.mobject.mobject import *
from manimx.mobject.mobject_update_utils import *
from manimx.mobject.number_line import *
from manimx.mobject.numbers import *
from manimx.mobject.probability import *
from manimx.mobject.shape_matchers import *
from manimx.mobject.svg.brace import *
from manimx.mobject.svg.drawings import *
from manimx.mobject.svg.tex_mobject import *
from manimx.mobject.svg.string_mobject import *
from manimx.mobject.svg.svg_mobject import *
from manimx.mobject.svg.special_tex import *
from manimx.mobject.svg.tex_mobject import *
from manimx.mobject.svg.text_mobject import *
from manimx.mobject.three_dimensions import *
from manimx.mobject.types.dot_cloud import *
from manimx.mobject.types.image_mobject import *
from manimx.mobject.types.point_cloud_mobject import *
from manimx.mobject.types.surface import *
from manimx.mobject.types.vectorized_mobject import *
from manimx.mobject.value_tracker import *
from manimx.mobject.vector_field import *

from manimx.scene.interactive_scene import *
from manimx.scene.scene import *

from manimx.utils.bezier import *
from manimx.utils.color import *
from manimx.utils.dict_ops import *
from manimx.utils.customization import *
from manimx.utils.debug import *
from manimx.utils.directories import *
from manimx.utils.file_ops import *
from manimx.utils.images import *
from manimx.utils.iterables import *
from manimx.utils.paths import *
from manimx.utils.rate_functions import *
from manimx.utils.simple_functions import *
from manimx.utils.shaders import *
from manimx.utils.sounds import *
from manimx.utils.space_ops import *
from manimx.utils.tex import *
