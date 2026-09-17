CREATE UNIQUE INDEX IF NOT EXISTS uq_documento_items_documento_material
    ON public.documento_items (documento_id, material_id);
