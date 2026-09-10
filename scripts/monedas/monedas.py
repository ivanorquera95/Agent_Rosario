import sys
sys.stdout.reconfigure(encoding="utf-8")
import unicodedata
import requests

API_URL = "https://dolarapi.com/v1"

# La API identifica de forma diferente algunas categorias por eso este diccionario 
ALIAS = {
    "mep": "bolsa",
    "dolar mep": "bolsa",
    "ccl": "contadoconliqui",
    "liqui": "contadoconliqui",
    "contado con liqui": "contadoconliqui",
    "contado con liquidacion": "contadoconliqui",
    "turista": "tarjeta",
    "dolar turista": "tarjeta",
    "solidario": "tarjeta",
    "informal": "blue",
    "paralelo": "blue",
}


def normalizar(texto):
    sin_acentos = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode()
    return sin_acentos.lower().strip()

def error(mensaje, instruccion, **extra):
    resultado = {"error": mensaje, "instruccion_para_el_agente": instruccion}
    resultado.update(extra)
    return resultado

def pedir(ruta):
    respuesta = requests.get(f"{API_URL}/{ruta}", timeout=15)
    respuesta.raise_for_status()
    return respuesta.json()

def limpiar(item):
    return {
        "nombre": item.get("nombre"),
        "casa": item.get("casa"),
        "moneda": item.get("moneda"),
        "compra": item.get("compra"),
        "venta": item.get("venta"),
        "actualizado": item.get("fechaActualizacion"),
    }

def obtener_dolares():
    return [limpiar(d) for d in pedir("dolares")]

def obtener_otras_monedas():
    # /cotizaciones incluye el dolar; se saca para no duplicarlo
    return [limpiar(c) for c in pedir("cotizaciones") if (c.get("moneda") or "").upper() != "USD"]

def resolver(consulta, universo):
    # Busca en la lista que devolvio la API, no en una lista fija escrita aca
    objetivo = normalizar(consulta)
    objetivo = ALIAS.get(objetivo, objetivo)

    for item in universo:
        if normalizar(item["casa"]) == objetivo or normalizar(item["moneda"]) == objetivo:
            return item

    for item in universo:
        if normalizar(item["nombre"]) == objetivo:
            return item

    parciales = [i for i in universo if objetivo in normalizar(i["nombre"])]
    if len(parciales) == 1:
        return parciales[0]

    return None


def obtener_cotizaciones(consulta=None):
    try:
        dolares = obtener_dolares()
        otras = obtener_otras_monedas()
    except requests.RequestException as e:
        return error(f"Falló la consulta de cotizaciones: {e}",
                     "Decile al usuario que el servicio no está disponible ahora. "
                     "NO inventes cotizaciones.")

    if not consulta:
        return {"consulta": None, "dolares": dolares, "otras_monedas": otras}

    encontrado = resolver(consulta, dolares + otras)

    if encontrado is None:
        return error(
            f"No encontré ninguna cotización para '{consulta}'.",
            "Mostrale al usuario las opciones disponibles y pedile que elija una. "
            "NO uses otra cotización como si fuera la que pidió.",
            dolares_disponibles=[d["nombre"] for d in dolares],
            monedas_disponibles=[m["nombre"] for m in otras],
        )

    return {"consulta": consulta, "cotizacion": encontrado}


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Cotizaciones de dólar y otras monedas en Argentina")
    parser.add_argument("--consulta", default=None,
                        help="Tipo de dólar o moneda (ej: mep, blue, euro, real). Sin esto, muestra todo")

    args = parser.parse_args()
    resultado = obtener_cotizaciones(args.consulta)

    if resultado.get("error"):
        print(resultado["error"])
        if resultado.get("dolares_disponibles"):
            print("Dólar:", ", ".join(resultado["dolares_disponibles"]))
            print("Monedas:", ", ".join(resultado["monedas_disponibles"]))
        return

    if resultado.get("cotizacion"):
        c = resultado["cotizacion"]
        print(f"{c['nombre']:<22} compra: ${c['compra']:<12} venta: ${c['venta']}")
        print(f"Actualizado: {c['actualizado']}")
        return

    print("DÓLAR")
    for c in resultado["dolares"]:
        print(f"  {c['nombre']:<22} compra: ${c['compra']:<12} venta: ${c['venta']}")

    print("\nOTRAS MONEDAS")
    for c in resultado["otras_monedas"]:
        print(f"  {c['nombre']:<22} compra: ${c['compra']:<12} venta: ${c['venta']}")

    if resultado["dolares"]:
        print(f"\nActualizado: {resultado['dolares'][0]['actualizado']}")


if __name__ == "__main__":
    main()