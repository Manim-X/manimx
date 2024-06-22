import os
import tempfile

from manimx.config import get_custom_config
from manimx.config import get_manim_dir


CUSTOMIZATION = {}


def get_customization():
    if not CUSTOMIZATION:
        CUSTOMIZATION.update(get_custom_config())
        directories = CUSTOMIZATION["directories"]
        # Unless user has specified otherwise, use the system default temp
        # directory for storing tex files, mobject_data, etc.
        if not directories["temporary_storage"]:
            directories["temporary_storage"] = tempfile.gettempdir()

        # Assumes all shaders are written into manimx/shaders
        directories["shaders"] = os.path.join(
            get_manim_dir(), "manimx", "shaders"
        )
    return CUSTOMIZATION
