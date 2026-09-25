# Cabeceras y limites que aplican a toda la API.
import os

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

# Un mensaje son 1000 caracteres y un audio hasta 5 MB: 6 MB cubre todo con
# margen. Sin esto, alguien puede mandar 100 MB y el servidor los recibe
# enteros antes de rechazarlos.
MAX_BYTES_CUERPO = 6 * 1024 * 1024

# El frontend se sirve desde el mismo origen que la API, asi que en produccion
# no hace falta CORS. La lista existe por si algun dia se separan.
def origenes_permitidos():
    crudo = os.getenv("ORIGENES_PERMITIDOS", "")
    return [o.strip() for o in crudo.split(",") if o.strip()]


class LimiteDeTamano(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        largo = request.headers.get("content-length")
        if largo and largo.isdigit() and int(largo) > MAX_BYTES_CUERPO:
            return JSONResponse(status_code=413, content={"detail": "El pedido es demasiado grande."})
        return await call_next(request)


class CabecerasDeSeguridad(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        respuesta = await call_next(request)
        # No adivines el tipo de archivo: si digo que es JSON, es JSON.
        respuesta.headers["X-Content-Type-Options"] = "nosniff"
        # Que nadie meta la pagina en un iframe ajeno.
        respuesta.headers["X-Frame-Options"] = "DENY"
        # No mandes la URL completa a otros sitios cuando el usuario hace clic
        # en un enlace: la URL no lleva datos, pero es la practica correcta.
        respuesta.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        # La pagina no necesita camara ni ubicacion; el microfono si.
        respuesta.headers["Permissions-Policy"] = "camera=(), geolocation=(), microphone=(self)"
        # Que recursos puede cargar la pagina. 'unsafe-inline' en style hace
        # falta porque los anillos usan estilos calculados en el SVG.
        respuesta.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; "
            "media-src 'self' blob:; "
            "connect-src 'self'; "
            "frame-ancestors 'none'; "
            "base-uri 'self'; "
            "form-action 'self'"
        )
        return respuesta