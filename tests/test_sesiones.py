# Logica de sesiones sin HTTP ni OpenAI.
import time
import uuid

import pytest

from api import sesiones
from api.sesiones import SesionOcupada, liberar_sesion, tomar_sesion, validar_id


@pytest.fixture(autouse=True)
def sin_sesiones():
    sesiones._sesiones.clear()
    yield
    sesiones._sesiones.clear()


def nuevo_id():
    return str(uuid.uuid4())


@pytest.mark.parametrize("texto", ["1", "admin", "", "00000000-0000-0000-0000-000000000000"])
def test_rechaza_ids_armados_a_mano(texto):
    assert validar_id(texto) is None


def test_normaliza_el_id():
    sid = nuevo_id()
    assert validar_id(sid.upper()) == sid


def test_doble_envio_da_ocupada():
    sid = nuevo_id()
    tomar_sesion(sid)
    with pytest.raises(SesionOcupada):
        tomar_sesion(sid)


def test_turno_fallido_no_toca_el_historial():
    sid = nuevo_id()
    s = tomar_sesion(sid)
    liberar_sesion(s, [{"role": "user", "content": "hola"}])
    s = tomar_sesion(sid)
    liberar_sesion(s, None)
    assert s.historial == [{"role": "user", "content": "hola"}]


def test_sesion_vencida_se_borra():
    viejo = nuevo_id()
    s = tomar_sesion(viejo)
    liberar_sesion(s)
    s.ultima_actividad = time.monotonic() - sesiones.VENCIMIENTO_SEGUNDOS - 1
    tomar_sesion(nuevo_id())
    assert viejo not in sesiones._sesiones


def test_sesion_trabada_se_destraba():
    sid = nuevo_id()
    s = tomar_sesion(sid)
    s.ultima_actividad = time.monotonic() - sesiones.MAX_DURACION_TURNO - 1
    tomar_sesion(sid)  # no tiene que tirar SesionOcupada