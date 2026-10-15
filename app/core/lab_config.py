"""Configuracion de laboratorios y reglas CantE/CantF/TotalP.

Lee config/laboratorios.json y expone:
- REGLAS: mapa de nombre de regla -> definicion (conservar/descartar).
- resolver(lab_nombre) -> (nombre_canonico, regla)
- regla_default() -> regla por defecto
- regla_total() -> regla para la fila/columna TOTAL
- orden_preferido() -> lista de nombres para ordenar (opcional)

Objetivo: aparezca un laboratorio nuevo, no se toque el codigo;
la regla por defecto lo cubre. Para aflorar comportamiento especial,
basta editar el JSON.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Tuple

from app.paths import ruta_config, ruta_datos_usuario

# --- Definicion canonica de reglas -----------------------------------------

#: Cada regla indica que metricas se CONSERVAN y cuales se DESCARTAN.
#: Las metricas posibles son: CantE, CantF, TotalP.
REGLAS: Dict[str, Dict[str, List[str]]] = {
    "solo_cante": {
        "conservar": ["CantE"],
        "descartar": ["CantF", "TotalP"],
    },
    "solo_totalp": {
        "conservar": ["TotalP"],
        "descartar": ["CantE", "CantF"],
    },
    "cante_cantf": {
        "conservar": ["CantE", "CantF"],
        "descartar": ["TotalP"],
    },
    "todas": {
        "conservar": ["CantE", "CantF", "TotalP"],
        "descartar": [],
    },
}

METRICAS_VALIDAS = ("CantE", "CantF", "TotalP")

# --- Errores especificos ---------------------------------------------------


class ConfigError(Exception):
    """Error al leer/interpretar config/laboratorios.json."""


class LaboratorioDesconocido(Exception):
    """No se encontro regla para un laboratorio (no deberia ocurrir)."""


# --- Ubicacion del JSON ----------------------------------------------------

_CONFIG_BASE_PATH = ruta_config("laboratorios.json")
_CONFIG_USUARIO_PATH = ruta_datos_usuario("laboratorios.json")

# --- Cache de configuracion -----------------------------------------------

_config_cache: Dict | None = None


def _validar_config(data: Dict) -> Dict:
    """Valida y devuelve una configuración de laboratorios."""
    if not isinstance(data, dict):
        raise ConfigError("laboratorios.json debe contener un objeto.")

    regla_def = data.get("regla_por_defecto", "cante_cantf")
    if regla_def not in REGLAS:
        raise ConfigError(
            f"regla_por_defecto '{regla_def}' no es valida. "
            f"Opciones: {list(REGLAS)}"
        )

    regla_tot = data.get("regla_total", "todas")
    if regla_tot not in REGLAS:
        raise ConfigError(
            f"regla_total '{regla_tot}' no es valida. "
            f"Opciones: {list(REGLAS)}"
        )

    overrides = data.get("overrides", {})
    if not isinstance(overrides, dict):
        raise ConfigError("overrides debe ser un objeto con los laboratorios.")

    for clave, definicion in overrides.items():
        if not isinstance(definicion, dict):
            raise ConfigError(f"override de '{clave}' debe ser un objeto.")
        regla = definicion.get("regla")
        if regla not in REGLAS:
            raise ConfigError(
                f"regla '{regla}' para '{clave}' no es valida. "
                f"Opciones: {list(REGLAS)}"
            )
        aliases = definicion.get("aliases", [])
        if not isinstance(aliases, list):
            raise ConfigError(f"aliases de '{clave}' debe ser una lista.")
        if "agrupar_productos" in definicion and not isinstance(
            definicion["agrupar_productos"], bool
        ):
            raise ConfigError(
                f"agrupar_productos de '{clave}' debe ser verdadero o falso."
            )
        if "unidades_combinadas" in definicion and not isinstance(
            definicion["unidades_combinadas"], bool
        ):
            raise ConfigError(
                f"unidades_combinadas de '{clave}' debe ser verdadero o falso."
            )
    return data


def _leer_desde(ruta: Path) -> Dict:
    try:
        with ruta.open("r", encoding="utf-8") as fh:
            return _validar_config(json.load(fh))
    except json.JSONDecodeError as exc:
        raise ConfigError(
            f"laboratorios.json mal formado: {exc.msg} (linea {exc.lineno})"
        ) from exc


def _ruta_lectura() -> Path:
    """Prioriza la copia editable y persistente del usuario."""
    return _CONFIG_USUARIO_PATH if _CONFIG_USUARIO_PATH.exists() else _CONFIG_BASE_PATH


def _cargar_config() -> Dict:
    """Carga y valida config/laboratorios.json; cachea el resultado."""
    global _config_cache
    if _config_cache is not None:
        return _config_cache

    ruta = _ruta_lectura()
    if not ruta.exists():
        # Config ausente: usamos defaults seguros (todo cante_cantf).
        _config_cache = {
            "regla_por_defecto": "cante_cantf",
            "regla_total": "todas",
            "overrides": {},
            "orden_preferido": [],
        }
        return _config_cache

    _config_cache = _leer_desde(ruta)
    return _config_cache


def recargar_config() -> None:
    """Fuerza releer el JSON en la proxima llamada (util para tests)."""
    global _config_cache
    _config_cache = None


def configuracion_editable() -> Dict:
    """Copia independiente de la configuración efectiva para el editor."""
    return json.loads(json.dumps(_cargar_config(), ensure_ascii=False))


def guardar_configuracion(data: Dict, ruta: Path | None = None) -> Path:
    """Guarda reglas de forma atómica en la ubicación persistente del usuario."""
    global _config_cache
    validada = _validar_config(data)
    destino = Path(ruta) if ruta is not None else _CONFIG_USUARIO_PATH
    destino.parent.mkdir(parents=True, exist_ok=True)
    temporal = destino.with_suffix(destino.suffix + ".tmp")
    temporal.write_text(
        json.dumps(validada, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporal.replace(destino)
    if ruta is None:
        _config_cache = None
    return destino


def cargar_configuracion_desde(ruta: Path) -> Dict:
    """Lectura explícita usada para comprobar copias persistentes."""
    return _leer_desde(Path(ruta))


# --- API publica -----------------------------------------------------------


def regla_default() -> str:
    cfg = _cargar_config()
    return cfg.get("regla_por_defecto", "cante_cantf")


def regla_total() -> str:
    cfg = _cargar_config()
    return cfg.get("regla_total", "todas")


def orden_preferido() -> List[str]:
    cfg = _cargar_config()
    return list(cfg.get("orden_preferido", []))


def boticas_fijas() -> List[str]:
    """Boticas que deben aparecer en matrices por producto, incluso en cero."""
    cfg = _cargar_config()
    boticas = cfg.get("boticas_fijas", [])
    if not isinstance(boticas, list):
        raise ConfigError("boticas_fijas debe ser una lista.")
    salida: List[str] = []
    for botica in boticas:
        nombre = str(botica).strip()
        if nombre and nombre not in salida:
            salida.append(nombre)
    return salida


def metricas_a_conservar(regla: str) -> List[str]:
    if regla not in REGLAS:
        raise ConfigError(f"regla '{regla}' no definida. Opciones: {list(REGLAS)}")
    return list(REGLAS[regla]["conservar"])


def metricas_a_descartar(regla: str) -> List[str]:
    if regla not in REGLAS:
        raise ConfigError(f"regla '{regla}' no definida. Opciones: {list(REGLAS)}")
    return list(REGLAS[regla]["descartar"])


def metricas_configuradas(lab_nombre: str) -> List[str]:
    """Metricas permitidas por laboratorio, configurables en JSON."""
    canonico, regla = resolver(lab_nombre)
    for clave, definicion in _cargar_config().get("overrides", {}).items():
        aliases = definicion.get("aliases", [clave])
        if canonico == aliases[0] or clave.upper() == str(lab_nombre).strip().upper():
            metricas = definicion.get("metricas")
            if metricas:
                invalidas = [m for m in metricas if m not in METRICAS_VALIDAS]
                if invalidas:
                    raise ConfigError(f"Metricas invalidas para '{clave}': {invalidas}")
                return [m for m in METRICAS_VALIDAS if m in metricas]
    return metricas_a_conservar(regla)


def resolver(lab_nombre: str) -> Tuple[str, str]:
    """Devuelve (nombre_canonico, regla) para un nombre de laboratorio.

    Resolucion:
    1) Coincidencia exacta (sin distinguir mayusculas) con un alias declarado.
    2) Coincidencia exacta con la clave de override.
    3) Subcadena (la clave en mayusculas esta contenida en lab_nombre.upper()).
    4) Si nada coincide: regla por defecto y el propio nombre como canonico.

    El nombre canonico devuelto es el PRIMER alias de la entrada (si existe)
    o la propia clave de override. Esto resuelve el problema del script
    original donde el reindex descartaba laboratorios con nombres cercanos
    pero no identicos.
    """
    if lab_nombre is None:
        raise LaboratorioDesconocido("Laboratorio es None")

    cfg = _cargar_config()
    overrides = cfg.get("overrides", {})
    target = str(lab_nombre).strip().upper()

    # 1) Coincidencia exacta con alias
    for clave, definicion in overrides.items():
        aliases = definicion.get("aliases", [])
        for alias in aliases:
            if alias.upper() == target:
                canonico = aliases[0] if aliases else clave
                return canonico, definicion["regla"]

    # 2) Coincidencia exacta con la clave
    for clave, definicion in overrides.items():
        if clave.upper() == target:
            canonico = definicion.get("aliases", [clave])[0]
            return canonico, definicion["regla"]

    # 3) Subcadena (tolerancia a variaciones tipo "LABORATORIO ALFA SRL")
    for clave, definicion in overrides.items():
        for alias in definicion.get("aliases", [clave]):
            if alias.upper() in target:
                canonico = definicion.get("aliases", [clave])[0]
                return canonico, definicion["regla"]

    # 4) Default
    return str(lab_nombre).strip(), regla_default()


def reglas_para_laboratorios(labs: List[str]) -> Dict[str, str]:
    """Mapa {nombre_canonico: regla} para una lista de laboratorios.

    Si dos nombres distintos del portapapeles resuelven al MISMO canonico
    (p.ej. dos variantes de LABORATORIO ALFA), se unifican bajo la misma entrada.
    Lanza LaboratorioDuplicadoCanonico si hay ambiguedad.
    """
    salida: Dict[str, str] = {}
    for lab in labs:
        canonico, regla = resolver(lab)
        if canonico in salida and salida[canonico] != regla:
            raise LaboratorioDesconocido(
                f"El canonico '{canonico}' recibe dos reglas distintas "
                f"('{salida[canonico]}' y '{regla}'). Revisa laboratorios.json."
            )
        salida[canonico] = regla
    return salida


def listar_reglas_disponibles() -> List[str]:
    return list(REGLAS)


def esta_configurado(lab_nombre: str) -> bool:
    target = str(lab_nombre).strip().upper()
    for clave, definicion in _cargar_config().get("overrides", {}).items():
        if clave.upper() == target:
            return True
        for alias in definicion.get("aliases", []):
            alias_up = str(alias).upper()
            if alias_up == target or alias_up in target:
                return True
    return False


def perfil(lab_nombre: str) -> Dict:
    """Devuelve la configuracion comercial del laboratorio.

    Permite agregar en el JSON productos objetivo, metricas visibles y meta.
    No rompe configuraciones antiguas: si no existen, devuelve valores vacios.
    """
    canonico, regla = resolver(lab_nombre)
    cfg = _cargar_config()
    for clave, definicion in cfg.get("overrides", {}).items():
        alias = definicion.get("aliases", [clave])[0]
        if alias == canonico or clave.upper() == str(lab_nombre).strip().upper():
            agrupar = definicion.get("agrupar_productos", False)
            unidades_combinadas = definicion.get("unidades_combinadas", False)
            return {
                "nombre": canonico,
                "regla": regla,
                "productos": list(definicion.get("productos", [])),
                "metricas": list(definicion.get("metricas", metricas_a_conservar(regla))),
                "meta": float(definicion.get("meta", 0) or 0),
                "agrupar_productos": bool(agrupar),
                "unidades_combinadas": bool(unidades_combinadas),
            }
    return {"nombre": canonico, "regla": regla,
            "productos": [], "metricas": metricas_a_conservar(regla), "meta": 0.0,
            "agrupar_productos": False, "unidades_combinadas": False}
