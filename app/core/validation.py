"""Validacion avanzada y limpieza segura de datos comerciales."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

COLUMNA_PRODUCTO = "Descripción Producto"


@dataclass
class ResultadoValidacion:
    dataframe: pd.DataFrame
    errores: pd.DataFrame

    @property
    def total_errores(self) -> int:
        return len(self.errores)


def validar_y_limpiar(df: pd.DataFrame) -> ResultadoValidacion:
    """Normaliza textos/numeros y registra problemas sin ocultarlos."""
    limpio = df.copy()
    hallazgos: list[dict] = []

    for columna in ("Botica", "Laboratorio", COLUMNA_PRODUCTO):
        if columna in limpio.columns:
            limpio[columna] = limpio[columna].fillna("").astype(str).str.strip()

    for idx in limpio.index[limpio["Botica"].eq("")]:
        hallazgos.append(_error(limpio, idx, "Botica vacía", "Botica", ""))
    for idx in limpio.index[limpio["Laboratorio"].eq("")]:
        hallazgos.append(_error(limpio, idx, "Laboratorio sin nombre", "Laboratorio", ""))

    for columna in ("CantE", "CantF", "TotalP"):
        original = limpio[columna]
        normalizado = original.astype(str).str.replace("S/", "", regex=False)
        normalizado = normalizado.str.replace(",", "", regex=False).str.strip()
        numerico = pd.to_numeric(normalizado, errors="coerce")
        for idx in limpio.index[numerico.isna() & original.notna()]:
            hallazgos.append(_error(limpio, idx, "Valor numérico inválido", columna, original.loc[idx]))
        for idx in limpio.index[numerico.fillna(0).lt(0)]:
            hallazgos.append(_error(limpio, idx, "Cantidad o monto negativo", columna, original.loc[idx]))
        limpio[columna] = numerico.fillna(0)

    duplicados = limpio.duplicated(keep=False)
    for idx in limpio.index[duplicados]:
        hallazgos.append(_error(limpio, idx, "Fila duplicada", "Fila completa", "Duplicada"))

    if COLUMNA_PRODUCTO in limpio.columns:
        for idx in limpio.index[limpio[COLUMNA_PRODUCTO].eq("")]:
            hallazgos.append(_error(limpio, idx, "Producto sin descripción", COLUMNA_PRODUCTO, ""))

    from . import lab_config
    for laboratorio in limpio["Laboratorio"].dropna().unique():
        if laboratorio and not lab_config.esta_configurado(laboratorio):
            idx = limpio.index[limpio["Laboratorio"].eq(laboratorio)][0]
            hallazgos.append(_error(
                limpio, idx, "Laboratorio no configurado", "Laboratorio", laboratorio
            ))

    errores = pd.DataFrame(
        hallazgos,
        columns=["Fila origen", "Tipo de error", "Columna", "Valor", "Botica", "Laboratorio"],
    )
    return ResultadoValidacion(limpio, errores)


def _error(df: pd.DataFrame, idx, tipo: str, columna: str, valor) -> dict:
    return {
        "Fila origen": int(idx) + 2 if isinstance(idx, int) else str(idx),
        "Tipo de error": tipo,
        "Columna": columna,
        "Valor": str(valor),
        "Botica": str(df.at[idx, "Botica"]) if "Botica" in df.columns else "",
        "Laboratorio": str(df.at[idx, "Laboratorio"]) if "Laboratorio" in df.columns else "",
    }
