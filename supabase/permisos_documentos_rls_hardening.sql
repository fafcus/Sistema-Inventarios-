-- ============================================================
-- ENDURECIMIENTO RLS PARA PERMISOS POR DOCUMENTO
-- Ejecutar DESPUÉS de supabase/permisos_documentos.sql
--
-- Las políticas RESTRICTIVE se combinan con las políticas
-- permisivas existentes mediante AND. Esto evita que una política
-- permisiva antigua (por ejemplo USING true) anule la restricción.
-- ============================================================

-- No debe existir acceso anónimo a los datos de inventario.
revoke all on table public.documentos from anon;
revoke all on table public.documento_items from anon;
revoke all on table public.ajustes_stock from anon;
revoke all on table public.movimientos from anon;
revoke all on table public.documento_permisos from anon;

-- ------------------------------------------------------------
-- DOCUMENTO_PERMISOS
-- ------------------------------------------------------------
drop policy if exists documento_permisos_restrictive_select on public.documento_permisos;
drop policy if exists documento_permisos_restrictive_insert on public.documento_permisos;
drop policy if exists documento_permisos_restrictive_update on public.documento_permisos;
drop policy if exists documento_permisos_restrictive_delete on public.documento_permisos;

create policy documento_permisos_restrictive_select
on public.documento_permisos as restrictive
for select to authenticated
using (
    user_id = (select auth.uid())
    or (select private.usuario_es_administrador())
);

create policy documento_permisos_restrictive_insert
on public.documento_permisos as restrictive
for insert to authenticated
with check ((select private.usuario_es_administrador()));

create policy documento_permisos_restrictive_update
on public.documento_permisos as restrictive
for update to authenticated
using ((select private.usuario_es_administrador()))
with check ((select private.usuario_es_administrador()));

create policy documento_permisos_restrictive_delete
on public.documento_permisos as restrictive
for delete to authenticated
using ((select private.usuario_es_administrador()));

-- ------------------------------------------------------------
-- DOCUMENTOS
-- ------------------------------------------------------------
drop policy if exists documentos_restrictive_select on public.documentos;
drop policy if exists documentos_restrictive_insert on public.documentos;
drop policy if exists documentos_restrictive_update on public.documentos;
drop policy if exists documentos_restrictive_delete on public.documentos;

create policy documentos_restrictive_select
on public.documentos as restrictive
for select to authenticated
using (
    (select private.usuario_puede_documento(id, 'ver'))
);

create policy documentos_restrictive_insert
on public.documentos as restrictive
for insert to authenticated
with check (
    (select private.usuario_es_administrador())
    or (select private.usuario_tiene_rol('encargado'))
);

create policy documentos_restrictive_update
on public.documentos as restrictive
for update to authenticated
using (
    (select private.usuario_puede_documento(id, 'modificar'))
    or (select private.usuario_puede_documento(id, 'importar'))
)
with check (
    (select private.usuario_puede_documento(id, 'modificar'))
    or (select private.usuario_puede_documento(id, 'importar'))
);

create policy documentos_restrictive_delete
on public.documentos as restrictive
for delete to authenticated
using (
    (select private.usuario_puede_documento(id, 'eliminar'))
);

-- ------------------------------------------------------------
-- DOCUMENTO_ITEMS
-- ------------------------------------------------------------
drop policy if exists documento_items_restrictive_select on public.documento_items;
drop policy if exists documento_items_restrictive_insert on public.documento_items;
drop policy if exists documento_items_restrictive_update on public.documento_items;
drop policy if exists documento_items_restrictive_delete on public.documento_items;

create policy documento_items_restrictive_select
on public.documento_items as restrictive
for select to authenticated
using (
    (select private.usuario_puede_documento(documento_id, 'ver'))
);

create policy documento_items_restrictive_insert
on public.documento_items as restrictive
for insert to authenticated
with check (
    (select private.usuario_puede_documento(documento_id, 'importar'))
    or (select private.usuario_puede_documento(documento_id, 'modificar'))
);

create policy documento_items_restrictive_update
on public.documento_items as restrictive
for update to authenticated
using (
    (select private.usuario_puede_documento(documento_id, 'modificar'))
    or (select private.usuario_puede_documento(documento_id, 'agregar'))
    or (select private.usuario_puede_documento(documento_id, 'retirar'))
)
with check (
    (select private.usuario_puede_documento(documento_id, 'modificar'))
    or (select private.usuario_puede_documento(documento_id, 'agregar'))
    or (select private.usuario_puede_documento(documento_id, 'retirar'))
);

create policy documento_items_restrictive_delete
on public.documento_items as restrictive
for delete to authenticated
using (
    (select private.usuario_puede_documento(documento_id, 'eliminar'))
);

-- ------------------------------------------------------------
-- AJUSTES_STOCK
-- ------------------------------------------------------------
drop policy if exists ajustes_restrictive_select on public.ajustes_stock;
drop policy if exists ajustes_restrictive_insert on public.ajustes_stock;
drop policy if exists ajustes_restrictive_update on public.ajustes_stock;
drop policy if exists ajustes_restrictive_delete on public.ajustes_stock;

create policy ajustes_restrictive_select
on public.ajustes_stock as restrictive
for select to authenticated
using (
    documento_id is null
    or (select private.usuario_puede_documento(documento_id, 'ver'))
);

create policy ajustes_restrictive_insert
on public.ajustes_stock as restrictive
for insert to authenticated
with check (
    documento_id is null
    or (select private.usuario_puede_documento(documento_id, 'agregar'))
    or (select private.usuario_puede_documento(documento_id, 'retirar'))
    or (select private.usuario_puede_documento(documento_id, 'modificar'))
);

create policy ajustes_restrictive_update
on public.ajustes_stock as restrictive
for update to authenticated
using (
    documento_id is null
    or (select private.usuario_puede_documento(documento_id, 'modificar'))
)
with check (
    documento_id is null
    or (select private.usuario_puede_documento(documento_id, 'modificar'))
);

create policy ajustes_restrictive_delete
on public.ajustes_stock as restrictive
for delete to authenticated
using (
    documento_id is null
    or (select private.usuario_puede_documento(documento_id, 'modificar'))
    or (select private.usuario_puede_documento(documento_id, 'agregar'))
    or (select private.usuario_puede_documento(documento_id, 'retirar'))
);

-- ------------------------------------------------------------
-- MOVIMIENTOS
-- ------------------------------------------------------------
drop policy if exists movimientos_restrictive_select on public.movimientos;
drop policy if exists movimientos_restrictive_insert on public.movimientos;

create policy movimientos_restrictive_select
on public.movimientos as restrictive
for select to authenticated
using (
    documento_id is null
    or (select private.usuario_puede_documento(documento_id, 'ver'))
);

create policy movimientos_restrictive_insert
on public.movimientos as restrictive
for insert to authenticated
with check (
    documento_id is null
    or (select private.usuario_puede_documento(documento_id, 'agregar'))
    or (select private.usuario_puede_documento(documento_id, 'retirar'))
    or (select private.usuario_puede_documento(documento_id, 'modificar'))
);

-- ============================================================
-- FIN
-- ============================================================
