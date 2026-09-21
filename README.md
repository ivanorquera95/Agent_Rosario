# Rosario Vivo

Agente conversacional sobre datos abiertos del Gran Rosario: precios de
supermercados, descuentos bancarios, colectivos, agenda cultural, clima y
cotizaciones.

Podés preguntarle en castellano y te contesta con datos reales, actualizados
todos los días por un pipeline propio.

```
Vos: ¿qué descuentos tengo con Personal Pay?
Rosario: En La Reina tenés 10% de reintegro los sábados, con compra mínima
de $30.000 y tope de $7.000 por semana, pagando con tarjeta física o QR
desde la app. Vigente hasta el 30/09.

Vos: ¿los jubilados tienen descuento en La Reina?
Rosario: Sí, dos:
  - 10% los martes y jueves, exclusivo para compras en sucursales
  - 10% los lunes y martes presentando carnet de ANSES

Vos: ¿dónde está más barata la leche?
Rosario: La más conveniente es la de 2,5 L de Coto, a $1.796 por litro.
Ojo que el sachet de 1 L figura más barato en el precio de góndola ($2.990)
pero sale más caro por litro.
```

---

## Por qué existe

Mi hermana no sabía qué descuentos tenía disponibles ni qué días le convenía
comprar. Terminó comparando a mano, precio por precio, La Reina contra Coto,
y se cambió de supermercado cuando descubrió que tenía un 30% de reintegro
que no estaba usando.

Esa información existe, es pública y está dispersa en ocho lugares distintos:
un dataset nacional de 1,65 GB, la API de una cadena, la web de otra y
carteles publicados como imágenes. Este proyecto la junta, la limpia y la
deja disponible para preguntarle en castellano.

---

## Arquitectura

```
  FUENTES                    EXTRACCIÓN        TRANSFORMACIÓN      CONSUMO

  SEPA (1,65 GB/día)    ─┐
  descuentito-data       │
  API propia de Coto     ├──►  Python     ──►  BigQuery  ──►  dbt  ──►  Agente
  web de La Gallega      │     + Vision        (raw_*)        (staging    (OpenAI
  web de La Reina        │       OCR                          + marts)   function
  agenda municipal       │                                               calling)
  API de colectivos     ─┘
                              ╰────────── Airflow ──────────╯
```

Cuatro DAGs orquestan todo:

| DAG | horario (Rosario) | qué hace |
|---|---|---|
| `precios` | 15:00 diario | SEPA → limpieza → BigQuery → dbt |
| `descuentos` | 07:00 diario | 3 extracciones en paralelo → limpieza → BigQuery → dbt |
| `agenda` | 07:00 diario | scraping → BigQuery → dbt |
| `colectivos` | domingo 03:00 | recorridos y paradas → BigQuery |

---

## Qué datos tiene

### Precios — 159.575 registros

Del dataset SEPA de la Secretaría de Comercio, filtrado al Gran Rosario.

| cadena | sucursales |
|---|---|
| Hipermercado Carrefour | 5 |
| COTO CICSA | 5 |
| Supermercados DIA | 2 |
| La Anónima | 1 |
| Jumbo | 1 |
| Vea | 1 |
| SIMPLICITY | 1 |

**Cobertura real: 15 supermercados de los ~28 del Gran Rosario.** Las cadenas
rosarinas (La Gallega, La Reina, Arcoiris, Dar, Micro Go, Libertad) no
publican en SEPA y por lo tanto no tienen precios acá. Está medido, no
estimado: ver *Limitaciones*.

### Descuentos — 194 promociones vigentes, 6 cadenas

| cadena | fuente | promos |
|---|---|---|
| Jumbo | descuentito-data | 61 |
| Coto | API propia (`getPromocionesMulticanal`) | 75 |
| Carrefour | descuentito-data | 30 |
| La Reina | web propia + OCR de los carteles | 15 |
| La Gallega | web propia (7 días) | 12 |
| DIA | descuentito-data | 1 |

### Otros

- **Colectivos**: 53 líneas, 8.733 paradas, 36.058 puntos de trazado, con
  llegadas en tiempo real
- **Agenda cultural**: ~190 eventos de la Municipalidad de Rosario
- **Clima** y **cotizaciones**: en vivo, sin almacenamiento

---

## Decisiones técnicas

Las que cambiaron el resultado, con el motivo.

### PySpark se sacó del proyecto después de medirlo

El pipeline de precios empezó con Spark por el tamaño del dataset. Al
verificar el resultado contra los CSV crudos, Spark devolvía **61.103 filas
donde había 159.575**: perdía el 62% de los datos sin lanzar un solo error.

Se reemplazó por pandas leyendo por trozos de 200.000 filas, filtrando contra
un `MultiIndex` y convirtiendo tipos recién al final, sobre 159 mil filas en
vez de 14,7 millones. Corre en menos de un minuto y el resultado coincide
sucursal por sucursal con la fuente.

La conclusión no es que Spark sea malo: es que 1,65 GB no justifica una JVM,
y que una herramienta que falla en silencio es peor que una lenta.

### El OCR se eligió midiendo, no por intuición

La Reina publica el porcentaje y el día **dentro de la imagen** del cartel, no
en el texto. Sin leer la imagen, de 15 promociones quedaban 12 sin porcentaje
y casi todas sin día.

Se armó `tests/verdad_lareina.json` con los valores leídos a ojo de cada
cartel, y con ese set se midió cada intento:

| intento | aciertos |
|---|---|
| Tesseract, imagen completa | 3 / 15 |
| + imagen original en vez de la miniatura | 11 / 15 |
| + recorte de la zona del número y lista blanca de dígitos | 12 / 15 |
| **Google Cloud Vision** | **15 / 15** |

Tesseract partía los números grandes y se comía el primer dígito: leía "0%"
donde decía "10%" y, peor, "45%" donde decía "15%". Un valor inventado y
plausible es más peligroso que un nulo.

**Por qué acá sí y en los folletos de precios no:** son 15 imágenes, el texto
es grande y sobre fondo plano, se buscan sólo dos datos de forma muy acotada,
y sobre todo **se puede verificar**. En un folleto de precios hay cientos de
productos, números de cuatro dígitos y ninguna forma de comprobar la lectura.

### El robots.txt de La Gallega cambió el diseño del scraper

El sitio muestra un día por vez y la única forma de pedir otro es
`PromoxDia.asp?Dia=N`. Su `robots.txt` desaconseja las URLs con query string.
El scraper se corre una vez, con pausa entre pedidos, y queda separado del
pipeline diario para que la excepción sea explícita.

### Una fila por promoción, no una por día

La primera versión guardaba una fila por cada combinación de promoción, día y
medio de pago: 539 filas para 194 promociones. El problema no era el espacio,
era la respuesta del agente: recibía la misma promo de Coto siete veces y la
repetía siete veces.

Ahora los días, las entidades y los medios de pago son arrays de BigQuery. La
consulta usa `unnest` y el agente ve 194 promociones reales.

### Las fechas viajan como texto

Al mover la limpieza al contenedor de Airflow, con otra versión de pandas y
pyarrow, BigQuery empezó a leer las fechas como `INT64` y dbt no podía
castearlas. Ahora se guardan como texto ISO y se convierten en dbt con
`parse_date`: el resultado es idéntico corra donde corra.

### Lo que el modelo hace mal se resuelve en código

Regla del proyecto: **si se puede resolver con un `if` en Python, no va en el
prompt.**

- **Comparaba mal los precios.** Con una lista de envases distintos elegía el
  número más chico. La herramienta ahora calcula cuál es el más barato por
  litro o kilo y se lo pasa masticado.
- **Inventaba productos.** Ante "¿qué conviene hoy?" llamaba a la búsqueda de
  precios con "leche", "yerba" y "fideos", que el usuario nunca nombró. Una
  guardia compara los argumentos contra lo que la persona escribió y rechaza
  lo que no está.
- **Rankeaba descuentos inútiles.** El 40% de Credicoop no le sirve a alguien
  que no tiene Credicoop. Cuando la pregunta es general, la herramienta no
  devuelve promociones: devuelve las entidades disponibles y le indica al
  agente que pregunte con qué paga.
- **Buscaba "leche" y traía alfajores**, porque "dulce de leche" contiene la
  palabra y las golosinas son más baratas. Se resolvió con relevancia por
  posición de la palabra y orden por precio por unidad.

---

## Limitaciones conocidas

Están acá porque un dato que parece completo y no lo es hace más daño que un
dato ausente.

- **Precios: 15 de ~28 supermercados.** Las cadenas rosarinas no publican en
  SEPA. Se evaluó scrapearlas: La Gallega tenía la tienda en mantenimiento,
  Arcoiris vende por WhatsApp y La Reina pide login. Sólo quedaban folletos en
  imágenes, que requerirían OCR sobre cientos de precios sin forma de
  verificarlos. Se documentó la limitación en vez de publicar precios que
  podrían estar mal leídos.
- **Los precios son de la última publicación de SEPA**, que es diaria: pueden
  no coincidir con la góndola de hoy. El agente lo aclara en cada respuesta.
- **descuentito-data acumula promociones vencidas.** De las 65 de DIA sólo 1
  seguía vigente, y las 18 de Coto habían vencido dos meses antes. Se filtra
  por fecha de vigencia y Coto se lee de su API propia.
- **Algunas promociones no publican vigencia.** Cuando no hay fecha se dejan
  pasar en vez de descartarlas: la mayoría de las promos bancarias no publican
  fin y descartar por falta de dato perdería más promos buenas de las que
  evitaría mostrar vencidas.
- **La Gallega necesita siete corridas** para tener la semana completa, porque
  el sitio muestra un día por vez.

---

## Stack

| capa | herramienta |
|---|---|
| extracción | Python, requests, BeautifulSoup |
| OCR | Google Cloud Vision |
| procesamiento | pandas (por trozos) |
| almacenamiento | BigQuery |
| transformación | dbt (staging en vistas, marts en tablas, tests declarativos) |
| orquestación | Airflow en Docker |
| agente | OpenAI function calling (gpt-4o-mini) |

---

## Cómo correrlo

### Requisitos

- Python 3.12 y [uv](https://docs.astral.sh/uv/)
- Un proyecto de Google Cloud con BigQuery y Vision habilitadas
- Una API key de OpenAI

### Puesta en marcha

```bash
git clone https://github.com/ivanorquera95/Agent_Rosario.git
cd Agent_Rosario
uv sync

# credenciales de Google
gcloud auth application-default login
gcloud services enable vision.googleapis.com

# la API key de OpenAI
echo "OPENAI_API_KEY=sk-..." > .env
```

### El pipeline a mano

```bash
# precios
uv run ./scripts/precios/extraccion_precios.py
uv run ./scripts/precios/limpieza_precios.py
uv run ./scripts/precios/subir_precios_bigquery.py

# descuentos
uv run ./scripts/descuentos/extraccion_descuentos.py
uv run ./scripts/descuentos/extraccion_lagallega.py
uv run ./scripts/descuentos/extraccion_lareina.py
uv run ./scripts/descuentos/limpieza_descuentos.py
uv run ./scripts/descuentos/subir_descuentos_bigquery.py

# transformación
cd agent_rosario_dbt && uv run dbt build --profiles-dir .
```

### El pipeline con Airflow

```bash
cd airflow
cp .env.ejemplo .env      # ajustar la ruta de las credenciales
mkdir dags logs
docker compose up init
docker compose up -d
```

La interfaz queda en `http://localhost:8080` (usuario `admin`, contraseña
`admin`).

### El agente

```bash
uv run ./agent_rosario.py
```

---

## Estructura

```
├── agent_rosario.py          el agente: tools, guardias y bucle de chat
├── rosario.md                el system prompt
├── agent_rosario_dbt/        modelos dbt (staging y marts)
├── airflow/
│   ├── dags/                 los cuatro DAGs
│   ├── Dockerfile
│   └── docker-compose.yml
├── scripts/
│   ├── precios/              SEPA: extracción, limpieza, carga, consulta
│   ├── descuentos/           5 fuentes, unificación y consulta
│   ├── colectivos/           recorridos, paradas y llegadas en vivo
│   ├── agenda/               agenda cultural municipal
│   ├── clima/  monedas/  lugares/
│   └── comun/
└── tests/
    └── verdad_lareina.json   set de verdad para medir el OCR
```

---

## Qué falta

- El agente sólo corre por terminal: falta una interfaz web
- Los recorridos de colectivos no tienen modelos dbt
- DIA se quedó con una sola promoción vigente: le falta fuente propia
- Billetera Santa Fe cubriría las 13 cadenas rosarinas de una sola fuente,
  que es justo el agujero que deja SEPA