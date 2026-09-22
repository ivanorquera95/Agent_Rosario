import os
import sys
import json
import re
import unicodedata
from dotenv import load_dotenv
from openai import OpenAI

RAIZ_PROYECTO = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(RAIZ_PROYECTO, "scripts"))
from agenda.consultar_agenda import consultar_agenda
from precios.consultar_precios import (
    buscar_precios,
    comparar_producto,
)
from descuentos.consultar_descuentos import consultar_descuentos
from clima.clima import obtener_clima
from monedas.monedas import obtener_cotizaciones
from colectivos.resolver_ubicacion import (
    planificar_viaje_resuelto,
    proximos_colectivos_resuelto,
    buscar_lugares_registrado,
    set_mensaje_usuario,
)
from comun.contexto import ContextoSesion, contexto, usar_contexto

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

MODELO = "gpt-4o-mini"
NOMBRE_AGENTE = "Rosario"

# Sin tope, cuando el modelo se empaca reintentando un argumento bloqueado se llama a si mismo indefinidamente.
MAX_PROFUNDIDAD = 5
MAX_MENSAJES_HISTORIAL = 40

with open(os.path.join(RAIZ_PROYECTO, "rosario.md"), encoding="utf-8") as f:
    SYSTEM_PROMPT = f.read()

def sin_acentos(texto):
    d = unicodedata.normalize("NFD", texto or "")
    return "".join(c for c in d if unicodedata.category(c) != "Mn").lower()
# Guardia contra productos inventados, hermana de la de direcciones.
# Ante "que conviene hoy" el modelo llama buscar_precios con "leche",
# "yerba" y "fideos" —que el usuario nunca nombro— y contesta como si
# esa fuera la pregunta. Si ninguna palabra del producto aparece en lo
# que escribio, la herramienta no corre y se le dice cual usar.


def buscar_precios_verificado(producto=None, **resto):
    escrito = sin_acentos(contexto().ultimo_mensaje)
    palabras = [p for p in sin_acentos(producto).split() if len(p) > 2]

    if palabras and not any(p in escrito for p in palabras):
        return {
            "error": f"El usuario no nombró '{producto}'.",
            "instruccion_para_el_agente": (
                "NO inventes productos. Si la pregunta es general sobre qué conviene, "
                "qué descuentos o promociones hay, usá consultar_descuentos. Si querés "
                "precios, preguntale al usuario qué producto le interesa. "
                "NO le menciones al usuario que intentaste buscar un producto: no lo pidió."
            ),
        }

    return buscar_precios(producto=producto, **resto)

def consultar_descuentos_verificado(cadena=None, **resto):
    # El modelo tiende a llamar una vez por cadena aunque el usuario no
    # haya nombrado ninguna: preguntó por Banco Nación y la llamó tres
    # veces, con Coto, Jumbo y DIA. Sin el filtro de cadena la herramienta
    # ya devuelve todas juntas, asi que una cadena que el usuario no
    # escribió se descarta.
    if cadena and sin_acentos(cadena) not in sin_acentos(contexto().ultimo_mensaje):
        cadena = None
    return consultar_descuentos(cadena=cadena, **resto)

# Lugares y colectivos NO apuntan a las funciones crudas: van a los wrappers de resolver_ubicacion.py, que resuelven nombres a direcciones y frenan las direcciones inventadas.
FUNCIONES_DISPONIBLES = {
    "obtener_clima": obtener_clima,
    "obtener_cotizaciones": obtener_cotizaciones,
    "buscar_lugares": buscar_lugares_registrado,
    "proximos_colectivos": proximos_colectivos_resuelto,
    "planificar_viaje": planificar_viaje_resuelto,
    "consultar_agenda": consultar_agenda,
    "buscar_precios": buscar_precios_verificado,
    "comparar_producto": comparar_producto,
    "consultar_descuentos": consultar_descuentos_verificado,
}


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "obtener_clima",
            "description": (
                "Clima actual y pronóstico de cualquier lugar. Sin 'lugar' asume Rosario. "
                "Devuelve siempre el clima de ahora Y el pronóstico del rango pedido."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "lugar": {"type": "string", "description": "Texto tal cual lo escribió el usuario"},
                    "dias": {"type": "integer", "description": "Días de pronóstico, 1 a 16"},
                    "desde": {
                        "type": "string",
                        "description": "hoy, mañana, un día de la semana, o una fecha tipo 2026-09-19",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "obtener_cotizaciones",
            "description": (
                "Cotizaciones del dólar y de otras monedas en Argentina. Sin 'consulta' devuelve "
                "todas. Con 'consulta' devuelve solo esa: oficial, blue, mep, ccl, tarjeta, "
                "cripto, mayorista, euro, real, peso chileno, peso uruguayo."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "consulta": {"type": "string", "description": "Tipo de dólar o moneda puntual"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "buscar_lugares",
            "description": (
                "Busca lugares en el Gran Rosario por categoría (bar, farmacia, supermercado...) "
                "o por nombre. NO la uses para resolver direcciones antes de pedir colectivos: "
                "las herramientas de colectivos ya lo hacen solas."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "categoria": {"type": "string", "description": "bar, cafe, farmacia, supermercado, banco..."},
                    "nombre": {"type": "string", "description": "Nombre puntual, ej 'El Cairo'"},
                    "lugar": {"type": "string", "description": "Zona, barrio, localidad o esquina"},
                    "abierto_ahora": {"type": "boolean"},
                    "limite": {"type": "integer"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "proximos_colectivos",
            "description": (
                "Qué colectivos pasan cerca de un punto y en cuántos minutos llegan. "
                "Solo dice qué pasa por ahí: NO sirve para saber si una línea va hacia un "
                "destino. Para eso está planificar_viaje."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "lugar": {"type": "string", "description": "Texto tal cual lo escribió el usuario"},
                    "linea": {"type": "string", "description": "Filtrar por número de línea"},
                    "radio_metros": {"type": "integer"},
                },
                "required": ["lugar"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "planificar_viaje",
            "description": (
                "Cómo ir en colectivo de un punto a otro del Gran Rosario. Devuelve hasta tres "
                "listas según lo que haga falta: 'directos' (líneas urbanas verificadas, con los "
                "minutos en vivo), 'con_transbordo' (cuando no hay directo) y 'google' (cuando "
                "hace falta un interurbano)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "origen": {"type": "string", "description": "Texto tal cual lo escribió el usuario"},
                    "destino": {"type": "string", "description": "Texto tal cual lo escribió el usuario"},
                    "max_opciones": {"type": "integer"},
                },
                "required": ["origen", "destino"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "consultar_agenda",
            "description": (
                "Eventos y actividades culturales de Rosario: recitales, teatro, muestras, "
                "talleres, ferias, visitas guiadas. Filtra por fecha, categoría, texto libre "
                "y si es gratis."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "fecha": {
                        "type": "string",
                        "description": "hoy, mañana, finde, esta semana, este mes, o una fecha tipo 2026-09-20",
                    },
                    "categoria": {
                        "type": "string",
                        "description": (
                            "Tipo de actividad (Música, Teatro, Muestras, Talleres, Danza...) "
                            "o distrito (Centro, Sur, Noroeste...). Si no existe, la herramienta "
                            "devuelve la lista de las que hay."
                        ),
                    },
                    "busqueda": {
                        "type": "string",
                        "description": (
                            "Texto libre que busca en el título, la descripción y el lugar. "
                            "Usalo para cosas puntuales: 'tango', 'para chicos', 'Fontanarrosa'."
                        ),
                    },
                    "solo_gratis": {"type": "boolean"},
                    "limite": {"type": "integer"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "buscar_precios",
            "description": (
                "Precios de un producto CONCRETO que el usuario nombró: 'leche', "
                "'yerba', 'fideos matarazzo'. Los resultados vienen ordenados por "
                "precio por el precio del envase. "
                "NO la uses si el usuario no nombró ningún producto: para '¿qué "
                "conviene hoy?', '¿qué descuentos hay?' o '¿dónde compro más barato?' "
                "la herramienta correcta es consultar_descuentos. "
                "Para comparar un producto puntual entre cadenas usá comparar_producto."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "producto": {
                        "type": "string",
                        "description": (
                            "Qué busca el usuario: 'leche', 'yerba', 'fideos matarazzo'. "
                            "Palabras sueltas, no una frase larga."
                        ),
                    },
                    "comercio": {
                        "type": "string",
                        "description": "Filtrar por cadena: Coto, Carrefour, DIA, La Anonima, Vea",
                    },
                    "localidad": {
                        "type": "string",
                        "description": "Rosario, Funes, Villa Gobernador Gálvez o Arroyo Seco",
                    },
                    "solo_promos": {"type": "boolean"},
                    "limite": {"type": "integer"},
                },
                "required": ["producto"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "comparar_producto",
            "description": (
                "El MISMO producto en todas las cadenas que lo tengan, comparado por "
                "código de barras. Usala cuando el usuario quiere saber dónde conviene "
                "comprar algo puntual, o si le conviene cambiar de supermercado."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "producto": {
                        "type": "string",
                        "description": "El producto puntual: 'coca cola 2.25', 'arroz gallo oro'",
                    },
                },
                "required": ["producto"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "consultar_descuentos",
            "description": (
                "Descuentos y reintegros de supermercados del Gran Rosario por banco, "
                "billetera virtual, día de la semana o condición (jubilados, ANSES, PAMI). "
                "Cubre Carrefour, Coto, DIA, Jumbo, La Gallega y La Reina. Llamala SIEMPRE "
                "que pregunten por descuentos, aunque creas saber la respuesta. "
                "Por defecto NO trae cuotas sin interés: eso es para electro, no para la "
                "compra del súper."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "entidad": {
                        "type": "string",
                        "description": (
                            "Banco, billetera o condición: 'personal pay', 'credicoop', "
                            "'mercado pago', 'modo', 'naranja x', 'jubilados', 'anses'"
                        ),
                    },
                    "cadena": {
                        "type": "string",
                        "description": "Carrefour, Coto, DIA, Jumbo, La Gallega o La Reina",
                    },
                    "dia": {
                        "type": "string",
                        "description": "hoy, mañana, o un día: lunes, martes, miércoles...",
                    },
                    "incluir_cuotas": {
                        "type": "boolean",
                        "description": "True solo si preguntan por cuotas sin interés",
                    },
                    "limite": {"type": "integer"},
                },
                "required": [],
            },
        },
    },
]


# Palabras que casi siempre piden un dato concreto. Con tool_choice="required" el modelo no puede contestar de memoria.
PALABRAS_CLAVE_DATOS = (
    "colectivo", "cole", "linea", "línea", "parada", "bondi", "llego", "llegar", "muestra",
    "ir a", "voy a", "viaje", "viajar", "llevame", "llévame", "desde", "hasta", "taller",
    "cómo voy", "como voy", "clima", "tiempo", "lluvia", "llueve", "temperatura", "teatro",
    "grados", "pronostico", "pronóstico", "dolar", "dólar", "blue", "mep", "euro", "festival",
    "real", "cotizacion", "cotización", "bar", "farmacia", "super", "cafe", "café",
    "restaurante", "banco", "cajero", "abierto", "cerca", "evento", "agenda", "recital",    
    "actividad", "actividades", "hacer", "obra", "feria", "concierto", "show",
    "gratis", "cultural", "precio", "precios", "barato", "barata", "baratos", "caro", "cuesta",
    "cuanto sale", "cuánto sale", "cuanto vale", "cuánto vale",
    "descuento", "descuentos", "promo", "promos", "promocion", "promoción",
    "oferta", "ofertas", "comparar", "conviene", "jubilado", "jubilados",
    "billetera", "supermercado", "changuito", "canasta",
    "reintegro", "reintegros", "personal pay", "mercado pago", "modo",
    "credicoop", "naranja", "cuenta dni", "anses", "pami", "plus pagos",
    "tarjeta", "debito", "débito", "credito", "crédito",
)

# Las lineas de Rosario van de 100 a 153, mas algunas de dos digitos. Un \d{2,4} suelto tambien pescaba años y alturas forzando una llamada.
PATRON_NUMERO_LINEA = re.compile(r"\b(1[0-5]\d|[1-9]\d)\b")
# "llevame a La Paz 1400" no tiene ninguna palabra clave, pero una calle con altura siempre es un pedido de dato concreto.
PATRON_DIRECCION = re.compile(r"\b[A-Za-zÁ-úñÑ]{3,}\s+\d{1,5}\b")

# Frases de cierre que el modelo mete por reflejo aunque el prompt se lo prohiba.
CIERRES_DE_RELLENO = re.compile(
    r"\n\s*(si (necesit|tenés|tienes|querés|quieres|hay algo)|cualquier (otra )?(cosa|duda)|"
    r"no dudes en|estoy (acá|aquí) para)[^\n]*$",
    re.IGNORECASE,
)


def limpiar_respuesta(texto):
    texto = (texto or "").replace("**", "")
    texto = re.sub(r"^#{1,6}\s*", "", texto, flags=re.MULTILINE)
    # Puede quedar más de una: se corta hasta que no haya
    anterior = None
    while anterior != texto:
        anterior = texto
        texto = CIERRES_DE_RELLENO.sub("", texto).rstrip()
    return texto


def podar_historial(mensajes):
    #Saca los resultados de herramientas de turnos ya cerrados.
    #Se puede porque la regla #1 obliga a volver a llamar la herramienta en cada seguimiento: nunca se lee un resultado viejo. 
    #Se descartan de a pares (el assistant con tool_calls junto con sus 'tool'): si se borra uno solo, la API rechaza la llamada siguiente.
    
    podado = []
    for m in mensajes:
        rol = m["role"] if isinstance(m, dict) else m.role

        if rol == "tool":
            continue
        if rol == "assistant":
            tool_calls = (m.get("tool_calls") if isinstance(m, dict)
                          else getattr(m, "tool_calls", None))
            if tool_calls:
                continue

        podado.append(m)

    if len(podado) > MAX_MENSAJES_HISTORIAL + 1:
        podado = podado[:1] + podado[-MAX_MENSAJES_HISTORIAL:]

    return podado


def requiere_tool_choice_forzado(mensajes):
    ultimo = mensajes[-1]
    rol = ultimo["role"] if isinstance(ultimo, dict) else ultimo.role
    if rol != "user":
        return False

    contenido = (ultimo["content"] if isinstance(ultimo, dict) else ultimo.content) or ""

    if any(palabra in contenido.lower() for palabra in PALABRAS_CLAVE_DATOS):
        return True
    return bool(PATRON_NUMERO_LINEA.search(contenido) or PATRON_DIRECCION.search(contenido))


def preguntar_al_agente(mensajes, profundidad=0):
    if profundidad >= MAX_PROFUNDIDAD:
        mensajes.append({
            "role": "assistant",
            "content": ("Me quedé dando vueltas con esa búsqueda y no llegué a nada firme. "
                        "¿Me lo pedís de nuevo con la dirección exacta?"),
        })
        return mensajes

    tool_choice = "required" if requiere_tool_choice_forzado(mensajes) else "auto"

    respuesta = client.chat.completions.create(
        model=MODELO,
        messages=mensajes,
        tools=TOOLS,
        tool_choice=tool_choice,
    )

    mensaje = respuesta.choices[0].message

    if not mensaje.tool_calls:
        mensajes.append({"role": "assistant", "content": limpiar_respuesta(mensaje.content)})
        return mensajes

    mensajes.append(mensaje)

    for tool_call in mensaje.tool_calls:
        nombre_funcion = tool_call.function.name
        argumentos = json.loads(tool_call.function.arguments)

        print(f"  [{nombre_funcion}] {argumentos}")

        funcion = FUNCIONES_DISPONIBLES.get(nombre_funcion)
        if funcion is None:
            resultado = {"error": f"Herramienta '{nombre_funcion}' no existe."}
        else:
            try:
                resultado = funcion(**argumentos)
            except Exception as e:
                resultado = {"error": str(e)}

        if isinstance(resultado, dict) and resultado.get("error"):
            print(f"      aviso: {resultado['error']}")

        mensajes.append({
            "role": "tool",
            "tool_call_id": tool_call.id,
            "content": json.dumps(resultado, ensure_ascii=False, default=str),
        })

    return preguntar_al_agente(mensajes, profundidad + 1)


def main():
    print(f"=== {NOMBRE_AGENTE} (Rosario Vivo) ===")
    print("Escribí 'salir' para terminar.\n")

    historial = [{"role": "system", "content": SYSTEM_PROMPT}]
    # La terminal es una sola conversacion: un solo contexto para toda la sesion.
    usar_contexto(ContextoSesion())

    while True:
        entrada = input("Vos: ").strip()
        if entrada.lower() in ("salir", "exit", "quit"):
            print(f"{NOMBRE_AGENTE}: Nos vemos.")
            break
        if not entrada:
            continue

        # Las dos guardias (precios y direcciones) comparan contra lo que escribio el usuario.
        set_mensaje_usuario(entrada)
        historial = podar_historial(historial)
        historial.append({"role": "user", "content": entrada})
        historial = preguntar_al_agente(historial)

        ultima = historial[-1]
        contenido = ultima["content"] if isinstance(ultima, dict) else ultima.content
        print(f"\n{NOMBRE_AGENTE}: {contenido}\n")


if __name__ == "__main__":
    main()