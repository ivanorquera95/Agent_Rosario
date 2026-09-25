# Limites de uso por IP. El link es publico: sin esto, un script puede gastar
# la cuenta de OpenAI en minutos.
#
# En memoria a proposito: es una proteccion, no un dato que valga la pena
# guardar. Si la API se reinicia, los contadores arrancan de cero.
import threading
import time
from collections import defaultdict, deque
from datetime import date

# Un mensaje cada 6 segundos sostenido, con margen para escribir varios seguidos.
CHATS_POR_MINUTO = 10
CHATS_POR_DIA_POR_IP = 150
CHATS_POR_DIA_TOTAL = 1500

_candado = threading.Lock()
_dia = None
_total_hoy = 0
_por_ip_hoy = defaultdict(int)
_ultimos_por_ip = defaultdict(deque)


class LimiteAlcanzado(Exception):
    def __init__(self, mensaje):
        super().__init__(mensaje)
        self.mensaje = mensaje


def _reiniciar_si_cambio_el_dia():
    global _dia, _total_hoy
    hoy = date.today()
    if _dia != hoy:
        _dia, _total_hoy = hoy, 0
        _por_ip_hoy.clear()
        _ultimos_por_ip.clear()


def tomar_turno_chat(ip, ahora=None):
    global _total_hoy
    ahora = ahora or time.monotonic()
    with _candado:
        _reiniciar_si_cambio_el_dia()

        # Ventana deslizante: se descartan los pedidos de hace mas de un minuto.
        recientes = _ultimos_por_ip[ip]
        while recientes and ahora - recientes[0] > 60:
            recientes.popleft()

        if len(recientes) >= CHATS_POR_MINUTO:
            raise LimiteAlcanzado("Estás yendo muy rápido. Esperá unos segundos.")
        if _por_ip_hoy[ip] >= CHATS_POR_DIA_POR_IP:
            raise LimiteAlcanzado("Llegaste al límite de consultas por hoy. Volvé mañana.")
        if _total_hoy >= CHATS_POR_DIA_TOTAL:
            raise LimiteAlcanzado("Por hoy llegué al límite de consultas. Volvé mañana.")

        recientes.append(ahora)
        _por_ip_hoy[ip] += 1
        _total_hoy += 1