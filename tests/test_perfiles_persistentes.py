from app.core import profiles


def test_perfiles_migran_a_ubicacion_persistente(tmp_path):
    fuente = tmp_path / "incluidos" / "perfiles.json"
    fuente.parent.mkdir()
    fuente.write_text('{"DEMO": {"laboratorios": ["LABORATORIO DEMO"]}}', encoding="utf-8")
    destino = tmp_path / "usuario" / "perfiles.json"

    cargados = profiles.cargar_perfiles(destino, fuente)

    assert cargados["DEMO"]["laboratorios"] == ["LABORATORIO DEMO"]
    assert destino.exists()


def test_perfiles_del_usuario_no_son_reemplazados(tmp_path):
    fuente = tmp_path / "incluidos.json"
    fuente.write_text('{"ANTIGUO": {}}', encoding="utf-8")
    destino = tmp_path / "usuario.json"
    profiles.guardar_perfiles({"CAMBIADO": {"productos": ["P1"]}}, destino)

    cargados = profiles.cargar_perfiles(destino, fuente)

    assert set(cargados) == {"CAMBIADO"}
    assert cargados["CAMBIADO"]["productos"] == ["P1"]
