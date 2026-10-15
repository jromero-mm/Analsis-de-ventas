"""Preferencias persistentes de la aplicación."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Optional

from app.paths import ruta_datos_usuario


OPCIONES_EXPORTACION_DEFAULT: Dict[str, object] = {
    "incluir_resumen": True,
    "incluir_detalle": True,
    "incluir_errores": True,
    "orden_boticas": "nombre",
    "carpeta": "",
}


def _normalizar(datos: object) -> Dict[str, object]:
    salida = dict(OPCIONES_EXPORTACION_DEFAULT)
    if not isinstance(datos, dict):
        return salida
    for clave in ("incluir_resumen", "incluir_detalle", "incluir_errores"):
        if isinstance(datos.get(clave), bool):
            salida[clave] = datos[clave]
    if datos.get("orden_boticas") in ("nombre", "ventas"):
        salida["orden_boticas"] = datos["orden_boticas"]
    if isinstance(datos.get("carpeta"), str):
        salida["carpeta"] = datos["carpeta"].strip()
    return salida


def cargar_exportacion(ruta: Optional[str | Path] = None) -> Dict[str, object]:
    destino = Path(ruta) if ruta is not None else ruta_datos_usuario("preferencias.json")
    if not destino.exists():
        return dict(OPCIONES_EXPORTACION_DEFAULT)
    try:
        datos = json.loads(destino.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return dict(OPCIONES_EXPORTACION_DEFAULT)
    return _normalizar(datos.get("exportacion", datos) if isinstance(datos, dict) else datos)


def guardar_exportacion(
    opciones: Dict[str, object],
    ruta: Optional[str | Path] = None,
) -> Path:
    destino = Path(ruta) if ruta is not None else ruta_datos_usuario("preferencias.json")
    destino.parent.mkdir(parents=True, exist_ok=True)
    datos = {"exportacion": _normalizar(opciones)}
    temporal = destino.with_suffix(destino.suffix + ".tmp")
    temporal.write_text(
        json.dumps(datos, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporal.replace(destino)
    return destino
