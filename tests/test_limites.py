# Los limites son logica pura: se testean sin red ni base.
import pytest

from api import limites
from api.limites import (
    CHATS_POR_DIA_POR_IP, CHATS_POR_MINUTO, LimiteAlcanzado, tomar_turno_chat,
)


@pytest.fixture(autouse=True)
def contadores_limpios():
    limites._dia = None
    limites._total_hoy = 0
    limites._por_ip_hoy.clear()
    limites._ultimos_por_ip.clear()


def test_limite_por_minuto():
    for _ in range(CHATS_POR_MINUTO):
        tomar_turno_chat("1.2.3.4", ahora=100)
    with pytest.raises(LimiteAlcanzado, match="rápido"):
        tomar_turno_chat("1.2.3.4", ahora=100)


def test_la_ventana_se_corre():
    for _ in range(CHATS_POR_MINUTO):
        tomar_turno_chat("1.2.3.4", ahora=100)
    # Un minuto despues los viejos ya no cuentan.
    tomar_turno_chat("1.2.3.4", ahora=161)


def test_otra_ip_no_se_ve_afectada():
    for _ in range(CHATS_POR_MINUTO):
        tomar_turno_chat("1.2.3.4", ahora=100)
    tomar_turno_chat("5.6.7.8", ahora=100)


def test_limite_diario_por_ip():
    # Espaciados para no chocar con el limite por minuto.
    for i in range(CHATS_POR_DIA_POR_IP):
        tomar_turno_chat("1.2.3.4", ahora=100 + i * 10)
    with pytest.raises(LimiteAlcanzado, match="por hoy"):
        tomar_turno_chat("1.2.3.4", ahora=100 + CHATS_POR_DIA_POR_IP * 10)