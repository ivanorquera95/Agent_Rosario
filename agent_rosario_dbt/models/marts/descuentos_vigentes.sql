{{ config(materialized='table') }}

with base as (
    select * from {{ ref('stg_descuentos') }}
),

vigentes as (
    select *
    from base
    -- Sin fecha de fin no sabemos cuando termina. La dejamos pasar en
    -- lugar de descartarla: la mayoria de las promos bancarias no
    -- publican vigencia y siguen activas. Descartar por falta de dato
    -- perderia mas promos buenas de las que evitaria mostrar vencidas.
    where vigencia_hasta is null
       or vigencia_hasta >= current_date('America/Argentina/Buenos_Aires')
)

select
    clave_descuento,
    id_promo,
    cadena,
    fuente,
    tipo_beneficio,
    porcentaje,
    cuotas,
    entidades,
    medios_pago,
    dias,

    -- 'Todos' significa que la promo corre cualquier dia. Expandirlo aca
    -- deja la consulta del agente en una sola condicion, en vez de un
    -- "o la lista contiene Todos" que hay que acordarse de escribir cada
    -- vez que se consulta la tabla.
    case
        when 'Todos' in unnest(dias)
            then ['Lunes', 'Martes', 'Miercoles', 'Jueves', 'Viernes', 'Sabado', 'Domingo']
        else dias
    end as dias_efectivos,

    vigencia_desde,
    vigencia_hasta,
    tope,
    sin_tope,
    donde,
    texto,
    texto_imagen,
    excluye,
    url,
    fecha_extraccion,

    -- Mismo criterio que en precios: un solo campo en mayusculas y sin
    -- acentos donde buscar, para que "personal pay" encuentre la promo
    -- este el nombre en la entidad, en el medio de pago o en el texto.
    upper(regexp_replace(
        normalize(
            concat(
                cadena, ' ',
                array_to_string(entidades, ' '), ' ',
                array_to_string(medios_pago, ' '), ' ',
                coalesce(texto, ''), ' ',
                coalesce(texto_imagen, '')
            ),
            NFD
        ),
        r'\p{Mn}', ''
    )) as busqueda

from vigentes