-- Tabla final de la agenda: es la que consulta el agente.
--
-- Una sola tabla ancha en vez de eventos + lugares. Con 225 filas, el join no
-- aporta nada y complica la consulta.

with eventos as (

    select * from {{ ref('stg_agenda') }}

)

select
    id_evento,
    titulo,
    url,
    descripcion,

    fecha_inicio,
    fecha_fin,
    duracion_dias,
    dias,
    hora_texto,

    lugar_nombre,
    lugar_direccion,
    lugar_latitud,
    lugar_longitud,
    origen_lugar,
    -- Con coordenadas se puede planificar el viaje en colectivo; con la
    -- dirección sola hay que geocodificarla primero.
    lugar_latitud is not null           as tiene_coordenadas,
    coalesce(lugar_nombre, lugar_direccion) is not null as tiene_ubicacion,

    entrada,
    es_gratis,
    categorias,
    etiqueta_serie,

    fecha_extraccion,
    date_diff(current_date('America/Argentina/Buenos_Aires'),
              date(fecha_extraccion, 'America/Argentina/Buenos_Aires'),
              day)                      as dias_desde_la_extraccion

from eventos
-- Las actividades marcadas como finalizadas siguen apareciendo en el buscador
-- del municipio, pero ofrecerlas sería mandar a alguien a algo que ya pasó.
where not finalizada
