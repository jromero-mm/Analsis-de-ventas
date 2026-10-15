"""Rutas estables para desarrollo y para el ejecutable de Windows."""

from __future__ import annotations

import sys
import os
from pathlib import Path


def raiz_aplicacion() -> Path:
    """Carpeta del proyecto o carpeta que contiene el ejecutable."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def ruta_config(nombre: str) -> Path:
    return raiz_aplicacion() / "config" / nombre


def ruta_datos_usuario(nombre: str) -> Path:
    """Ruta persistente que no se pierde al reemplazar el ejecutable."""
    base = os.environ.get("APPDATA") or os.environ.get("LOCALAPPDATA")
    if base:
        return Path(base) / "AnalisisVentasDemo" / nombre
    return raiz_aplicacion() / "datos_usuario" / nombre


def preparar_tkinter_empaquetado() -> None:
    """Indica a Tcl/Tk dónde están sus recursos dentro del ejecutable."""
    if not getattr(sys, "frozen", False):
        return
    recursos = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    os.environ.setdefault("TCL_LIBRARY", str(recursos / "_tcl_data"))
    os.environ.setdefault("TK_LIBRARY", str(recursos / "_tk_data"))
