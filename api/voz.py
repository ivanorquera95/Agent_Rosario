# Genera el audio con OpenAI TTS. Va en el servidor y no en el navegador porque
# speechSynthesis depende de las voces instaladas en cada maquina: en una sin
# voces en español no suena nada.
import re
import time
from agent_rosario import client
import threading
from datetime import date

# Tope duro de gasto: los audios cuestan por caracter y el link es publico.
MAX_POR_DIA = 200
SEGUNDOS_ENTRE_AUDIOS = 60
# En memoria a proposito: es una proteccion, no un dato que valga la pena
# guardar. Si la API se reinicia, el contador arranca de cero.
_candado = threading.Lock()
_dia = None
_usados = 0
_ultimo_por_sesion = {}
MODELO_VOZ = "gpt-4o-mini-tts"
VOZ = "coral"
MAX_CARACTERES = 600
MODELO_TRANSCRIPCION = "gpt-4o-mini-transcribe"
MAX_SEGUNDOS_AUDIO = 60
MAX_BYTES_AUDIO = 5 * 1024 * 1024
SEGUNDOS_ENTRE_TRANSCRIPCIONES = 3
MAX_TRANSCRIPCIONES_POR_DIA = 200


# El resumen hablado es corto, pero si no hubo herramienta se habla el texto del
# modelo, que puede ser largo. Se corta en el ultimo punto que entre.
def recortar(texto):
    texto = re.sub(r"\s+", " ", (texto or "").strip())
    if len(texto) <= MAX_CARACTERES:
        return texto
    corte = texto.rfind(".", 0, MAX_CARACTERES)
    return texto[: corte + 1] if corte > 0 else texto[:MAX_CARACTERES]


def generar_audio(texto):
    # Devuelve los bytes de un MP3.
    respuesta = client.audio.speech.create(
        model=MODELO_VOZ,
        voice=VOZ,
        input=texto,
        instructions="Hablá en español rioplatense, con tono cercano y natural, a ritmo normal.",
        response_format="mp3",
    )
    return respuesta.content


class LimiteVoz(Exception):
    def __init__(self, mensaje, segundos=None):
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.segundos = segundos


def tomar_turno(sesion_id, ahora=None):
    # Devuelve cuantos audios quedan hoy, o levanta LimiteVoz.
    global _dia, _usados
    ahora = ahora or time.monotonic()
    hoy = date.today()

    with _candado:
        if _dia != hoy:
            _dia, _usados = hoy, 0
            _ultimo_por_sesion.clear()

        ultimo = _ultimo_por_sesion.get(sesion_id)
        if ultimo is not None and ahora - ultimo < SEGUNDOS_ENTRE_AUDIOS:
            espera = round(SEGUNDOS_ENTRE_AUDIOS - (ahora - ultimo))
            raise LimiteVoz(f"Esperá {espera} segundos para volver a escucharme.", espera)

        if _usados >= MAX_POR_DIA:
            raise LimiteVoz("Por hoy llegué al límite de audios. Mañana vuelvo a hablar.")

        _usados += 1
        _ultimo_por_sesion[sesion_id] = ahora
        return MAX_POR_DIA - _usados


def devolver_turno(sesion_id):
    # Si OpenAI falla, el audio no se genero: no se cobra el turno.
    global _usados
    with _candado:
        _usados = max(0, _usados - 1)
        _ultimo_por_sesion.pop(sesion_id, None)

def transcribir(audio, nombre="audio.webm"):
    # Devuelve el texto que dijo el usuario.
    respuesta = client.audio.transcriptions.create(
        model=MODELO_TRANSCRIPCION,
        file=(nombre, audio),
        language="es",
        # El modelo escribe mejor los nombres propios si sabe de qué se habla.
        prompt="Consulta sobre Rosario: colectivos, líneas, calles, supermercados, descuentos, precios, clima o eventos.",
    )
    return (respuesta.text or "").strip()


# Contadores propios: transcribir es mas barato que generar audio, asi que el
# limite es mas holgado. Misma mecanica en memoria que tomar_turno.
_dia_tr = None
_usados_tr = 0
_ultimo_tr_por_sesion = {}


def tomar_turno_transcripcion(sesion_id, ahora=None):
    global _dia_tr, _usados_tr
    ahora = ahora or time.monotonic()
    hoy = date.today()

    with _candado:
        if _dia_tr != hoy:
            _dia_tr, _usados_tr = hoy, 0
            _ultimo_tr_por_sesion.clear()

        ultimo = _ultimo_tr_por_sesion.get(sesion_id)
        if ultimo is not None and ahora - ultimo < SEGUNDOS_ENTRE_TRANSCRIPCIONES:
            raise LimiteVoz("Esperá un momento antes de volver a grabar.")

        if _usados_tr >= MAX_TRANSCRIPCIONES_POR_DIA:
            raise LimiteVoz("Por hoy llegué al límite de audios. Escribime el mensaje.")

        _usados_tr += 1
        _ultimo_tr_por_sesion[sesion_id] = ahora