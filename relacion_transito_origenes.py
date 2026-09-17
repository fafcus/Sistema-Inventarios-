from __future__ import annotations

from typing import Mapping

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
    """Devuelve los orígenes de un material con stock efectivo.

    ``ajustes_stock`` identifica el origen por documento + material, no por
    ``documento_item``. Por eso, si un documento contiene accidentalmente dos
    filas del mismo material, se consolidan en una sola fila lógica antes de
    aplicar los ajustes. Así un mismo ajuste no se duplica en dos filas.
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

    documento_ids = sorted({
        item.get("documento_id")
        for item in items
        if item.get("documento_id") is not None
    })
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
        documentos = {item.get("id"): item for item in data}

    ajustes = (
        supabase.table("ajustes_stock")
        .select("documento_id,material_id,cantidad")
        .eq("material_id", int(material_id))
        .execute()
        .data
        or []
    )
    ajustes_por_documento = {}
    for ajuste in ajustes:
        documento_id = ajuste.get("documento_id")
        if documento_id is None:
            continue
        ajustes_por_documento[documento_id] = (
            ajustes_por_documento.get(documento_id, 0.0)
            + _float(ajuste.get("cantidad"))
        )

    # Agrupar por documento porque ese es el nivel de trazabilidad que
    # permite actualmente ajustes_stock.
    grupos = {}
    for item in items:
        documento_id = item.get("documento_id")
        clave = documento_id if documento_id is not None else f"sin_documento:{item.get('id')}"
        grupo = grupos.setdefault(clave, {
            "items": [],
            "documento_id": documento_id,
            "cantidad_base": 0.0,
            "ubicaciones": [],
            "observaciones": [],
        })
        grupo["items"].append(item)
        grupo["cantidad_base"] += _float(item.get("cantidad"))

        ubicacion = str(item.get("ubicacion") or "").strip()
        if ubicacion and ubicacion != "-" and ubicacion not in grupo["ubicaciones"]:
            grupo["ubicaciones"].append(ubicacion)

        observacion = str(item.get("observaciones") or "").strip()
        if observacion and observacion != "-" and observacion not in grupo["observaciones"]:
            grupo["observaciones"].append(observacion)

    resultado = []
    for grupo in grupos.values():
        documento_id = grupo["documento_id"]
        ajuste = ajustes_por_documento.get(documento_id, 0.0) if documento_id is not None else 0.0
        stock = grupo["cantidad_base"] + ajuste
        if stock < 0 and stock > -0.000001:
            stock = 0.0

        primer_item = grupo["items"][0]
        documento = documentos.get(documento_id) or {}
        fila = dict(primer_item)
        fila["documento_item_id"] = primer_item.get("id")
        fila["documento_id"] = documento_id
        fila["archivo_origen"] = _nombre_documento(documento)
        fila["ubicacion"] = " / ".join(grupo["ubicaciones"])
        fila["observaciones"] = " / ".join(grupo["observaciones"])
        fila["stock_base_consolidado"] = grupo["cantidad_base"]
        fila["ajuste_acumulado"] = ajuste
        fila["stock_disponible"] = stock
        fila["documento_item_ids"] = [
            item.get("id") for item in grupo["items"] if item.get("id") is not None
        ]
        fila["origen_consolidado"] = len(grupo["items"]) > 1
        resultado.append(fila)

    resultado.sort(key=lambda fila: (fila.get("documento_id") is None, fila.get("documento_id") or 0, fila.get("documento_item_id") or 0))
    return resultado


def descontar_origen_material(origen: Mapping, cantidad: float, usuario=None, observaciones=None):
    """Registra una salida contra un origen documento/material concreto."""
    material_id = origen.get("material_id")
    documento_id = origen.get("documento_id")
    if material_id is None or documento_id is None:
        raise Exception("El origen del material no tiene documento o material válido.")

    cantidad = _float(cantidad)
    if cantidad <= 0:
        raise Exception("La cantidad a retirar debe ser mayor que cero.")

    origenes = obtener_origenes_material(material_id)
    origen_encontrado = next(
        (
            item for item in origenes
            if item.get("documento_id") == documento_id
            and (
                origen.get("documento_item_id") is None
                or item.get("documento_item_id") == origen.get("documento_item_id")
            )
        ),
        None,
    )
    if origen_encontrado is None:
        raise Exception("No se encontró el origen del material.")

    stock = _float(origen_encontrado.get("stock_disponible"))
    if cantidad > stock + 0.000001:
        raise Exception(
            f"Stock insuficiente en el origen. Disponible: {stock:g}. A retirar: {cantidad:g}."
        )

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
        try:
            supabase.table("ajustes_stock").delete().eq("id", ajuste[0]["id"]).execute()
        except Exception:
            pass
        raise

    return stock - cantidad
