-- Cuando el contenido se puede leer de la descripcion, el precio por kilo/litro
-- tiene que ser el precio dividido por ese contenido. Se tolera un 5% por
-- redondeos y por el descuento de promo aplicado sobre el precio de lista.
-- Este test es el que hubiera cazado el "* 1000" que multiplicaba por mil el
-- 46% de los precios por kilo.
with esperado as (
    select
        clave_precio,
        descripcion,
        precio_efectivo,
        precio_por_unidad,
        case
            when contenido_chico > 0 then safe_divide(precio_efectivo, contenido_chico / 1000)
            when contenido_grande > 0 then safe_divide(precio_efectivo, contenido_grande)
        end as por_unidad_esperado
    from {{ ref('precios_gran_rosario') }}
    where precio_por_unidad is not null
      and unidad_comparable in ('kg', 'l')
      and coalesce(contenido_chico, contenido_grande) > 0
)
select *
from esperado
where por_unidad_esperado is not null
  and abs(precio_por_unidad - por_unidad_esperado) > 0.05 * por_unidad_esperado