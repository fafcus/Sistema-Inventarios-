from config import supabase


def _float(valor, default=0.0):
    try:
        return float(valor or 0)
    except (TypeError, ValueError):
        return float(default)


def obtener_ubicaciones_material(material_id):
    """Obtiene el stock del material desglosado por ubicación."""
    data = (
        supabase.table("material_ubicaciones")
        .select("*")
        .eq("material_id", int(material_id))
        .order("ubicacion")
        .execute()
        .data
        or []
    )

    for fila in data:
        fila["cantidad"] = _float(fila.get("cantidad"))

    return data


def obtener_inventario_documento(documento_id):
    """Obtiene el inventario de un inventario lógico concreto desde Supabase."""
    data = (
        supabase.table("material_ubicaciones")
        .select("*")
        .eq("documento_id", int(documento_id))
        .order("id")
        .execute()
        .data
        or []
    )

    for fila in data:
        fila["cantidad"] = _float(fila.get("cantidad"))

    return data


def obtener_inventario_por_ubicacion():
    """Obtiene todo el inventario almacenado en la base, agrupado por ubicación."""
    data = (
        supabase.table("material_ubicaciones")
        .select("*")
        .order("ubicacion")
        .order("material_id")
        .execute()
        .data
        or []
    )

    for fila in data:
        fila["cantidad"] = _float(fila.get("cantidad"))

    return data


def obtener_stock_ubicacion(material_id, ubicacion):
    """Devuelve el stock de un material en una ubicación concreta."""
    ubicacion = str(ubicacion or "").strip() or "Sin ubicación"

    data = (
        supabase.table("material_ubicaciones")
        .select("cantidad")
        .eq("material_id", int(material_id))
        .eq("ubicacion", ubicacion)
        .limit(1)
        .execute()
        .data
        or []
    )

    return _float(data[0].get("cantidad")) if data else 0.0


def guardar_stock_ubicacion(material_id, ubicacion, cantidad):
    """
    Crea o actualiza el stock de un material en una ubicación.

    Esta función todavía no modifica movimientos ni documento_items.
    Se utiliza durante la transición hacia el inventario 100% basado
    en Supabase.
    """
    material_id = int(material_id)
    ubicacion = str(ubicacion or "").strip() or "Sin ubicación"
    cantidad = _float(cantidad)

    if cantidad < 0:
        raise ValueError("La cantidad no puede ser negativa.")

    datos = {
        "material_id": material_id,
        "ubicacion": ubicacion,
        "cantidad": cantidad,
    }

    existente = (
        supabase.table("material_ubicaciones")
        .select("id")
        .eq("material_id", material_id)
        .eq("ubicacion", ubicacion)
        .limit(1)
        .execute()
        .data
        or []
    )

    if existente:
        data = (
            supabase.table("material_ubicaciones")
            .update({"cantidad": cantidad})
            .eq("id", existente[0]["id"])
            .execute()
            .data
            or []
        )
    else:
        data = (
            supabase.table("material_ubicaciones")
            .insert(datos)
            .execute()
            .data
            or []
        )

    return data[0] if data else None


def mover_stock_entre_ubicaciones(material_id, origen, destino, cantidad):
    """
    Mueve stock entre dos ubicaciones dentro de Supabase.

    No modifica todavía movimientos ni documento_items; esa integración
    se hará en una etapa posterior para evitar alterar el flujo actual.
    """
    material_id = int(material_id)
    cantidad = _float(cantidad)
    origen = str(origen or "").strip() or "Sin ubicación"
    destino = str(destino or "").strip() or "Sin ubicación"

    if cantidad <= 0:
        raise ValueError("La cantidad a mover debe ser mayor que cero.")

    if origen == destino:
        raise ValueError("El origen y el destino deben ser diferentes.")

    stock_origen = obtener_stock_ubicacion(material_id, origen)

    if cantidad > stock_origen:
        raise ValueError(
            f"No hay stock suficiente en '{origen}'. "
            f"Stock disponible: {stock_origen:g}"
        )

    guardar_stock_ubicacion(material_id, origen, stock_origen - cantidad)

    try:
        stock_destino = obtener_stock_ubicacion(material_id, destino)
        guardar_stock_ubicacion(
            material_id,
            destino,
            stock_destino + cantidad,
        )
    except Exception:
        # Intentamos restaurar el origen si falla el destino.
        guardar_stock_ubicacion(material_id, origen, stock_origen)
        raise

    return {
        "material_id": material_id,
        "origen": origen,
        "destino": destino,
        "cantidad": cantidad,
        "stock_origen": stock_origen - cantidad,
        "stock_destino": stock_destino + cantidad,
    }
