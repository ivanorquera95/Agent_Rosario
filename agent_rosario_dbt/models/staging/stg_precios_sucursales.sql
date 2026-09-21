with crudo as (
    select * from {{ source('rosario_vivo', 'raw_precios_sucursales') }}
)

select
    id_comercio,
    id_bandera,
    id_sucursal,

    sucursales_nombre as nombre,
    sucursales_tipo as tipo,
    trim(concat(sucursales_calle, ' ', sucursales_numero)) as direccion,

    -- Dos localidades a proposito: la que carga el comercio (suele ser un
    -- barrio) y la que se dedujo de las coordenadas, que es la confiable.
    sucursales_localidad as localidad_declarada,
    localidad_gran_rosario as localidad,

    sucursales_provincia as provincia,
    latitud,
    longitud,

    timestamp(fecha_extraccion) as fecha_extraccion

from crudo