"""Opciones de lectura antes de incorporar un archivo de ventas."""

from pathlib import Path
import tkinter as tk
from tkinter import simpledialog, ttk


class DialogoImportacion(simpledialog.Dialog):
    def __init__(self, parent, ruta: str, hojas: list[str] | None = None):
        self.ruta = ruta
        self.hojas = hojas
        super().__init__(parent, title="Importar ventas")

    def body(self, master):
        ttk.Label(master, text=Path(self.ruta).name, wraplength=460).grid(
            row=0, column=0, sticky="w", padx=10, pady=10)
        ttk.Label(
            master,
            text="La primera fila debe contener los encabezados: Botica, Laboratorio, "
                 "CantE, CantF y TotalP. Descripción Producto y Presentación son opcionales.",
            wraplength=460,
        ).grid(row=1, column=0, sticky="w", padx=10, pady=(0, 12))
        if self.hojas is not None:
            ttk.Label(master, text="Hoja con las ventas:").grid(row=2, column=0, sticky="w", padx=10)
            self.seleccion = tk.StringVar(master, value=self.hojas[0])
            control = ttk.Combobox(master, textvariable=self.seleccion, values=self.hojas,
                                   state="readonly", width=48)
            control.grid(row=3, column=0, sticky="ew", padx=10, pady=(5, 10))
        else:
            ttk.Label(master, text="Separador decimal de los importes:").grid(
                row=2, column=0, sticky="w", padx=10)
            self.seleccion = tk.StringVar(master, value=".")
            control = ttk.Radiobutton(master, text="Punto: 1234.50 o 1,234.50",
                                       variable=self.seleccion, value=".")
            control.grid(row=3, column=0, sticky="w", padx=10, pady=5)
            ttk.Radiobutton(master, text="Coma: 1234,50 o 1.234,50",
                            variable=self.seleccion, value=",").grid(
                row=4, column=0, sticky="w", padx=10, pady=(0, 10))
            ttk.Label(master, text="El separador de columnas se detecta automáticamente.").grid(
                row=5, column=0, sticky="w", padx=10, pady=(0, 10))
        return control

    def buttonbox(self):
        barra = ttk.Frame(self)
        ttk.Button(barra, text="Importar", command=self.ok).pack(side="left", padx=5)
        ttk.Button(barra, text="Cancelar", command=self.cancel).pack(side="left", padx=5)
        barra.pack(pady=10)
        self.bind("<Return>", self.ok)
        self.bind("<Escape>", self.cancel)

    def apply(self):
        self.result = self.seleccion.get()
