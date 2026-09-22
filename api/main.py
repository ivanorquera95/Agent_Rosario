import json

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from agent_rosario import SYSTEM_PROMPT, podar_historial, responder_en_stream
from api.sesiones import SesionOcupada, liberar_sesion, tomar_sesion, validar_id
from colectivos.resolver_ubicacion import set_mensaje_usuario
from comun.contexto import usar_contexto

MAX_LARGO_MENSAJE = 1000

app = FastAPI(title="Rosario Vivo")


class Pedido(BaseModel):
    sesion_id: str
    mensaje: str


@app.get("/salud")
def salud():
    # Para chequear que el servidor esta vivo (lo va a usar el deploy).
    return {"ok": True}


@app.post("/chat")
def chat(pedido: Pedido):
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
        guardar = None
        if termino_bien:
            # Solo lo que sobrevive a la poda: la pregunta y la respuesta final.
            guardar = base[1:] + [pregunta, historial[-1]]
        liberar_sesion(sesion, guardar)