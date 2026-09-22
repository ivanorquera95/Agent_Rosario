-- Toda leyenda que tiene una fecha tiene que terminar con promo_hasta.
select clave_precio, leyenda_promo1
from {{ ref('precios_gran_rosario') }}
where regexp_contains(leyenda_promo1, r'\d{1,2}/\d{1,2}/\d{4}')
  and promo_hasta is null