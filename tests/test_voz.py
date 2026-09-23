# El recorte es logica pura: se testea sin llamar a OpenAI.
from api.voz import MAX_CARACTERES, recortar
import pytest
from api import voz as modulo_voz
from api.voz import LimiteVoz, MAX_POR_DIA, SEGUNDOS_ENTRE_AUDIOS, devolver_turno, tomar_turno


def test_texto_corto_queda_igual():
    assert recortar("Hace 13 grados.") == "Hace 13 grados."


def test_normaliza_espacios_y_saltos():
    assert recortar("  Hola\n\n  Rosario  ") == "Hola Rosario"


def test_corta_en_el_ultimo_punto():
    texto = ("Una oración de prueba. " * 40) + "Final."
    recortado = recortar(texto)
    assert len(recortado) <= MAX_CARACTERES
    assert recortado.endswith(".")


def test_vacio():
    assert recortar(None) == ""

@pytest.fixture(autouse=True)
def contadores_limpios():
    modulo_voz._dia = None
    modulo_voz._usados = 0
    modulo_voz._ultimo_por_sesion.clear()


def test_una_sesion_espera_un_minuto():
    tomar_turno("a", ahora=100)
    with pytest.raises(LimiteVoz):
        tomar_turno("a", ahora=130)
    tomar_turno("a", ahora=100 + SEGUNDOS_ENTRE_AUDIOS)


def test_otra_sesion_no_espera():
    tomar_turno("a", ahora=100)
    tomar_turno("b", ahora=100)  # no tiene que levantar


def test_tope_diario():
    for i in range(MAX_POR_DIA):
        tomar_turno(f"sesion-{i}", ahora=100)
    with pytest.raises(LimiteVoz, match="límite"):
        tomar_turno("otra", ahora=100)


def test_si_falla_openai_no_se_cobra_el_turno():
    tomar_turno("a", ahora=100)
    devolver_turno("a")
    tomar_turno("a", ahora=101)  # puede reintentar enseguida