{{ config(materialized='table') }}

with productos as (
    select * from {{ ref('stg_precios_productos') }}
),

comercios as (
    select * from {{ ref('stg_precios_comercios') }}
),

sucursales as (
    select * from {{ ref('stg_precios_sucursales') }}
)

select
    -- Clave compuesta pegada en una sola columna, para poder testear la
    -- unicidad de las tres juntas sin instalar dbt_utils.
    concat(p.id_comercio, '-', p.id_sucursal, '-', p.id_producto) as clave_precio,

    p.id_producto,
    p.descripcion,
    p.marca,
    p.cantidad_presentacion,
    p.unidad_presentacion,
    -- Descripcion y marca juntas, en mayusculas y sin acentos: normalize(NFD)
    -- separa cada letra de su tilde y el regexp borra las tildes sueltas, asi
    -- "cafe" encuentra "CAFÉ". Se calcula una vez por corrida, no por consulta.
    upper(regexp_replace(
        normalize(concat(coalesce(p.descripcion, ''), ' ', coalesce(p.marca, '')), NFD),
        r'\p{Mn}', ''
    )) as busqueda,

    p.precio_lista,
    p.precio_efectivo,
    p.tiene_promo,
    p.leyenda_promo1,
    p.precio_referencia,
    p.precio_por_unidad,
    p.unidad_comparable,
    p.cantidad_referencia,
    p.unidad_referencia,

    c.nombre_bandera as comercio,
    c.razon_social,

    s.nombre as sucursal,
    s.direccion as sucursal_direccion,
    s.localidad,
    s.latitud,
    s.longitud,

    p.id_comercio,
    p.id_bandera,
    p.id_sucursal,
    p.fecha_extraccion

from productos as p

-- Por las DOS columnas: el comercio 10 son Carrefour, Maxi, Express y Market.
-- Joinear solo por id_comercio multiplicaria cada precio por cuatro.
left join comercios as c
    on p.id_comercio = c.id_comercio
   and p.id_bandera = c.id_bandera

left join sucursales as s
    on p.id_comercio = s.id_comercio
   and p.id_sucursal = s.id_sucursal