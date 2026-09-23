# El ciclo del agente no se puede caer por culpa del modelo: cualquier falla
# al ejecutar una herramienta tiene que volver como error, no como excepcion.
from agent_rosario import ejecutar_herramienta
import pytest
from agent_rosario import detectar_dia_pedido
from agent_rosario import requiere_tool_choice_forzado
from agent_rosario import limpiar_respuesta, pide_pronostico


def test_json_invalido_no_rompe_el_turno():
    r = ejecutar_herramienta("obtener_clima", '{"lugar": "Rosario"')  # falta la llave de cierre
    assert "JSON" in r["error"]


def test_herramienta_inexistente():
    r = ejecutar_herramienta("herramienta_inventada", "{}")
    assert "no existe" in r["error"]


def test_parametro_inventado_no_rompe_el_turno():
    # El modelo a veces inventa parametros: funcion(**argumentos) tira TypeError
    # antes de tocar la red.
    r = ejecutar_herramienta("comparar_producto", '{"parametro_inventado": 1}')
    assert "error" in r


@pytest.mark.parametrize("texto, esperado", [
    ("¿y mañana?", "mañana"),
    ("¿llueve pasado mañana?", "pasado mañana"),
    ("¿cómo está hoy a la mañana?", None),
    ("¿y mañana a la mañana?", "mañana"),
    ("¿llueve el sábado?", "sabado"),
    ("¿cómo está el clima?", None),
])
def test_detectar_dia_pedido(texto, esperado):
    assert detectar_dia_pedido(texto) == esperado
    

@pytest.mark.parametrize("texto", ["¿y mañana?", "¿y el sábado?", "¿qué hay para el finde?"])
def test_seguimientos_de_fecha_fuerzan_herramienta(texto):
    assert requiere_tool_choice_forzado([{"role": "user", "content": texto}])
    

@pytest.mark.parametrize("texto, esperado", [
    ("¿qué clima hace hoy?", False),
    ("¿cómo está el clima?", False),
    ("dame el pronóstico", True),
    ("¿cómo viene la semana?", True),
    ("¿llueve el finde?", True),
])
def test_pide_pronostico(texto, esperado):
    assert pide_pronostico(texto) is esperado


@pytest.mark.parametrize("cierre", [
    "\n\n¿Necesitás algo más?",
    "\n\nSi necesitás algo más, decime.",
    "\n\n¿Querés que te busque otra cosa?",
    "\n\nAvisame si te sirve.",
])
def test_limpia_cierres_de_relleno(cierre):
    assert limpiar_respuesta("Hace 13 grados." + cierre) == "Hace 13 grados."

@pytest.mark.parametrize("cierre", [
    "\n\nHay más eventos, si querés más detalles, decime.",
    "\n\nSi querés más info, avisame.",
])
def test_limpia_cierres_vagos(cierre):
    assert limpiar_respuesta("Dos eventos." + cierre) == "Dos eventos."