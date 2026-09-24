with crudo as (
    select * from {{ source('rosario_vivo', 'raw_precios_productos') }}
),

normalizado as (
    select
        *,
        -- Lo que realmente pagas hoy por una unidad. El menor de los dos a
        -- proposito: hay filas donde la "promo" viene mas cara que el precio
        -- de lista, y sin el least() el agente recomendaria la mas cara.
        least(precio_lista, coalesce(precio_promo1, precio_lista)) as precio_hoy,

        -- Cada cadena escribe la unidad como se le canta: hay 49 variantes
        -- para tres magnitudes (lt/LT/ltr/L, GRM/GRS/gr./GR1, KG/kgm/kgr).
        -- Sin unificarlas, comparar "precio por unidad" entre comercios es
        -- comparar $/ml contra $/litro.
        upper(replace(trim(unidad_referencia), '.', '')) as unidad_limpia,

        -- El contenido real esta en la descripcion ("X 70 GRS", "200 ML",
        -- "PAQ-500-gr."). Es el dato mas confiable de los tres: la fuente
        -- publica cantidad_referencia = 1 en el 54% de las filas (una caja de
        -- 228 gr aparece como "1 KG"), y precio_referencia trae la escala
        -- corrida en unas 8.500. Medido: de 89.840 filas con contenido legible,
        -- precio_referencia coincide en 81.433 y el calculo por cantidad en 40.145.
        --
        -- Primero el sufijo de Vea y Jumbo ("PAQ-500-gr.", "BSA-0.21-Kg"), que
        -- va siempre al final y es inequivoco. Sin el, "Yerba UNION 1/2kg
        -- PAQ-500-gr." leia el 2 de "1/2" como si fueran 2 kilos.
        coalesce(
            safe_cast(regexp_extract(upper(descripcion),
                r'-\s*([0-9]+(?:[.,][0-9]+)?)\s*-\s*(?:ML|CC|CM3|GRS|GRM|GR)\.?\s*$') as float64),
            safe_cast(regexp_extract(upper(descripcion),
                r'(?:^|[\s(])X?\s*([0-9]+(?:[.,][0-9]+)?)\s*(?:ML|CC|CM3|GRS|GRM|GR)\b') as float64)
        ) as contenido_chico,
        coalesce(
            safe_cast(regexp_extract(upper(descripcion),
                r'-\s*([0-9]+(?:[.,][0-9]+)?)\s*-\s*(?:KG|KGR|KGM|LT|LTR|L)\.?\s*$') as float64),
            safe_cast(regexp_extract(upper(descripcion),
                r'(?:^|[\s(])X?\s*([0-9]+(?:[.,][0-9]+)?)\s*(?:KG|KGR|KGM|LT|LTR|L)\b') as float64)
        ) as contenido_grande,

        -- "BSA-6-un.", "x 6u": la descripcion dice cuantas unidades trae, no
        -- cuanto pesa. La fuente igual etiqueta esas filas como KG y calcula
        -- el precio por alfajor: asi una caja quedaba a "$599 el kilo" y le
        -- ganaba a cualquier producto real en una busqueda amplia.
        regexp_contains(upper(descripcion), r'[0-9]+\s*-?\s*(?:UN|UNI|UNID|UNIDADES?|U)\b') as dice_unidades

    from crudo
),

con_precio_unidad as (
    select
        *,
        -- Precio por kilo o litro: el que decide cual conviene, porque el mismo
        -- producto viene en envases distintos. No se muestra al usuario (el kilo
        -- de alfajor es una cifra que nadie paga), solo ordena los resultados.
        --
        -- Primero la descripcion, que es donde esta el contenido real. Si no se
        -- puede leer, precio_referencia de la fuente, escalado por la promo
        -- porque viene calculado sobre el precio de lista.
        round(
            case
                when contenido_chico > 0 then safe_divide(precio_hoy, contenido_chico / 1000)
                when contenido_grande > 0 then safe_divide(precio_hoy, contenido_grande)
                else precio_referencia * safe_divide(precio_hoy, precio_lista)
            end,
            2
        ) as precio_unidad_crudo

    from normalizado
)

select
    id_comercio,
    id_bandera,
    id_sucursal,
    id_producto,

    descripcion,
    marca,
    cantidad_presentacion,
    unidad_presentacion,

    precio_lista,
    precio_referencia,
    cantidad_referencia,
    unidad_referencia,
    contenido_chico,
    contenido_grande,

    precio_promo1,
    leyenda_promo1,
    precio_promo2,
    leyenda_promo2,

    precio_hoy as precio_efectivo,
    precio_promo1 is not null as tiene_promo,

    -- Tres magnitudes comparables. Lo que no entra en ninguna (m2, mtr, par,
    -- Pie) queda nulo: son productos que no se comparan por peso ni volumen.
    case
        -- Servicios que la fuente carga como productos a precio simbolico
        -- ("REPARACION CONTINGENCIA", "GARANTIA EXTENDIDA" a $1). No se comparan.
        when precio_lista <= 10 then null
        -- La descripcion manda sobre unidad_referencia: si dice unidades y no
        -- trae peso ni volumen, se compara por unidad.
        when dice_unidades and coalesce(contenido_chico, contenido_grande) is null then 'unidad'
        when unidad_limpia in ('KG', 'KGM', 'KGR', 'GRM', 'GRS', 'GR', 'GR1') then 'kg'
        when unidad_limpia in ('LT', 'LTR', 'L', 'DM3', 'ML', 'ML1', 'CM3', 'CC') then 'l'
        when unidad_limpia in ('UNI', 'UN', 'UN1', 'UD', 'UNIDAD', 'PC', 'CU', 'PCK') then 'unidad'
    end as unidad_comparable,

    -- Menos de $100 el kilo o el litro no existe: es la fuente equivocandose de
    -- escala (alimento para perro de "8000 kgr" cuando son gramos, pan a "$40
    -- el kilo"). Sin precio por unidad el producto igual aparece, solo que
    -- ordenado por el precio del envase.
    if(precio_unidad_crudo >= 100, precio_unidad_crudo, null) as precio_por_unidad,

    timestamp(fecha_extraccion) as fecha_extraccion

from con_precio_unidad
-- Sin precio no hay nada que comparar, y un precio 0 es un error de carga del
-- comercio, no una oferta. El precio_referencia negativo tambien existe: son
-- 26 mil pesos bajo cero en la tabla de KG.
where precio_lista is not null
  and precio_lista > 0
  and coalesce(precio_referencia, 0) >= 0