# Sesiones de chat en Postgres. El resto de la API solo usa las funciones de
# este archivo, asi que el cambio de memoria a base de datos quedo aca adentro.
import os
import uuid
from dataclasses import dataclass, field
from pathlib import Path

import psycopg
from dotenv import load_dotenv
from psycopg.types.json import Jsonb

from colectivos.resolver_ubicacion import MAX_MENSAJES_RECORDADOS
from comun.contexto import ContextoSesion

load_dotenv()

VENCIMIENTO = "2 hours"
# Un turno normal tarda segundos. Si una sesion sigue ocupada despues de esto,
# el turno murio sin liberarla (el cliente se fue antes de que arrancara el stream).
MAX_DURACION_TURNO = "10 minutes"
# Para no cargar miles de filas. El tope fino lo sigue aplicando podar_historial.
MAX_MENSAJES_CARGADOS = 40
ESQUEMA = Path(__file__).with_name("esquema.sql")


class SesionOcupada(Exception):
    pass


@dataclass
class Sesion:
    id: str
    # Solo mensajes del usuario y respuestas finales, sin el system prompt.
    historial: list = field(default_factory=list)
    contexto: ContextoSesion = field(default_factory=ContextoSesion)


def conectar():
    # Se lee en cada llamada y no al importar: los tests la cambian por la base de prueba.
    return psycopg.connect(os.environ["DATABASE_URL"])


def crear_esquema():
    with conectar() as con:
        con.execute(ESQUEMA.read_text(encoding="utf-8"))


def validar_id(sesion_id):
    # Solo UUID v4, el que genera crypto.randomUUID() en el navegador. Deja
    # afuera ids armados a mano ("1", "admin") y normaliza mayusculas y formato.
    try:
        u = uuid.UUID(sesion_id)
    except (ValueError, TypeError, AttributeError):
        return None
    return str(u) if u.version == 4 else None


def tomar_sesion(sesion_id):
    with conectar() as con:
        # Sin esto la tabla crece para siempre. Los mensajes se borran por el cascade.
        con.execute("delete from sesiones where ultima_actividad < now() - %s::interval", (VENCIMIENTO,))
        con.execute("insert into sesiones (id) values (%s) on conflict (id) do nothing", (sesion_id,))

        # Chequear y marcar en UNA sentencia: la base garantiza que de dos
        # requests simultaneos gana uno solo, aunque vengan de procesos distintos.
        fila = con.execute(
            """
            update sesiones
               set ocupada_desde = now(), ultima_actividad = now()
             where id = %s
               and (ocupada_desde is null or ocupada_desde < now() - %s::interval)
            returning direcciones_conocidas
            """,
            (sesion_id, MAX_DURACION_TURNO),
        ).fetchone()
        if fila is None:
            raise SesionOcupada()

        mensajes = con.execute(
            """
            select rol, contenido from (
                select id, rol, contenido from mensajes
                 where sesion_id = %s
                 order by id desc
                 limit %s
            ) ultimos
            order by id
            """,
            (sesion_id, MAX_MENSAJES_CARGADOS),
        ).fetchall()

    contexto = ContextoSesion(
        # Se reconstruye de los mensajes guardados: no hace falta guardarlo aparte.
        mensajes_usuario=[c for r, c in mensajes if r == "user"][-MAX_MENSAJES_RECORDADOS:],
        direcciones_conocidas=set(fila[0]),
    )
    historial = [{"role": r, "content": c} for r, c in mensajes]
    return Sesion(id=sesion_id, historial=historial, contexto=contexto)


def liberar_sesion(sesion, pregunta=None, respuesta=None):
    # Sin pregunta y respuesta, el turno no termino bien: solo se libera.
    # Con las dos, todo va en UNA transaccion: se guarda el turno entero o nada.
    with conectar() as con:
        if pregunta is not None and respuesta is not None:
            con.execute(
                "insert into mensajes (sesion_id, rol, contenido) values (%s, 'user', %s), (%s, 'assistant', %s)",
                (sesion.id, pregunta, sesion.id, respuesta),
            )
            con.execute(
                "update sesiones set direcciones_conocidas = %s where id = %s",
                (Jsonb(sorted(sesion.contexto.direcciones_conocidas)), sesion.id),
            )
        con.execute(
            "update sesiones set ocupada_desde = null, ultima_actividad = now() where id = %s",
            (sesion.id,),
        )

def leer_historial(sesion_id):
    # Solo lectura: no toma la sesion ni la crea. Sirve para volver a mostrar
    # la charla en pantalla cuando el usuario recarga la pagina.
    with conectar() as con:
        filas = con.execute(
            """
            select m.rol, m.contenido
              from mensajes m
              join sesiones s on s.id = m.sesion_id
             where m.sesion_id = %s
               and s.ultima_actividad >= now() - %s::interval
             order by m.id
            """,
            (sesion_id, VENCIMIENTO),
        ).fetchall()
    return [{"rol": r, "contenido": c} for r, c in filas]