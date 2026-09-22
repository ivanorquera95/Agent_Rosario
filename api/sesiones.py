# Sesiones de chat en memoria. En el paso 4 pasan a Postgres: el resto de la
# API solo usa las funciones de este archivo, asi que el cambio queda aca.
import threading
import time
import uuid
from dataclasses import dataclass, field

from comun.contexto import ContextoSesion

VENCIMIENTO_SEGUNDOS = 2 * 60 * 60
# Un turno normal tarda segundos. Si una sesion sigue "ocupada" despues de esto,
# el turno murio sin liberarla (el cliente se fue antes de que arrancara el stream).
MAX_DURACION_TURNO = 10 * 60


@dataclass
class Sesion:
    # Solo mensajes del usuario y respuestas finales, sin el system prompt.
    historial: list = field(default_factory=list)
    contexto: ContextoSesion = field(default_factory=ContextoSesion)
    ocupada: bool = False
    ultima_actividad: float = field(default_factory=time.monotonic)


class SesionOcupada(Exception):
    pass


_sesiones: dict[str, Sesion] = {}
_candado = threading.Lock()


def validar_id(sesion_id):
    # Solo UUID v4, el que genera crypto.randomUUID() en el navegador. Deja
    # afuera ids armados a mano ("1", "admin") y normaliza mayusculas y formato.
    try:
        u = uuid.UUID(sesion_id)
    except (ValueError, TypeError, AttributeError):
        return None
    return str(u) if u.version == 4 else None


def tomar_sesion(sesion_id):
    # Chequear y marcar "ocupada" va bajo el mismo candado: si no, dos requests
    # simultaneos chequean a la vez, ven la sesion libre y pasan los dos.
    ahora = time.monotonic()
    with _candado:
        _borrar_vencidas(ahora)
        sesion = _sesiones.setdefault(sesion_id, Sesion())
        if sesion.ocupada and ahora - sesion.ultima_actividad < MAX_DURACION_TURNO:
            raise SesionOcupada()
        sesion.ocupada = True
        sesion.ultima_actividad = ahora
        return sesion


def liberar_sesion(sesion, historial_nuevo=None):
    # historial_nuevo es None cuando el turno no termino bien: la sesion queda como estaba.
    with _candado:
        if historial_nuevo is not None:
            sesion.historial = historial_nuevo
        sesion.ocupada = False
        sesion.ultima_actividad = time.monotonic()


def _borrar_vencidas(ahora):
    # Sin esto el diccionario crece para siempre.
    vencidas = [sid for sid, s in _sesiones.items() if ahora - s.ultima_actividad > VENCIMIENTO_SEGUNDOS]
    for sid in vencidas:
        del _sesiones[sid]