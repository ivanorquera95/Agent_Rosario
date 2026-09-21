with crudo as (
    select * from {{ source('rosario_vivo', 'raw_descuentos') }}
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
    parse_date('%Y-%m-%d', vigencia_desde) as vigencia_desde,
    parse_date('%Y-%m-%d', vigencia_hasta) as vigencia_hasta,
    tope,
    sin_tope,
    donde,
    texto,
    texto_imagen,
    excluye,
    url,
    parse_date('%Y-%m-%d', fecha_extraccion) as fecha_extraccion
from crudo