#Deduce el lugar de un evento leyendo su descripcion. Solo corre para los eventos que el municipio dejo sin direccion. 
#El dato suele estar en el texto. Se hace UNA vez por corrida y queda guardado. 

import json
import os
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

MODELO = os.environ.get("MODELO_DEDUCCION", "gpt-4o-mini")
PAUSA_SEG = 0.2

INSTRUCCIONES = """
Sos un extractor de datos. Te paso el título y la descripción de un evento
cultural de Rosario, Argentina, y tenés que decir en qué lugar se hace.

Reglas:
- Extraé SOLO lo que el texto dice literalmente. No uses lo que sepas de Rosario.
- Si el texto no menciona un lugar concreto, devolvé null en los dos campos.
- "en Rosario", "en el oeste", "en la zona sur" NO son lugares: son la ciudad o
  una zona. Eso es null.
- Si el texto trae la dirección, ponela. Si no, dejá direccion en null pero
  completá el nombre.

Respondé SOLO un JSON con esta forma, sin explicaciones:
{"lugar": "nombre del lugar o null", "direccion": "calle y altura o null"}"""


cliente = None


def obtener_cliente():
    global cliente
    if cliente is None:
        cliente = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    return cliente


def deducir_uno(titulo, descripcion, modelo=None):
    #Devuelve (lugar, direccion), cualquiera de los dos puede ser None.
    if not descripcion:
        return None, None

    try:
        respuesta = obtener_cliente().chat.completions.create(
            model=modelo or MODELO,
            messages=[
                {"role": "system", "content": INSTRUCCIONES},
                {"role": "user", "content": f"Título: {titulo}\n\nDescripción: {descripcion}"},
            ],
            response_format={"type": "json_object"},
            temperature=0,
        )
        datos = json.loads(respuesta.choices[0].message.content)
    except Exception:
        return None, None

    def limpiar(valor):
        if not valor or str(valor).strip().lower() in ("null", "none", "-", ""):
            return None
        return str(valor).strip()

    return limpiar(datos.get("lugar")), limpiar(datos.get("direccion"))


def deducir_lugares(eventos, modelo=None):
    #Completa lugar y direccion de los eventos que no los tienen.

    pendientes = [e for e in eventos if not e.get("lugar_direccion") and not e.get("lugar_nombre")]

    if not pendientes:
        print("  no hay eventos sin lugar")
        return eventos

    print(f"  deduciendo el lugar de {len(pendientes)} evento(s) con {modelo or MODELO}")

    completados = 0
    for e in pendientes:
        lugar, direccion = deducir_uno(e.get("titulo"), e.get("descripcion"), modelo)

        if not lugar and not direccion:
            continue

        e["lugar_nombre"] = lugar
        e["lugar_direccion"] = direccion
        e["lugar_deducido"] = True
        completados += 1

        time.sleep(PAUSA_SEG)

    print(f"  {completados} de {len(pendientes)} resueltos")
    return eventos


def main():
    #Corre la deduccion sobre el CSV ya extraido, sin volver a scrapear.
    import argparse
    import csv
    from pathlib import Path

    parser = argparse.ArgumentParser(description="Deducir el lugar de los eventos sin dirección")
    parser.add_argument("--modelo", default=None, help="Modelo de OpenAI a usar")
    parser.add_argument("--csv", default="./data/raw/agenda/agenda.csv")
    parser.add_argument("--guardar", action="store_true", help="Escribir el resultado al CSV")

    args = parser.parse_args()
    ruta = Path(args.csv)

    with open(ruta, encoding="utf-8") as f:
        eventos = list(csv.DictReader(f))
        columnas = list(eventos[0].keys()) if eventos else []

    pendientes = [e for e in eventos if not e.get("lugar_direccion") and not e.get("lugar_nombre")]
    print(f"{len(pendientes)} evento(s) sin lugar\n")

    for e in pendientes:
        lugar, direccion = deducir_uno(e.get("titulo"), e.get("descripcion"), args.modelo)
        estado = "OK" if (lugar or direccion) else "--"
        print(f"  {estado}  {e['titulo'][:52]:<52} | {lugar or '-'} | {direccion or '-'}")

        if args.guardar and (lugar or direccion):
            e["lugar_nombre"] = lugar
            e["lugar_direccion"] = direccion
            e["lugar_deducido"] = True

        time.sleep(PAUSA_SEG)

    if args.guardar:
        if "lugar_deducido" not in columnas:
            columnas.append("lugar_deducido")
        with open(ruta, "w", newline="", encoding="utf-8") as f:
            escritor = csv.DictWriter(f, fieldnames=columnas, quoting=csv.QUOTE_ALL)
            escritor.writeheader()
            escritor.writerows(eventos)
        print(f"\nGuardado en {ruta}")


if __name__ == "__main__":
    main()