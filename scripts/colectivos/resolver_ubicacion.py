#Capa de arriba de las herramientas de colectivos. Hace dos cosas que las tools de colectivos no hacen:
#1. Traduce nombres de lugares ("Alto Rosario") a direcciones, eligiendo entre los resultados de Google por consenso geografico.
#2. Bloquea las direcciones que el modelo inventa de memoria.

import sys
import os
import math
import re
import unicodedata
import difflib

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from comun.localidades import nombra_otra_ciudad
from lugares.lugares import buscar_lugares
from colectivos.colectivos_gran_rosario import planificar_viaje_completo, proximos_colectivos
from comun.contexto import contexto

RADIO_MISMO_LUGAR_M = 400
RATIO_AMBIGUEDAD = 0.45
LIMITE_BUSQUEDA = 10
MAX_MENSAJES_RECORDADOS = 20


def normalizar(texto):
    if not texto:
        return ""
    t = unicodedata.normalize("NFD", texto.lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s]", " ", t)).strip()



ALTURA_AL_FINAL = re.compile(r"\d{1,5}\s*$")                                 # "Uruguay 1050"
ESQUINA = re.compile(r"\s+(y|e|esq\.?|esquina)\s+|\s*/\s*", re.IGNORECASE)   # "Pellegrini y Corrientes"
SEGMENTO_CALLE = re.compile(r"^(.+?)\s+(\d{1,5})$")


def parece_direccion(texto):
    #True si el texto tiene forma de direccion de calle.
    
    if not texto:
        return False
    t = texto.strip()
    return bool(ALTURA_AL_FINAL.search(t) or ESQUINA.search(t))


def limpiar_direccion(direccion_google):
    #Extrae "Calle Numero" de una direccion formateada de Google.
    #Ejemplo: "Alto Rosario Shopping, Junín 501, S2013DJK Rosario, Santa Fe, Argentina" -> "Junín 501"
    
    if not direccion_google:
        return ""
    for segmento in direccion_google.split(","):
        segmento = segmento.strip()
        if SEGMENTO_CALLE.match(segmento):
            return segmento
    return direccion_google.split(",")[0].strip()


def distancia_metros(lat1, lon1, lat2, lon2):
    # Aproximacion plana, de sobra a escala de ciudad
    dlat = (lat1 - lat2) * 111_320
    dlon = (lon1 - lon2) * 111_320 * math.cos(math.radians((lat1 + lat2) / 2))
    return math.hypot(dlat, dlon)

def set_mensaje_usuario(texto):
    #El agente llama a esto cada vez que el usuario escribe algo.
    ctx = contexto()
    ctx.ultimo_mensaje = texto or ""
    if texto:
        ctx.mensajes_usuario.append(texto)
        del ctx.mensajes_usuario[:-MAX_MENSAJES_RECORDADOS]


def registrar_conocida(texto):
    if texto:
        contexto().direcciones_conocidas.add(normalizar(texto))

def viene_del_usuario(argumento):
    #True si el argumento se puede rastrear a algo que el usuario escribio, o a algo que devolvio una herramienta en esta charla.
    #Falla: si todavia no hay mensaje registrado, no bloquea nada. Es a proposito, para que un olvido de set_mensaje_usuario() no rompa el agente.
    ctx = contexto()
    if not ctx.ultimo_mensaje or not argumento:
        return True
    if normalizar(argumento) in ctx.direcciones_conocidas:
        return True
    # El modelo suele copiar la direccion de Google a media asta ("Nansen 323, S2013APG Rosario"): se compara tambien la version limpia.
    if normalizar(limpiar_direccion(argumento)) in ctx.direcciones_conocidas:
        return True

    mensaje = normalizar(" ".join(ctx.mensajes_usuario))
    tokens = [t for t in normalizar(argumento).split() if len(t) > 2 or t.isdigit()]
    if not tokens:
        return True

    palabras_mensaje = mensaje.split()

    def esta_en_el_mensaje(token):
        if token in mensaje:
            return True
        # El modelo corrige la ortografia antes de llamar: "arquidiosesano" ->
        # "arquidiocesano". Eso no es inventar, asi que se tolera una diferencia
        # chica. Los numeros van exactos: una altura distinta es otra direccion.
        if token.isdigit():
            return False
        return any(
            difflib.SequenceMatcher(None, token, palabra).ratio() >= 0.8
            for palabra in palabras_mensaje
            if abs(len(palabra) - len(token)) <= 3
        )

    return all(esta_en_el_mensaje(t) for t in tokens)


def error_inventado(etiqueta, argumento):
    base = (
        f"El {etiqueta} '{argumento}' lo inventaste vos o lo copiaste de una respuesta "
        "anterior: el usuario nunca lo escribió."
    )
    if etiqueta == "lugar":
        instruccion = (
            "Si esto es una pregunta de seguimiento sobre un viaje que ya buscaste, NO uses "
            "proximos_colectivos: volvé a llamar a planificar_viaje con el MISMO origen y "
            "destino que usó el usuario antes, y buscá la línea pedida en el resultado. "
            "proximos_colectivos solo dice qué pasa cerca de un punto, no si va en la "
            "dirección correcta. Si el usuario no dijo de dónde sale, preguntáselo."
        )
    else:
        instruccion = (
            "NO reintentes con otra dirección inventada: si el usuario no dijo de dónde sale "
            "o adónde va, PREGUNTASELO y esperá la respuesta. Si sí lo dijo, volvé a llamar "
            "poniendo su texto TEXTUAL, que la herramienta resuelve la dirección sola."
        )
    return {"error": base, "instruccion_para_el_agente": instruccion}


# Articulos y preposiciones: no aportan a la identidad del lugar y generan coincidencias accidentales ("el" matchea adentro de "Del").
PALABRAS_VACIAS = {"el", "la", "los", "las", "un", "una", "de", "del", "al", "a", "en", "y", "e", "o", "u"}


def puntaje_coincidencia(consulta, lugar):
    #1.0  -> el nombre del lugar contiene todas las palabras significativas
    #0.5  -> no, pero la direccion las contiene (tipico de locales adentro de un shopping: "VER" en "Alto Rosario Shopping, Junín 501")
    #0.0  -> nada que ver, se descarta
    
    q = normalizar(consulta)
    tokens = [t for t in q.split() if t and t not in PALABRAS_VACIAS]
    if not tokens:
        tokens = [t for t in q.split() if t]
    if not tokens:
        return 0.0
    if all(t in normalizar(lugar.get("nombre", "")) for t in tokens):
        return 1.0
    if all(t in normalizar(lugar.get("direccion", "")) for t in tokens):
        return 0.5
    return 0.0


def rankear_lugares(consulta, lugares):
    #Agrupa los resultados por cercania y devuelve el grupo con mas peso.

    candidatos = []
    descartados = 0

    for i, lugar in enumerate(lugares):
        if not isinstance(lugar, dict):
            continue
        puntaje = puntaje_coincidencia(consulta, lugar)
        if puntaje == 0.0 or lugar.get("latitud") is None:
            descartados += 1
            continue
        candidatos.append({"lugar": lugar, "pos": i, "peso": puntaje / (i + 1)})

    grupos = []
    for c in candidatos:
        lat, lon = c["lugar"]["latitud"], c["lugar"]["longitud"]
        for g in grupos:
            if distancia_metros(lat, lon, g["lat"], g["lon"]) <= RADIO_MISMO_LUGAR_M:
                g["miembros"].append(c)
                g["peso"] += c["peso"]
                break
        else:
            grupos.append({"lat": lat, "lon": lon, "peso": c["peso"], "miembros": [c]})

    grupos.sort(key=lambda g: g["peso"], reverse=True)

    if not grupos:
        return {"ganador": None, "peso_top": 0.0, "peso_segundo": 0.0,
                "grupos": [], "descartados": descartados}

    # Dentro del grupo ganador, el representante es el que coincide por nombre y quedo mas arriba en Google.
    mejor = sorted(grupos[0]["miembros"], key=lambda c: (-puntaje_coincidencia(consulta, c["lugar"]), c["pos"]),)[0]

    return {
        "ganador": mejor["lugar"],
        "peso_top": grupos[0]["peso"],
        "peso_segundo": grupos[1]["peso"] if len(grupos) > 1 else 0.0,
        "grupos": grupos,
        "descartados": descartados,
    }


def hay_ambiguedad(r):
    return r["peso_segundo"] >= r["peso_top"] * RATIO_AMBIGUEDAD


def resolver_ubicacion(texto):
    base = {
        "ok": False, "tipo": "direccion", "texto_original": texto,
        "direccion": None, "direccion_completa": None, "nombre_lugar": None,
        "latitud": None, "longitud": None,
        "ambiguo": False, "candidatos": [], "motivo": None,
    }

    if not texto or not texto.strip():
        base["motivo"] = "No se indicó ninguna ubicación."
        return base

    texto = texto.strip()

    if nombra_otra_ciudad(texto):
        base["motivo"] = (
            f"'{texto}' es otra ciudad, fuera de Rosario y el Gran Rosario. "
            "Decíselo al usuario tal cual: el sistema de colectivos no llega ahí. "
            "No busques alternativas ni ofrezcas otro destino."
        )
        return base

    # Cuando el modelo copia el resultado de buscar_lugares llega el string completo de Google, que no pasa parece_direccion() porque termina en "Argentina".
    if "," in texto:
        candidata = limpiar_direccion(texto)
        if parece_direccion(candidata):
            texto = candidata

    if parece_direccion(texto):
        base.update(ok=True, tipo="direccion", direccion=texto)
        registrar_conocida(texto)
        return base

    base["tipo"] = "lugar"

    try:
        resultado = buscar_lugares(nombre=texto, limite=LIMITE_BUSQUEDA)
    except Exception as e:
        base["motivo"] = f"Falló la búsqueda del lugar '{texto}': {e}"
        return base

    if isinstance(resultado, dict) and resultado.get("error"):
        base["motivo"] = f"Búsqueda de lugares con error: {resultado['error']}"
        return base

    lugares = resultado.get("lugares", []) if isinstance(resultado, dict) else []
    if not lugares:
        base["motivo"] = (
            f"No encontré ningún lugar llamado '{texto}' en el Gran Rosario, "
            "así que no puedo sacar una dirección para buscar colectivos."
        )
        return base

    r = rankear_lugares(texto, lugares)
    base["candidatos"] = [
        {"nombre": g["miembros"][0]["lugar"].get("nombre"),
         "direccion": limpiar_direccion(g["miembros"][0]["lugar"].get("direccion", ""))}
        for g in r["grupos"][:4]
    ]

    # Los candidatos se le muestran al usuario para que elija: cuando elige, el modelo va a llamar con ese nombre. 
    # #Si no quedan registrados, la guardia lo bloquea por inventado y la conversacion entra en bucle.
    for c in base["candidatos"]:
        registrar_conocida(c["nombre"])
        registrar_conocida(c["direccion"])

    if not r["ganador"]:
        base["motivo"] = (
            f"Encontré resultados para '{texto}' pero ninguno coincide de verdad "
            "con lo que buscabas."
        )
        return base

    # Dos zonas distintas con peso parecido: son sucursales. Que pregunte el agente.
    if hay_ambiguedad(r):
        base.update(
            ambiguo=True,
            motivo=(
                f"Hay más de un lugar que coincide con '{texto}', en zonas distintas. "
                "Mostrale las opciones de 'candidatos' al usuario, preguntale a cuál se "
                "refiere y volvé a llamar a la herramienta con la dirección elegida."
            ),
        )
        return base

    direccion_completa = r["ganador"].get("direccion", "")
    direccion = limpiar_direccion(direccion_completa)
    base.update(
        ok=True,
        direccion=direccion,
        direccion_completa=direccion_completa,
        nombre_lugar=r["ganador"].get("nombre"),
        latitud=r["ganador"].get("latitud"),
        longitud=r["ganador"].get("longitud"),
    )
    registrar_conocida(direccion)
    registrar_conocida(texto)
    return base


def interpretacion(r):
    #Lo que ve el modelo para poder confirmarle la ubicación al usuario.
    return {
        "pidio": r["texto_original"],
        "tipo": r["tipo"],
        "nombre_lugar": r["nombre_lugar"],
        "direccion_usada": r["direccion"],
    }


def error_resolucion(etiqueta, r):
    return {
        "error": f"No pude resolver el {etiqueta}.",
        "motivo": r["motivo"],
        "ambiguo": r["ambiguo"],
        "candidatos": r["candidatos"] if r["ambiguo"] else [],
        "instruccion_para_el_agente": (
            "No inventes una dirección ni vuelvas a llamar a esta herramienta con el mismo "
            "texto. Contale al usuario lo que dice 'motivo'. Solo si 'ambiguo' es true "
            "ofrecele los candidatos para que elija."
        ),
    }


def buscar_lugares_registrado(*args, **kwargs):
    #buscar_lugares, mas dos agregados:
    #1. Anota nombres y direcciones devueltos, para que la guardia no bloquee al modelo cuando le pasa a otra tool algo que esta misma tool le dio.
    #2. Si los resultados caen en zonas distintas, se lo avisa. Sin esto el modelo elige una sucursal por su cuenta y la ambiguedad nunca se evalua.
    
    try:
        resultado = buscar_lugares(*args, **kwargs)
    except Exception as e:
        return {"error": f"Falló la búsqueda de lugares: {e}"}

    if not isinstance(resultado, dict):
        return resultado

    lugares = resultado.get("lugares", []) or []
    for lugar in lugares:
        if not isinstance(lugar, dict):
            continue
        registrar_conocida(lugar.get("nombre"))
        direccion = lugar.get("direccion") or ""
        if direccion:
            registrar_conocida(direccion)
            registrar_conocida(limpiar_direccion(direccion))

    nombre_buscado = kwargs.get("nombre")
    consulta = nombre_buscado or kwargs.get("categoria") or ""

    if nombre_buscado and lugares:
        coinciden = [l for l in lugares
                     if isinstance(l, dict) and puntaje_coincidencia(nombre_buscado, l) > 0]
        if not coinciden:
            return {
                "error": f"No existe ningún lugar llamado '{nombre_buscado}' en el Gran Rosario.",
                "instruccion_para_el_agente": (
                    f"Decile al usuario que no encontraste '{nombre_buscado}'. "
                    "NO ofrezcas otro lugar como si fuera ese, ni des ninguna dirección."
                ),
            }
        lugares = coinciden
        resultado["lugares"] = coinciden

    if consulta and len(lugares) > 1:
        r = rankear_lugares(consulta, lugares)
        if r["ganador"] and hay_ambiguedad(r):
            resultado["instruccion_para_el_agente"] = (
                f"Hay varios lugares distintos que coinciden con '{consulta}', en zonas "
                "diferentes. NO elijas uno vos ni le pases una dirección a otra herramienta. "
                "Mostrale las opciones al usuario y preguntale a cuál se refiere."
            )

    return resultado

def falta_dato(etiqueta, pregunta):
      return {
          "error": f"Falta el {etiqueta}: el usuario no dijo {pregunta}.",
          "instruccion_para_el_agente": (
              f"Preguntale al usuario {pregunta}. NO lo inventes ni vuelvas a llamar "
              "a la herramienta hasta que te lo diga."
          ),
      }
      
def planificar_viaje_resuelto(origen=None, destino=None, max_opciones=10, **kwargs):
    # Con tool_choice="required" el modelo tiene que llamar a algo aunque el
    # usuario no haya dicho de donde sale, y entonces inventaba el origen.
    # Ahora puede llamar sin origen y la herramienta le dice que pregunte.
    if not origen:
          return falta_dato("origen", "de dónde sale")
    if not destino:
          return falta_dato("destino", "adónde va")
      
    if not viene_del_usuario(origen):
        return error_inventado("origen", origen)
    if not viene_del_usuario(destino):
        return error_inventado("destino", destino)

    o = resolver_ubicacion(origen)
    if not o["ok"]:
        return error_resolucion("origen", o)

    d = resolver_ubicacion(destino)
    if not d["ok"]:
        return error_resolucion("destino", d)
    
    def punto(r):
        if r["latitud"] is None:
            return None
        return {"nombre": r["nombre_lugar"] or r["direccion"],
                "latitud": r["latitud"], "longitud": r["longitud"]}

    resultado = planificar_viaje_completo(
        o["direccion"], d["direccion"], max_opciones=max_opciones,
        punto_origen=punto(o), punto_destino=punto(d),
    )

    if isinstance(resultado, dict):
        resultado["origen_interpretado"] = interpretacion(o)
        resultado["destino_interpretado"] = interpretacion(d)
        registrar_conocida(resultado.get("origen_resuelto"))
        registrar_conocida(resultado.get("destino_resuelto"))

    return resultado


def proximos_colectivos_resuelto(lugar=None, **kwargs):
    if not lugar:
          return falta_dato("lugar", "dónde está")
    if not viene_del_usuario(lugar):
        return error_inventado("lugar", lugar)

    u = resolver_ubicacion(lugar)
    if not u["ok"]:
        return error_resolucion("lugar", u)

    resultado = proximos_colectivos(u["direccion"], **kwargs)

    if isinstance(resultado, dict):
        resultado["ubicacion_interpretada"] = interpretacion(u)
        registrar_conocida(resultado.get("ubicacion_resuelta"))

    return resultado