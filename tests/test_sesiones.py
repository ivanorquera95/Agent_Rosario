# Sesiones contra un Postgres real (base rosario_test). Si no esta levantado,
# estos tests se saltean. Para levantarlo: docker compose up -d postgres-app
import os
import threading
import uuid

import psycopg
import pytest
from dotenv import load_dotenv

from api.sesiones import SesionOcupada, crear_esquema, liberar_sesion, tomar_sesion, validar_id, leer_historial

load_dotenv()
URL_TEST = os.getenv("DATABASE_URL_TEST")


def base_disponible():
    if not URL_TEST:
        return False
    try:
        psycopg.connect(URL_TEST, connect_timeout=2).close()
        return True
    except psycopg.OperationalError:
        return False


necesita_base = pytest.mark.skipif(not base_disponible(), reason="Postgres de prueba no levantado")


@pytest.fixture
def base(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", URL_TEST)
    crear_esquema()
    with psycopg.connect(URL_TEST) as con:
        con.execute("truncate sesiones cascade")


def ejecutar(sql, *params):
    with psycopg.connect(URL_TEST) as con:
        cur = con.execute(sql, params)
        # Solo un select devuelve filas; un update no.
        return cur.fetchone() if cur.description else None


def nuevo_id():
    return str(uuid.uuid4())


# ------------------------------------------------------ validacion (sin base)

@pytest.mark.parametrize("texto", ["1", "admin", "", "00000000-0000-0000-0000-000000000000"])
def test_rechaza_ids_armados_a_mano(texto):
    assert validar_id(texto) is None


def test_normaliza_el_id():
    sid = nuevo_id()
    assert validar_id(sid.upper()) == sid


# ------------------------------------------------------------ con base real

@necesita_base
def test_doble_envio_da_ocupada(base):
    sid = nuevo_id()
    tomar_sesion(sid)
    with pytest.raises(SesionOcupada):
        tomar_sesion(sid)


@necesita_base
def test_solo_uno_gana_con_requests_simultaneos(base):
    # Cinco hilos, cada uno con su conexion, piden la misma sesion a la vez.
    sid = nuevo_id()
    salida = threading.Barrier(5)
    ganaron = []

    def pedir():
        salida.wait()
        try:
            tomar_sesion(sid)
            ganaron.append(1)
        except SesionOcupada:
            pass

    hilos = [threading.Thread(target=pedir) for _ in range(5)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()

    assert len(ganaron) == 1


@necesita_base
def test_turno_completo_se_guarda_y_se_recupera(base):
    sid = nuevo_id()
    s = tomar_sesion(sid)
    s.contexto.direcciones_conocidas.add("junin 501")
    liberar_sesion(s, "hola", "¡Hola!")

    s = tomar_sesion(sid)
    assert s.historial == [
        {"role": "user", "content": "hola"},
        {"role": "assistant", "content": "¡Hola!"},
    ]
    assert s.contexto.mensajes_usuario == ["hola"]
    assert "junin 501" in s.contexto.direcciones_conocidas


@necesita_base
def test_turno_fallido_no_guarda_nada(base):
    sid = nuevo_id()
    s = tomar_sesion(sid)
    liberar_sesion(s)
    assert tomar_sesion(sid).historial == []


@necesita_base
def test_sesion_vencida_se_borra(base):
    viejo = nuevo_id()
    liberar_sesion(tomar_sesion(viejo), "hola", "¡Hola!")
    ejecutar("update sesiones set ultima_actividad = now() - interval '3 hours' where id = %s", viejo)

    tomar_sesion(nuevo_id())
    assert ejecutar("select count(*) from mensajes where sesion_id = %s", viejo)[0] == 0


@necesita_base
def test_sesion_trabada_se_destraba(base):
    sid = nuevo_id()
    tomar_sesion(sid)
    ejecutar("update sesiones set ocupada_desde = now() - interval '11 minutes' where id = %s", sid)
    tomar_sesion(sid)  # no tiene que tirar SesionOcupada

@necesita_base
def test_historial_para_la_pantalla(base):
    sid = nuevo_id()
    liberar_sesion(tomar_sesion(sid), "hola", "¡Hola!")
    assert leer_historial(sid) == [
        {"rol": "user", "contenido": "hola"},
        {"rol": "assistant", "contenido": "¡Hola!"},
    ]
    assert leer_historial(nuevo_id()) == []