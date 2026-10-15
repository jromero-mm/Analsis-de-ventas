"""Entry point de la aplicacion V1.

Modo de uso:
    python -m app.main            # abre ventana Tk (placeholder)
    python -m app.main --selftest # corre un self-test sin UI (sin portapapeles)

En la etapa 1 solo se garantiza que importe y arranque. La logica de
negocio se prueba mediante:
    python -m app.main --selftest
y por los tests en tests/ (pytest, opcional).
"""

from __future__ import annotations

import sys
from pathlib import Path

from app.paths import preparar_tkinter_empaquetado

preparar_tkinter_empaquetado()


def _run_selftest() -> int:
    """Test end-to-end sobre datos sinteticos; no requiere portapapeles ni UI."""
    import pandas as pd

    from app.core.data_source import detectar_laboratorios, validar_columnas
    from app.core.processing import generar_matriz, resumen_matriz
    from app.core.excel_export import exportar
    from app.core.lab_config import (
        listar_reglas_disponibles,
        metricas_a_conservar,
        orden_preferido,
        regla_total,
        resolver,
    )

    print("[1/6] Importaciones OK")

    # Datos sinteticos con los 4 laboratorios conocidos + uno extra
    filas = []
    labs = [
        ("LABORATORIO ALFA", 2, 3, 150.50),
        ("LABORATORIO BETA", 1, 1, 80.20),
        ("LABORATORIO GAMMA", 4, 2, 320.75),
        ("LABORATORIO DELTA", 0, 5, 410.00),
        ("LABORATORIO EPSILON", 3, 3, 220.10),
    ]
    for botica in ["B001", "B002", "B003"]:
        for lab, ce, cf, tp in labs:
            filas.append({
                "Botica": botica,
                "Laboratorio": lab,
                "CantE": ce,
                "CantF": cf,
                "TotalP": tp,
            })
    df = pd.DataFrame(filas)

    validar_columnas(df)
    print(f"[2/6] Columnas validadas OK. Filas={len(df)}, Boticas={df['Botica'].nunique()}")

    labs_detectados = detectar_laboratorios(df)
    print(f"[3/6] Laboratorios detectados: {labs_detectados}")
    assert "LABORATORIO ALFA" in labs_detectados
    assert "LABORATORIO EPSILON" in labs_detectados  # laboratorio extra (regla por defecto)

    # La configuración es editable: comprobamos consistencia, no nombres
    # históricos que el usuario puede retirar de un mes a otro.
    for laboratorio in labs_detectados:
        canonico, regla = resolver(laboratorio)
        assert canonico.strip(), laboratorio
        assert regla in listar_reglas_disponibles(), (laboratorio, regla)

    print(f"[4/6] resolver OK. regla_total={regla_total()}, orden_preferido={orden_preferido()}")

    # Procesar matriz (sin seleccion -> todos)
    tabla = generar_matriz(df)
    res = resumen_matriz(tabla)
    print(f"[5/6] Matriz generada: {res}")

    # Comprobar que TOTAL conserva exactamente las métricas configuradas.
    cols = tabla.columns
    tot_cols = [c for c in cols if c[0] == "TOTAL"]
    metricas_tot = {c[1] for c in tot_cols}
    esperadas_total = set(metricas_a_conservar(regla_total()))
    assert metricas_tot == esperadas_total, (metricas_tot, esperadas_total)
    print(f"     TOTAL conserva: {sorted(metricas_tot)}")

    # Todos los laboratorios detectados deben conservar al menos una columna.
    labs_salida = {c[0] for c in cols if c[0] != "TOTAL"}
    assert labs_salida, "La matriz no contiene laboratorios."
    print(f"     Laboratorios resueltos dinámicamente: {sorted(labs_salida)}")

    # Exportar (en directorio temporal para no pisar el del usuario)
    import tempfile
    destino = Path(tempfile.gettempdir()) / "matriz_selftest.xlsx"
    ruta_exportada = exportar(tabla, destino)
    print(f"[6/6] Excel exportado: {ruta_exportada}")
    Path(ruta_exportada).unlink()  # limpiar
    print("OK: selftest completo.")
    return 0


def main(argv: list[str]) -> int:
    if "--selftest" in argv:
        return _run_selftest()
    # Default: abrir ventana placeholder
    from app.ui.main_window import abrir_ventana
    abrir_ventana()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
