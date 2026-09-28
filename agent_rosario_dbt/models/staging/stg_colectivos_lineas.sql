select
    id_linea,
    nombre,
    nombre_corto,
    codigo_emr,
    color,
    id_empresa,
    nombre_empresa,
    fecha_extraccion
from {{ source('rosario_vivo', 'raw_colectivos_lineas') }}