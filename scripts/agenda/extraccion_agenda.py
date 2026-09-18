#Extrae la agenda cultural de rosario.gob.ar.

import sys
import os
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import csv
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://www.rosario.gob.ar"
# Sin los tres parametros vacios el buscador aplica un filtro por defecto y devuelve menos eventos de los que hay.
URL_BUSCADOR = f"{BASE_URL}/inicio/agenda/buscar?titulo-actividad=&fin=&inicio="
HEADERS = {"User-Agent": "RosarioVivo/1.0 (proyecto de portfolio, uso de datos publicos)"}
ZONA_ROSARIO = ZoneInfo("America/Argentina/Buenos_Aires")

SALIDA = Path("./data/raw/agenda")
MAX_PAGINAS = 60
PAUSA_ENTRE_PAGINAS_SEG = 0.5
HILOS_DETALLE = 6


def ahora():
    return datetime.now(ZONA_ROSARIO).isoformat(timespec="seconds")


def parsear_fecha_parcial(texto_dia_mes, hoy):
    dia, mes = (int(x) for x in texto_dia_mes.split("."))
    fecha = date(hoy.year, mes, dia)
    # La agenda solo muestra lo que viene: si la fecha ya paso, es del año que viene
    if fecha < hoy.replace(day=1):
        fecha = date(hoy.year + 1, mes, dia)
    return fecha


def parsear_fecha_card(texto, hoy=None):
    hoy = hoy or datetime.now(ZONA_ROSARIO).date()
    texto = texto.strip()

    if " al " in texto:
        inicio_txt, fin_txt = texto.split(" al ")
        fecha_inicio = parsear_fecha_parcial(inicio_txt.strip(), hoy)
        fecha_fin = parsear_fecha_parcial(fin_txt.strip(), hoy)
        if fecha_fin < fecha_inicio:
            fecha_fin = date(fecha_fin.year + 1, fecha_fin.month, fecha_fin.day)
        return fecha_inicio, fecha_fin

    return parsear_fecha_parcial(texto, hoy), None


def parsear_tarjetas(soup):
    eventos = []

    for tarjeta in soup.find_all("actividad"):
        link = tarjeta.find("a", href=True)
        if not link:
            continue

        titulo_tag = tarjeta.find("h3", class_="govuk-heading-s")
        fecha_tag = tarjeta.find("div", class_="fecha-card")
        etiqueta_tag = tarjeta.select_one("div.etiqueta-actividad-card > div")
        img_tag = tarjeta.find("img")

        titulo = titulo_tag.get_text(strip=True) if titulo_tag else None
        fecha_texto = fecha_tag.get_text(" ", strip=True) if fecha_tag else None

        if not titulo or not fecha_texto:
            continue

        fecha_inicio, fecha_fin = parsear_fecha_card(fecha_texto)

        eventos.append({
            "titulo": titulo,
            "url": BASE_URL + link["href"],
            "slug": link["href"].strip("/").split("/")[-1],
            "fecha_inicio": fecha_inicio.isoformat(),
            "fecha_fin": fecha_fin.isoformat() if fecha_fin else None,
            "etiqueta_serie": etiqueta_tag.get_text(strip=True) if etiqueta_tag else None,
            "imagen_descripcion": img_tag.get("alt") if img_tag else None,
        })

    return eventos


def texto_propio(tag):
    #Solo los nodos de texto directos del tag, sin los hijos.
    #El <p class="title-lugar"> contiene adentro la direccion y los enlaces "Cómo llego" y "Ver mapa": con get_text() sale todo pegado

    return "".join(tag.find_all(string=True, recursive=False)).strip()


def obtener_detalle_evento(url):
    detalle = {
        "lugar_nombre": None,
        "lugar_direccion": None,
        "lugar_id": None,
        "lugar_latitud": None,
        "lugar_longitud": None,
        "dias": None,
        "hora_texto": None,
        "entrada": None,
        "es_gratis": None,
        "descripcion": None,
        "categorias": [],
        "detalle_ok": False,
        "lugar_eventual": False,
        "lugar_heredado": False,
        "url_padre": None,
        "lugar_deducido": False,
        "finalizada": False,
    }

    REINTENTOS = 3
    respuesta = None
    for intento in range(REINTENTOS):
        try:
            respuesta = requests.get(url, headers=HEADERS, timeout=20)
            respuesta.raise_for_status()
            break
        except requests.RequestException:
            respuesta = None
            if intento < REINTENTOS - 1:
                # Con 222 pedidos en paralelo, alguno falla por timeout. Al
                # reintentar suele salir bien.
                time.sleep(1 + intento)

    if respuesta is None:
        return detalle

    soup = BeautifulSoup(respuesta.text, "html.parser")
    detalle["detalle_ok"] = True

    dias_tag = soup.select_one("span.rule-dias")
    if dias_tag:
        detalle["dias"] = dias_tag.get_text(" ", strip=True)

    hora_tag = soup.select_one("span.rule-text")
    if hora_tag:
        detalle["hora_texto"] = hora_tag.get_text(" ", strip=True)
    else:
        match = re.search(r"DE\s+\d{1,2}(:\d{2})?\s+a\s+\d{1,2}(:\d{2})?\s+horas?",
                          soup.get_text(" ", strip=True), re.IGNORECASE)
        if match:
            detalle["hora_texto"] = match.group(0)

    nombre_tag = soup.select_one("lugar p.title-lugar")
    if nombre_tag:
        detalle["lugar_nombre"] = texto_propio(nombre_tag) or None

    direccion_tag = soup.select_one("lugar p.direccion-lugar")
    if direccion_tag:
        detalle["lugar_direccion"] = direccion_tag.get_text(" ", strip=True)
    # Cuando el evento es en un lugar ocasional (una esquina, una plaza) el
    # municipio no usa la etiqueta <lugar> sino este div, con solo la direccion.
    if not detalle["lugar_direccion"]:
        eventual_tag = soup.select_one("div.field_lugar_eventual")
        if eventual_tag:
            detalle["lugar_direccion"] = eventual_tag.get_text(" ", strip=True)
            detalle["lugar_eventual"] = True

    # "Ver mapa" apunta a /inicio/mapa-lugar/6300: ese id es una clave real del
    # lugar, mucho mejor que joinear por nombre.
    mapa_tag = soup.select_one("a[href*='mapa-lugar']")
    if mapa_tag:
        match = re.search(r"mapa-lugar/(\d+)", mapa_tag["href"])
        if match:
            detalle["lugar_id"] = match.group(1)

    como_llego_tag = soup.select_one("a[href*='hasta-el-destino']")
    if como_llego_tag:
        match = re.search(r"hasta-el-destino/(-?\d+\.\d+),(-?\d+\.\d+)", como_llego_tag["href"])
        if match:
            detalle["lugar_latitud"] = float(match.group(1))
            detalle["lugar_longitud"] = float(match.group(2))

    entrada_tag = soup.select_one("div.entrada-actividad b div")
    if entrada_tag:
        detalle["entrada"] = entrada_tag.get_text(" ", strip=True)
        detalle["es_gratis"] = "gratis" in detalle["entrada"].lower()

    categorias = [c.get_text(strip=True) for c in soup.select("a[href*='agenda/buscar?etiquetas']")]
    detalle["categorias"] = sorted({c for c in categorias if c})
    # "Forma parte de": el evento hereda el lugar de su padre, que suele tener
    # la sede cargada aunque el hijo no.
    madre_tag = soup.select_one("div.container-actividad-madre a[href^='/inicio/']")
    if madre_tag:
        detalle["url_padre"] = BASE_URL + madre_tag["href"].replace("/index.php", "")

    detalle["finalizada"] = "actividad finalizada" in soup.get_text(" ", strip=True).lower()
    desc_tag = soup.select_one(".descripcion")
    if desc_tag:
        # La descripcion completa: el agente la usa para contar de que se trata
        # el evento, y de aca se deduce el lugar cuando el municipio no lo carga.
        detalle["descripcion"] = desc_tag.get_text(" ", strip=True)[:1500]
    
    
    return detalle


def enriquecer_con_detalle(eventos):
    total = len(eventos)
    completados = 0

    with ThreadPoolExecutor(max_workers=HILOS_DETALLE) as executor:
        futuros = {executor.submit(obtener_detalle_evento, e["url"]): e for e in eventos}

        for futuro in as_completed(futuros):
            futuros[futuro].update(futuro.result())
            completados += 1
            if completados % 25 == 0 or completados == total:
                print(f"  detalle: {completados}/{total}")

    return eventos

def heredar_lugar_del_padre(eventos):
    #Los eventos que "forman parte de" otro heredan su lugar.

    por_url = {e["url"]: e for e in eventos}
    heredados = 0

    for e in eventos:
        if e.get("lugar_direccion") or not e.get("url_padre"):
            continue

        padre = por_url.get(e["url_padre"])
        if not padre or not padre.get("lugar_direccion"):
            continue

        for campo in ("lugar_nombre", "lugar_direccion", "lugar_id",
                      "lugar_latitud", "lugar_longitud", "lugar_deducido"):
            e[campo] = padre.get(campo)
        e["lugar_heredado"] = True
        heredados += 1

    print(f"  {heredados} evento(s) heredaron el lugar de su actividad madre")
    return eventos

def scrapear_agenda(max_paginas=MAX_PAGINAS):
    todos = {}

    for pagina in range(max_paginas):
        url = URL_BUSCADOR if pagina == 0 else f"{URL_BUSCADOR}&page={pagina}"
        respuesta = requests.get(url, headers=HEADERS, timeout=20)
        respuesta.raise_for_status()

        eventos_pagina = parsear_tarjetas(BeautifulSoup(respuesta.text, "html.parser"))
        if not eventos_pagina:
            print(f"  página {pagina}: sin resultados, fin")
            break

        nuevos = 0
        for evento in eventos_pagina:
            if evento["slug"] not in todos:
                todos[evento["slug"]] = evento
                nuevos += 1

        print(f"  página {pagina}: {len(eventos_pagina)} eventos ({nuevos} nuevos)")

        if nuevos == 0:
            print("  sin eventos nuevos, fin")
            break

        time.sleep(PAUSA_ENTRE_PAGINAS_SEG)

    return list(todos.values())


COLUMNAS = [
    "slug", "titulo", "url", "fecha_inicio", "fecha_fin", "etiqueta_serie",
    "imagen_descripcion", "lugar_id", "lugar_nombre", "lugar_direccion",
    "lugar_latitud", "lugar_longitud", "lugar_eventual", "lugar_heredado",
    "url_padre", "finalizada", "dias", "hora_texto", "entrada","lugar_deducido",
    "es_gratis", "categorias", "descripcion", "detalle_ok", "fecha_extraccion",
]


def guardar_csv(eventos, ruta):
    ruta.parent.mkdir(parents=True, exist_ok=True)

    # Aviso: si un evento trae campos que no estan en COLUMNAS, se pierden al
    # guardar. Paso tres veces antes de que lo notaramos.
    extras = {c for e in eventos for c in e} - set(COLUMNAS)
    if extras:
        print(f"  [!] campos que no se guardan por faltar en COLUMNAS: {sorted(extras)}")

    filas = []
    for e in eventos:
        fila = {c: e.get(c) for c in COLUMNAS}
        fila["categorias"] = "; ".join(e.get("categorias") or [])
        filas.append(fila)

    with open(ruta, "w", newline="", encoding="utf-8") as f:
        escritor = csv.DictWriter(f, fieldnames=COLUMNAS, quoting=csv.QUOTE_ALL)
        escritor.writeheader()
        escritor.writerows(filas)

    print(f"  {ruta}: {len(filas)} filas")


def resumen(eventos):
    total = len(eventos)
    def contar(condicion):
        return sum(1 for e in eventos if condicion(e))

    print(f"\nEventos: {total}")
    print(f"con lugar  : {contar(lambda e: e.get('lugar_nombre'))}")
    print(f"con dirección : {contar(lambda e: e.get('lugar_direccion'))}")
    print(f"con coordenadas : {contar(lambda e: e.get('lugar_latitud'))}")
    print(f"con id de lugar : {contar(lambda e: e.get('lugar_id'))}")
    print(f"con días : {contar(lambda e: e.get('dias'))}")
    print(f"con hora : {contar(lambda e: e.get('hora_texto'))}")
    print(f"con entrada : {contar(lambda e: e.get('entrada'))}")
    print(f"con categorías : {contar(lambda e: e.get('categorias'))}")
    print(f"lugar heredado : {contar(lambda e: e.get('lugar_heredado'))}")
    print(f"finalizadas : {contar(lambda e: e.get('finalizada'))}")
    print(f"detalle falló : {contar(lambda e: not e.get('detalle_ok'))}")

    sucios = [e for e in eventos if e.get("lugar_nombre") and
              ("Cómo llego" in e["lugar_nombre"] or "Ver mapa" in e["lugar_nombre"])]
    if sucios:
        print(f"\n[!] {len(sucios)} lugar(es) con el nombre sucio:")
        for e in sucios[:5]:
            print(f"    {e['lugar_nombre'][:80]}")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Scrapear la agenda cultural de Rosario")
    parser.add_argument("--max-paginas", type=int, default=MAX_PAGINAS)
    parser.add_argument("--sin-detalle", action="store_true",
                        help="Saltear la página de detalle de cada evento")
    parser.add_argument("--sin-deducir", action="store_true",
                        help="Saltear la deducción del lugar con el modelo")

    args = parser.parse_args()
    fecha_extraccion = ahora()

    print("Scrapeando el listado...")
    eventos = scrapear_agenda(max_paginas=args.max_paginas)
    print(f"\nTotal de eventos: {len(eventos)}")

    if not args.sin_detalle:
        print("\nBuscando el detalle de cada evento...")
        eventos = enriquecer_con_detalle(eventos)

        if not args.sin_deducir:
            print("\nDeduciendo el lugar de los que no lo tienen...")
            from agenda.deducir_lugar import deducir_lugares
            eventos = deducir_lugares(eventos)

        # Despues de deducir: si el padre consiguio lugar, los hijos lo heredan.
        eventos = heredar_lugar_del_padre(eventos)

    for e in eventos:
        e["fecha_extraccion"] = fecha_extraccion

    print("\nGuardando:")
    guardar_csv(eventos, SALIDA / "agenda.csv")
    resumen(eventos)
    print(f"\nFecha de extracción: {fecha_extraccion}")


if __name__ == "__main__":
    main()