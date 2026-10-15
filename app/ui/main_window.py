"""Ventana principal de la aplicacion V1 (Tkinter/ttk).

Construida sobre app.core (motor validado). Esta capa solo:
  - presenta datos al usuario,
  - recoge la seleccion del usuario,
  - llama al motor,
  - muestra resultados y mensajes de estado claros.

NO reimplementa reglas de negocio: todas viven en app.core.
"""

from __future__ import annotations

import threading
import json
import re
from queue import Empty, Queue
from datetime import datetime
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import Dict, List, Optional

import pandas as pd

from app.core import contest, data_source, excel_export, lab_config, preferences, processing, profiles
from app.paths import raiz_aplicacion


# --------------------------------------------------------------------------- #
# Constantes de UI
# --------------------------------------------------------------------------- #

APP_TITLE = "Análisis de Ventas"
APP_VERSION = "V2"
WINDOW_GEOMETRY = "1100x780"
MIN_WINDOW_SIZE = (820, 600)

COLOR_STATUS_OK = "#1b7a3d"
COLOR_STATUS_INFO = "#0b5fb3"
COLOR_STATUS_WARN = "#a26400"
COLOR_STATUS_ERR = "#a3231b"

FORMATO_SOLES_UI = "S/ {:,.2f}"

VISTA_PREVIA_FILAS = 200  # limite de filas mostradas en el Treeview
LABS_POR_PAGINA = 60


# --------------------------------------------------------------------------- #
# Aplicacion
# --------------------------------------------------------------------------- #


class AplicacionVentas:
    """Controlador de la ventana principal.

    Mantiene estado minimo en atributos:
      - df_crudo: DataFrame leido del portapapeles (None si aun no se ha leido)
      - labs_detectados: lista de laboratorios presentes
      - productos_por_lab: dict {lab: [productos]} detectados
      - tiene_productos: True si el DF trae la columna 'Descripción Producto'
      - tabla_resultado: matriz generada por el motor (None si no analizado)
      - seleccion_labs: {nombre_lab: BooleanVar} para checkboxes
      - seleccion_productos: {lab: {producto: BooleanVar}} para checkboxes
      - lab_expandido: lab cuyo subpanel se muestra (None si ninguno)
    """

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title(f"{APP_TITLE} — {APP_VERSION}")
        self.root.geometry(WINDOW_GEOMETRY)
        self.root.minsize(*MIN_WINDOW_SIZE)

        # Estado
        self.df_crudo: Optional[pd.DataFrame] = None
        self.tarea_en_curso = False
        self.labs_detectados: List[str] = []
        self.productos_por_lab: Dict[str, List[str]] = {}
        self.tiene_productos: bool = False
        self.tabla_resultado: Optional[pd.DataFrame] = None
        self.detalle_resultado: Optional[pd.DataFrame] = None
        self.errores_detectados: pd.DataFrame = pd.DataFrame()
        self.concurso_seleccionado: Optional[str] = None
        self.avance_concurso: Optional[pd.DataFrame] = None
        self.opciones_exportacion: Dict[str, object] = preferences.cargar_exportacion()
        self.seleccion_labs: Dict[str, tk.BooleanVar] = {}
        self.seleccion_productos: Dict[str, Dict[str, tk.BooleanVar]] = {}
        self.productos_explicitos: set[str] = set()
        self.seleccion_metricas: Dict[str, Dict[str, tk.BooleanVar]] = {}
        self.lab_expandido: Optional[str] = None
        self.ultimos_resumen: Dict[str, int] = {}
        self.pagina_labs: int = 0
        self.perfiles_path = profiles.ruta_perfiles_usuario()

        # Construir UI
        self._build_styles()
        self._build_layout()
        self._build_seccion_datos()
        self._build_seccion_laboratorios()
        self._build_seccion_analisis()
        self._build_seccion_resultados()
        self._build_barra_estado()

        # Estado inicial
        self._set_estado("Esperando datos...")
        self._actualizar_controles()

    # ------------------------------------------------------------------ #
    # Estilos
    # ------------------------------------------------------------------ #
    def _build_styles(self) -> None:
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure("Titulo.TLabel", font=("Segoe UI", 11, "bold"))
        style.configure("Estado.TLabel", font=("Segoe UI", 10))
        style.configure("EstadoOk.TLabel", foreground=COLOR_STATUS_OK)
        style.configure("EstadoInfo.TLabel", foreground=COLOR_STATUS_INFO)
        style.configure("EstadoWarn.TLabel", foreground=COLOR_STATUS_WARN)
        style.configure("EstadoErr.TLabel", foreground=COLOR_STATUS_ERR)

        style.configure("Accion.TButton", font=("Segoe UI", 10))
        style.configure("Primario.TButton", font=("Segoe UI", 10, "bold"))

        style.configure(
            "Treeview",
            font=("Segoe UI", 9),
            rowheight=22,
        )
        style.configure("Treeview.Heading", font=("Segoe UI", 9, "bold"))

    # ------------------------------------------------------------------ #
    # Layout general: 4 secciones + barra de estado
    # ------------------------------------------------------------------ #
    def _build_layout(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(3, weight=1)  # resultados crece

        self.frm_datos = ttk.LabelFrame(self.root, text="1. Datos", padding=10)
        self.frm_datos.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 5))

        self.frm_labs = ttk.LabelFrame(self.root, text="2. Laboratorios", padding=10)
        self.frm_labs.grid(row=1, column=0, sticky="nsew", padx=10, pady=5)
        self.frm_labs.columnconfigure(0, weight=1)
        self.frm_labs.rowconfigure(1, weight=1)

        self.frm_analisis = ttk.LabelFrame(self.root, text="3. Análisis", padding=10)
        self.frm_analisis.grid(row=2, column=0, sticky="ew", padx=10, pady=5)

        self.frm_resultados = ttk.LabelFrame(self.root, text="4. Resultados", padding=10)
        self.frm_resultados.grid(row=3, column=0, sticky="nsew", padx=10, pady=5)
        self.frm_resultados.columnconfigure(0, weight=1)
        self.frm_resultados.rowconfigure(1, weight=1)

        self.frm_estado = ttk.Frame(self.root, padding=(10, 5))
        self.frm_estado.grid(row=4, column=0, sticky="ew", padx=10, pady=(5, 10))

    # ------------------------------------------------------------------ #
    # Seccion 1: Datos
    # ------------------------------------------------------------------ #
    def _build_seccion_datos(self) -> None:
        # La columna central crece y empuja las acciones hacia la derecha.
        self.frm_datos.columnconfigure(2, weight=1)

        ttk.Label(self.frm_datos, text="Carga de datos:", style="Titulo.TLabel").grid(
            row=0, column=0, sticky="w"
        )

        self.btn_leer = ttk.Button(
            self.frm_datos,
            text="Leer portapapeles",
            style="Accion.TButton",
            command=self.on_leer_portapapeles,
        )
        self.btn_leer.grid(row=0, column=1, padx=(10, 0))

        self.lbl_info_datos = ttk.Label(
            self.frm_datos,
            text="Aún no se han cargado datos.",
            style="Estado.TLabel",
            wraplength=760,
        )
        self.lbl_info_datos.grid(row=1, column=0, columnspan=6, sticky="ew", pady=(8, 0))
        self.lbl_info_datos.bind(
            "<Configure>", lambda event: self.lbl_info_datos.configure(wraplength=max(200, event.width))
        )

        self.btn_validacion = ttk.Button(
            self.frm_datos, text="Ver validación", command=self.ver_validacion,
            state="disabled"
        )
        self.btn_validacion.grid(row=0, column=3, padx=(10, 0))

        self.btn_reglas = ttk.Button(
            self.frm_datos, text="Editar reglas", command=self.abrir_editor_reglas
        )
        self.btn_reglas.grid(row=0, column=4, padx=(10, 0))
        self.btn_concursos = ttk.Button(
            self.frm_datos, text="Concursos", command=self.abrir_concursos
        )
        self.btn_concursos.grid(row=0, column=5, padx=(10, 0))

    def abrir_editor_reglas(self) -> None:
        from app.ui.rules_editor import EditorReglas

        EditorReglas(
            self.root,
            al_guardar=lambda: self._set_estado(
                "Reglas actualizadas. Se aplicarán al siguiente análisis.", "ok"
            ),
        )

    def abrir_concursos(self) -> None:
        if self.df_crudo is None:
            self._error_usuario("Primero carga los datos desde el portapapeles.", "warn")
            return
        try:
            nombres = sorted(contest.cargar_concursos())
        except contest.ErrorConcurso as exc:
            self._error_usuario(str(exc), "err")
            return
        if not nombres:
            self._error_usuario("No hay concursos configurados.", "warn")
            return

        ventana = tk.Toplevel(self.root)
        ventana.title("Avance de concursos")
        ventana.geometry("1050x520")
        ventana.transient(self.root)
        ventana.columnconfigure(0, weight=1)
        ventana.rowconfigure(2, weight=1)
        barra = ttk.Frame(ventana, padding=10)
        barra.grid(row=0, column=0, sticky="ew")
        ttk.Label(barra, text="Concurso:", style="Titulo.TLabel").pack(side="left")
        seleccionado = tk.StringVar(value=self.concurso_seleccionado or nombres[0])
        combo = ttk.Combobox(barra, textvariable=seleccionado, values=nombres, state="readonly", width=30)
        combo.pack(side="left", padx=8)
        resumen = ttk.Label(ventana, text="Selecciona un concurso para calcular el avance.", padding=(10, 0))
        resumen.grid(row=1, column=0, sticky="w")
        cont = ttk.Frame(ventana, padding=10)
        cont.grid(row=2, column=0, sticky="nsew")
        cont.rowconfigure(0, weight=1)
        cont.columnconfigure(0, weight=1)
        tree = ttk.Treeview(cont, show="headings")
        tree.grid(row=0, column=0, sticky="nsew")
        sy = ttk.Scrollbar(cont, orient="vertical", command=tree.yview)
        sy.grid(row=0, column=1, sticky="ns")
        tree.configure(yscrollcommand=sy.set)

        def calcular():
            try:
                avance = contest.calcular_avance(self.df_crudo, seleccionado.get())
                self.concurso_seleccionado = seleccionado.get()
                self.avance_concurso = avance
                tree.delete(*tree.get_children())
                columnas = list(avance.columns)
                tree.configure(columns=columnas)
                for col in columnas:
                    tree.heading(col, text=col)
                    tree.column(col, width=145, anchor="center")
                for fila in avance.itertuples(index=False, name=None):
                    tree.insert("", "end", values=tuple(
                        f"{v:.2f}" if isinstance(v, float) else v for v in fila
                    ))
                total = contest.resumen_concurso(self.df_crudo, seleccionado.get())
                texto = (
                    f"Productos con cuota: {total['cajas_vendidas']:.2f} / "
                    f"{total['cajas_meta']:.2f} cajas · "
                    f"Cumplimiento: {total['cumplimiento_productos']:.2%}"
                )
                if total["meta_soles"]:
                    texto = (
                        f"Todo el laboratorio: S/ {total['avance_soles']:,.2f} / "
                        f"S/ {total['meta_soles']:,.2f} "
                        f"({total['cumplimiento_soles']:.2%}) · " + texto
                    )
                resumen.configure(text=texto)
            except contest.ErrorConcurso as exc:
                messagebox.showwarning("Avance de concurso", str(exc), parent=ventana)

        ttk.Button(barra, text="Calcular avance", command=calcular, style="Primario.TButton").pack(side="left")
        ttk.Button(barra, text="Cerrar", command=ventana.destroy).pack(side="left", padx=8)
        calcular()

    # ------------------------------------------------------------------ #
    # Seccion 2: Laboratorios
    # ------------------------------------------------------------------ #
    def _build_seccion_laboratorios(self) -> None:
        # Barra superior: busqueda + botones seleccion
        barra = ttk.Frame(self.frm_labs)
        barra.grid(row=0, column=0, sticky="ew", columnspan=2)
        barra.columnconfigure(3, weight=1)

        ttk.Label(barra, text="Buscar:").grid(row=0, column=0, sticky="w")

        self.var_busqueda = tk.StringVar()
        self.var_busqueda.trace_add("write", lambda *_: self._aplicar_filtro_busqueda())
        self.entry_busqueda = ttk.Entry(barra, textvariable=self.var_busqueda)
        self.entry_busqueda.grid(row=0, column=1, sticky="ew", padx=(5, 15))

        self.btn_seleccionar_todos = ttk.Button(
            barra,
            text="Seleccionar todos",
            style="Accion.TButton",
            command=self.on_seleccionar_todos,
        )
        self.btn_seleccionar_todos.grid(row=0, column=2, padx=(0, 5))

        self.btn_limpiar_seleccion = ttk.Button(
            barra,
            text="Limpiar selección",
            style="Accion.TButton",
            command=self.on_limpiar_seleccion,
        )
        self.btn_limpiar_seleccion.grid(row=0, column=3, sticky="w")

        self.lbl_contador_labs = ttk.Label(
            barra, text="", style="Estado.TLabel"
        )
        self.lbl_contador_labs.grid(row=0, column=4, sticky="e", padx=(10, 0))

        ttk.Label(barra, text="Perfil:").grid(row=1, column=0, sticky="w", pady=(6, 0))
        self.var_perfil = tk.StringVar()
        self.combo_perfiles = ttk.Combobox(barra, textvariable=self.var_perfil,
                                           state="readonly", width=22)
        self.combo_perfiles.grid(row=1, column=1, sticky="w", padx=(5, 5), pady=(6, 0))
        ttk.Button(barra, text="Guardar favorito", command=self.guardar_perfil).grid(
            row=1, column=2, padx=(0, 5), pady=(6, 0))
        ttk.Button(barra, text="Cargar", command=self.cargar_perfil).grid(
            row=1, column=3, sticky="w", pady=(6, 0))
        ttk.Button(barra, text="Eliminar", command=self.eliminar_perfil).grid(
            row=1, column=4, sticky="e", padx=(5, 0), pady=(6, 0))
        ttk.Button(barra, text="Gestionar perfiles", command=self.gestionar_perfiles).grid(
            row=1, column=5, sticky="e", padx=(5, 0), pady=(6, 0))
        self._actualizar_lista_perfiles()

        nav = ttk.Frame(barra)
        nav.grid(row=2, column=0, columnspan=6, sticky="w", pady=(6, 0))
        self.btn_labs_anterior = ttk.Button(nav, text="◀ Anterior", command=lambda: self._cambiar_pagina_labs(-1))
        self.btn_labs_anterior.pack(side="left")
        self.lbl_pagina_labs = ttk.Label(nav, text="Página 1 / 1")
        self.lbl_pagina_labs.pack(side="left", padx=10)
        self.btn_labs_siguiente = ttk.Button(nav, text="Siguiente ▶", command=lambda: self._cambiar_pagina_labs(1))
        self.btn_labs_siguiente.pack(side="left")

        # ---- Columna izquierda: lista de laboratorios (original)
        cont_labs = ttk.Frame(self.frm_labs)
        cont_labs.grid(row=1, column=0, sticky="nsew", pady=(10, 0))
        cont_labs.rowconfigure(0, weight=1)
        cont_labs.columnconfigure(0, weight=1)
        self.frm_labs.rowconfigure(1, weight=1)
        self.frm_labs.columnconfigure(0, weight=1, minsize=300)
        self.frm_labs.columnconfigure(1, weight=1, minsize=300)

        self.canvas_labs = tk.Canvas(cont_labs, highlightthickness=0, height=220)
        self.scroll_labs = ttk.Scrollbar(cont_labs, orient="vertical", command=self.canvas_labs.yview)
        self.frame_labs_inner = ttk.Frame(self.canvas_labs)

        self.frame_labs_inner.bind(
            "<Configure>",
            lambda e: self.canvas_labs.configure(scrollregion=self.canvas_labs.bbox("all")),
        )
        self.canvas_labs.create_window((0, 0), window=self.frame_labs_inner, anchor="nw")
        self.canvas_labs.configure(yscrollcommand=self.scroll_labs.set)

        self.canvas_labs.grid(row=0, column=0, sticky="nsew")
        self.scroll_labs.grid(row=0, column=1, sticky="ns")

        # Scroll con rueda del mouse
        self.canvas_labs.bind(
            "<Enter>",
            lambda e: self.canvas_labs.bind_all("<MouseWheel>", self._on_wheel_labs),
        )
        self.canvas_labs.bind(
            "<Leave>",
            lambda e: self.canvas_labs.unbind_all("<MouseWheel>"),
        )

        # Placeholder visual
        self.lbl_labs_placeholder = ttk.Label(
            self.frame_labs_inner,
            text="Cargue datos para ver los laboratorios disponibles.",
            style="Estado.TLabel",
        )
        self.lbl_labs_placeholder.grid(row=0, column=0, sticky="w")

        # ---- Columna derecha: subpanel de productos del lab seleccionado
        cont_prod = ttk.Frame(self.frm_labs)
        cont_prod.grid(row=1, column=1, sticky="nsew", pady=(10, 0), padx=(10, 0))
        cont_prod.rowconfigure(2, weight=1)
        cont_prod.columnconfigure(0, weight=1)

        self.lbl_titulo_productos = ttk.Label(
            cont_prod,
            text="Productos: (selecciona un laboratorio)",
            style="Titulo.TLabel",
        )
        self.lbl_titulo_productos.grid(row=0, column=0, sticky="w")

        self.lbl_aviso_productos = ttk.Label(
            cont_prod, text="", style="EstadoWarn.TLabel"
        )
        self.lbl_aviso_productos.grid(row=1, column=0, sticky="w")

        # Barra de botones + busqueda de productos
        barra_prod = ttk.Frame(cont_prod)
        barra_prod.grid(row=2, column=0, sticky="ew")
        barra_prod.columnconfigure(1, weight=1)

        self.btn_prod_seleccionar_todos = ttk.Button(
            barra_prod,
            text="Seleccionar todos",
            style="Accion.TButton",
            command=self.on_seleccionar_todos_productos,
        )
        self.btn_prod_seleccionar_todos.grid(row=0, column=0, padx=(0, 5))

        self.btn_prod_limpiar = ttk.Button(
            barra_prod,
            text="Limpiar",
            style="Accion.TButton",
            command=self.on_limpiar_productos,
        )
        self.btn_prod_limpiar.grid(row=0, column=2, padx=(5, 0))

        self.var_busqueda_productos = tk.StringVar()
        self.var_busqueda_productos.trace_add(
            "write", lambda *_: self._aplicar_filtro_busqueda_productos()
        )
        ttk.Label(barra_prod, text="Buscar:").grid(row=1, column=0, sticky="w", pady=(5, 0))
        self.entry_busqueda_productos = ttk.Entry(
            barra_prod, textvariable=self.var_busqueda_productos
        )
        self.entry_busqueda_productos.grid(row=1, column=1, sticky="ew", pady=(5, 0))
        self.lbl_contador_productos = ttk.Label(
            barra_prod, text="", style="Estado.TLabel"
        )
        self.lbl_contador_productos.grid(row=1, column=2, sticky="e", padx=(5, 0), pady=(5, 0))

        # Canvas scrollable con checkboxes de productos
        cont_lista_prod = ttk.Frame(cont_prod)
        cont_lista_prod.grid(row=3, column=0, sticky="nsew", pady=(5, 0))
        cont_lista_prod.rowconfigure(0, weight=1)
        cont_lista_prod.columnconfigure(0, weight=1)
        cont_prod.rowconfigure(3, weight=1)

        self.canvas_productos = tk.Canvas(cont_lista_prod, highlightthickness=0)
        self.scroll_productos = ttk.Scrollbar(
            cont_lista_prod, orient="vertical", command=self.canvas_productos.yview
        )
        self.frame_productos_inner = ttk.Frame(self.canvas_productos)

        self.frame_productos_inner.bind(
            "<Configure>",
            lambda e: self.canvas_productos.configure(
                scrollregion=self.canvas_productos.bbox("all")
            ),
        )
        self.canvas_productos.create_window(
            (0, 0), window=self.frame_productos_inner, anchor="nw"
        )
        self.canvas_productos.configure(yscrollcommand=self.scroll_productos.set)

        self.canvas_productos.grid(row=0, column=0, sticky="nsew")
        self.scroll_productos.grid(row=0, column=1, sticky="ns")

        self.canvas_productos.bind(
            "<Enter>",
            lambda e: self.canvas_productos.bind_all("<MouseWheel>", self._on_wheel_productos),
        )
        self.canvas_productos.bind(
            "<Leave>",
            lambda e: self.canvas_productos.unbind_all("<MouseWheel>"),
        )

        # Estado inicial: subpanel deshabilitado
        self._actualizar_estado_subpanel_productos()

    def _on_wheel_labs(self, event) -> None:
        self.canvas_labs.yview_scroll(int(-event.delta / 120), "units")

    def _on_wheel_productos(self, event) -> None:
        self.canvas_productos.yview_scroll(int(-event.delta / 120), "units")

    def _actualizar_estado_subpanel_productos(self) -> None:
        """Habilita/deshabilita el subpanel de productos segun estado."""
        habilitado = self.lab_expandido is not None
        estado = "normal" if habilitado else "disabled"
        self.btn_prod_seleccionar_todos.configure(state=estado)
        self.btn_prod_limpiar.configure(state=estado)
        self.entry_busqueda_productos.configure(state=estado)

    # ------------------------------------------------------------------ #
    # Seccion 3: Analisis
    # ------------------------------------------------------------------ #
    def _build_seccion_analisis(self) -> None:
        self.frm_analisis.columnconfigure(2, weight=1)

        self.btn_analizar = ttk.Button(
            self.frm_analisis,
            text="Analizar ventas",
            style="Primario.TButton",
            command=self.on_analizar,
        )
        self.btn_analizar.grid(row=0, column=0, sticky="w")

        self.btn_exportar = ttk.Button(
            self.frm_analisis,
            text="Exportar a Excel",
            style="Accion.TButton",
            command=self.on_exportar,
        )
        self.btn_exportar.grid(row=0, column=1, padx=(10, 0), sticky="w")

        self.btn_opciones_exportacion = ttk.Button(
            self.frm_analisis,
            text="Opciones de exportación",
            command=self.abrir_opciones_exportacion,
        )
        self.btn_opciones_exportacion.grid(row=0, column=2, padx=(10, 0), sticky="w")

        self.lbl_resumen = ttk.Label(
            self.frm_analisis,
            text="",
            style="Estado.TLabel",
        )
        self.frm_analisis.columnconfigure(3, weight=1)
        self.lbl_resumen.grid(row=0, column=3, sticky="w", padx=(15, 0))

    # ------------------------------------------------------------------ #
    # Seccion 4: Resultados
    # ------------------------------------------------------------------ #
    def _build_seccion_resultados(self) -> None:
        # Barra superior de la vista previa
        barra = ttk.Frame(self.frm_resultados)
        barra.grid(row=0, column=0, sticky="ew")
        barra.columnconfigure(1, weight=1)

        ttk.Label(barra, text="Vista previa:", style="Titulo.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        self.lbl_vista_previa_info = ttk.Label(
            barra, text="", style="Estado.TLabel"
        )
        self.lbl_vista_previa_info.grid(row=0, column=1, sticky="w", padx=(10, 0))

        # Treeview de la matriz dentro de un frame con scrollbars
        cont = ttk.Frame(self.frm_resultados)
        cont.grid(row=1, column=0, sticky="nsew", pady=(5, 0))
        cont.rowconfigure(0, weight=1)
        cont.columnconfigure(0, weight=1)

        self.tree = ttk.Treeview(cont, show="headings")
        self.tree.grid(row=0, column=0, sticky="nsew")

        sb_y = ttk.Scrollbar(cont, orient="vertical", command=self.tree.yview)
        sb_y.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=sb_y.set)

        sb_x = ttk.Scrollbar(cont, orient="horizontal", command=self.tree.xview)
        sb_x.grid(row=1, column=0, sticky="ew")
        self.tree.configure(xscrollcommand=sb_x.set)

        self.tree.bind("<Configure>", lambda e: self._ajustar_ancho_columnas_tree())

    # ------------------------------------------------------------------ #
    # Barra de estado
    # ------------------------------------------------------------------ #
    def _build_barra_estado(self) -> None:
        self.frm_estado.columnconfigure(0, weight=1)
        self.lbl_estado = ttk.Label(
            self.frm_estado,
            text="",
            style="Estado.TLabel",
        )
        self.lbl_estado.grid(row=0, column=0, sticky="w")

    # ------------------------------------------------------------------ #
    # Estado + control de botones
    # ------------------------------------------------------------------ #
    def _set_estado(self, mensaje: str, nivel: str = "info") -> None:
        estilo = {
            "info": "EstadoInfo.TLabel",
            "ok": "EstadoOk.TLabel",
            "warn": "EstadoWarn.TLabel",
            "err": "EstadoErr.TLabel",
        }.get(nivel, "Estado.TLabel")
        self.lbl_estado.configure(text=mensaje, style=estilo)

    def _actualizar_controles(self) -> None:
        tiene_datos = self.df_crudo is not None
        disponible = not self.tarea_en_curso
        self.btn_leer.configure(state="normal" if disponible else "disabled")
        self.btn_analizar.configure(state="normal" if tiene_datos and disponible else "disabled")
        self.btn_exportar.configure(
            state="normal" if self.tabla_resultado is not None and disponible else "disabled"
        )
        self.btn_validacion.configure(state="normal" if tiene_datos else "disabled")
        # Busqueda solo util si hay labs
        if not self.labs_detectados:
            self.entry_busqueda.configure(state="disabled")
        else:
            self.entry_busqueda.configure(state="normal")
        self._actualizar_estado_subpanel_productos()

    # ------------------------------------------------------------------ #
    # Accion: Leer portapapeles
    # ------------------------------------------------------------------ #
    def on_leer_portapapeles(self) -> None:
        self._ejecutar_tarea(
            data_source.read_clipboard,
            lambda resultado: self._on_datos_cargados(resultado, "Portapapeles"),
            "Leyendo portapapeles...",
        )

    def _ejecutar_tarea(self, lector, al_completar, mensaje: str) -> None:
        """Ejecuta fuera de Tk y entrega el resultado en el hilo de la ventana."""
        if self.tarea_en_curso:
            return
        self.tarea_en_curso = True
        self._actualizar_controles()
        self._set_estado(mensaje, "info")
        pendientes = Queue()

        def trabajo():
            try:
                pendientes.put((True, lector()))
            except Exception as exc:
                pendientes.put((False, exc))

        def recoger():
            try:
                correcto, resultado = pendientes.get_nowait()
            except Empty:
                self.root.after(50, recoger)
                return
            self.tarea_en_curso = False
            self._actualizar_controles()
            if correcto:
                al_completar(resultado)
            else:
                self._error_usuario(
                    str(resultado), "warn" if isinstance(resultado, (data_source.ErrorLectura, processing.ErrorProcesamiento, excel_export.ArchivoAbierto)) else "err"
                )

        threading.Thread(target=trabajo, daemon=True).start()
        self.root.after(50, recoger)

    def on_importar_archivo(self) -> None:
        if self.tarea_en_curso:
            return
        ruta = filedialog.askopenfilename(
            parent=self.root, title="Importar archivo de ventas",
            filetypes=[("Excel y CSV", "*.xlsx *.xlsm *.csv"),
                       ("Excel", "*.xlsx *.xlsm"), ("CSV", "*.csv")],
        )
        if not ruta:
            return
        extension = Path(ruta).suffix.lower()
        if extension == ".csv":
            self._configurar_importacion(ruta)
        elif extension in (".xlsx", ".xlsm"):
            self._ejecutar_tarea(
                lambda: data_source.listar_hojas_excel(ruta),
                lambda hojas: self._configurar_importacion(ruta, hojas),
                f"Leyendo hojas de {Path(ruta).name}...",
            )
        else:
            self._error_usuario("Selecciona un archivo .xlsx, .xlsm o .csv. Para un Excel "
                                "antiguo (.xls), guárdalo primero como .xlsx.", "warn")

    def _configurar_importacion(self, ruta: str, hojas: list[str] | None = None) -> None:
        from app.ui.import_dialog import DialogoImportacion

        if hojas is not None and not hojas:
            self._error_usuario("El libro no contiene hojas disponibles.", "warn")
            return
        opciones = DialogoImportacion(self.root, ruta, hojas)
        if opciones.result is None:
            self._set_estado("Importación cancelada.", "info")
            return
        seleccion = opciones.result
        origen = Path(ruta).name
        if hojas is None:
            lector = lambda: data_source.read_csv(ruta, decimal=seleccion)
        else:
            lector = lambda: data_source.read_excel(ruta, hoja=seleccion)
            origen += f" · Hoja: {seleccion}"
        self._ejecutar_tarea(
            lector, lambda resultado: self._on_datos_cargados(resultado, origen),
            f"Importando {origen}...",
        )

    def _on_datos_cargados(self, resultado: data_source.ResultadoLectura,
                          origen: str = "Portapapeles") -> None:
        self.df_crudo = resultado.dataframe
        self.labs_detectados = resultado.laboratorios
        self.productos_por_lab = resultado.productos_por_lab
        self.tiene_productos = resultado.tiene_columna_producto
        self.errores_detectados = resultado.errores_detectados
        self.tabla_resultado = None
        self.detalle_resultado = None
        self.ultimos_resumen = {}
        self.tree.delete(*self.tree.get_children())
        self.tree.configure(columns=())
        self.lbl_resumen.configure(text="")
        self.lbl_vista_previa_info.configure(text="")
        self.concurso_seleccionado = None
        self.avance_concurso = None
        self.seleccion_productos.clear()
        self.productos_explicitos.clear()
        self.lab_expandido = None

        # Construir lista de checkboxes
        self._construir_lista_labs()

        n_total_productos = sum(len(v) for v in self.productos_por_lab.values())
        info = (
            f"{origen}\nDatos cargados correctamente: "
            f"{resultado.n_filas} registros · "
            f"{resultado.n_boticas} boticas · "
            f"{len(resultado.laboratorios)} laboratorios."
        )
        if self.tiene_productos:
            info += f" · {n_total_productos} productos."
        else:
            info += "  (sin columna 'Descripción Producto': filtro por producto deshabilitado)."
        if not self.errores_detectados.empty:
            info += f" · {len(self.errores_detectados)} observaciones de validación."
        self.lbl_info_datos.configure(text=info)

        if self.tiene_productos:
            self.lbl_aviso_productos.configure(text="")
        else:
            self.lbl_aviso_productos.configure(
                text="Los datos cargados no contienen la columna 'Descripción Producto'. "
                     "El análisis continuará en modo general."
            )

        self.limpiar_subpanel_productos()
        self._set_estado("Datos cargados correctamente.", "ok")
        self._actualizar_controles()

    def ver_validacion(self) -> None:
        ventana = tk.Toplevel(self.root)
        ventana.title("Validación de datos")
        ventana.geometry("1000x500")
        ventana.transient(self.root)

        errores = self.errores_detectados
        if errores.empty:
            ttk.Label(
                ventana, text="No se detectaron observaciones en los datos cargados.",
                style="EstadoOk.TLabel", padding=20
            ).pack(anchor="w")
            return

        ttk.Label(
            ventana,
            text=f"Se detectaron {len(errores)} observaciones. Serán incluidas en el Excel si la opción está activa.",
            style="EstadoWarn.TLabel", padding=10,
        ).pack(anchor="w")
        cont = ttk.Frame(ventana, padding=(10, 0, 10, 10))
        cont.pack(fill="both", expand=True)
        cont.rowconfigure(0, weight=1)
        cont.columnconfigure(0, weight=1)
        columnas = list(errores.columns)
        tree = ttk.Treeview(cont, columns=columnas, show="headings")
        for col in columnas:
            tree.heading(col, text=col)
            tree.column(col, width=150, anchor="w")
        for fila in errores.itertuples(index=False, name=None):
            tree.insert("", "end", values=fila)
        tree.grid(row=0, column=0, sticky="nsew")
        sy = ttk.Scrollbar(cont, orient="vertical", command=tree.yview)
        sy.grid(row=0, column=1, sticky="ns")
        sx = ttk.Scrollbar(cont, orient="horizontal", command=tree.xview)
        sx.grid(row=1, column=0, sticky="ew")
        tree.configure(yscrollcommand=sy.set, xscrollcommand=sx.set)

    def abrir_opciones_exportacion(self) -> None:
        ventana = tk.Toplevel(self.root)
        ventana.title("Opciones de exportación")
        ventana.geometry("520x330")
        ventana.transient(self.root)
        ventana.grab_set()

        v_resumen = tk.BooleanVar(value=bool(self.opciones_exportacion["incluir_resumen"]))
        v_detalle = tk.BooleanVar(value=bool(self.opciones_exportacion["incluir_detalle"]))
        v_errores = tk.BooleanVar(value=bool(self.opciones_exportacion["incluir_errores"]))
        v_orden = tk.StringVar(value=str(self.opciones_exportacion["orden_boticas"]))
        v_carpeta = tk.StringVar(value=str(self._carpeta_exportacion()))

        cuerpo = ttk.Frame(ventana, padding=15)
        cuerpo.pack(fill="both", expand=True)
        ttk.Checkbutton(cuerpo, text="Incluir Resumen Ejecutivo", variable=v_resumen).grid(row=0, column=0, sticky="w")
        ttk.Checkbutton(cuerpo, text="Incluir Detalle de Productos", variable=v_detalle).grid(row=1, column=0, sticky="w", pady=5)
        ttk.Checkbutton(cuerpo, text="Incluir Errores Detectados", variable=v_errores).grid(row=2, column=0, sticky="w")
        ttk.Label(cuerpo, text="Orden de boticas:").grid(row=3, column=0, sticky="w", pady=(15, 3))
        ttk.Radiobutton(cuerpo, text="Por nombre", variable=v_orden, value="nombre").grid(row=4, column=0, sticky="w")
        ttk.Radiobutton(cuerpo, text="Por resultado en soles", variable=v_orden, value="ventas").grid(row=5, column=0, sticky="w")
        ttk.Label(cuerpo, text="Carpeta predeterminada:").grid(row=6, column=0, sticky="w", pady=(15, 3))
        fila = ttk.Frame(cuerpo)
        fila.grid(row=7, column=0, sticky="ew")
        fila.columnconfigure(0, weight=1)
        ttk.Entry(fila, textvariable=v_carpeta).grid(row=0, column=0, sticky="ew")
        ttk.Button(
            fila, text="Elegir...",
            command=lambda: v_carpeta.set(filedialog.askdirectory(parent=ventana) or v_carpeta.get())
        ).grid(row=0, column=1, padx=(5, 0))

        def guardar():
            self.opciones_exportacion.update({
                "incluir_resumen": v_resumen.get(),
                "incluir_detalle": v_detalle.get(),
                "incluir_errores": v_errores.get(),
                "orden_boticas": v_orden.get(),
                "carpeta": v_carpeta.get().strip(),
            })
            try:
                preferences.guardar_exportacion(self.opciones_exportacion)
            except OSError as exc:
                self._error_usuario(
                    f"No se pudieron guardar las preferencias: {exc}", "warn"
                )
                return
            ventana.destroy()
            self._set_estado(
                "Opciones de exportación guardadas permanentemente.", "ok"
            )

        ttk.Button(cuerpo, text="Guardar opciones", command=guardar, style="Primario.TButton").grid(row=8, column=0, sticky="e", pady=(18, 0))

    def _construir_lista_labs(self) -> None:
        self.seleccion_labs.clear()
        self.seleccion_productos.clear()
        self.lab_expandido = None
        self.pagina_labs = 0
        self.limpiar_subpanel_productos()

        for lab in self.labs_detectados:
            self.seleccion_labs[lab] = tk.BooleanVar(value=True)
        self._renderizar_pagina_labs()
        self._actualizar_contador_labs()

    def _labs_filtrados(self) -> List[str]:
        termino = self.var_busqueda.get().strip().casefold()
        if not termino:
            return list(self.labs_detectados)
        palabras = termino.split()
        return [lab for lab in self.labs_detectados if all(p in lab.casefold() for p in palabras)]

    def _renderizar_pagina_labs(self) -> None:
        for child in self.frame_labs_inner.winfo_children():
            child.destroy()

        if not self.labs_detectados:
            ttk.Label(
                self.frame_labs_inner,
                text="No se detectaron laboratorios en los datos.",
                style="Estado.TLabel",
            ).grid(row=0, column=0, sticky="w")
            return

        filtrados = self._labs_filtrados()
        total_paginas = max(1, (len(filtrados) + LABS_POR_PAGINA - 1) // LABS_POR_PAGINA)
        self.pagina_labs = min(self.pagina_labs, total_paginas - 1)
        inicio = self.pagina_labs * LABS_POR_PAGINA
        visibles = filtrados[inicio:inicio + LABS_POR_PAGINA]
        self.lbl_pagina_labs.configure(text=f"Página {self.pagina_labs + 1} / {total_paginas} · {len(filtrados)} resultados")
        self.btn_labs_anterior.configure(state="normal" if self.pagina_labs > 0 else "disabled")
        self.btn_labs_siguiente.configure(state="normal" if self.pagina_labs + 1 < total_paginas else "disabled")

        if not visibles:
            ttk.Label(self.frame_labs_inner, text="Sin coincidencias para el filtro.", style="EstadoWarn.TLabel").grid(row=0, column=0, sticky="w")
            return

        for i, lab in enumerate(visibles):
            var = self.seleccion_labs[lab]
            fila = ttk.Frame(self.frame_labs_inner)
            fila.grid(row=i, column=0, sticky="ew")
            fila.columnconfigure(0, weight=1)

            cb = ttk.Checkbutton(
                fila,
                variable=var,
                text=lab,
                command=self._actualizar_contador_labs,
            )
            cb.grid(row=0, column=0, sticky="w")

            info_prod = ""
            if self.tiene_productos:
                n = len(self.productos_por_lab.get(lab, []))
                info_prod = f"Productos: {n}" if n > 0 else "Sin productos"
            ttk.Label(
                fila,
                text=info_prod,
                style="Estado.TLabel",
            ).grid(row=0, column=1, sticky="w", padx=(10, 0))

            try:
                _canonico, regla = lab_config.resolver(lab)
            except Exception:
                regla = "?"
            ttk.Label(
                fila,
                text=f"regla: {regla}",
                style="Estado.TLabel",
            ).grid(row=0, column=2, sticky="w", padx=(10, 0))

            # Botón para abrir el subpanel de productos (solo si hay productos)
            if self.tiene_productos and self.productos_por_lab.get(lab):
                btn = ttk.Button(
                    fila,
                    text="Ver productos",
                    style="Accion.TButton",
                    command=lambda l=lab: self.abrir_subpanel_productos(l),
                )
                btn.grid(row=0, column=3, sticky="w", padx=(10, 0))

    def _cambiar_pagina_labs(self, delta: int) -> None:
        self.pagina_labs = max(0, self.pagina_labs + delta)
        self._renderizar_pagina_labs()

    def _actualizar_contador_labs(self) -> None:
        total = len(self.seleccion_labs)
        elegidos = sum(1 for v in self.seleccion_labs.values() if v.get())
        if total == 0:
            self.lbl_contador_labs.configure(text="")
        else:
            self.lbl_contador_labs.configure(text=f"{elegidos} / {total} seleccionados")

    # ------------------------------------------------------------------ #
    # Perfiles/favoritos
    # ------------------------------------------------------------------ #
    def _leer_perfiles(self) -> Dict:
        try:
            return profiles.cargar_perfiles(self.perfiles_path)
        except (OSError, ValueError, json.JSONDecodeError):
            return {}

    def _guardar_perfiles(self, perfiles_guardados: Dict) -> None:
        profiles.guardar_perfiles(perfiles_guardados, self.perfiles_path)

    def _actualizar_lista_perfiles(self) -> None:
        if hasattr(self, "combo_perfiles"):
            self.combo_perfiles["values"] = sorted(self._leer_perfiles())

    def _capturar_perfil(self) -> Dict:
        perfil = {"laboratorios": [l for l, v in self.seleccion_labs.items() if v.get()],
                  "productos": {}, "metricas": {},
                  "exportacion": dict(self.opciones_exportacion)}
        for lab, productos in self.seleccion_productos.items():
            marcados = [p for p, v in productos.items() if v.get()]
            if lab in self.productos_explicitos or len(marcados) < len(productos):
                perfil["productos"][lab] = marcados
        for lab, metricas in self.seleccion_metricas.items():
            marcadas = [m for m, v in metricas.items() if v.get()]
            if len(marcadas) < len(metricas):
                perfil["metricas"][lab] = marcadas
        return perfil

    def guardar_perfil(self) -> None:
        if not self.labs_detectados:
            self._error_usuario("Primero carga los datos desde el portapapeles.", "warn")
            return
        nombre = self.var_perfil.get().strip() or ""
        nombre = simpledialog.askstring("Guardar favorito", "Nombre del perfil:",
                                        initialvalue=nombre, parent=self.root)
        if not nombre or not nombre.strip():
            return
        perfiles = self._leer_perfiles()
        perfiles[nombre.strip()] = self._capturar_perfil()
        self._guardar_perfiles(perfiles)
        self.var_perfil.set(nombre.strip())
        self._actualizar_lista_perfiles()
        self._set_estado(f"Perfil '{nombre.strip()}' guardado.", "ok")

    def cargar_perfil(self) -> None:
        nombre = self.var_perfil.get().strip()
        perfil = self._leer_perfiles().get(nombre)
        if not perfil:
            self._error_usuario("Selecciona un perfil guardado.", "warn")
            return
        self.opciones_exportacion.update(perfil.get("exportacion", {}))
        self.productos_explicitos.clear()
        self.seleccion_productos.clear()
        self.seleccion_metricas.clear()
        if self.df_crudo is not None and self.tiene_productos:
            for lab in perfil.get("laboratorios", []):
                if lab not in self.seleccion_labs:
                    self.labs_detectados.append(lab)
                    self.seleccion_labs[lab] = tk.BooleanVar(value=False)
        for lab, var in self.seleccion_labs.items():
            var.set(lab in perfil.get("laboratorios", []))
        for lab in perfil.get("laboratorios", []):
            if lab in self.seleccion_labs:
                productos = perfil.get("productos", {}).get(lab)
                if productos is not None:
                    seleccion = set(productos)
                    self.productos_explicitos.add(lab)
                    self.seleccion_productos[lab] = {
                        p: tk.BooleanVar(value=p in seleccion)
                        for p in dict.fromkeys([*productos, *self.productos_por_lab.get(lab, [])])
                    }
                metricas = perfil.get("metricas", {}).get(lab)
                if metricas is not None:
                    seleccion_m = set(metricas)
                    permitidas = lab_config.metricas_configuradas(lab)
                    self.seleccion_metricas[lab] = {
                        m: tk.BooleanVar(value=m in seleccion_m) for m in permitidas
                    }
        self._actualizar_contador_labs()
        self._renderizar_pagina_labs()
        self._set_estado(f"Perfil '{nombre}' cargado.", "ok")

    def eliminar_perfil(self) -> None:
        nombre = self.var_perfil.get().strip()
        if not nombre:
            return
        perfiles = self._leer_perfiles()
        if nombre in perfiles and messagebox.askyesno("Eliminar perfil", f"¿Eliminar '{nombre}'?"):
            del perfiles[nombre]
            self._guardar_perfiles(perfiles)
            self.var_perfil.set("")
            self._actualizar_lista_perfiles()
            self._set_estado(f"Perfil '{nombre}' eliminado.", "info")

    def gestionar_perfiles(self) -> None:
        ventana = tk.Toplevel(self.root)
        ventana.title("Gestión de perfiles")
        ventana.geometry("560x360")
        ventana.transient(self.root)
        cuerpo = ttk.Frame(ventana, padding=12)
        cuerpo.pack(fill="both", expand=True)
        cuerpo.rowconfigure(0, weight=1)
        cuerpo.columnconfigure(0, weight=1)
        lista = tk.Listbox(cuerpo, exportselection=False)
        lista.grid(row=0, column=0, columnspan=4, sticky="nsew")

        def refrescar(seleccionar: str = ""):
            lista.delete(0, "end")
            nombres = sorted(self._leer_perfiles())
            for n in nombres:
                lista.insert("end", n)
            if seleccionar in nombres:
                lista.selection_set(nombres.index(seleccionar))
            self._actualizar_lista_perfiles()

        def elegido() -> str:
            sel = lista.curselection()
            return lista.get(sel[0]) if sel else ""

        def duplicar():
            origen = elegido()
            if not origen:
                return
            nuevo = simpledialog.askstring("Duplicar perfil", "Nombre de la copia:", parent=ventana)
            if not nuevo:
                return
            perfiles = self._leer_perfiles()
            perfiles[nuevo.strip()] = json.loads(json.dumps(perfiles[origen]))
            self._guardar_perfiles(perfiles)
            refrescar(nuevo.strip())

        def renombrar():
            origen = elegido()
            if not origen:
                return
            nuevo = simpledialog.askstring("Renombrar perfil", "Nuevo nombre:", initialvalue=origen, parent=ventana)
            if not nuevo or nuevo.strip() == origen:
                return
            perfiles = self._leer_perfiles()
            perfiles[nuevo.strip()] = perfiles.pop(origen)
            self._guardar_perfiles(perfiles)
            refrescar(nuevo.strip())

        def exportar_perfiles():
            ruta = filedialog.asksaveasfilename(parent=ventana, defaultextension=".json", initialfile="respaldo_perfiles.json", filetypes=[("JSON", "*.json")])
            if ruta:
                Path(ruta).write_text(json.dumps(self._leer_perfiles(), ensure_ascii=False, indent=2), encoding="utf-8")

        def importar_perfiles():
            ruta = filedialog.askopenfilename(parent=ventana, filetypes=[("JSON", "*.json")])
            if not ruta:
                return
            try:
                nuevos = json.loads(Path(ruta).read_text(encoding="utf-8"))
                if not isinstance(nuevos, dict):
                    raise ValueError("El respaldo no contiene perfiles válidos.")
                perfiles = self._leer_perfiles()
                perfiles.update(nuevos)
                self._guardar_perfiles(perfiles)
                refrescar()
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                messagebox.showerror("Importar perfiles", str(exc), parent=ventana)

        ttk.Button(cuerpo, text="Duplicar", command=duplicar).grid(row=1, column=0, sticky="ew", pady=(8, 0), padx=2)
        ttk.Button(cuerpo, text="Renombrar", command=renombrar).grid(row=1, column=1, sticky="ew", pady=(8, 0), padx=2)
        ttk.Button(cuerpo, text="Exportar respaldo", command=exportar_perfiles).grid(row=1, column=2, sticky="ew", pady=(8, 0), padx=2)
        ttk.Button(cuerpo, text="Importar respaldo", command=importar_perfiles).grid(row=1, column=3, sticky="ew", pady=(8, 0), padx=2)
        refrescar()

    # ------------------------------------------------------------------ #
    # Subpanel: productos
    # ------------------------------------------------------------------ #
    def limpiar_subpanel_productos(self) -> None:
        for child in self.frame_productos_inner.winfo_children():
            child.destroy()
        self.lbl_titulo_productos.configure(
            text="Productos: (selecciona un laboratorio)"
        )
        self.lbl_contador_productos.configure(text="")

    def abrir_subpanel_productos(self, lab: str) -> None:
        """Construye (o reconstruye) el subpanel con los productos de `lab`."""
        self.lab_expandido = lab
        self.limpiar_subpanel_productos()
        self._actualizar_estado_subpanel_productos()

        productos = list(dict.fromkeys([
            *self.seleccion_productos.get(lab, {}), *self.productos_por_lab.get(lab, [])
        ]))
        n = len(productos)
        self.lbl_titulo_productos.configure(
            text=f"Productos de {lab}: {n}"
        )

        if n == 0:
            ttk.Label(
                self.frame_productos_inner,
                text="Este laboratorio no tiene productos registrados.",
                style="Estado.TLabel",
            ).grid(row=0, column=0, sticky="w")
            self._actualizar_contador_productos()
            return

        # Usa favoritos configurados; si no existen, marca todos los productos.
        if lab not in self.seleccion_productos:
            favoritos = set(lab_config.perfil(lab).get("productos", []))
            self.seleccion_productos[lab] = {
                p: tk.BooleanVar(value=(p in favoritos if favoritos else True))
                for p in productos
            }
        else:
            # Aseguramos productos nuevos no presentes anteriormente
            existentes = self.seleccion_productos[lab]
            for p in productos:
                if p not in existentes:
                    existentes[p] = tk.BooleanVar(value=True)

        for i, prod in enumerate(productos):
            cb = ttk.Checkbutton(
                self.frame_productos_inner,
                variable=self.seleccion_productos[lab][prod],
                text=prod,
                command=self._actualizar_contador_productos,
            )
            cb.grid(row=i, column=0, sticky="w")

        # --- Selector de metricas para este lab ---
        # Solo se muestran las metricas permitidas por la regla del lab;
        # todas marcadas por defecto (= comportamiento V2).
        try:
            _canonico, regla = lab_config.resolver(lab)
            metricas_permitidas = lab_config.metricas_configuradas(lab)
        except Exception:
            metricas_permitidas = list(processing.METRICAS)

        if metricas_permitidas:
            separador = ttk.Separator(self.frame_productos_inner, orient="horizontal")
            separador.grid(row=len(productos), column=0, sticky="ew", pady=(10, 5))

            ttk.Label(
                self.frame_productos_inner,
                text="Métricas a mostrar:",
                style="Titulo.TLabel",
            ).grid(row=len(productos) + 1, column=0, sticky="w")

            fila_metricas = ttk.Frame(self.frame_productos_inner)
            fila_metricas.grid(row=len(productos) + 2, column=0, sticky="w", pady=(2, 0))

            # Inicializa selección de métricas para este lab (todas marcadas)
            if lab not in self.seleccion_metricas:
                self.seleccion_metricas[lab] = {
                    m: tk.BooleanVar(value=True) for m in metricas_permitidas
                }
            else:
                existentes = self.seleccion_metricas[lab]
                for m in metricas_permitidas:
                    if m not in existentes:
                        existentes[m] = tk.BooleanVar(value=True)

            for j, m in enumerate(metricas_permitidas):
                cbm = ttk.Checkbutton(
                    fila_metricas,
                    variable=self.seleccion_metricas[lab][m],
                    text=m,
                )
                cbm.grid(row=0, column=j, sticky="w", padx=(0, 10))

        self._actualizar_contador_productos()

    def _actualizar_contador_productos(self) -> None:
        if self.lab_expandido is None:
            self.lbl_contador_productos.configure(text="")
            return
        d = self.seleccion_productos.get(self.lab_expandido, {})
        total = len(d)
        if total == 0:
            self.lbl_contador_productos.configure(text="0 productos")
            return
        elegidos = sum(1 for v in d.values() if v.get())
        self.lbl_contador_productos.configure(
            text=f"{elegidos} / {total} productos seleccionados"
        )

    def on_seleccionar_todos_productos(self) -> None:
        if self.lab_expandido is None:
            return
        termino = self.var_busqueda_productos.get().strip().upper()
        d = self.seleccion_productos.get(self.lab_expandido, {})
        for prod, var in d.items():
            if not termino or termino in prod.upper():
                var.set(True)
        self._actualizar_contador_productos()
        self._aplicar_filtro_busqueda_productos()

    def on_limpiar_productos(self) -> None:
        if self.lab_expandido is None:
            return
        termino = self.var_busqueda_productos.get().strip().upper()
        d = self.seleccion_productos.get(self.lab_expandido, {})
        for prod, var in d.items():
            if not termino or termino in prod.upper():
                var.set(False)
        self._actualizar_contador_productos()
        self._aplicar_filtro_busqueda_productos()

    def _aplicar_filtro_busqueda_productos(self) -> None:
        if self.lab_expandido is None:
            return
        termino = self.var_busqueda_productos.get().strip().upper()
        for child in self.frame_productos_inner.winfo_children():
            try:
                txt = str(child.cget("text"))
            except (tk.TclError, AttributeError):
                txt = ""
            visible = not termino or termino in txt.upper()
            child.grid() if visible else child.grid_remove()

    # ------------------------------------------------------------------ #
    # Accion: Seleccion laboratorios
    # ------------------------------------------------------------------ #
    def on_seleccionar_todos(self) -> None:
        filtrados = set(self._labs_filtrados())
        for lab, var in self.seleccion_labs.items():
            if lab in filtrados:
                var.set(True)
        self._actualizar_contador_labs()

    def on_limpiar_seleccion(self) -> None:
        filtrados = set(self._labs_filtrados())
        for lab, var in self.seleccion_labs.items():
            if lab in filtrados:
                var.set(False)
        self._actualizar_contador_labs()

    def _aplicar_filtro_busqueda(self) -> None:
        """Filtra por varias palabras y renderiza solo una página de resultados."""
        self.pagina_labs = 0
        self._renderizar_pagina_labs()

    # ------------------------------------------------------------------ #
    # Accion: Analizar ventas
    # ------------------------------------------------------------------ #
    def on_analizar(self) -> None:
        if self.tarea_en_curso:
            return
        if self.df_crudo is None:
            self._error_usuario("Primero carga los datos desde el portapapeles.", "warn")
            return

        labs_sel = [lab for lab, v in self.seleccion_labs.items() if v.get()]
        if not labs_sel:
            self._error_usuario(
                "Selecciona al menos un laboratorio antes de analizar.", "warn"
            )
            return

        # Construir dict de productos por laboratorio (SOLO para labs con
        # subpanel abierto y al menos un desmarcado|marcado explicito).
        # Para labs sin subpanel abierto o con todos marcados, no se.include
        # en el dict -> el motor usara todos sus productos (V1 behavior).
        productos_por_lab_motor: Dict[str, List[str]] = {}
        if self.tiene_productos:
            for lab in labs_sel:
                d = self.seleccion_productos.get(lab)
                if d is None:
                    continue
                # Convertimos a lista de productos marcados
                marcados = [p for p, v in d.items() if v.get()]
                # Solo se pasa al motor si hay al menos un desmarcado
                # (si todos estan marcados, no filtrar = mismo resultado, evita PASAR nada)
                if lab in self.productos_explicitos or len(marcados) < len(d):
                    productos_por_lab_motor[lab] = marcados

        # Construir dict de metricas por laboratorio (SOLO para labs con
        # al menos una metrica desmarcada). Si todas marcadas -> no se pasa
        # para ese lab y el motor usa la regla completa (V2 behavior).
        metricas_por_lab_motor: Dict[str, List[str]] = {}
        for lab in labs_sel:
            dm = self.seleccion_metricas.get(lab)
            if dm is None:
                continue
            marcadas = [m for m, v in dm.items() if v.get()]
            if len(marcadas) < len(dm):
                metricas_por_lab_motor[lab] = marcadas

        self._set_estado("Analizando ventas...", "info")
        self.root.update_idletasks()

        # Modo productos: se activa solo cuando hay seleccion de productos.
        # En ese modo la matriz muestra una columna por producto (CantF) y
        # el TOTAL al final; no se genera la hoja Detalle_Productos.
        modo_productos = self.tiene_productos and bool(productos_por_lab_motor)
        boticas_obligatorias = lab_config.boticas_fijas()

        def trabajo():
            if modo_productos:
                tabla = processing.generar_matriz_productos(
                    self.df_crudo,
                    labs_sel,
                    productos_por_lab_motor,
                    metricas_por_lab=(
                        metricas_por_lab_motor if metricas_por_lab_motor else None
                    ),
                    boticas_obligatorias=boticas_obligatorias,
                )
                detalle = None
            else:
                tabla = processing.generar_matriz(
                    self.df_crudo,
                    labs_sel,
                    productos_por_lab=(
                        productos_por_lab_motor if productos_por_lab_motor else None
                    ),
                    metricas_por_lab=(
                        metricas_por_lab_motor if metricas_por_lab_motor else None
                    ),
                    boticas_obligatorias=boticas_obligatorias,
                )
                detalle = None
                if self.tiene_productos:
                    detalle = processing.construir_detalle(
                        self.df_crudo,
                        labs_sel,
                        productos_por_lab=(
                            productos_por_lab_motor
                            if productos_por_lab_motor
                            else None
                        ),
                        metricas_por_lab=(
                            metricas_por_lab_motor
                            if metricas_por_lab_motor
                            else None
                        ),
                    )

            res = processing.resumen_matriz(tabla)
            totalp = self._calcular_totalp(tabla)

            return (tabla, res, totalp, labs_sel, productos_por_lab_motor,
                    metricas_por_lab_motor, detalle)

        self._ejecutar_tarea(
            trabajo, lambda resultado: self._on_analisis_completado(*resultado),
            "Analizando ventas...",
        )

    def _calcular_totalp(self, tabla: pd.DataFrame) -> float:
        """Suma la columna TotalP del TOTAL (o la ultima fila TOTAL)."""
        try:
            cols_totalp = [c for c in tabla.columns if c[1] == "TotalP" and c[0] == "TOTAL"]
            if not cols_totalp:
                cols_totalp = [c for c in tabla.columns if c[1] == "TotalP"]
            if not cols_totalp:
                return 0.0
            serie = tabla[cols_totalp[0]]
            if "TOTAL" in serie.index:
                return float(serie.loc["TOTAL"])
            return float(serie.sum())
        except Exception:
            return 0.0

    def _on_analisis_completado(
        self,
        tabla: pd.DataFrame,
        res: Dict[str, int],
        totalp: float,
        labs_sel: List[str],
        productos_filtrados: Dict[str, List[str]],
        metricas_filtradas: Dict[str, List[str]],
        detalle: Optional[pd.DataFrame],
    ) -> None:
        self.tabla_resultado = tabla
        self.detalle_resultado = detalle
        self.ultimos_resumen = res

        # Info de productos filtrados
        if productos_filtrados:
            total_prod_sel = sum(len(v) for v in productos_filtrados.values())
            info_prod = f" · Productos filtrados: {total_prod_sel}"
        else:
            info_prod = " · Productos: todos"

        # Info de metricas filtradas
        if metricas_filtradas:
            info_metricas = (
                f" · Métricas filtradas en {len(metricas_filtradas)} lab(s)"
            )
        else:
            info_metricas = " · Métricas: por regla"

        # Info de detalle
        if detalle is not None and not detalle.empty:
            info_det = f" · Detalle: {len(detalle)} filas"
        else:
            info_det = ""

        texto = (
            f"Análisis completado: "
            f"{len(labs_sel)} laboratorio(s) · "
            f"{res['boticas']} boticas · "
            f"{res['filas']} filas en la matriz"
            f"{info_prod}"
            f"{info_metricas}"
            f"{info_det}"
            f" · TotalP total: {FORMATO_SOLES_UI.format(totalp)}"
        )
        self.lbl_resumen.configure(text=texto)
        self._set_estado("Análisis completado.", "ok")

        self._poblar_vista_previa(tabla)
        self._actualizar_controles()

    # ------------------------------------------------------------------ #
    # Vista previa (Treeview)
    # ------------------------------------------------------------------ #
    def _poblar_vista_previa(self, tabla: pd.DataFrame) -> None:
        # Aplanar el MultiIndex de columnas; en modo productos (3 niveles)
        # se muestra "LAB · PRODUCTO" y para TOTAL "TOTAL · Métrica".
        columnas_planas = ["Botica"]
        for col in tabla.columns:
            if len(col) >= 3 and str(col[2]) != "":
                columnas_planas.append(f"{col[0]} · {col[2]}")
            else:
                columnas_planas.append(f"{col[0]} · {col[1]}")

        # Limpiar
        self.tree.delete(*self.tree.get_children())
        self.tree.configure(columns=columnas_planas)

        # Cabeceras
        for cname in columnas_planas:
            self.tree.heading(cname, text=cname)
            self.tree.column(cname, width=120, anchor="e", stretch=True)
        self.tree.column("Botica", anchor="w", width=140)

        # Filas (limitadas)
        limite = VISTA_PREVIA_FILAS
        df_view = tabla.head(limite)
        for idx, fila in df_view.iterrows():
            valores = [str(idx)]
            for col in tabla.columns:
                val = fila[col]
                if col == ("__placeholder__",):
                    continue
                if pd.isna(val):
                    valores.append("")
                    continue
                if col[1] == "TotalP":
                    valores.append(FORMATO_SOLES_UI.format(float(val)))
                else:
                    valores.append(f"{int(val):,}".replace(",", "."))
            self.tree.insert("", "end", values=valores)

        total_filas = len(tabla)
        if total_filas > limite:
            info = f"Mostrando {limite} de {total_filas} filas."
        else:
            info = f"{total_filas} filas."
        self.lbl_vista_previa_info.configure(text=info)

        self._ajustar_ancho_columnas_tree()

    def _ajustar_ancho_columnas_tree(self) -> None:
        # Ancho simple: basado en el contenido visible (limita coste).
        for col in self.tree["columns"]:
            max_len = len(str(col))
            for item in self.tree.get_children()[:50]:
                val = self.tree.set(item, col)
                if len(val) > max_len:
                    max_len = len(val)
            self.tree.column(col, width=min(max_len * 8 + 12, 280))

    # ------------------------------------------------------------------ #
    # Accion: Exportar a Excel
    # ------------------------------------------------------------------ #
    def _carpeta_exportacion(self) -> Path:
        configurada = str(self.opciones_exportacion.get("carpeta", "")).strip()
        return Path(configurada).expanduser().resolve() if configurada else raiz_aplicacion() / "Reportes"

    def _tabla_ordenada_para_exportar(self) -> pd.DataFrame:
        tabla = self.tabla_resultado.copy()
        filas = [x for x in tabla.index if str(x) != "TOTAL"]
        if self.opciones_exportacion.get("orden_boticas") == "ventas":
            cols = [c for c in tabla.columns if len(c) >= 2 and c[0] == "TOTAL" and c[1] == "TotalP"]
            if cols:
                filas = tabla.loc[filas, cols[0]].sort_values(ascending=False).index.tolist()
        else:
            filas = sorted(filas, key=lambda x: str(x).casefold())
        if "TOTAL" in tabla.index:
            filas.append("TOTAL")
        return tabla.loc[filas]

    def on_exportar(self) -> None:
        if self.tarea_en_curso:
            return
        if self.tabla_resultado is None:
            self._error_usuario("Primero analiza las ventas antes de exportar.", "warn")
            return

        # Nombre unico: perfil (si existe) + fecha y hora de la exportacion.
        perfil = self.var_perfil.get().strip() if hasattr(self, "var_perfil") else ""
        base = perfil or "Matriz_Ventas"
        base = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", base).strip(" ._")[:80] or "Matriz_Ventas"
        marca_tiempo = datetime.now().strftime("%Y-%m-%d_%H%M%S_%f")
        nombre_sugerido = f"{base}_{marca_tiempo}.xlsx"
        carpeta = self._carpeta_exportacion()

        def trabajo():
            # La matriz por productos ya contiene el desglose en sus columnas.
            tabla_exportar = self._tabla_ordenada_para_exportar()
            detalle = self.detalle_resultado
            if tabla_exportar.columns.nlevels >= 3:
                detalle = None
            carpeta.mkdir(parents=True, exist_ok=True)
            ruta = carpeta / nombre_sugerido
            # Reserva exclusiva: ni otra instancia ni dos clics sobrescriben un reporte.
            numero = 1
            while True:
                try:
                    with ruta.open("xb"):
                        pass
                    break
                except FileExistsError:
                    numero += 1
                    ruta = carpeta / f"{Path(nombre_sugerido).stem}_{numero}.xlsx"
            try:
                excel_export.exportar(
                    tabla_exportar,
                    ruta,
                    detalle_productos=detalle,
                    errores_detectados=(
                        self.errores_detectados
                        if self.opciones_exportacion.get("incluir_errores") else None
                    ),
                    incluir_resumen=bool(self.opciones_exportacion.get("incluir_resumen")),
                    incluir_detalle=bool(self.opciones_exportacion.get("incluir_detalle")),
                    avance_concurso=self.avance_concurso,
                    nombre_concurso=self.concurso_seleccionado,
                )
            except Exception:
                # Solo se limpia el archivo nuevo reservado por esta exportación.
                try:
                    ruta.unlink()
                except OSError:
                    pass
                raise
            return str(ruta)

        self._ejecutar_tarea(
            trabajo, self._on_exportacion_ok, f"Guardando {nombre_sugerido}...",
        )

    def _on_exportacion_ok(self, ruta: str) -> None:
        # Recordar la carpeta efectiva también cuando se usó Reportes por defecto.
        self.opciones_exportacion["carpeta"] = str(Path(ruta).resolve().parent)
        try:
            preferences.guardar_exportacion(self.opciones_exportacion)
        except OSError:
            pass
        self._set_estado(f"Guardado: {ruta}", "ok")
        try:
            import os
            import subprocess
            if os.name == "nt":
                os.startfile(str(Path(ruta).resolve()))
            else:
                subprocess.Popen(["xdg-open", str(Path(ruta).resolve())])
        except OSError as exc:
            self._error_usuario(
                f"El reporte se guardó correctamente en:\n{ruta}\n\n"
                f"No se pudo abrir automáticamente en Excel. Puedes abrirlo desde esa ruta.\n{exc}",
                "warn",
            )

    # ------------------------------------------------------------------ #
    # Utilidad: errores de usuario
    # ------------------------------------------------------------------ #
    def _error_usuario(self, mensaje: str, nivel: str = "err") -> None:
        self._set_estado(mensaje, nivel)
        if nivel == "err":
            messagebox.showerror("Error", mensaje)
        elif nivel == "warn":
            messagebox.showwarning("Aviso", mensaje)


# --------------------------------------------------------------------------- #
# Entry point del modulo UI
# --------------------------------------------------------------------------- #


def abrir_ventana() -> None:
    try:
        import tkinter as tk  # noqa: F401 (asegura disponibilidad)
    except ImportError:
        print("tkinter no disponible en este Python.")
        print("En Windows: instala Python 3.12+ desde python.org (incluye tkinter).")
        return

    root = tk.Tk()
    AplicacionVentas(root)
    root.mainloop()
