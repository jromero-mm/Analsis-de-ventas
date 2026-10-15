"""Cálculo de avance de concursos por producto y cajas."""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Dict

import pandas as pd

from app.paths import ruta_config
from app.core.data_source import calcular_unidades_vendidas


class ErrorConcurso(Exception):
    pass


def cargar_concursos() -> Dict:
    ruta = ruta_config("concursos.json")
    if not ruta.exists():
        return {}
    try:
        data = json.loads(ruta.read_text(encoding="utf-8"))
        return data.get("concursos", {})
    except (OSError, json.JSONDecodeError) as exc:
        raise ErrorConcurso(f"No se pudo leer concursos.json: {exc}") from exc


def _normalizar(valor: object) -> str:
    texto = unicodedata.normalize("NFKD", str(valor or ""))
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", texto).strip().upper()


def _filtrar_laboratorio(df: pd.DataFrame, cfg: Dict) -> pd.Series:
    """Selecciona todas las filas del laboratorio, incluidos sus alias."""
    if "Laboratorio" not in df.columns:
        return pd.Series(True, index=df.index, dtype=bool)
    nombres = [cfg.get("laboratorio", ""), *cfg.get("alias_laboratorio", [])]
    nombres = [_normalizar(nombre) for nombre in nombres if _normalizar(nombre)]
    if not nombres:
        return pd.Series(True, index=df.index, dtype=bool)
    laboratorios = df["Laboratorio"].map(_normalizar)
    return laboratorios.map(
        lambda valor: any(nombre in valor or valor in nombre for nombre in nombres)
    )


def calcular_avance(df: pd.DataFrame, nombre_concurso: str) -> pd.DataFrame:
    concursos = cargar_concursos()
    if nombre_concurso not in concursos:
        raise ErrorConcurso(f"No existe el concurso configurado: {nombre_concurso}")
    if "Descripción Producto" not in df.columns:
        raise ErrorConcurso("Los datos no contienen 'Descripción Producto'.")
    cfg = concursos[nombre_concurso]
    productos = df["Descripción Producto"].map(_normalizar)
    filtro_laboratorio = _filtrar_laboratorio(df, cfg)
    filas = []
    for producto in cfg.get("productos", []):
        patrones = [_normalizar(p) for p in producto.get("patrones", [])]
        mascara = filtro_laboratorio & productos.map(lambda x: any(p in x for p in patrones))
        unidades = float(calcular_unidades_vendidas(df.loc[mascara]).sum())
        unidades_caja = float(producto.get("unidades_por_caja", 1) or 1)
        cajas = unidades / unidades_caja
        meta = float(producto.get("cuota_cajas", 0) or 0)
        avance17 = float(producto.get("avance_cajas_dia17", 0) or 0)
        filas.append({
            "Producto": producto.get("nombre", ""),
            "Meta (cajas)": meta,
            "Unidades por caja": unidades_caja,
            "Vendido (unidades)": unidades,
            "Vendido (cajas)": cajas,
            "Faltante (cajas)": max(meta - cajas, 0),
            "Cumplimiento": (cajas / meta) if meta else 0,
            "Avance día 17": avance17,
            "Variación desde día 17": cajas - avance17,
        })
    return pd.DataFrame(filas)


def resumen_concurso(df: pd.DataFrame, nombre_concurso: str) -> Dict[str, float]:
    detalle = calcular_avance(df, nombre_concurso)
    cfg = cargar_concursos()[nombre_concurso]
    meta = float(cfg.get("meta_soles", 0) or 0)
    filtro_laboratorio = _filtrar_laboratorio(df, cfg)
    if "TotalP" in df.columns:
        avance_soles = float(
            pd.to_numeric(df.loc[filtro_laboratorio, "TotalP"], errors="coerce")
            .fillna(0)
            .sum()
        )
    else:
        avance_soles = 0.0
    resultado = {
        "meta_soles": meta,
        "avance_soles_dia17": float(cfg.get("avance_soles_dia17", 0) or 0),
        # Incluye todos los productos del laboratorio, no solo los que tienen cuota.
        "avance_soles": avance_soles,
        "faltante_soles": max(meta - avance_soles, 0),
        "productos": float(len(detalle)),
        "cajas_meta": float(detalle["Meta (cajas)"].sum()) if not detalle.empty else 0,
        "cajas_vendidas": float(detalle["Vendido (cajas)"].sum()) if not detalle.empty else 0,
    }
    resultado["cumplimiento_productos"] = (
        resultado["cajas_vendidas"] / resultado["cajas_meta"]
        if resultado["cajas_meta"] else 0
    )
    resultado["cumplimiento_soles"] = avance_soles / meta if meta else 0
    resultado["variacion_soles_dia17"] = (
        avance_soles - resultado["avance_soles_dia17"]
    )
    return resultado
