# Prueba lo que motivo ContextoSesion: en la web cada request corre en su
# propio hilo, y con variables globales un usuario veia el estado de otro.
import threading

from comun.contexto import ContextoSesion, contexto, usar_contexto
from colectivos.resolver_ubicacion import set_mensaje_usuario, viene_del_usuario


def test_dos_usuarios_no_se_mezclan():
    # A escribe "Uruguay 1050"; B nunca lo escribio. Con las globales de antes,
    # la guardia de B lo aceptaba porque lo habia escrito A.
    a_termino = threading.Event()
    resultados = {}

    def usuario_a():
        usar_contexto(ContextoSesion())
        set_mensaje_usuario("quiero ir al Alto Rosario desde Uruguay 1050")
        a_termino.set()

    def usuario_b():
        usar_contexto(ContextoSesion())
        a_termino.wait()
        set_mensaje_usuario("como voy al Monumento")
        resultados["b"] = viene_del_usuario("Uruguay 1050")

    hilos = [threading.Thread(target=usuario_a), threading.Thread(target=usuario_b)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()

    assert resultados["b"] is False


def test_hilo_sin_contexto_falla_rapido():
    # Un hilo nuevo arranca sin contexto, aunque el hilo principal tenga uno
    # (el de conftest). Es la misma trampa que la API: si no se activa en el
    # hilo correcto, tiene que explotar, no compartir uno por defecto.
    errores = []

    def sin_contexto():
        try:
            contexto()
        except RuntimeError as e:
            errores.append(e)

    h = threading.Thread(target=sin_contexto)
    h.start()
    h.join()

    assert len(errores) == 1