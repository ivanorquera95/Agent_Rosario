-- Un precio por kilo/litro de menos de $100 no existe: es la fuente
-- equivocandose de escala. Esas filas tienen que quedar sin precio por unidad.
select clave_precio, descripcion, comercio, precio_efectivo, precio_por_unidad
from {{ ref('precios_gran_rosario') }}
where unidad_comparable in ('kg', 'l')
  and precio_por_unidad is not null
  and precio_por_unidad < 100