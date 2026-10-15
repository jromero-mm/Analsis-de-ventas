"""Lectura y validacion de datos de entrada (portapapeles o archivo).

Esta capa aísla pandas del resto de la app para facilitar tests y para
permitir en el futuro leer de Excel/CSV sin cambiar el resto del codigo.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import csv
from pathlib import Path
from typing import Dict, List

import pandas as pd

COLUMNAS_OBLIGATORIAS = ("Botica", "Laboratorio", "CantE", "CantF", "TotalP")
COLUMNA_PRODUCTO = "Descripción Producto"
COLUMNA_PRESENTACION = "Presentación"


@dataclass
class ResultadoLectura:
    dataframe: pd.DataFrame
    laboratorios: List[str]
    n_boticas: int
    n_filas: int
    productos_por_lab: Dict[str, List[str]] = field(default_factory=dict)
    tiene_columna_producto: bool = False
    errores_detectados: pd.DataFrame = field(default_factory=pd.DataFrame)


class ErrorLectura(Exception):
    """Error base de lectura de datos."""


class PortapapelesVacio(ErrorLectura):
    """No se encontro una tabla en el portapapeles."""


class PortapapelesInvalido(ErrorLectura):
    """El portapapeles no se pudo parsear como tabla."""


class ColumnasFaltantes(ErrorLectura):
    """Faltan columnas obligatorias."""

    def __init__(self, faltan: List[str]):
        super().__init__(f"Faltan columnas obligatorias: {', '.join(faltan)}")
        self.faltan = faltan


def validar_columnas(df: pd.DataFrame) -> None:
    faltan = [c for c in COLUMNAS_OBLIGATORIAS if c not in df.columns]
    if faltan:
        raise ColumnasFaltantes(faltan)


def detectar_laboratorios(df: pd.DataFrame) -> List[str]:
    """Lista de laboratorios presente (sin NaN, sin TOTAL), ordenada alfabeticamente."""
    if "Laboratorio" not in df.columns:
        return []
    serie = df["Laboratorio"].dropna().astype(str)
    serie = serie[serie.str.upper() != "TOTAL"]
    unicos = sorted(serie.unique().tolist())
    return unicos


def detectar_boticas(df: pd.DataFrame) -> List[str]:
    if "Botica" not in df.columns:
        return []
    serie = df["Botica"].dropna().astype(str)
    serie = serie[serie.str.upper() != "TOTAL"]
    return sorted(serie.unique().tolist())


def detectar_productos(df: pd.DataFrame, laboratorio: str) -> List[str]:
    """Lista ordenada de productos (Descripcion Producto) para un laboratorio.

    - Ignora NaN y cadenas vacias.
    - Mantiene los nombres tal como aparecen (sin normalizar).
    - Evita duplicados.
    - Si no existe la columna 'Descripción Producto', devuelve lista vacia.
    """
    if COLUMNA_PRODUCTO not in df.columns:
        return []
    if "Laboratorio" not in df.columns:
        return []
    sub = df[df["Laboratorio"].astype(str) == laboratorio]
    serie = sub[COLUMNA_PRODUCTO].dropna().astype(str)
    serie = serie[serie.str.strip() != ""]
    # Orden natural por defecto (alphabetic, case-insensitive para estabilidad)
    unicos = sorted(serie.unique().tolist(), key=lambda s: (s.casefold(), s))
    return unicos


def detectar_productos_por_lab(df: pd.DataFrame) -> Dict[str, List[str]]:
    """Mapa {laboratorio: [productos]} para todos los laboratorios detectados.

    Si no existe la columna de producto, devuelve {}.
    """
    if COLUMNA_PRODUCTO not in df.columns:
        return {}
    resultado: Dict[str, List[str]] = {}
    for lab in detectar_laboratorios(df):
        resultado[lab] = detectar_productos(df, lab)
    return resultado


def tiene_columna_producto(df: pd.DataFrame) -> bool:
    return COLUMNA_PRODUCTO in df.columns


def calcular_unidades_vendidas(df: pd.DataFrame) -> pd.Series:
    """Convierte enteros y fracciones a unidades comerciales comparables.

    En los datos de ventas, ``CantE`` representa envases/cajas completas y
    ``CantF`` las unidades sueltas. Por eso una caja de 100 tabletas equivale
    a ``1 * 100 + 0`` y un jarabe de presentación 1 a ``1 * 1 + 0``.

    Para conservar compatibilidad con archivos antiguos que no traen la
    columna Presentación, se devuelve CantF sin alterar.
    """
    cantf = pd.to_numeric(df["CantF"], errors="coerce").fillna(0)
    if COLUMNA_PRESENTACION not in df.columns:
        return cantf
    cante = pd.to_numeric(df["CantE"], errors="coerce").fillna(0)
    presentacion = pd.to_numeric(
        df[COLUMNA_PRESENTACION], errors="coerce"
    ).fillna(1)
    presentacion = presentacion.where(presentacion.gt(0), 1)
    return cante * presentacion + cantf


def _construir_resultado(df: pd.DataFrame) -> ResultadoLectura:
    from .validation import validar_y_limpiar

    validar_columnas(df)
    validacion = validar_y_limpiar(df)
    limpio = validacion.dataframe
    return ResultadoLectura(
        dataframe=limpio,
        laboratorios=detectar_laboratorios(limpio),
        n_boticas=len(detectar_boticas(limpio)),
        n_filas=len(limpio),
        productos_por_lab=detectar_productos_por_lab(limpio),
        tiene_columna_producto=tiene_columna_producto(limpio),
        errores_detectados=validacion.errores,
    )


def read_clipboard() -> ResultadoLectura:
    """Lee datos del portapapeles; valida y devuelve un ResultadoLectura."""
    try:
        df = pd.read_clipboard()
    except Exception as exc:
        msg = str(exc).lower()
        if "empty" in msg or "no" in msg or "could not" in msg:
            raise PortapapelesVacio(
                "No se encontro una tabla en el portapapeles. Copia las ventas desde la app de trabajo e inténtalo de nuevo."
            ) from exc
        raise PortapapelesInvalido(
            f"No se pudo parsear el portapapeles como tabla: {exc}"
        ) from exc

    if df is None or df.empty or len(df.columns) == 0:
        raise PortapapelesVacio(
            "El portapapeles esta vacio o no contiene una tabla. Copia las ventas e inténtalo de nuevo."
        )

    return _construir_resultado(df)


def _validar_tabla_archivo(df: pd.DataFrame) -> ResultadoLectura:
    if df.empty:
        raise ErrorLectura("El archivo o la hoja seleccionada no contiene registros de ventas.")
    df.columns = [str(col).strip() for col in df.columns]
    if df.columns.duplicated().any():
        raise ErrorLectura("Hay encabezados repetidos. Cada columna debe tener un nombre único.")
    return _construir_resultado(df)


def read_csv(ruta: str, decimal: str = ".") -> ResultadoLectura:
    """Lee CSV UTF-8/Windows, detectando coma, punto y coma o tabulador.

    El separador decimal se elige explícitamente para no adivinar importes.
    Se conservan los códigos de botica con ceros iniciales.
    """
    if decimal not in (".", ","):
        raise ErrorLectura("El separador decimal debe ser punto o coma.")
    try:
        for encoding in ("utf-8-sig", "cp1252"):
            try:
                with open(ruta, encoding=encoding, newline="") as archivo:
                    cabecera = archivo.readline()
                    if not cabecera.strip():
                        raise ErrorLectura("El CSV está vacío o no tiene encabezados en la primera fila.")
                    separador = csv.Sniffer().sniff(cabecera, delimiters=",;\t").delimiter
                    archivo.seek(0)
                    df = pd.read_csv(archivo, sep=separador, dtype=str, keep_default_na=False)
                break
            except UnicodeDecodeError:
                if encoding == "cp1252":
                    raise
    except pd.errors.EmptyDataError as exc:
        raise ErrorLectura("El CSV no contiene datos.") from exc
    except (OSError, UnicodeError, csv.Error, pd.errors.ParserError) as exc:
        raise ErrorLectura(
            f"No se pudo leer '{Path(ruta).name}'. Verifica que sea un CSV con "
            f"encabezados y columnas separadas por coma, punto y coma o tabulador.\n{exc}"
        ) from exc
    df.columns = [str(col).strip() for col in df.columns]
    if decimal == ",":
        for columna in (*COLUMNAS_OBLIGATORIAS[2:], COLUMNA_PRESENTACION):
            if columna in df.columns:
                df[columna] = (df[columna].str.replace(".", "", regex=False)
                               .str.replace(",", ".", regex=False))
    return _validar_tabla_archivo(df)


def listar_hojas_excel(ruta: str) -> List[str]:
    try:
        with pd.ExcelFile(ruta, engine="openpyxl") as libro:
            return list(libro.sheet_names)
    except Exception as exc:
        raise ErrorLectura(
            f"No se pudo abrir '{Path(ruta).name}'. Utiliza un archivo .xlsx o .xlsm "
            f"válido y sin contraseña.\n{exc}"
        ) from exc


def read_excel(ruta: str, hoja: str | int = 0) -> ResultadoLectura:
    try:
        df = pd.read_excel(ruta, sheet_name=hoja, engine="openpyxl",
                           dtype={"Botica": str}, keep_default_na=False)
    except Exception as exc:
        raise ErrorLectura(
            f"No se pudo leer la hoja de '{Path(ruta).name}'. "
            f"Verifica que el archivo sea accesible y la hoja exista.\n{exc}"
        ) from exc
    return _validar_tabla_archivo(df)
