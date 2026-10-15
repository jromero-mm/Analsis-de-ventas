"""Persistencia segura de perfiles/favoritos del usuario."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict

from app.paths import ruta_config, ruta_datos_usuario


def ruta_perfiles_usuario() -> Path:
    """Ubicación que sobrevive a recompilaciones del ejecutable."""
    return ruta_datos_usuario("perfiles.json")


def cargar_perfiles(
    ruta: Path | None = None,
    fuente_inicial: Path | None = None,
) -> Dict:
    """Carga perfiles y migra la configuración incluida si aún no existe."""
    destino = Path(ruta) if ruta is not None else ruta_perfiles_usuario()
    fuente = (
        Path(fuente_inicial)
        if fuente_inicial is not None
        else ruta_config("perfiles.json")
    )
    if not destino.exists():
        iniciales: Dict = {}
        if fuente.exists() and fuente.resolve() != destino.resolve():
            data = json.loads(fuente.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                iniciales = data
        guardar_perfiles(iniciales, destino)
        return iniciales
    data = json.loads(destino.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("El archivo de perfiles no contiene un objeto válido.")
    return data


def guardar_perfiles(perfiles: Dict, ruta: Path | None = None) -> Path:
    """Guarda perfiles de forma atómica para evitar archivos incompletos."""
    if not isinstance(perfiles, dict):
        raise ValueError("Los perfiles deben ser un objeto.")
    destino = Path(ruta) if ruta is not None else ruta_perfiles_usuario()
    destino.parent.mkdir(parents=True, exist_ok=True)
    temporal = destino.with_suffix(destino.suffix + ".tmp")
    temporal.write_text(
        json.dumps(perfiles, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporal.replace(destino)
    return destino
