from __future__ import annotations

"""Funciones auxiliares para obtener el origen real de cada material.

Cada origen corresponde a un documento_items concreto. Esto permite que la
Relación de Tránsito conserve trazabilidad del archivo/documento y ubicación
desde donde sale el material.
"""

from config import supabase


def _float(valor, default=0.0):
    try:
        return float(valor or 0)
    except (TypeError, ValueError):
        return float(default)


def _texto(valor) -> str:
    return "" if valor is None else str(valor).strip()


def _nombre_documento(documento) -> str:
    if not isinstance(documento, dict):
        return ""

    nombre = _texto(documento.get("nombre"))
    if nombre:
        return nombre

    for campo in ("nombre_archivo", "archivo_origen", "archivo", "ruta"):
        valor = _texto(documento.get(campo))
        if valor:
            return valor.replace("\\", "/").rsplit("/", 1)[-1]

    if documento.get("id") is not None:
        return f"Inventario #{documento['id']}"
    return "Inventario sin nombre"


def obtener_origenes_material(material_id):
    """Devuelve los orígenes/documentos con stock disponible de un material.

    Cada elemento identifica un documento_items mediante documento_item_id y
    documento_id. El stock se calcula como cantidad base del item más los
    ajustes asociados a ese documento y material.
    """
    try:
        material_id = int(material_id)
    except (TypeError, ValueError):
        return []

    items = (
        supabase.table("documento_items")
        .select("*")
        .eq("material_id", material_id)
        .order("id")
        .execute()
        .data
        or []
    )

    if not items:
        return []

    documento_ids = sorted({
        int(item["documento_id"])
        for item in items
        if item.get("documento_id") is not None
    })

    documentos = {}
    if documento_ids:
        docs = (
            supabase.table("documentos")
            .select("*")
            .in_("id", documento_ids)
            .execute()
            .data
            or []
        )
        documentos = {int(doc["id"]): doc for doc in docs if doc.get("id") is not None}

    ajustes_por_documento = {}
    if documento_ids:
        ajustes = (
            supabase.table("ajustes_stock")
            .select("documento_id,material_id,cantidad")
            .eq("material_id", material_id)
            .in_("documento_id", documento_ids)
            .execute()
            .data
            or []
        )
        for ajuste in ajustes:
            documento_id = ajuste.get("documento_id")
            if documento_id is None:
                continue
            documento_id = int(documento_id)
            ajustes_por_documento[documento_id] = (
                ajustes_por_documento.get(documento_id, 0.0)
                + _float(ajuste.get("cantidad"))
            )

    resultado = []
    for item in items:
        documento_id = item.get("documento_id")
        if documento_id is None:
            continue
        documento_id = int(documento_id)

        stock = _float(item.get("cantidad")) + ajustes_por_documento.get(documento_id, 0.0)
        if stock <= 0.000001:
            continue

        documento = documentos.get(documento_id, {})
        origen = {
            "documento_item_id": item.get("id"),
            "documento_id": documento_id,
            "archivo_origen": _nombre_documento(documento),
            "ubicacion": _texto(item.get("ubicacion")),
            "observaciones": _texto(item.get("observaciones")),
            "stock_disponible": stock,
        }
        resultado.append(origen)

    return resultado
