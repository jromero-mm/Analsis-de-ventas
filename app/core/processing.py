"""Procesamiento de ventas: pivot, filtrado por laboratorios y aplicacion de reglas.

Conserva el comportamiento del script OTROS_LABORATORIOS.py para
LABORATORIO ALFA, LABORATORIO BETA, LABORATORIO GAMMA y LABORATORIO DELTA y corrige:
- laboratorios que desaparecian por diferencias de nombre (usando resolver()),
- TOTAL ahora conservan TotalP (regla_total='todas'),
- validacion explicita de columnas.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence

import pandas as pd

from . import lab_config
from .data_source import COLUMNA_PRODUCTO


METRICAS = ("CantE", "CantF", "TotalP")
TOTAL = "TOTAL"


class ErrorProcesamiento(Exception):
    """Error en el pipeline de matriz."""


def generar_pivot(df: pd.DataFrame) -> pd.DataFrame:
    """Pivote identico al del script original, con TOTAL en filas y columnas."""
    if df is None or df.empty:
        raise ErrorProcesamiento("DataFrame vacio: no hay datos para pivotar.")

    tabla = pd.pivot_table(
        df,
        index="Botica",
        columns="Laboratorio",
        values=list(METRICAS),
        aggfunc="sum",
        fill_value=0,
        margins=True,
        margins_name=TOTAL,
    )
    tabla = tabla.swaplevel(0, 1, axis=1)
    tabla = tabla.sort_index(axis=1, level=0)
    return tabla


def _regla_para_lab(lab_nombre: str) -> str:
    """Devuelve la regla aplicable: regla_total para TOTAL, o resolver() para el resto."""
    if lab_nombre == TOTAL:
        return lab_config.regla_total()
    _canonico, regla = lab_config.resolver(lab_nombre)
    return regla


def calcular_cols_a_eliminar(
    tabla: pd.DataFrame,
    metricas_por_lab: Optional[Dict[str, List[str]]] = None,
) -> List[tuple]:
    """Recorre las columnas (Laboratorio, Metrica) y construye la lista a descartar.

    Sustituye al bloque if/elif/else hardcoded del script original;
    ahora las reglas se definen en lab_config.REGLAS.

    Parametros
    ----------
    metricas_por_lab : opcional, {lab: [metricas_seleccionadas]}.
        - None  -> comportamiento V1: descarta segun la regla del laboratorio.
        - dict  -> ademas de descartar por regla, descarta las metricas que
                   NO esten en la lista seleccionada para ese lab.
                   Las metricas prohibidas por la regla SIGUEN descartadas
                   aunque el usuario las marque: la interseccion se hace
                   contra lab_config.metricas_a_conservar(regla).
                   TOTAL se rige por regla_total y NO se ve afectado por
                   metricas_por_lab (no se seleciona manualmente).
    """
    cols_eliminar: List[tuple] = []
    for col in tabla.columns:
        lab_nombre = str(col[0])
        metrica = col[1]
        if metrica not in METRICAS:
            continue
        regla = _regla_para_lab(lab_nombre)

        # 1) Prohibidas por la regla: siempre se descartan
        permitidas = (lab_config.metricas_configuradas(lab_nombre)
                      if lab_nombre != TOTAL else lab_config.metricas_a_conservar(regla))
        if metrica not in permitidas:
            cols_eliminar.append(col)
            continue

        # 2) Si el usuario indico subconjunto para este lab, descartar las no seleccionadas.
        # TOTAL no se ve afectado por metricas_por_lab.
        if metricas_por_lab is not None and lab_nombre != TOTAL:
            permitidas_seleccion = metricas_por_lab.get(lab_nombre)
            if permitidas_seleccion is not None and metrica not in permitidas_seleccion:
                cols_eliminar.append(col)
    return cols_eliminar


def seleccion_por_defecto(labs_detectados: List[str]) -> List[str]:
    """Seleccion por defecto: todos los laboratorios detectados.

    En V1 la UI pedira al usuario que marque los deseados; si no se especifica,
    procesamos todos (los test de paridad usan este camino).
    """
    return list(labs_detectados)


def _canonizar_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Unifica cada nombre real de laboratorio con su nombre configurado."""
    salida = df.copy()
    salida["Laboratorio"] = salida["Laboratorio"].map(
        lambda nombre: lab_config.resolver(str(nombre))[0]
    )
    return salida


def _canonizar_mapa_laboratorios(
    mapa: Optional[Dict[str, List[str]]],
) -> Optional[Dict[str, List[str]]]:
    """Convierte las claves de selecciones de la UI a nombres canónicos."""
    if mapa is None:
        return None
    salida: Dict[str, List[str]] = {}
    for laboratorio, valores in mapa.items():
        canonico, _regla = lab_config.resolver(laboratorio)
        destino = salida.setdefault(canonico, [])
        for valor in valores:
            if valor not in destino:
                destino.append(valor)
    return salida


def _filtrar_por_producto(
    df: pd.DataFrame,
    productos_por_lab: Dict[str, List[str]],
) -> pd.DataFrame:
    """Filtra un DataFrame por (Laboratorio, Descripción Producto).

    Reglas:
    - Si un laboratorio NO esta como clave en el dict -> se conservan todas
      sus filas (igual que V1).
    - Si un laboratorio esta como clave con lista VACIA -> se conservan todas
      sus filas (no filtra).
    - Si un laboratorio esta como clave con lista NO vacia -> se conservan
      solo las filas cuyo 'Descripción Producto' este en la lista.

    La columna de producto se toma literal, sin normalizar (matches exactos).
    Esto es intencional: la UI ya entrega nombres normalizados desde
    data_source.detectar_productos.

    Devuelve una COPIA del DataFrame filtrado; nunca muta el original.
    """
    if COLUMNA_PRODUCTO not in df.columns:
        return df

    from .data_source import detectar_laboratorios

    labs_presentes = detectar_laboratorios(df)

    # Construimos una mascara OR por laboratorio
    mascara = pd.Series(False, index=df.index)

    for lab in labs_presentes:
        prod_sel = productos_por_lab.get(lab)
        # Lab no listado o lista vacia -> se queda todo
        if prod_sel is None or len(prod_sel) == 0:
            mascara |= (df["Laboratorio"].astype(str) == lab)
            continue
        # Lab con seleccion -> solo las filas cuyo producto este en la lista
        conjunto = set(prod_sel)
        es_lab = df["Laboratorio"].astype(str) == lab
        es_prod = df[COLUMNA_PRODUCTO].astype(str).isin(conjunto)
        mascara |= (es_lab & es_prod)

    return df[mascara].copy()


def _completar_boticas(
    tabla: pd.DataFrame,
    boticas_obligatorias: Optional[Sequence[str]],
) -> pd.DataFrame:
    """Agrega boticas sin ventas como filas en cero y conserva TOTAL al final."""
    if not boticas_obligatorias:
        return tabla

    nombre_indice = tabla.index.name
    tiene_total = TOTAL in tabla.index
    fila_total = tabla.loc[[TOTAL]].copy() if tiene_total else None
    datos = tabla.drop(index=TOTAL) if tiene_total else tabla.copy()

    orden: List[str] = []
    for botica in boticas_obligatorias:
        nombre = str(botica).strip()
        if nombre and nombre not in orden:
            orden.append(nombre)
    for botica in datos.index:
        nombre = str(botica).strip()
        if nombre and nombre not in orden:
            orden.append(nombre)

    datos = datos.reindex(orden, fill_value=0)
    if fila_total is not None:
        datos = pd.concat([datos, fila_total])
    datos.index.name = nombre_indice
    return datos


def generar_matriz(
    df: pd.DataFrame,
    labs_seleccionados: Sequence[str] | None = None,
    productos_por_lab: Optional[Dict[str, List[str]]] = None,
    metricas_por_lab: Optional[Dict[str, List[str]]] = None,
    boticas_obligatorias: Optional[Sequence[str]] = None,
) -> pd.DataFrame:
    """Pipeline completo: pivot -> filtrado por labs -> eliminar metricas por regla.

    Parametros
    ----------
    df : DataFrame crudo con columnas Botica, Laboratorio, CantE, CantF, TotalP.
    labs_seleccionados : nombre exacto de los laboratorios a conservar (None = todos).
    productos_por_lab : opcional, {nombre_laboratorio: [productos]}.
        - None  -> comportamiento EXACTAMENTE igual a V1 (no se filtra por producto).
        - dict  -> para cada laboratorio presente en el dict:
            * si la lista esta vacia    -> se usan todos los productos (no filtra).
            * si la lista tiene valores -> se conservan solo las filas cuyo
              'Descripción Producto' este en la lista.
          Los labs seleccionados que NO aparecen como clave en el dict
          se procesan con todos sus productos (igual que V1).
    metricas_por_lab : opcional, {nombre_laboratorio: [metricas_seleccionadas]}.
        - None  -> comportamiento V1/V2: la matriz conserva las metricas
                   permitidas por la regla del laboratorio.
        - dict  -> el usuario selecciona un SUBCONJUNTO de las metricas
                   permitidas. Las metricas prohibidas por la regla siguen
                   sin aparecer (no se puede 'forzar' una metrica prohibida).
                   TOTAL no se ve afectado por este parametro.

    Devuelve la tabla_matriz escalonada (Laboratorio, Metrica) con fila TOTAL
    y columna TOTAL.
    """
    from .data_source import detectar_laboratorios, validar_columnas

    validar_columnas(df)

    labs_detectados = detectar_laboratorios(df)
    if labs_seleccionados is None:
        labs_seleccionados = seleccion_por_defecto(labs_detectados)

    # Convertimos a canonico para tolerar nombres del portapapeles
    # cercanos a los del config (p.ej. "LABORATORIO ALFA SAC" -> "LABORATORIO ALFA").
    seleccion_canonica: List[str] = []
    for lab in labs_seleccionados:
        canonico, _regla = lab_config.resolver(lab)
        if canonico not in seleccion_canonica:
            seleccion_canonica.append(canonico)

    df_canonico = _canonizar_dataframe(df)
    productos_por_lab = _canonizar_mapa_laboratorios(productos_por_lab)
    metricas_por_lab = _canonizar_mapa_laboratorios(metricas_por_lab)

    # Filtramos el DataFrame crudo: solo filas con laboratorio seleccionado.
    # Las filas con Laboratorio NaN se descartan (serian ruido).
    df_filtrado = df_canonico[
        df_canonico["Laboratorio"].isin(seleccion_canonica)
    ].copy()

    # Filtrado opcional por producto (V2). Si productos_por_lab es None o
    # si el DF no contiene la columna de producto, no se aplica (compat V1).
    if productos_por_lab is not None and COLUMNA_PRODUCTO in df_filtrado.columns:
        df_filtrado = _filtrar_por_producto(df_filtrado, productos_por_lab)

    if df_filtrado.empty:
        raise ErrorProcesamiento(
            "Ningun laboratorio seleccionado esta presente en los datos."
        )

    tabla = generar_pivot(df_filtrado)

    cols_eliminar = calcular_cols_a_eliminar(tabla, metricas_por_lab)
    if cols_eliminar:
        tabla = tabla.drop(columns=cols_eliminar, errors="ignore")

    tabla = _completar_boticas(tabla, boticas_obligatorias)

    # Reorden laboratorios ( orden_preferido primero, despues alfabeticos ),
    # conservando TOTAL al final.
    orden = lab_config.orden_preferido()
    labs_presentes = tabla.columns.get_level_values(0).unique().tolist()

    orden_efectivo: List[str] = []
    for lab in orden:
        if lab in labs_presentes and lab != TOTAL:
            orden_efectivo.append(lab)
    for lab in labs_presentes:
        if lab not in orden_efectivo and lab != TOTAL:
            orden_efectivo.append(lab)
    orden_efectivo.append(TOTAL)

    tabla = tabla.reindex(columns=orden_efectivo, level=0)

    return tabla


def generar_matriz_productos(
    df: pd.DataFrame,
    labs_seleccionados: Sequence[str] | None = None,
    productos_por_lab: Optional[Dict[str, List[str]]] = None,
    metricas_por_lab: Optional[Dict[str, List[str]]] = None,
    boticas_obligatorias: Optional[Sequence[str]] = None,
) -> pd.DataFrame:
    """Matriz en modo productos (mezcla columnas por producto y por laboratorio).

    Reglas:
    - Para cada laboratorio seleccionado:
        * Si esta en productos_por_lab con lista NO vacia -> se usan SOLO los
          productos de esa lista. Normalmente se genera una columna por
          producto y metrica; si el perfil tiene agrupar_productos activado,
          se suman en una sola columna (Laboratorio, metrica).
          Subproducto del bug anterior: nunca se usan todos los productos
          del laboratorio como fallback.
        * Si NO esta en productos_por_lab (o lista vacia) -> se genera una
          columna (Laboratorio, metrica, '') a nivel del laboratorio, con la
          suma de todos sus productos.
    - La metrica de cada columna es la interseccion de:
        (a) las metricas conservadas por la regla del laboratorio, y
        (b) las metricas seleccionadas en metricas_por_lab (si se paso);
      si la interseccion es vacia, se conservan todas las de la regla.
    - Las columnas TOTAL al final conservan las metricas de regla_total y
      suman solo los productos seleccionados para los labs en modo producto.
    - Se conserva la fila TOTAL (margen) al final.

    No modifica generar_matriz(): la matriz de metricas sigue intacta.
    """
    from .data_source import (
        COLUMNA_PRODUCTO,
        calcular_unidades_vendidas,
        detectar_laboratorios,
        validar_columnas,
    )

    validar_columnas(df)
    if COLUMNA_PRODUCTO not in df.columns:
        raise ErrorProcesamiento(
            "El origen no tiene 'Descripción Producto': "
            "no se puede construir la matriz por producto."
        )

    labs_detectados = detectar_laboratorios(df)
    if labs_seleccionados is None:
        labs_seleccionados = seleccion_por_defecto(labs_detectados)

    seleccion_canonica: List[str] = []
    for lab in labs_seleccionados:
        canonico, _regla = lab_config.resolver(lab)
        if canonico not in seleccion_canonica:
            seleccion_canonica.append(canonico)

    df_canonico = _canonizar_dataframe(df)
    productos_por_lab = _canonizar_mapa_laboratorios(productos_por_lab)
    metricas_por_lab = _canonizar_mapa_laboratorios(metricas_por_lab)

    # DataFrame solo con los labs seleccionados y filas con producto valido.
    df_filtrado = df_canonico[
        df_canonico["Laboratorio"].isin(seleccion_canonica)
    ].copy()
    df_filtrado = df_filtrado[
        df_filtrado[COLUMNA_PRODUCTO].notna()
        & df_filtrado[COLUMNA_PRODUCTO].astype(str).str.strip().ne("")
    ].copy()

    # Labs con seleccion explicita de productos (lista no vacia).
    labs_con_productos: List[str] = []
    if productos_por_lab is not None:
        for lab in seleccion_canonica:
            prods = productos_por_lab.get(lab)
            if prods is not None and len(prods) > 0:
                labs_con_productos.append(lab)

    # Filtro por producto para esos labs: df_filtrado solo conserva, para cada
    # lab con seleccion, las filas cuyos productos fueron seleccionados. Asi
    # las columnas TOTAL y las de cualquier lab se calculan UNICAMENTE sobre
    # los productos seleccionados de ese lab (NO sobre todos los disponibles).
    if labs_con_productos:
        mascara = pd.Series(False, index=df_filtrado.index)
        for lab in labs_con_productos:
            prods_sel = set(productos_por_lab[lab])
            es_lab = df_filtrado["Laboratorio"].astype(str) == lab
            es_prod = df_filtrado[COLUMNA_PRODUCTO].astype(str).isin(prods_sel)
            mascara |= (es_lab & es_prod)
        # Los labs SIN seleccion explicita conservan TODAS sus filas.
        for lab in seleccion_canonica:
            if lab == TOTAL or lab in labs_con_productos:
                continue
            mascara |= (df_filtrado["Laboratorio"].astype(str) == lab)
        df_filtrado = df_filtrado[mascara].copy()

    if df_filtrado.empty and not labs_con_productos:
        raise ErrorProcesamiento(
            "Ningun laboratorio seleccionado esta presente en los datos."
        )

    def _metricas_efectivas(lab: str) -> List[str]:
        _c, regla = lab_config.resolver(lab)
        permitidas = list(lab_config.metricas_configuradas(lab))
        if metricas_por_lab is None:
            return permitidas
        sel = metricas_por_lab.get(lab)
        if sel is None:
            return permitidas
        inter = [m for m in permitidas if m in sel]
        return inter if inter else permitidas

    def _valores_metrica(datos: pd.DataFrame, metrica: str) -> pd.Series:
        """Valores usados por el reporte, incluyendo unidades completas DEMO."""
        valores = pd.to_numeric(datos[metrica], errors="coerce").fillna(0)
        if metrica != "CantF" or "Presentación" not in datos.columns:
            return valores
        usa_combinadas = datos["Laboratorio"].map(
            lambda nombre: bool(
                lab_config.perfil(str(nombre)).get("unidades_combinadas", False)
            )
        )
        if usa_combinadas.any():
            combinadas = calcular_unidades_vendidas(datos)
            valores = valores.where(~usa_combinadas, combinadas)
        return valores

    def _agrupar(datos: pd.DataFrame, metrica: str) -> pd.Series:
        valores = _valores_metrica(datos, metrica)
        return valores.groupby(datos["Botica"]).sum()

    # Indice: primero las boticas configuradas para seguimiento, incluso si
    # no tuvieron ventas; despues cualquier botica adicional detectada.
    boticas_presentes = sorted(
        b for b in df_canonico["Botica"].dropna().astype(str).unique() if b and b != TOTAL
    )
    index_boticas = []
    for botica in boticas_obligatorias or []:
        nombre = str(botica).strip()
        if nombre and nombre not in index_boticas:
            index_boticas.append(nombre)
    index_boticas.extend(b for b in boticas_presentes if b not in index_boticas)

    columnas: List[tuple] = []  # (lab, metrica, producto, pd.Series)
    for lab in seleccion_canonica:
        if lab == TOTAL:
            continue
        metricas_lab = _metricas_efectivas(lab)
        if lab in labs_con_productos:
            prods_sel = set(productos_por_lab[lab])
            sub = df_filtrado[
                (df_filtrado["Laboratorio"].astype(str) == lab)
                & df_filtrado[COLUMNA_PRODUCTO].astype(str).isin(prods_sel)
            ]
            if lab_config.perfil(lab).get("agrupar_productos", False):
                for metrica in metricas_lab:
                    serie = _agrupar(sub, metrica)
                    columnas.append((lab, metrica, "", serie))
            else:
                for metrica in metricas_lab:
                    # La selección define las columnas, aunque no existan ventas.
                    for prod in dict.fromkeys(productos_por_lab[lab]):
                        serie = _agrupar(sub[sub[COLUMNA_PRODUCTO].eq(prod)], metrica)
                        columnas.append((lab, metrica, prod, serie))
        else:
            sub = df_filtrado[df_filtrado["Laboratorio"].astype(str) == lab]
            for metrica in metricas_lab:
                serie = _agrupar(sub, metrica)
                columnas.append((lab, metrica, "", serie))

    # Columnas TOTAL: metricas de regla_total sobre todos los labs
    # visibles (con sus productos seleccionados, si aplica el filtro).
    for metrica in lab_config.metricas_a_conservar(lab_config.regla_total()):
        serie = _agrupar(df_filtrado, metrica)
        columnas.append((TOTAL, metrica, "", serie))

    if not columnas:
        raise ErrorProcesamiento("No se pudo construir ninguna columna para la matriz.")

    mat = pd.DataFrame(index=pd.Index(index_boticas, name="Botica"))
    for lab, metrica, prod, serie in columnas:
        mat[(lab, metrica, prod)] = serie.reindex(index_boticas, fill_value=0)
    mat.columns = pd.MultiIndex.from_tuples(
        [(c[0], c[1], c[2]) for c in mat.columns]
    )

    # Reorden de laboratorios (orden_preferido primero, luego alfabeticos),
    # conservando TOTAL al final.
    orden = lab_config.orden_preferido()
    labs_presentes = mat.columns.get_level_values(0).unique().tolist()
    orden_efectivo: List[str] = []
    for lab in orden:
        if lab in labs_presentes and lab != TOTAL:
            orden_efectivo.append(lab)
    for lab in labs_presentes:
        if lab not in orden_efectivo and lab != TOTAL:
            orden_efectivo.append(lab)
    orden_efectivo.append(TOTAL)
    mat = mat.reindex(columns=orden_efectivo, level=0)

    # Si ningun laboratorio necesita desglose por producto, eliminamos el
    # tercer nivel vacio para que Excel no cree una fila de encabezado extra.
    if all(not str(col[2]).strip() for col in mat.columns):
        mat.columns = pd.MultiIndex.from_tuples(
            [(col[0], col[1]) for col in mat.columns]
        )

    # Fila TOTAL (margen inferior): suma de cada columna.
    fila_total = mat.sum(axis=0)
    fila_total.name = TOTAL
    mat = pd.concat([mat, fila_total.to_frame().T])
    mat.index.name = "Botica"

    return mat


def resumen_matriz(tabla: pd.DataFrame) -> Dict[str, int]:
    """Diccionario con metricas basicas para mostrar en la UI."""
    labs = tabla.columns.get_level_values(0).unique().tolist()
    return {
        "laboratorios": len([l for l in labs if l != TOTAL]),
        "boticas": len(tabla.index) - 1 if TOTAL in tabla.index else len(tabla.index),
        "columnas": tabla.shape[1],
        "filas": tabla.shape[0],
    }


def construir_detalle(
    df: pd.DataFrame,
    labs_seleccionados: Sequence[str] | None = None,
    productos_por_lab: Optional[Dict[str, List[str]]] = None,
    metricas_por_lab: Optional[Dict[str, List[str]]] = None,
) -> Optional[pd.DataFrame]:
    """Devuelve un DataFrame plano con el detalle por producto.

    Columnas:
        Botica | Laboratorio | Descripción Producto | <metricas seleccionadas>

    - Filas filtradas por laboratorios seleccionados.
    - Filas filtradas por productos seleccionados (si aplica).
    - Metricas no seleccionadas no aparecen como columnas.
    - Metricas prohibidas por la regla tampoco aparecen (interseccion con
      lab_config.metricas_a_conservar(regla)).
    - Si el DataFrame no contiene 'Descripción Producto', devuelve None
      (no hay detalle posible).
    - Si tras el filtrado no queda ninguna fila, devuelve None.
    """
    from .data_source import COLUMNA_PRODUCTO, detectar_laboratorios, validar_columnas

    validar_columnas(df)
    if COLUMNA_PRODUCTO not in df.columns:
        return None

    labs_detectados = detectar_laboratorios(df)
    if labs_seleccionados is None:
        labs_seleccionados = seleccion_por_defecto(labs_detectados)

    # Canonizar seleccion (igual que en generar_matriz)
    seleccion_canonica: List[str] = []
    for lab in labs_seleccionados:
        canonico, _regla = lab_config.resolver(lab)
        if canonico not in seleccion_canonica:
            seleccion_canonica.append(canonico)

    df_canonico = _canonizar_dataframe(df)
    productos_por_lab = _canonizar_mapa_laboratorios(productos_por_lab)
    metricas_por_lab = _canonizar_mapa_laboratorios(metricas_por_lab)

    df_filtrado = df_canonico[
        df_canonico["Laboratorio"].isin(seleccion_canonica)
    ].copy()

    if productos_por_lab is not None:
        df_filtrado = _filtrar_por_producto(df_filtrado, productos_por_lab)

    if df_filtrado.empty:
        return None

    # Decidir metricas por lab (interseccion con la regla)
    detalle_partes: List[pd.DataFrame] = []
    for lab in seleccion_canonica:
        sub = df_filtrado[df_filtrado["Laboratorio"].astype(str) == lab]
        if sub.empty:
            continue

        # Regla del lab
        _canon, regla = lab_config.resolver(lab)
        metricas_permitidas = list(lab_config.metricas_configuradas(lab))

        # Subseleccion del usuario (si aplica)
        if metricas_por_lab is not None:
            sel = metricas_por_lab.get(lab)
            if sel is not None:
                metricas_permitidas = [
                    m for m in metricas_permitidas if m in sel
                ]

        # Columnas a conservar: identificadoras + metricas seleccionadas
        cols = ["Botica", "Laboratorio", COLUMNA_PRODUCTO] + metricas_permitidas
        cols = [c for c in cols if c in sub.columns]
        detalle_partes.append(sub[cols].copy())

    if not detalle_partes:
        return None

    detalle = pd.concat(detalle_partes, ignore_index=True)
    # Ordenar para una vista estable
    detalle.sort_values(
        by=["Botica", "Laboratorio", COLUMNA_PRODUCTO], inplace=True, kind="stable"
    )
    detalle.reset_index(drop=True, inplace=True)
    return detalle
