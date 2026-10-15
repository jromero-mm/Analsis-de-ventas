"""Fuerza la deteccion de tkinter en instalaciones locales de Python."""

import sys
from pathlib import Path


def pre_find_module_path(hook_api):
    hook_api.search_dirs = [str(Path(sys.base_prefix) / "Lib")]
