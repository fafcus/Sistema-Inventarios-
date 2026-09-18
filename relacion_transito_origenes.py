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
    """Devuelve los orígenes reales desde material_ubicaciones."""
    try:
        material_id = int(material_id)
    except (TypeError, ValueError):
        return []

    filas = (
        supabase.table("material_ubicaciones")
        .select("id,material_id,documento_id,ubicacion,cantidad")
        .eq("material_id", material_id)
        .gt("cantidad", 0)
        .order("id")
        .execute()
        .data
        or []
    )
    if not filas:
        return []

    documento_ids = sorted({int(f["documento_id"]) for f in filas if f.get("documento_id") is not None})
    documentos = {}
    if documento_ids:
        docs = supabase.table("documentos").select("id,nombre").in_("id", documento_ids).execute().data or []
        documentos = {int(d["id"]): d for d in docs if d.get("id") is not None}

    resultado = []
    for fila in filas:
        documento_id = fila.get("documento_id")
        if documento_id is None:
            continue
        documento_id = int(documento_id)
        resultado.append({
            "material_ubicacion_id": fila.get("id"),
            "documento_id": documento_id,
            "archivo_origen": _nombre_documento(documentos.get(documento_id, {})),
            "ubicacion": _texto(fila.get("ubicacion")),
            "observaciones": "",
            "stock_disponible": _float(fila.get("cantidad")),
        })
    return resultado
