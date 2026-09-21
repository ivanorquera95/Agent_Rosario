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
    date(vigencia_desde) as vigencia_desde,
    date(vigencia_hasta) as vigencia_hasta,
    tope,
    sin_tope,
    donde,
    texto,
    texto_imagen,
    excluye,
    url,
    date(fecha_extraccion) as fecha_extraccion
from crudo