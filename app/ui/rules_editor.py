"""Editor visual de config/laboratorios.json."""

from __future__ import annotations

import json
import tkinter as tk
from tkinter import messagebox, ttk

from app.core import lab_config


class EditorReglas:
    def __init__(self, parent: tk.Misc, al_guardar=None) -> None:
        self.parent = parent
        self.al_guardar = al_guardar
        self.cfg = self._leer()
        self.ventana = tk.Toplevel(parent)
        self.ventana.title("Editor de reglas de laboratorios")
        self.ventana.geometry("1050x560")
        self.ventana.transient(parent)
        self._construir()
        self._refrescar()

    def _leer(self) -> dict:
        return lab_config.configuracion_editable()

    def _guardar(self) -> None:
        lab_config.guardar_configuracion(self.cfg)
        if self.al_guardar:
            self.al_guardar()

    def _construir(self) -> None:
        cuerpo = ttk.Frame(self.ventana, padding=10)
        cuerpo.pack(fill="both", expand=True)
        cuerpo.rowconfigure(0, weight=1)
        cuerpo.columnconfigure(0, weight=1)
        columnas = ("clave", "mostrar", "metricas", "aliases", "productos", "agrupar", "orden")
        self.tree = ttk.Treeview(cuerpo, columns=columnas, show="headings")
        titulos = {
            "clave": "Laboratorio", "mostrar": "Nombre para mostrar",
            "metricas": "Métricas", "aliases": "Alias",
            "productos": "Productos favoritos", "agrupar": "Agrupar", "orden": "Orden",
        }
        for col in columnas:
            self.tree.heading(col, text=titulos[col])
            self.tree.column(col, width=145 if col != "aliases" else 260, anchor="w")
        self.tree.grid(row=0, column=0, sticky="nsew")
        sb = ttk.Scrollbar(cuerpo, orient="vertical", command=self.tree.yview)
        sb.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=sb.set)
        botones = ttk.Frame(cuerpo)
        botones.grid(row=1, column=0, sticky="w", pady=(10, 0))
        ttk.Button(botones, text="Nuevo laboratorio", command=lambda: self._editar(None)).pack(side="left")
        ttk.Button(botones, text="Editar seleccionado", command=self._editar_seleccion).pack(side="left", padx=5)
        ttk.Button(botones, text="Eliminar", command=self._eliminar).pack(side="left")
        ttk.Button(botones, text="Cerrar", command=self.ventana.destroy).pack(side="left", padx=(20, 0))
        self.tree.bind("<Double-1>", lambda _e: self._editar_seleccion())

    def _refrescar(self) -> None:
        self.tree.delete(*self.tree.get_children())
        orden = self.cfg.get("orden_preferido", [])
        for clave, definicion in self.cfg.get("overrides", {}).items():
            aliases = definicion.get("aliases", [])
            mostrar = definicion.get("nombre_mostrar") or (aliases[0] if aliases else clave)
            try:
                posicion = orden.index(mostrar) + 1
            except ValueError:
                posicion = ""
            self.tree.insert("", "end", iid=clave, values=(
                clave, mostrar, ", ".join(definicion.get("metricas", [])),
                ", ".join(aliases), len(definicion.get("productos", [])),
                "Sí" if lab_config.perfil(clave).get("agrupar_productos") else "No",
                posicion,
            ))

    def _editar_seleccion(self) -> None:
        sel = self.tree.selection()
        if sel:
            self._editar(sel[0])

    def _editar(self, clave_original: str | None) -> None:
        definicion = self.cfg.get("overrides", {}).get(clave_original, {})
        aliases = definicion.get("aliases", [])
        dialogo = tk.Toplevel(self.ventana)
        dialogo.title("Laboratorio")
        dialogo.geometry("650x610")
        dialogo.transient(self.ventana)
        dialogo.grab_set()
        frame = ttk.Frame(dialogo, padding=15)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(1, weight=1)

        v_clave = tk.StringVar(value=clave_original or "")
        v_mostrar = tk.StringVar(value=definicion.get("nombre_mostrar") or (aliases[0] if aliases else ""))
        v_aliases = tk.StringVar(value=", ".join(aliases))
        v_orden = tk.StringVar(value="")
        orden_actual = self.cfg.get("orden_preferido", [])
        if v_mostrar.get() in orden_actual:
            v_orden.set(str(orden_actual.index(v_mostrar.get()) + 1))
        metricas_actuales = definicion.get("metricas", [])
        vm = {m: tk.BooleanVar(value=m in metricas_actuales) for m in ("CantE", "CantF", "TotalP")}
        v_agrupar = tk.BooleanVar(
            value=lab_config.perfil(clave_original).get("agrupar_productos", False)
            if clave_original else False
        )
        v_unidades = tk.BooleanVar(
            value=lab_config.perfil(clave_original).get("unidades_combinadas", False)
            if clave_original else False
        )

        campos = [("Identificador:", v_clave), ("Nombre para mostrar:", v_mostrar), ("Alias separados por coma:", v_aliases)]
        for fila, (texto, variable) in enumerate(campos):
            ttk.Label(frame, text=texto).grid(row=fila, column=0, sticky="w", pady=5)
            ttk.Entry(frame, textvariable=variable).grid(row=fila, column=1, sticky="ew", pady=5)
        ttk.Label(frame, text="Métricas permitidas:").grid(row=3, column=0, sticky="nw", pady=5)
        fm = ttk.Frame(frame)
        fm.grid(row=3, column=1, sticky="w", pady=5)
        for m in vm:
            ttk.Checkbutton(fm, text=m, variable=vm[m]).pack(side="left", padx=(0, 10))
        ttk.Label(frame, text="Productos favoritos (uno por línea):").grid(row=4, column=0, sticky="nw", pady=5)
        txt_productos = tk.Text(frame, height=12, width=45)
        txt_productos.grid(row=4, column=1, sticky="nsew", pady=5)
        txt_productos.insert("1.0", "\n".join(definicion.get("productos", [])))
        frame.rowconfigure(4, weight=1)
        ttk.Checkbutton(
            frame,
            text="Agrupar los productos seleccionados en una sola columna",
            variable=v_agrupar,
        ).grid(row=5, column=1, sticky="w", pady=5)
        ttk.Checkbutton(
            frame,
            text="CantF incluye cajas completas (CantE × presentación + CantF)",
            variable=v_unidades,
        ).grid(row=6, column=1, sticky="w", pady=5)
        ttk.Label(frame, text="Posición en columnas:").grid(row=7, column=0, sticky="w", pady=5)
        ttk.Entry(frame, textvariable=v_orden, width=10).grid(row=7, column=1, sticky="w", pady=5)

        def guardar():
            clave = v_clave.get().strip().upper()
            mostrar = v_mostrar.get().strip()
            metricas = [m for m, var in vm.items() if var.get()]
            if not clave or not mostrar or not metricas:
                messagebox.showwarning("Laboratorio", "Identificador, nombre y al menos una métrica son obligatorios.", parent=dialogo)
                return
            lista_aliases = [x.strip() for x in v_aliases.get().split(",") if x.strip()]
            if mostrar not in lista_aliases:
                lista_aliases.insert(0, mostrar)
            # El identificador suele ser el nombre exacto que llega desde el
            # sistema de ventas. Siempre debe mantenerse como alias de origen.
            if clave not in lista_aliases:
                lista_aliases.append(clave)
            productos = [x.strip() for x in txt_productos.get("1.0", "end").splitlines() if x.strip()]
            if clave_original and clave_original != clave:
                self.cfg["overrides"].pop(clave_original, None)
            regla = self._regla_base(metricas)
            self.cfg.setdefault("overrides", {})[clave] = {
                "regla": regla, "aliases": lista_aliases,
                "nombre_mostrar": mostrar, "metricas": metricas,
                "productos": productos, "meta": definicion.get("meta", 0),
                "agrupar_productos": v_agrupar.get(),
                "unidades_combinadas": v_unidades.get(),
            }
            orden = [x for x in self.cfg.get("orden_preferido", []) if x not in aliases and x != mostrar]
            try:
                pos = max(0, int(v_orden.get()) - 1)
                orden.insert(min(pos, len(orden)), mostrar)
            except ValueError:
                orden.append(mostrar)
            self.cfg["orden_preferido"] = orden
            self._guardar()
            self._refrescar()
            dialogo.destroy()

        ttk.Button(frame, text="Guardar laboratorio", command=guardar).grid(row=8, column=1, sticky="e", pady=(12, 0))

    @staticmethod
    def _regla_base(metricas: list[str]) -> str:
        conjunto = set(metricas)
        if conjunto == {"CantE"}:
            return "solo_cante"
        if conjunto == {"TotalP"}:
            return "solo_totalp"
        if conjunto == {"CantE", "CantF"}:
            return "cante_cantf"
        return "todas"

    def _eliminar(self) -> None:
        sel = self.tree.selection()
        if not sel:
            return
        clave = sel[0]
        if messagebox.askyesno("Eliminar", f"¿Eliminar la configuración de {clave}?", parent=self.ventana):
            definicion = self.cfg.get("overrides", {}).pop(clave, {})
            aliases = definicion.get("aliases", [])
            self.cfg["orden_preferido"] = [x for x in self.cfg.get("orden_preferido", []) if x not in aliases]
            self._guardar()
            self._refrescar()
