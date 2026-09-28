-- El orden de los puntos es lo que hace funcionar la verificacion de sentido:
-- si la bajada queda antes que la subida sobre el trazado, ese colectivo va
-- para el otro lado. Por eso 'tramo' y 'orden' se castean a entero y no se
-- ordena por texto, donde "10" viene antes que "2".
select
    id_linea,
    sentido,
    safe_cast(tramo as int64) as tramo,
    safe_cast(orden as int64) as orden,
    safe_cast(latitud as float64) as latitud,
    safe_cast(longitud as float64) as longitud,
    fecha_extraccion
from {{ source('rosario_vivo', 'raw_colectivos_trazados') }}
where safe_cast(latitud as float64) is not null
  and safe_cast(longitud as float64) is not null
  and safe_cast(orden as int64) is not null