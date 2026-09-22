-- Se ejecuta cada vez que arranca la API: "if not exists" lo hace inofensivo.
create table if not exists sesiones (
    id uuid primary key,
    creada timestamptz not null default now(),
    ultima_actividad timestamptz not null default now(),
    ocupada_desde timestamptz,                          -- null = libre
    direcciones_conocidas jsonb not null default '[]'
);

create table if not exists mensajes (
    id bigserial primary key,
    sesion_id uuid not null references sesiones(id) on delete cascade,
    rol text not null check (rol in ('user', 'assistant')),
    contenido text not null,
    creado timestamptz not null default now()
);

create index if not exists mensajes_por_sesion on mensajes (sesion_id, id);
create index if not exists sesiones_por_actividad on sesiones (ultima_actividad);