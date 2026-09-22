# El ciclo del agente no se puede caer por culpa del modelo: cualquier falla
# al ejecutar una herramienta tiene que volver como error, no como excepcion.
from agent_rosario import ejecutar_herramienta


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