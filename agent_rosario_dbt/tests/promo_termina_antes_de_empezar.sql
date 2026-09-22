select clave_precio, leyenda_promo1, promo_desde, promo_hasta
from {{ ref('precios_gran_rosario') }}
where promo_desde > promo_hasta