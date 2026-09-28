-- La capa raw guarda todo como texto a proposito (los ids de linea tienen
-- letras y el tipo no puede depender de la version de pandas de cada entorno).
-- El casteo va aca.
select
    id_linea,
    id_parada,
    nombre,
    ochava,
    safe_cast(latitud as float64) as latitud,
    safe_cast(longitud as float64) as longitud,
    fecha_extraccion
from {{ source('rosario_vivo', 'raw_colectivos_paradas') }}
where safe_cast(latitud as float64) is not null
  and safe_cast(longitud as float64) is not null