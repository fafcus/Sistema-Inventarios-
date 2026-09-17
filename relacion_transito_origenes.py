from __future__ import annotations

from typing import Iterable, Mapping

from config import supabase


def _float(valor, default=0.0):
    try:
        return float(valor or 0)
    except (TypeError, ValueError):
        return float(default)


def _nombre_documento(documento: Mapping | None) -> str:
    if not documento:
        return ""
    nombre = str(documento.get("nombre") or "").strip()
    if nombre:
        return nombre
    ruta = str(documento.get("ruta") or "").strip().replace("\\", "/")
    return ruta.rsplit("/", 1)[-1] if ruta else ""


def obtener_origenes_material(material_id: int) -> list[dict]:
    """Devuelve cada origen físico/lógico de un material con stock efectivo.

    Un mismo material global puede tener varios documento_items. Cada fila
    conserva su documento_item_id, documento_id, ubicación y stock efectivo,
    evitando que una salida termine descontándose de un origen equivocado.
    """
    items = (
        supabase.table("documento_items")
        .select("*")
        .eq("material_id", int(material_id))
        .order("id")
        .execute()
        .data
        or []
    )
    if not items:
        return []

    documento_ids = sorted({i.get("documento_id") for i in items if i.get("documento_id") is not None})
    documentos = {}
    if documento_ids:
        data = (
            supabase.table("documentos")
            .select("id,nombre,ruta")
            .in_("id", documento_ids)
            .execute()
            .data
            or []
        )
        documentos = {d.get("id"): d for d in data}

    ajustes = (
        supabase.table("ajustes_stock")
        .select("documento_id,material_id,cantidad")
        .eq("material_id", int(material_id))
        .execute()
        .data
        or []
    )
    ajustes_por_item = {}
    for ajuste in ajustes:
        documento_id = ajuste.get("documento_id")
        if documento_id is None:
            continue
        ajustes_por_item[documento_id] = ajustes_por_item.get(documento_id, 0.0) + _float(ajuste.get("cantidad"))

    resultado = []
    for item in items:
        documento_id = item.get("documento_id")
        stock = _float(item.get("cantidad")) + ajustes_por_item.get(documento_id, 0.0)
        if stock < 0 and stock > -0.000001:
            stock = 0.0
        documento = documentos.get(documento_id) or {}
        fila = dict(item)
        fila["documento_item_id"] = item.get("id")
        fila["documento_id"] = documento_id
        fila["archivo_origen"] = _nombre_documento(documento)
        fila["stock_disponible"] = stock
        resultado.append(fila)
    return resultado


def descontar_origen_material(origen: Mapping, cantidad: float, usuario=None, observaciones=None):
    """Registra una salida contra un documento_item concreto."""
    material_id = origen.get("material_id")
    documento_id = origen.get("documento_id")
    if material_id is None or documento_id is None:
        raise Exception("El origen del material no tiene documento o material válido.")

    cantidad = _float(cantidad)
    if cantidad <= 0:
        raise Exception("La cantidad a retirar debe ser mayor que cero.")

    stock = next(
        (x.get("stock_disponible", 0.0) for x in obtener_origenes_material(material_id)
         if x.get("documento_item_id") == origen.get("documento_item_id")),
        None,
    )
    if stock is None:
        raise Exception("No se encontró el origen del material.")
    stock = _float(stock)
    if cantidad > stock + 0.000001:
        raise Exception(f"Stock insuficiente en el origen. Disponible: {stock:g}. A retirar: {cantidad:g}.")

    ajuste = (
        supabase.table("ajustes_stock")
        .insert({
            "material_id": int(material_id),
            "documento_id": int(documento_id),
            "cantidad": -cantidad,
            "usuario": usuario,
            "observaciones": observaciones,
        })
        .execute()
        .data
        or []
    )
    if not ajuste:
        raise Exception("No se pudo registrar el descuento del origen.")

    try:
        from supabase_db import registrar_movimiento
        registrar_movimiento(
            material_id,
            "SALIDA",
            cantidad,
            stock,
            stock - cantidad,
            usuario,
            observaciones,
            origen.get("archivo_origen"),
            documento_id=int(documento_id),
        )
    except Exception:
        # El ajuste ya quedó persistido; se intenta revertir para no dejar un
        # movimiento sin auditoría si el registro de movimiento falla.
        try:
            supabase.table("ajustes_stock").delete().eq("id", ajuste[0]["id"]).execute()
        except Exception:
            pass
        raise

    return stock - cantidad
