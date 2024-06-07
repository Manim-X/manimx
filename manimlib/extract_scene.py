import copy
import inspect
import sys

from manimlib.config import get_custom_config
from manimlib.logger import log
from manimlib.scene.interactive_scene import InteractiveScene
from manimlib.scene.scene import Scene


class BlankScene(InteractiveScene):
    def construct(self):
        exec(get_custom_config()["universal_import_line"])
        self.embed()


def is_child_scene(obj, module):
    if not inspect.isclass(obj):
        return False
    if not issubclass(obj, Scene):
        return False
    if obj == Scene:
        return False
    if not obj.__module__.startswith(module.__name__):
        return False
    return True


def prompt_user_for_choice(scene_classes):
    name_to_class = {}
    max_digits = len(str(len(scene_classes)))
    for idx, scene_class in enumerate(scene_classes, start=1):
        name = scene_class.__name__
        print(f"{str(idx).zfill(max_digits)}: {name}")
        name_to_class[name] = scene_class
    try:
        user_input = input(
            "\nThat module has multiple scenes, " + \
            "which ones would you like to render?" + \
            "\nScene Name or Number: "
        )
        return [
            name_to_class[split_str] if not split_str.isnumeric() else scene_classes[int(split_str) - 1]
            for split_str in user_input.replace(" ", "").split(",")
        ]
    except IndexError:
        log.error("Invalid scene number")
        sys.exit(2)
    except KeyError:
        log.error("Invalid scene name")
        sys.exit(2)
    except EOFError:
        sys.exit(1)


def get_scene_config(config):
    scene_parameters = inspect.signature(Scene).parameters.keys()
    return {
        key: config[key]
        for key in set(scene_parameters).intersection(config.keys())
    }


def compute_total_frames(scene_class, scene_config):
    """
    When a scene is being written to file, a copy of the scene is run with
    skip_animations set to true so as to count how many frames it will require.
    This allows for a total progress bar on rendering, and also allows runtime
    errors to be exposed preemptively for long running scenes.
    """
    pre_config = copy.deepcopy(scene_config)
    pre_config["file_writer_config"]["write_to_movie"] = False
    pre_config["file_writer_config"]["save_last_frame"] = False
    pre_config["file_writer_config"]["quiet"] = True
    pre_config["skip_animations"] = True
    pre_scene = scene_class(**pre_config)
    pre_scene.run()
    total_time = pre_scene.time - pre_scene.skip_time
    return int(total_time * scene_config["camera_config"]["fps"])


def scene_from_class(scene_class, scene_config, config):
    fw_config = scene_config["file_writer_config"]
    if fw_config["write_to_movie"] and config["prerun"]:
        fw_config["total_frames"] = compute_total_frames(scene_class, scene_config)
    return scene_class(**scene_config)


def get_scenes_to_render(all_scene_classes, scene_config, config):
    if config["write_all"]:
        return [sc(**scene_config) for sc in all_scene_classes]

    names_to_classes = {sc.__name__ : sc for sc in all_scene_classes}
    scene_names = config["scene_names"]

    for name in set.difference(set(scene_names), names_to_classes):
        log.error(f"No scene named {name} found")
        scene_names.remove(name)

    if scene_names:
        classes_to_run = [names_to_classes[name] for name in scene_names]
    elif len(all_scene_classes) == 1:
        classes_to_run = [all_scene_classes[0]]
    else:
        classes_to_run = prompt_user_for_choice(all_scene_classes)

    return [
        scene_from_class(scene_class, scene_config, config)
        for scene_class in classes_to_run
    ]


def get_scene_classes_from_module(module):
    if hasattr(module, "SCENES_IN_ORDER"):
        return module.SCENES_IN_ORDER
    else:
        return [
            member[1]
            for member in inspect.getmembers(
                module,
                lambda x: is_child_scene(x, module)
            )
        ]


def main(config):
    module = config["module"]
    scene_config = get_scene_config(config)
    if module is None:
        # If no module was passed in, just play the blank scene
        return [BlankScene(**scene_config)]

    all_scene_classes = get_scene_classes_from_module(module)
    scenes = get_scenes_to_render(all_scene_classes, scene_config, config)
    return scenes
