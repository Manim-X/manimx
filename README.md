# ManimX

[![pypi version](https://img.shields.io/pypi/v/manimx?logo=pypi)](https://pypi.org/project/manimx/)
[![MIT License](https://img.shields.io/badge/license-MIT-blue.svg?style=flat)](http://choosealicense.com/licenses/mit/)
[![docs](https://github.com/Manim-X/manimx/actions/workflows/docs.yml/badge.svg?branch=main)](https://github.com/Manim-X/manimx/actions/workflows/docs.yml)
[![Manim Subreddit](https://img.shields.io/reddit/subreddit-subscribers/manimx.svg?color=ff4301&label=reddit&logo=reddit)](https://www.reddit.com/r/ManimX/)
[![ManimX Discord](https://img.shields.io/discord/581738731934056449.svg?label=discord&logo=discord)]([https://discord.com](https://discord.com/channels/1248543359472111684))

Manim is an engine for precise programmatic animations, designed for creating explanatory math videos.

## Installation

Manim runs on Python 3.8 or higher.

System requirements are [FFmpeg](https://ffmpeg.org/), [OpenGL](https://www.opengl.org/) and [LaTeX](https://www.latex-project.org) (optional, if you want to use LaTeX).
For Linux, [Pango](https://pango.gnome.org) along with its development headers are required. See instruction [here](https://github.com/ManimCommunity/ManimPango#building).


### Directly

```sh
# Install manimx
pip install manimx

# Try it out
manimx
```

For more options, take a look at the [Using manim](#using-manim) sections further below.

If you want to hack on manimx itself, clone this repository and in that directory execute:

```sh
# Install manimx
pip install -e .

# Try it out
manimx example_scenes.py OpeningManimExample
# or
manim-render example_scenes.py OpeningManimExample
```

### Directly (Windows)

1. [Install FFmpeg](https://www.wikihow.com/Install-FFmpeg-on-Windows).
2. Install a LaTeX distribution. [MiKTeX](https://miktex.org/download) is recommended.
3. Install the remaining Python packages.
    ```sh
    git clone https://github.com/Manim-X/manimx.git
    cd manimx
    pip install -e .
    manimx example_scenes.py OpeningManimExample
    ```

### Mac OSX

1. Install FFmpeg, LaTeX in terminal using homebrew.
    ```sh
    brew install ffmpeg mactex
    ```
   
2. Install latest version of manimx using these command.
    ```sh
    git clone https://github.com/Manim-X/manimx.git
    cd manimx
    pip install -e .
    manimx example_scenes.py OpeningManimExample
    ```

## Anaconda Install

1. Install LaTeX as above.
2. Create a conda environment using `conda create -n manimx python=3.11`.
3. Activate the environment using `conda activate manimx`.
4. Install manimx using `pip install -e .`.


## Using manim
Try running the following:
```sh
manimx example_scenes.py OpeningManimExample
```
This should pop up a window playing a simple scene.

Some useful flags include:
* `-w` to write the scene to a file
* `-o` to write the scene to a file and open the result
* `-s` to skip to the end and just show the final frame.
    * `-so` will save the final frame to an image and show it
* `-n <number>` to skip ahead to the `n`'th animation of a scene.
* `-f` to make the playback window fullscreen

Take a look at custom_config.yml for further configuration.  To add your customization, you can either edit this file, or add another file by the same name "custom_config.yml" to whatever directory you are running manim from. There you can specify where videos should be output to, where manim should look for image files and sounds you want to read in, and other defaults regarding style and video quality.

- [example scenes](https://manim-x.github.io/manimx/getting_started/example_scenes.html) 

### Documentation

- [https://manim-x.github.io/manimx](https://manim-x.github.io/manimx)

## License
This project falls under the MIT license.
