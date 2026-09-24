-- El precio por kilo/litro es el que decide cuál conviene: si falta en
-- demasiados productos, la comparación deja de servir. Falla si más del 5%
-- de los que tienen unidad comparable quedaron sin él.
select
    countif(precio_por_unidad is null) as sin_precio_por_unidad,
    count(*) as total
from {{ ref('precios_gran_rosario') }}
where unidad_comparable in ('kg', 'l')
having safe_divide(countif(precio_por_unidad is null), count(*)) > 0.05