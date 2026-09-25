import json
import logging
from openai import APIError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import BaseModel
from contextlib import asynccontextmanager

from api.limites import LimiteAlcanzado, tomar_turno_chat
from agent_rosario import SYSTEM_PROMPT, podar_historial, responder_en_stream
from api.sesiones import SesionOcupada, crear_esquema, liberar_sesion, tomar_sesion, validar_id, leer_historial
from api.voz import (
    LimiteVoz, MAX_BYTES_AUDIO, devolver_turno, generar_audio, recortar,
    tomar_turno, tomar_turno_transcripcion, transcribir,
)
from colectivos.resolver_ubicacion import set_mensaje_usuario
from comun.contexto import usar_contexto

MAX_LARGO_MENSAJE = 1000

@asynccontextmanager
async def ciclo_de_vida(app):
    # Crea las tablas al arrancar si no existen.
    crear_esquema()
    yield


# Sin docs ni openapi: exponen todos los endpoints y sus parametros, y en una
# demo publica no aportan nada. Se pueden volver a activar en desarrollo
# poniendo docs_url="/docs".
app = FastAPI(title="Rosario Vivo", lifespan=ciclo_de_vida, docs_url=None, redoc_url=None, openapi_url=None)


def ip_de(request):
    # Detras de nginx, la IP real viene en X-Forwarded-For; sin proxy, en client.
    reenviada = request.headers.get("x-forwarded-for")
    if reenviada:
        return reenviada.split(",")[0].strip()
    return request.client.host if request.client else "desconocida"


@app.exception_handler(RequestValidationError)
async def error_de_validacion(request, exc):
    # El detalle de pydantic describe la estructura interna de los modelos:
    # util en desarrollo, informacion de mas en una API publica.
    logger.info("Pedido invalido en %s desde %s", request.url.path, ip_de(request))
    return JSONResponse(status_code=422, content={"detail": "El pedido no tiene el formato esperado."})


@app.exception_handler(Exception)
async def error_inesperado(request, exc):
    # Lo que no atrapamos en otro lado: se registra completo y al usuario le
    # llega un mensaje sin datos internos.
    logger.exception("Error inesperado en %s desde %s", request.url.path, ip_de(request))
    return JSONResponse(status_code=500, content={"detail": "Algo falló de mi lado. Probá de nuevo."})


class Pedido(BaseModel):
    sesion_id: str
    mensaje: str


@app.get("/salud")
def salud():
    # Para chequear que el servidor esta vivo (lo va a usar el deploy).
    return {"ok": True}



class PedidoHistorial(BaseModel):
    sesion_id: str


@app.post("/historial")
def historial(pedido: PedidoHistorial):
    # POST y no GET: el id va en el cuerpo, nunca en la URL.
    sesion_id = validar_id(pedido.sesion_id)
    if sesion_id is None:
        raise HTTPException(400, "sesion_id tiene que ser un UUID v4.")
    return {"mensajes": leer_historial(sesion_id)}

@app.post("/chat")
def chat(pedido: Pedido, request: Request):
    try:
        tomar_turno_chat(ip_de(request))
    except LimiteAlcanzado as e:
        raise HTTPException(429, e.mensaje)

    sesion_id = validar_id(pedido.sesion_id)
    if sesion_id is None:
        raise HTTPException(400, "sesion_id tiene que ser un UUID v4.")

    mensaje = pedido.mensaje.strip()
    if not mensaje:
        raise HTTPException(400, "El mensaje está vacío.")
    if len(mensaje) > MAX_LARGO_MENSAJE:
        raise HTTPException(400, f"El mensaje supera los {MAX_LARGO_MENSAJE} caracteres.")

    try:
        sesion = tomar_sesion(sesion_id)
    except SesionOcupada:
        raise HTTPException(409, "Esta sesión todavía está respondiendo el mensaje anterior.")

    return StreamingResponse(
        eventos_sse(sesion, mensaje),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache"},
    )


def eventos_sse(sesion, mensaje):
    # StreamingResponse ejecuta cada paso de este generador en un hilo del pool,
    # y la contextvar no pasa de un paso al siguiente: se activa en cada uno.
    base = podar_historial([{"role": "system", "content": SYSTEM_PROMPT}] + sesion.historial)
    pregunta = {"role": "user", "content": mensaje}
    # El turno trabaja sobre una copia: si falla, la sesion no se entera.
    historial = base + [pregunta]
    turno = responder_en_stream(historial)
    termino_bien = False

    try:
        usar_contexto(sesion.contexto)
        set_mensaje_usuario(mensaje)
        while True:
            usar_contexto(sesion.contexto)
            try:
                evento = next(turno)
            except StopIteration:
                break
            if evento["tipo"] == "fin":
                termino_bien = True
            yield f"data: {json.dumps(evento, ensure_ascii=False)}\n\n"
    finally:
        # Corre aunque el usuario cierre la pestaña a mitad de la respuesta.
        turno.close()
        if termino_bien:
            liberar_sesion(sesion, mensaje, historial[-1]["content"])
        else:
            liberar_sesion(sesion)
            
class PedidoVoz(BaseModel):
    sesion_id: str
    texto: str


@app.post("/voz")
def voz(pedido: PedidoVoz):
    sesion_id = validar_id(pedido.sesion_id)
    if sesion_id is None:
        raise HTTPException(400, "sesion_id tiene que ser un UUID v4.")

    texto = recortar(pedido.texto)
    if not texto:
        raise HTTPException(400, "No hay texto para leer.")

    try:
        restantes = tomar_turno(sesion_id)
    except LimiteVoz as e:
        # 429 = demasiados pedidos. El frontend muestra el mensaje tal cual.
        raise HTTPException(429, e.mensaje)

    try:
        audio = generar_audio(texto)
    except APIError as e:
        devolver_turno(sesion_id)
        logger.warning("Falló la generación de audio: %s", e)
        raise HTTPException(503, "No pude generar el audio.")

    return Response(
        content=audio,
        media_type="audio/mpeg",
        headers={"Cache-Control": "no-store", "X-Audios-Restantes": str(restantes)},
    )

@app.post("/transcribir")
async def transcribir_audio(sesion_id: str = Form(...), audio: UploadFile = File(...)):
    # El audio va como archivo, no como JSON: por eso Form y File en vez de un modelo.
    sesion_validada = validar_id(sesion_id)
    if sesion_validada is None:
        raise HTTPException(400, "sesion_id tiene que ser un UUID v4.")

    datos = await audio.read()
    if not datos:
        raise HTTPException(400, "El audio llegó vacío.")
    if len(datos) > MAX_BYTES_AUDIO:
        raise HTTPException(413, "El audio es demasiado largo.")

    try:
        tomar_turno_transcripcion(sesion_validada)
    except LimiteVoz as e:
        raise HTTPException(429, e.mensaje)

    try:
        texto = transcribir(datos, audio.filename or "audio.webm")
    except APIError as e:
        logger.warning("Falló la transcripción: %s", e)
        raise HTTPException(503, "No pude entender el audio. Probá de nuevo.")

    if not texto:
        raise HTTPException(422, "No se escuchó nada. Probá de nuevo.")

    return {"texto": texto}