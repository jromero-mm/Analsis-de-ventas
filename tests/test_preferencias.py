import json

from app.core import preferences


def test_preferencias_exportacion_persisten_entre_cargas(tmp_path):
    ruta = tmp_path / "preferencias.json"
    opciones = {
        "incluir_resumen": False,
        "incluir_detalle": True,
        "incluir_errores": False,
        "orden_boticas": "ventas",
        "carpeta": r"C:\Reportes\Concurso",
    }
    preferences.guardar_exportacion(opciones, ruta)
    cargadas = preferences.cargar_exportacion(ruta)
    assert cargadas == opciones


def test_preferencias_invalidas_recuperan_valores_seguros(tmp_path):
    ruta = tmp_path / "preferencias.json"
    ruta.write_text(json.dumps({"exportacion": {"orden_boticas": "otro"}}), encoding="utf-8")
    cargadas = preferences.cargar_exportacion(ruta)
    assert cargadas["orden_boticas"] == "nombre"
    assert cargadas["incluir_resumen"] is True
