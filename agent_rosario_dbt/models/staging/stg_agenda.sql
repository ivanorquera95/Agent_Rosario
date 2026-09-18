-- Capa de staging: limpia la fuente, uno a uno con raw_agenda.
-- Los tipos ya vienen bien desde la carga (fechas DATE, booleanos BOOLEAN,
-- categorias ARRAY), asi que no hace falta castear nada.
-- Acá no se decide nada de negocio, solo se normaliza lo que vino del scraper.

with origen as (

    select * from {{ source('rosario_vivo', 'raw_agenda') }}

)

select
    slug                                as id_evento,
    titulo,
    url,
    descripcion,

    fecha_inicio,
    -- El scraper deja fecha_fin nula cuando el evento es de un solo día. Se
    -- rellena acá para que toda consulta posterior compare rangos y no tenga
    -- que contemplar el caso nulo.
    coalesce(fecha_fin, fecha_inicio)   as fecha_fin,
    date_diff(coalesce(fecha_fin, fecha_inicio), fecha_inicio, day) + 1 as duracion_dias,

    dias,
    hora_texto,

    lugar_id,
    lugar_nombre,
    lugar_direccion,
    lugar_latitud,
    lugar_longitud,

    -- De dónde salió el lugar. El agente lo usa para saber si puede afirmarlo
    -- como dato oficial o tiene que decir que lo dedujo de la descripción.
    case
        when lugar_deducido then 'deducido'
        when lugar_heredado then 'heredado'
        when lugar_eventual then 'eventual'
        when lugar_nombre is not null then 'municipio'
        else 'sin_dato'
    end                                 as origen_lugar,

    entrada,
    es_gratis,
    categorias,
    etiqueta_serie,
    url_padre,
    finalizada,
    imagen_descripcion,

    fecha_extraccion

from origen
where detalle_ok
