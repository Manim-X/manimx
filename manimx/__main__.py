#!/usr/bin/env python
from manimx import __version__
import manimx.config
import manimx.extract_scene
import manimx.logger
import manimx.utils.init_config


def main():
    print(f"manimx \033[32mv{__version__}\033[0m")

    args = manimx.config.parse_cli()
    if args.version and args.file is None:
        return
    if args.log_level:
        manimx.logger.log.setLevel(args.log_level)

    if args.config:
        manimx.utils.init_config.init_customization()
    else:
        config = manimx.config.get_configuration(args)
        scenes = manimx.extract_scene.main(config)

        for scene in scenes:
            scene.run()


if __name__ == "__main__":
    main()
