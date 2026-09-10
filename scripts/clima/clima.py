import sys
sys.stdout.reconfigure(encoding="utf-8")
import unicodedata
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
import requests

API_URL_FORECAST = "https://api.open-meteo.com/v1/forecast" # coordenadas -> clima
API_URL_GEOCODING = "https://geocoding-api.open-meteo.com/v1/search" # nombre de lugar -> coordenadas

LUGAR_POR_DEFECTO = "Rosario"
ZONA_ROSARIO = ZoneInfo("America/Argentina/Buenos_Aires")

DIAS_MAXIMOS = 16          # limite de Open-Meteo
DIAS_POR_DEFECTO = 7

VARIABLES_ACTUALES = [
    "temperature_2m",
    "apparent_temperature",
    "relative_humidity_2m",
    "precipitation",
    "weather_code",
    "wind_speed_10m",
]

VARIABLES_DIARIAS = [
    "weather_code",
    "temperature_2m_max",
    "temperature_2m_min",
    "precipitation_sum",
    "precipitation_probability_max",
    "wind_speed_10m_max",
]

CODIGOS_CLIMA = {     # Codigos WMO
    0: "Despejado",
    1: "Mayormente despejado",
    2: "Parcialmente nublado",
    3: "Nublado",
    45: "Niebla",
    48: "Niebla con escarcha",
    51: "Llovizna leve",
    53: "Llovizna moderada",
    55: "Llovizna intensa",
    56: "Llovizna helada leve",
    57: "Llovizna helada intensa",
    61: "Lluvia leve",
    63: "Lluvia moderada",
    65: "Lluvia intensa",
    66: "Lluvia helada leve",
    67: "Lluvia helada intensa",
    71: "Nevada leve",
    73: "Nevada moderada",
    75: "Nevada intensa",
    77: "Granos de nieve",
    80: "Chubascos leves",
    81: "Chubascos moderados",
    82: "Chubascos intensos",
    85: "Chubascos de nieve leves",
    86: "Chubascos de nieve intensos",
    95: "Tormenta",
    96: "Tormenta con granizo leve",
    99: "Tormenta con granizo intenso",
}

DIAS_SEMANA = {"lunes": 0, "martes": 1, "miercoles": 2, "jueves": 3,"viernes": 4, "sabado": 5, "domingo": 6,}

def normalizar(texto):
    sin_acentos = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode()
    return sin_acentos.lower().strip()

def hoy_en_rosario():
    return datetime.now(ZONA_ROSARIO).date()

def describir_codigo_clima(codigo):
    if codigo is None:
        return "Sin dato"
    return CODIGOS_CLIMA.get(codigo, f"Condición no reconocida (código {codigo})")

def error(mensaje, instruccion, **extra):
    resultado = {"error": mensaje, "instruccion_para_el_agente": instruccion}
    resultado.update(extra)
    return resultado

# -------------------------------------------------------------------------------------------------------------------------------------------

def interpretar_desde(texto, hoy=None):
    #Devuelve la fecha de inicio del pronostico o None si no se entiende.
    hoy = hoy or hoy_en_rosario()
    t = normalizar(texto)

    if not t or t in ("hoy", "ahora", "hoy mismo"):
        return hoy

    if t in ("manana", "el dia de manana"):
        return hoy + timedelta(days=1)

    if t == "pasado manana":
        return hoy + timedelta(days=2)

    # dia de la semana: el proximo que caiga, contando hoy
    t_dia = t.replace("el ", "").replace("este ", "").replace("proximo ", "").strip()
    if t_dia in DIAS_SEMANA:
        objetivo = DIAS_SEMANA[t_dia]
        return hoy + timedelta(days=(objetivo - hoy.weekday()) % 7)

    try:
        return date.fromisoformat(t)
    except ValueError:
        pass

    partes = [p for p in t.replace("-", "/").split("/") if p.strip()]
    if len(partes) in (2, 3):
        try:
            numeros = [int(p) for p in partes]
        except ValueError:
            return None
        dia, mes = numeros[0], numeros[1]
        anio = (numeros[2] + 2000 if numeros[2] < 100 else numeros[2]) if len(numeros) == 3 else hoy.year
        try:
            candidata = date(anio, mes, dia)
        except ValueError:
            return None
        if len(numeros) == 2 and candidata < hoy:
            try:
                candidata = date(anio + 1, mes, dia)
            except ValueError:
                return None
        return candidata

    return None

# ----------------------------------------------------------- geocoding

def elegir_mejor_candidato(resultados, preferir_pais="AR"):
    # Elige entre los candidatos que devolvio el geocodificador en Argentina y el mas poblado. Si no especifica

    if not resultados:
        return None

    del_pais = [r for r in resultados if (r.get("country_code") or "").upper() == preferir_pais]
    candidatos = del_pais or resultados

    return max(candidatos, key=lambda r: r.get("population") or 0)


def resolver_lugar(nombre, preferir_pais="AR"):
    #Nombre de lugar -> coordenadas. Devuelve dict o None si no encontro.
    respuesta = requests.get(
        API_URL_GEOCODING,
        params={"name": nombre, "count": 10, "language": "es", "format": "json"},
        timeout=15,
    )
    respuesta.raise_for_status()

    elegido = elegir_mejor_candidato(respuesta.json().get("results", []), preferir_pais)
    if elegido is None:
        return None

    partes = [elegido["name"], elegido.get("admin1"), elegido.get("country")]

    return {
        "nombre": elegido["name"],
        # El agente muestra esto al empezar la respuesta, para que el usuario detecte si se entendio mal el lugar.
        "nombre_completo": ", ".join(p for p in partes if p),
        "latitud": elegido["latitude"],
        "longitud": elegido["longitude"],
        "pais_codigo": elegido.get("country_code"),
    }

# -------------------------------------------------------------- clima

def obtener_clima(lugar=None, dias=DIAS_POR_DEFECTO, desde=None):
    # Devuelve siempre el clima actual Y el pronostico
    hoy = hoy_en_rosario()
    lugar_pedido = lugar or LUGAR_POR_DEFECTO

    fecha_inicio = interpretar_desde(desde, hoy)
    if fecha_inicio is None:
        return error(
            f"No entendí desde cuándo querés el pronóstico ('{desde}').",
            "Pedile al usuario que aclare la fecha. NO inventes el pronóstico.",
            valores_aceptados=["hoy", "mañana", "pasado mañana", "un día de la semana",
                               "una fecha tipo 2026-09-19 o 19/09"],
        )

    if fecha_inicio < hoy:
        return error(
            f"La fecha pedida ({fecha_inicio.isoformat()}) ya pasó.",
            "Decile al usuario que solo podés dar pronóstico de hoy en adelante.",
        )

    if (fecha_inicio - hoy).days > DIAS_MAXIMOS - 1:
        return error(
            f"El pronóstico llega hasta {DIAS_MAXIMOS} días; {fecha_inicio.isoformat()} está más lejos.",
            "Decile al usuario hasta qué fecha podés pronosticar. NO inventes datos de esa fecha.",
        )

    dias = max(1, min(int(dias or DIAS_POR_DEFECTO), DIAS_MAXIMOS))
    fecha_fin = min(fecha_inicio + timedelta(days=dias - 1), hoy + timedelta(days=DIAS_MAXIMOS - 1))

    try:
        ubicacion = resolver_lugar(lugar_pedido)
    except requests.RequestException as e:
        return error(f"No pude resolver la ubicación: {e}",
                      "Decile al usuario que el servicio de clima no está disponible ahora.")

    if ubicacion is None:
        return error(
            f"No encontré ningún lugar llamado '{lugar_pedido}'.",
            "Pedile al usuario el nombre de la ciudad o localidad. Los barrios no "
            "suelen resolverse: pedile la ciudad. NO uses Rosario como reemplazo "
            "sin avisarle.",
        )

    parametros = {
        "latitude": ubicacion["latitud"],
        "longitude": ubicacion["longitud"],
        "current": ",".join(VARIABLES_ACTUALES),
        "daily": ",".join(VARIABLES_DIARIAS),
        "timezone": "auto",  # "auto" usa la zona horaria del lugar consultado, que es lo correcto cuando alguien pregunta por Bariloche o por Madrid.
        "start_date": fecha_inicio.isoformat(),
        "end_date": fecha_fin.isoformat(),
    }

    try:
        respuesta = requests.get(API_URL_FORECAST, params=parametros, timeout=15)
        respuesta.raise_for_status()
        datos = respuesta.json()
    except requests.RequestException as e:
        return error(f"Falló la consulta del clima: {e}",
                      "Decile al usuario que el servicio de clima no está disponible ahora. "
                      "NO inventes temperaturas.")

    actual_crudo = datos.get("current", {})
    actual = {
        "descripcion": describir_codigo_clima(actual_crudo.get("weather_code")),
        "codigo": actual_crudo.get("weather_code"),
        "temperatura": actual_crudo.get("temperature_2m"),
        "sensacion_termica": actual_crudo.get("apparent_temperature"),
        "humedad": actual_crudo.get("relative_humidity_2m"),
        "precipitacion_mm": actual_crudo.get("precipitation"),
        "viento_kmh": actual_crudo.get("wind_speed_10m"),
    }

    diarios = datos.get("daily", {})
    pronostico = [
        {
            "fecha": fecha,
            "descripcion": describir_codigo_clima(diarios["weather_code"][i]),
            "codigo": diarios["weather_code"][i],
            "temp_min": diarios["temperature_2m_min"][i],
            "temp_max": diarios["temperature_2m_max"][i],
            "precipitacion_mm": diarios["precipitation_sum"][i],
            "probabilidad_lluvia": diarios["precipitation_probability_max"][i],
            "viento_max_kmh": diarios["wind_speed_10m_max"][i],
        }
        for i, fecha in enumerate(diarios.get("time", []))
    ]

    return {
        "lugar_pedido": lugar_pedido,
        "lugar_interpretado": ubicacion["nombre_completo"],
        "coordenadas": {"lat": ubicacion["latitud"], "lon": ubicacion["longitud"]},
        "asumio_rosario": lugar is None,
        "hoy": hoy.isoformat(),
        "rango_pronostico": {"desde": fecha_inicio.isoformat(), "hasta": fecha_fin.isoformat()},
        "actual": actual,
        "pronostico": pronostico,
    }

# -------------------------------------------------------------------------------------------------------------------------------------------
 
def main():
    import argparse
    parser = argparse.ArgumentParser(description="Clima actual y pronóstico de cualquier lugar")
    parser.add_argument("--lugar", default=None, help="Nombre del lugar (default: Rosario)")
    parser.add_argument("--dias", type=int, default=DIAS_POR_DEFECTO, help="Días de pronóstico")
    parser.add_argument("--desde", default=None, help="hoy, mañana, un día de la semana o una fecha")
 
    args = parser.parse_args()
    clima = obtener_clima(lugar=args.lugar, dias=args.dias, desde=args.desde)
 
    if clima.get("error"):
        print(clima["error"])
        return
 
    print(clima["lugar_interpretado"])
 
    a = clima["actual"]
    print(f"Ahora: {a['descripcion']}, {a['temperatura']}°C (sensación {a['sensacion_termica']}°C), "
          f"humedad {a['humedad']}%, viento {a['viento_kmh']} km/h")
 
    for d in clima["pronostico"]:
        print(f"{d['fecha']}  {d['descripcion']:<26} {d['temp_min']:>5.1f}° / {d['temp_max']:>5.1f}°   "
              f"lluvia {d['probabilidad_lluvia']}%")
 
 
if __name__ == "__main__":
    main()