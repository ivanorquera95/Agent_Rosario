# Estado de UNA conversacion. Antes vivia en variables globales, que en la web
# comparten todos los usuarios: la guardia de uno comparaba contra el mensaje
# de otro. Cada sesion tiene su ContextoSesion y la ContextVar indica cual esta
# activo mientras corren las herramientas.

from contextvars import ContextVar
from dataclasses import dataclass, field


@dataclass
class ContextoSesion:
    ultimo_mensaje: str = ""
    mensajes_usuario: list[str] = field(default_factory=list)
    direcciones_conocidas: set[str] = field(default_factory=set)


_contexto_actual: ContextVar[ContextoSesion] = ContextVar("contexto_actual")


def usar_contexto(ctx):
    # Devuelve un token para poder volver al contexto anterior.
    return _contexto_actual.set(ctx)


def soltar_contexto(token):
    _contexto_actual.reset(token)


def contexto():
    # Falla rapido a proposito: olvidarse de activar un contexto es un error de
    # programacion. Un contexto compartido por defecto mezclaria usuarios en silencio.
    try:
        return _contexto_actual.get()
    except LookupError:
        raise RuntimeError(
            "No hay un ContextoSesion activo: llamá a usar_contexto() antes de usar las herramientas."
        ) from None