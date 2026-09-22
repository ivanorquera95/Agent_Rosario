# Cada test corre con un ContextoSesion nuevo: el estado de las guardias no
# pasa de un test al siguiente y contexto() siempre encuentra uno activo.
import pytest

from comun.contexto import ContextoSesion, soltar_contexto, usar_contexto


@pytest.fixture(autouse=True)
def contexto_nuevo():
    token = usar_contexto(ContextoSesion())
    yield
    soltar_contexto(token)