alter table public.materiales enable row level security;
alter table public.usuarios enable row level security;

create policy materiales_select_authenticated
on public.materiales
for select
to authenticated
using (
  exists (
    select 1 from public.usuarios u
    where u.id = (select auth.uid())
      and u.activo = true
  )
);

create policy materiales_insert_encargado_admin
on public.materiales
for insert
to authenticated
with check (
  (select private.usuario_es_administrador())
  or (select private.usuario_tiene_rol('encargado'))
);

create policy materiales_update_encargado_admin
on public.materiales
for update
to authenticated
using (
  (select private.usuario_es_administrador())
  or (select private.usuario_tiene_rol('encargado'))
)
with check (
  (select private.usuario_es_administrador())
  or (select private.usuario_tiene_rol('encargado'))
);

create policy materiales_delete_encargado_admin
on public.materiales
for delete
to authenticated
using (
  (select private.usuario_es_administrador())
  or (select private.usuario_tiene_rol('encargado'))
);

create policy usuarios_select_propio_admin
on public.usuarios
for select
to authenticated
using (
  id = (select auth.uid())
  or (select private.usuario_es_administrador())
);

create policy usuarios_insert_admin
on public.usuarios
for insert
to authenticated
with check (
  (select private.usuario_es_administrador())
);

create policy usuarios_update_admin
on public.usuarios
for update
to authenticated
using (
  (select private.usuario_es_administrador())
)
with check (
  (select private.usuario_es_administrador())
);

create policy usuarios_delete_admin
on public.usuarios
for delete
to authenticated
using (
  (select private.usuario_es_administrador())
);