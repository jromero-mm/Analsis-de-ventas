"""Importación real de archivos: formatos, hojas y errores recuperables."""

import threading
import time
from types import SimpleNamespace

import pandas as pd
import pytest

from app.core import data_source, processing, excel_export
from app.ui.main_window import AplicacionVentas


def datos():
    return pd.DataFrame([{
        "Botica": "001", "Laboratorio": "LAB PRUEBA",
        "Descripción Producto": "Solución, frasco; 100 ml",
        "CantE": 2, "CantF": 3, "TotalP": 1234.50, "Presentación": 10,
    }])


@pytest.mark.parametrize("sep,encoding,decimal", [
    (",", "utf-8-sig", "."), (";", "cp1252", ","), ("\t", "utf-8", "."),
])
def test_csv_preserva_codigos_acentos_y_decimales(tmp_path, sep, encoding, decimal):
    ruta = tmp_path / "ventas.csv"
    datos().to_csv(ruta, sep=sep, encoding=encoding, decimal=decimal, index=False)
    resultado = data_source.read_csv(str(ruta), decimal=decimal)
    assert resultado.n_filas == 1
    assert resultado.dataframe.loc[0, "Botica"] == "001"
    assert resultado.dataframe.loc[0, "TotalP"] == 1234.50
    assert resultado.productos_por_lab["LAB PRUEBA"] == ["Solución, frasco; 100 ml"]
    assert data_source.calcular_unidades_vendidas(resultado.dataframe).iloc[0] == 23


def test_csv_importe_con_moneda_y_miles(tmp_path):
    ruta = tmp_path / "ventas.csv"
    tabla = datos()
    tabla["TotalP"] = "S/ 1.234,50"
    tabla.to_csv(ruta, sep=";", index=False)
    assert data_source.read_csv(str(ruta), decimal=",").dataframe.loc[0, "TotalP"] == 1234.50


def test_excel_selecciona_segunda_hoja_y_exporta(tmp_path):
    ruta = tmp_path / "ventas.xlsx"
    with pd.ExcelWriter(ruta) as libro:
        pd.DataFrame({"Instrucciones": ["Usar la hoja Ventas"]}).to_excel(libro, sheet_name="Notas", index=False)
        datos().to_excel(libro, sheet_name="Ventas", index=False)
    assert data_source.listar_hojas_excel(str(ruta)) == ["Notas", "Ventas"]
    resultado = data_source.read_excel(str(ruta), hoja="Ventas")
    assert resultado.dataframe.loc[0, "Botica"] == "001"
    tabla = processing.generar_matriz(resultado.dataframe)
    assert tabla.loc["TOTAL", ("TOTAL", "TotalP")] == 1234.50
    salida = tmp_path / "resultado.xlsx"
    excel_export.exportar(tabla, salida)
    with pd.ExcelFile(salida) as libro:
        assert "Matriz" in libro.sheet_names
    with pytest.raises(data_source.ColumnasFaltantes):
        data_source.read_excel(str(ruta), hoja="Notas")
    with pytest.raises(data_source.ErrorLectura, match="hoja"):
        data_source.read_excel(str(ruta), hoja="Ausente")


@pytest.mark.parametrize("extension", ["csv", "xlsx"])
def test_rechaza_archivo_sin_registros(tmp_path, extension):
    ruta = tmp_path / f"vacio.{extension}"
    vacio = datos().iloc[:0]
    if extension == "csv":
        vacio.to_csv(ruta, index=False)
        leer = data_source.read_csv
    else:
        vacio.to_excel(ruta, index=False)
        leer = data_source.read_excel
    with pytest.raises(data_source.ErrorLectura, match="no contiene registros"):
        leer(str(ruta))


def test_rechaza_csv_mal_formado_y_excel_corrupto(tmp_path):
    ruta = tmp_path / "roto.csv"
    ruta.write_text('Botica,Laboratorio,CantE,CantF,TotalP\n001,"sin cierre,1,2,3\n', encoding="utf-8")
    with pytest.raises(data_source.ErrorLectura, match="No se pudo leer"):
        data_source.read_csv(str(ruta))
    ruta_excel = tmp_path / "roto.xlsx"
    ruta_excel.write_text("No es un Excel", encoding="utf-8")
    with pytest.raises(data_source.ErrorLectura, match="No se pudo abrir"):
        data_source.listar_hojas_excel(str(ruta_excel))
    with pytest.raises(data_source.ErrorLectura):
        data_source.read_csv(str(tmp_path / "ausente.csv"))


def test_importacion_conserva_observaciones_de_validacion(tmp_path):
    ruta = tmp_path / "observaciones.csv"
    tabla = datos().astype(object)
    tabla.loc[0, "CantE"] = "error"
    tabla.to_csv(ruta, index=False)
    resultado = data_source.read_csv(str(ruta))
    assert "Valor numérico inválido" in resultado.errores_detectados["Tipo de error"].tolist()


@pytest.mark.parametrize("falla", [False, True])
def test_carga_asincrona_entrega_resultado_en_hilo_principal(falla):
    app = AplicacionVentas.__new__(AplicacionVentas)
    pendientes = []
    hilo_principal = threading.get_ident()
    app.root = SimpleNamespace(after=lambda demora, callback: pendientes.append(callback))
    app.tarea_en_curso = False
    app.df_crudo = anterior = datos()
    app._actualizar_controles = lambda: None
    app._set_estado = lambda *args: None
    errores, resultados = [], []
    app._error_usuario = lambda mensaje, nivel: errores.append((mensaje, nivel, threading.get_ident()))

    def lector():
        assert threading.get_ident() != hilo_principal
        if falla:
            raise data_source.ErrorLectura("Archivo inválido")
        return "nuevo"

    app._ejecutar_tarea(lector, lambda valor: resultados.append((valor, threading.get_ident())), "Leyendo...")
    assert app.tarea_en_curso
    # Una segunda carga no puede reemplazar a la primera mientras está en curso.
    app._ejecutar_tarea(lambda: pytest.fail("Carga simultánea"), resultados.append, "Otra carga")
    limite = time.monotonic() + 5
    while app.tarea_en_curso and time.monotonic() < limite:
        pendientes.pop(0)()
        time.sleep(0.001)
    assert not app.tarea_en_curso
    assert app.df_crudo is anterior
    if falla:
        assert errores == [("Archivo inválido", "warn", hilo_principal)]
        assert resultados == []
    else:
        assert resultados == [("nuevo", hilo_principal)]
        assert errores == []


def test_cancelar_selector_no_inicia_lectura(monkeypatch):
    app = AplicacionVentas.__new__(AplicacionVentas)
    app.root = None
    app.tarea_en_curso = False
    app.df_crudo = anterior = datos()
    monkeypatch.setattr("app.ui.main_window.filedialog.askopenfilename", lambda **kw: "")
    app._ejecutar_tarea = lambda *args: pytest.fail("No debe leer al cancelar")
    app.on_importar_archivo()
    assert app.df_crudo is anterior
