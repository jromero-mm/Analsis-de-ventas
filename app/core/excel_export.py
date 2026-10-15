"""Exportacion a Excel con formato profesional (soles, bordes, cabeceras,
fila TOTAL y columnas TOTAL destacadas, freeze panes y disposicion de
impresion). Solo presentacion: la logica de calculo esta en processing.py
(generar_matriz / generar_matriz_productos).

Diferencias respecto de OTROS_LABORATORIOS.py:
- Usa pd.ExcelWriter(engine='openpyxl') en un UNICO paso: no reabrir el
  archivo y volver a guardar (evita doble escritura y posibles archivos
  a medias si el estilizado falla).
- Formato SOLES y ENTERO, bordes sutiles, alineacion derecha en datos.
- Encabezados multinivel en negrita y centrados; fila y columnas TOTAL
  destacadas; freeze panes en cabeera + columna de Botica; impresion
  horizontal con cabeeras repetidas.
- Detecta archivo abierto (PermissionError) y lanza un error claro.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import pandas as pd
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

FORMATO_SOLES = '"S/" #,##0.00'
FORMATO_ENTERO = "#,##0"

#: Color de borde sutil para todos los datos.
THIN_BORDER = Border(
    left=Side(style="thin", color="D3D3D3"),
    right=Side(style="thin", color="D3D3D3"),
    top=Side(style="thin", color="D3D3D3"),
    bottom=Side(style="thin", color="D3D3D3"),
)
#: Borde algo mas marcado para la fila TOTAL.
TOTAL_BORDER = Border(
    left=Side(style="thin", color="9AA0A6"),
    right=Side(style="thin", color="9AA0A6"),
    top=Side(style="medium", color="4A4A4A"),
    bottom=Side(style="medium", color="4A4A4A"),
)

# Rellenos suaves para diferenciar bloques.
_FILL_CABECERA = PatternFill("solid", fgColor="305496")   # azul fuerte
_FILL_CABECERA_LAB = PatternFill("solid", fgColor="8EA9DB")  # azul claro
_FILL_CABECERA_TOTAL = PatternFill("solid", fgColor="C9D3DD")  # gris claro
_FILL_FILA_TOTAL = PatternFill("solid", fgColor="FCE4D6")  # crema
_FILL_COL_TOTALP_HDR = PatternFill("solid", fgColor="FFE699")  # amarillo claro

_FONT_CABECERA = Font(bold=True, color="1F3864")
_FONT_CABECERA_TOTAL = Font(bold=True, color="1F3864")
_FONT_FILA_TOTAL = Font(name="Arial", size=14, bold=True, color="1F3864")
_ALIGN_CABECERA = Alignment(
    horizontal="center", vertical="center", wrap_text=True
)
_ALIGN_DATO_NUM = Alignment(horizontal="center", vertical="center")
_ALIGN_DATO_TXT = Alignment(horizontal="left", vertical="center", wrap_text=True)
_FONT_NUMERO_DIARIO = Font(name="Arial", size=14, bold=False, color="000000")
_FONT_CERO = Font(name="Arial", size=14, bold=False, color="FF0000")
_WIDTH_MIN = 12
_WIDTH_MAX = 42
_WIDTH_PROD_MAX = 40


class ErrorExportacion(Exception):
    """Error de exportacion a Excel."""


class ArchivoAbierto(ErrorExportacion):
    """El archivo destino esta bloqueado por otra aplicacion."""


def validar_destino(ruta: str | Path) -> None:
    """Comprueba que se puede escribir en ruta; si no, lanza ArchivoAbierto."""
    ruta = Path(ruta)
    if not ruta.exists():
        return
    try:
        with open(ruta, "a"):
            pass
    except PermissionError as exc:
        raise ArchivoAbierto(
            f"No se puede escribir en '{ruta.name}'. "
            "Cierra el archivo en Excel u otra aplicacion e inténtalo de nuevo."
        ) from exc


def _eliminar_fila_nombre_indice(ws, n_headers: int) -> None:
    """Elimina la fila residual del nombre del indice que pandas anade justo
    debajo de las cabeceras (todas sus celdas de datos vacias; la col 1
    guarda 'Botica'/'Laboratorio'). Deja los datos pegados a las cabeceras.
    """
    r = n_headers + 1
    if r > ws.max_row:
        return
    todas_vacias = all(
        ws.cell(row=r, column=c).value is None
        for c in range(2, ws.max_column + 1)
    )
    if todas_vacias:
        ws.delete_rows(r)


def _es_columna_total(ws, col_idx: int) -> bool:
    """True si la columna pertenece al bloque TOTAL (fila 1 == 'TOTAL')."""
    return _valor_cabecera(ws, 1, col_idx) == "TOTAL"


def _es_totalp(ws, col_idx: int) -> bool:
    """True si la columna es la metrica TotalP (fila 2 == 'TotalP')."""
    return _valor_cabecera(ws, 2, col_idx) == "TotalP"


def _valor_cabecera(ws, row_idx: int, col_idx: int):
    """Obtiene el encabezado aunque la celda pertenezca a un rango fusionado.

    En matrices por producto, pandas fusiona CantE/CantF/TotalP sobre varias
    columnas. Solo la primera celda conserva el texto; las demas son vacias.
    """
    valor = ws.cell(row=row_idx, column=col_idx).value
    if valor is not None:
        return valor
    for rango in ws.merged_cells.ranges:
        if (
            rango.min_row <= row_idx <= rango.max_row
            and rango.min_col <= col_idx <= rango.max_col
        ):
            return ws.cell(row=rango.min_row, column=rango.min_col).value
    return None


def _aplicar_cabeceras(ws, n_headers: int) -> None:
    """Estilo de las filas de encabezado (1..n_headers).

    - Negrita, centrado y wrap_text.
    - Relleno: azul para lab normal, gris/amarillo para TOTAL y TotalP.
    - Merge vertical de la columna A (Botica) para una cabecera unificada.
    """
    # Cabecera de la columna de indice (Botica): fusion vertical A1:A_n.
    etiqueta = "Botica"
    if n_headers >= 1:
        # Limpia y fija el valor en la celda superior; fusiona verticalmente.
        ws.cell(row=1, column=1, value=etiqueta)
        rng = f"A1:A{n_headers}"
        if rng not in {str(m) for m in ws.merged_cells.ranges}:
            ws.merge_cells(rng)
        c = ws.cell(row=1, column=1)
        c.font = _FONT_CABECERA
        c.alignment = _ALIGN_CABECERA
        c.fill = _FILL_CABECERA

    for r in range(1, n_headers + 1):
        for col_idx in range(2, ws.max_column + 1):
            cell = ws.cell(row=r, column=col_idx)
            cell.font = _FONT_CABECERA
            cell.alignment = _ALIGN_CABECERA
            if _es_columna_total(ws, col_idx):
                cell.fill = _FILL_CABECERA_TOTAL
            else:
                cell.fill = _FILL_CABECERA_LAB
            cell.border = THIN_BORDER


def _aplicar_filas_datos(ws, n_headers: int) -> None:
    """Bordes, formatos numericos y alineacion de filas de datos
    (excluyendo la ultima fila TOTAL)."""
    ultima = ws.max_row
    for row_idx in range(n_headers + 1, ultima):  # sin la fila TOTAL final
        es_fila_total = ws.cell(row=row_idx, column=1).value == "TOTAL"
        for col_idx in range(1, ws.max_column + 1):
            cell = ws.cell(row=row_idx, column=col_idx)
            cell.border = THIN_BORDER
            if col_idx == 1:
                cell.alignment = _ALIGN_DATO_TXT
                if es_fila_total:
                    cell.font = _FONT_FILA_TOTAL
                    cell.fill = _FILL_FILA_TOTAL
                continue
            header_metric = _valor_cabecera(ws, 2, col_idx)
            if header_metric == "TotalP":
                cell.number_format = FORMATO_SOLES
                cell.alignment = _ALIGN_DATO_NUM
                cell.font = _FONT_NUMERO_DIARIO
            elif header_metric in ("CantE", "CantF"):
                cell.number_format = FORMATO_ENTERO
                cell.alignment = _ALIGN_DATO_NUM
                cell.font = _FONT_NUMERO_DIARIO
            else:
                cell.alignment = _ALIGN_DATO_TXT
            if es_fila_total:
                cell.font = _FONT_FILA_TOTAL
                cell.fill = _FILL_FILA_TOTAL
                cell.border = TOTAL_BORDER
            elif header_metric in ("CantE", "CantF", "TotalP"):
                try:
                    if float(cell.value or 0) == 0:
                        cell.font = _FONT_CERO
                except (TypeError, ValueError):
                    pass


def _resaltar_total_inferior(ws, n_headers: int) -> None:
    """Ultima fila (TOTAL) con bordes medio arriba/abajo y color destacado."""
    ultima = ws.max_row
    if ws.cell(row=ultima, column=1).value != "TOTAL":
        return  # nothing to do
    for col_idx in range(1, ws.max_column + 1):
        cell = ws.cell(row=ultima, column=col_idx)
        cell.font = _FONT_FILA_TOTAL
        cell.fill = _FILL_FILA_TOTAL
        cell.border = TOTAL_BORDER
        if col_idx == 1:
            cell.alignment = _ALIGN_DATO_TXT
            continue
        header_metric = _valor_cabecera(ws, 2, col_idx)
        if header_metric == "TotalP":
            cell.number_format = FORMATO_SOLES
            cell.alignment = _ALIGN_DATO_NUM
        elif header_metric in ("CantE", "CantF"):
            cell.number_format = FORMATO_ENTERO
            cell.alignment = _ALIGN_DATO_NUM
        else:
            cell.alignment = _ALIGN_DATO_TXT


def _calcular_anchos(ws, n_headers: int) -> None:
    """Anchos razonables con techo; datos + cabecera, evitando excesos."""
    for col_idx in range(1, ws.max_column + 1):
        col_letter = get_column_letter(col_idx)
        max_len = 0
        for row_idx in range(1, ws.max_row + 1):
            val = ws.cell(row=row_idx, column=col_idx).value
            if val is None:
                continue
            txt_len = len(str(val))
            # metricas/TotalP margen por el prefijo S/
            if row_idx <= n_headers and isinstance(val, str) and val == "TotalP":
                txt_len += 4
            if txt_len > max_len:
                max_len = txt_len
        if col_idx == 1:
            # Botica: nombres de almacen largos
            width = min(max(max_len + 2, _WIDTH_MIN), _WIDTH_MAX)
        elif n_headers >= 3 and ws.cell(row=3, column=col_idx).value is not None:
            # Columna de producto
            width = min(max(max_len + 2, _WIDTH_MIN), _WIDTH_PROD_MAX)
        else:
            width = min(max(max_len + 4, _WIDTH_MIN), _WIDTH_MAX)
        ws.column_dimensions[col_letter].width = width


def _altura_cabeceras(ws, n_headers: int) -> None:
    """Altura de filas de cabecera suficiente para nombres largos con wrap."""
    for r in range(1, n_headers + 1):
        # Estimacion: el largo maximo de la fila / ancho de columna ~ lineas.
        max_largo = 0
        for col_idx in range(1, ws.max_column + 1):
            v = ws.cell(row=r, column=col_idx).value
            if v is None:
                continue
            max_largo = max(max_largo, len(str(v)))
        # ~15 pts por linea, asumiendo ~40 chars por linea con wrap.
        lineas = max(1, (max_largo // 40) + (1 if max_largo % 40 else 0))
        altura = max(18, min(lineas * 15, 60))
        if n_headers >= 3 and r == n_headers:
            # Los nombres de producto suelen ocupar dos lineas incluso cuando
            # su longitud es menor de 40 caracteres (por espacios y palabras
            # largas). Una altura minima fija evita que Excel los recorte al
            # mostrar muchos productos en pantalla o al imprimir.
            altura = max(42, altura)
        ws.row_dimensions[r].height = altura


def _configurar_freeze_impresion(ws, n_headers: int) -> None:
    """Freeze panes (cabeceras + columna Botica) y disposicion de impresion."""
    primera_fila_datos = n_headers + 1
    # Congela filas de cabecera y la columna A (Botica): celda (B, datos).
    ws.freeze_panes = ws.cell(row=primera_fila_datos, column=2)

    # Impresion: horizontal, ajustar ancho a una pagina, repetir cabeceras.
    ws.page_setup.orientation = ws.ORIENTATION_LANDSCAPE
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.print_title_rows = f"1:{n_headers}"
    from openpyxl.worksheet.page import PageMargins
    ws.page_margins = PageMargins(left=0.3, right=0.3, top=0.5, bottom=0.5,
                                   header=0.2, footer=0.2)


def _estilizar_hoja(ws, n_headers: int = 2) -> None:
    """Estiliza la hoja Matriz (cabeceras, datos, TOTAL, freeze y impresion).

    n_headers es el numero de filas de encabezado:
    - 2 -> Matriz de metricas (Laboratorio / Metrica).
    - 3 -> Matriz por producto (Laboratorio / Metrica / Producto).
    La fila 2 siempre contiene la metrica (CantE/CantF/TotalP); los datos
    empiezan en la fila n_headers + 1.

    En modo producto (3 niveles) pandas anade una fila extra con el nombre
    del indice ('Botica'); se elimina para dejar exactamente las 3 filas de
    encabezado (Laboratorio / Metrica / Producto).
    """
    if n_headers >= 3:
        # Equivale a la eliminacion robusta de la fila del nombre del indice.
        pass
    _eliminar_fila_nombre_indice(ws, n_headers)

    _aplicar_cabeceras(ws, n_headers)
    _aplicar_filas_datos(ws, n_headers)
    _resaltar_total_inferior(ws, n_headers)
    _calcular_anchos(ws, n_headers)
    _altura_cabeceras(ws, n_headers)
    _configurar_freeze_impresion(ws, n_headers)


def _estilizar_detalle(ws) -> None:
    """Estilizado simple para la hoja Detalle_Productos.
    Encabezados en negrita, bordes en filas de datos, formatos numericos
    en CantE/CantF (entero) y TotalP (soles), ancho automatico.
    """
    from openpyxl.styles import Font

    # Cabecera (fila 1)
    header_font = Font(bold=True)
    for col_idx in range(1, ws.max_column + 1):
        ws.cell(row=1, column=col_idx).font = header_font
        ws.cell(row=1, column=col_idx).border = THIN_BORDER

    for col_idx in range(1, ws.max_column + 1):
        header_val = ws.cell(row=1, column=col_idx).value

        if header_val in ("CantE", "CantF"):
            for row_idx in range(2, ws.max_row + 1):
                cell = ws.cell(row=row_idx, column=col_idx)
                cell.number_format = FORMATO_ENTERO
                cell.border = THIN_BORDER
                cell.alignment = Alignment(horizontal="right", vertical="center")
        elif header_val == "TotalP":
            for row_idx in range(2, ws.max_row + 1):
                cell = ws.cell(row=row_idx, column=col_idx)
                cell.number_format = FORMATO_SOLES
                cell.border = THIN_BORDER
                cell.alignment = Alignment(horizontal="right", vertical="center")
        else:
            for row_idx in range(2, ws.max_row + 1):
                cell = ws.cell(row=row_idx, column=col_idx)
                cell.border = THIN_BORDER

    for col_idx in range(1, ws.max_column + 1):
        col_letter = get_column_letter(col_idx)
        max_len = 0
        for row_idx in range(1, ws.max_row + 1):
            val = ws.cell(row=row_idx, column=col_idx).value
            if val is None:
                continue
            txt_len = len(str(val))
            if row_idx == 1 and val == "TotalP":
                txt_len += 6
            if txt_len > max_len:
                max_len = txt_len
        ws.column_dimensions[col_letter].width = max(max_len + 4, 15)


def exportar(
    tabla: pd.DataFrame,
    ruta: str | Path = "Matriz_Ventas_Soles.xlsx",
    Nombre_columna_index: Optional[str] = None,
    detalle_productos: Optional[pd.DataFrame] = None,
    errores_detectados: Optional[pd.DataFrame] = None,
    incluir_resumen: bool = True,
    incluir_detalle: bool = True,
    avance_concurso: Optional[pd.DataFrame] = None,
    nombre_concurso: Optional[str] = None,
) -> str:
    """Exporta tabla (MultiIndex de columnas) a Excel con formato S/.

    Si se pasa detalle_productos (DataFrame plano con columnas
    Botica/Laboratorio/Descripción Producto/metricas), se anade una segunda
    hoja 'Detalle_Productos' tras la hoja principal.

    Devuelve la ruta absoluta del archivo escrito.
    """
    ruta = Path(ruta).resolve()
    validar_destino(ruta)

    try:
        with pd.ExcelWriter(ruta, engine="openpyxl") as writer:
            # En el informe visual no repetimos el bloque TOTAL de columnas.
            # La fila TOTAL inferior se conserva como resumen por laboratorio.
            tabla_export = tabla
            if isinstance(tabla.columns, pd.MultiIndex):
                columnas_visibles = [c for c in tabla.columns if str(c[0]) != "TOTAL"]
                if columnas_visibles:
                    tabla_export = tabla.loc[:, columnas_visibles]

            tabla_export.to_excel(writer, index=True, sheet_name="Matriz")
            # La matriz sigue siendo la hoja activa/primera por compatibilidad.
            # El resumen ejecutivo queda disponible para presentacion rapida.
            if incluir_resumen:
                resumen = _crear_resumen(tabla)
                resumen.to_excel(writer, index=False, sheet_name="Resumen Ejecutivo")
                _estilizar_resumen(writer.sheets["Resumen Ejecutivo"])
            ws = writer.sheets["Matriz" if "Matriz" in writer.sheets else list(writer.sheets)[0]]
            _estilizar_hoja(ws, n_headers=tabla_export.columns.nlevels)

            if incluir_detalle and detalle_productos is not None and not detalle_productos.empty:
                detalle_productos.to_excel(
                    writer, index=False, sheet_name="Detalle_Productos"
                )
                ws_det = writer.sheets["Detalle_Productos"]
                _estilizar_detalle(ws_det)

            if errores_detectados is not None and not errores_detectados.empty:
                errores_detectados.to_excel(
                    writer, index=False, sheet_name="Errores_Detectados"
                )
                _estilizar_detalle(writer.sheets["Errores_Detectados"])

            if avance_concurso is not None and not avance_concurso.empty:
                avance_concurso.to_excel(writer, index=False, sheet_name="Avance_Concurso")
                ws_avance = writer.sheets["Avance_Concurso"]
                _estilizar_detalle(ws_avance)
                if nombre_concurso:
                    ws_avance.insert_rows(1)
                    ws_avance.cell(row=1, column=1, value=f"Concurso: {nombre_concurso}")
                    ws_avance.cell(row=1, column=1).font = Font(bold=True, size=14, color="1F3864")
        # writer cierra y guarda automaticamente al salir del with.
    except PermissionError as exc:
        raise ArchivoAbierto(
            f"No se pudo guardar '{ruta.name}'. "
            "Cierra el archivo en Excel e inténtalo de nuevo."
        ) from exc
    except Exception as exc:
        raise ErrorExportacion(f"Error al exportar a Excel: {exc}") from exc

    return str(ruta)


def _crear_resumen(tabla: pd.DataFrame) -> pd.DataFrame:
    """Resume ventas por laboratorio a partir de la fila TOTAL."""
    fila = tabla.loc["TOTAL"] if "TOTAL" in tabla.index else tabla.sum(numeric_only=True)
    filas = []
    labs = [x for x in tabla.columns.get_level_values(0).unique() if x != "TOTAL"]
    for lab in labs:
        def valor(m):
            try:
                return float(fila[(lab, m)])
            except (KeyError, TypeError):
                return 0.0
        soles = valor("TotalP")
        filas.append({"Laboratorio": lab, "Enteros": valor("CantE"),
                      "Fracciones": valor("CantF"), "Ventas (S/.)": soles})
    out = pd.DataFrame(filas)
    if not out.empty:
        out["% del total"] = (out["Ventas (S/.)"] / out["Ventas (S/.)"].sum() * 100).round(2)
        out = out.sort_values("Ventas (S/.)", ascending=False)
    return out


def _estilizar_resumen(ws) -> None:
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    for cell in ws[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = _FILL_CABECERA
        cell.alignment = _ALIGN_CABECERA
    for row in ws.iter_rows(min_row=2):
        for cell in row:
            cell.border = THIN_BORDER
            if cell.column in (4,):
                cell.number_format = FORMATO_SOLES
            elif cell.column == 5:
                cell.number_format = "0.00%"
    for col in range(1, ws.max_column + 1):
        ws.column_dimensions[get_column_letter(col)].width = 22
