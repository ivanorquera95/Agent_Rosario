with crudo as (
    select * from {{ source('rosario_vivo', 'raw_precios_productos') }}
),

normalizado as (
    select
        *,
        -- Lo que realmente pagas hoy por una unidad. El menor de los dos a
        -- proposito: hay filas donde la "promo" viene mas cara que el precio
        -- de lista, y sin el least() el agente recomendaria la mas cara.
        least(precio_lista, coalesce(precio_promo1, precio_lista)) as precio_hoy,

        -- Cada cadena escribe la unidad como se le canta: hay 49 variantes
        -- para tres magnitudes (lt/LT/ltr/L, GRM/GRS/gr./GR1, KG/kgm/kgr).
        -- Sin unificarlas, comparar "precio por unidad" entre comercios es
        -- comparar $/ml contra $/litro.
        upper(replace(trim(unidad_referencia), '.', '')) as unidad_limpia

    from crudo
)

select
    id_comercio,
    id_bandera,
    id_sucursal,
    id_producto,

    descripcion,
    marca,
    cantidad_presentacion,
    unidad_presentacion,

    precio_lista,
    precio_referencia,
    cantidad_referencia,
    unidad_referencia,

    precio_promo1,
    leyenda_promo1,
    precio_promo2,
    leyenda_promo2,

    precio_hoy as precio_efectivo,
    precio_promo1 is not null as tiene_promo,

    -- Tres magnitudes comparables. Lo que no entra en ninguna (m2, mtr, par,
    -- Pie) queda nulo: son productos que no se comparan por peso ni volumen.
    case
        when unidad_limpia in ('KG', 'KGM', 'KGR', 'GRM', 'GRS', 'GR', 'GR1') then 'kg'
        when unidad_limpia in ('LT', 'LTR', 'L', 'DM3', 'ML', 'ML1', 'CM3', 'CC') then 'l'
        when unidad_limpia in ('UNI', 'UN', 'UN1', 'UD', 'UNIDAD', 'PC', 'CU', 'PCK') then 'unidad'
    end as unidad_comparable,

    -- Precio por kilo, litro o unidad. Las unidades chicas (gramo, mililitro)
    -- se multiplican por mil. precio_referencia viene calculado sobre el
    -- precio de lista, asi que se le aplica el mismo descuento de la promo.
    case
        when unidad_limpia in ('GRM', 'GRS', 'GR', 'GR1', 'ML', 'ML1', 'CM3', 'CC')
            then round(precio_referencia * safe_divide(precio_hoy, precio_lista) * 1000, 2)
        when unidad_limpia in ('KG', 'KGM', 'KGR', 'LT', 'LTR', 'L', 'DM3',
                               'UNI', 'UN', 'UN1', 'UD', 'UNIDAD', 'PC', 'CU', 'PCK')
            then round(precio_referencia * safe_divide(precio_hoy, precio_lista), 2)
    end as precio_por_unidad,

    timestamp(fecha_extraccion) as fecha_extraccion

from normalizado
-- Sin precio no hay nada que comparar, y un precio 0 es un error de carga del
-- comercio, no una oferta. El precio_referencia negativo tambien existe: son
-- 26 mil pesos bajo cero en la tabla de KG.
where precio_lista is not null
  and precio_lista > 0
  and coalesce(precio_referencia, 0) >= 0