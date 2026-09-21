with crudo as (
    select * from {{ source('rosario_vivo', 'raw_precios_comercios') }}
)

select
    id_comercio,
    id_bandera,
    cuit,
    razon_social,
    nombre_bandera,
    timestamp(fecha_extraccion) as fecha_extraccion

from crudo