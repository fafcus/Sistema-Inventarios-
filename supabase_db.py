from config import supabase
from pathlib import Path
import re


def probar_conexion():
    """Prueba la conexión con Supabase."""
    try:
        supabase.table("materiales").select("id").limit(1).execute()
        return True
    except Exception as e:
        print(f"Error de conexión con Supabase: {e}")
        return False


def _float(valor, default=0.0):
    try:
        return float(valor or 0)
    except (TypeError, ValueError):
        return float(default)


def _normalizar_tipo(tipo):
    tipo = str(tipo or "").strip().upper()
    return {"AGREGAR": "ENTRADA", "RETIRAR": "SALIDA"}.get(tipo, tipo)


def _nombre_documento_portable(documento):
    """
    Obtiene un nombre visible para el inventario sin depender de la PC
    donde fue importado originalmente.

    Si `nombre` está vacío, se intenta obtener el nombre desde otros campos
    y finalmente desde `ruta`. Se soportan rutas Windows y Unix.
    """
    if not isinstance(documento, dict):
        return ""

    nombre = str(documento.get("nombre") or "").strip()
    if nombre:
        return nombre

    for campo in ("nombre_archivo", "archivo_origen", "archivo"):
        valor = str(documento.get(campo) or "").strip()
        if valor:
            valor = valor.replace("\\", "/")
            nombre = valor.rsplit("/", 1)[-1].strip()
            if nombre:
                return nombre

    ruta = str(documento.get("ruta") or "").strip()
    if ruta:
        ruta = ruta.replace("\\", "/")
        nombre = ruta.rsplit("/", 1)[-1].strip()
        if nombre:
            return nombre

    documento_id = documento.get("id")
    if documento_id is not None:
        return f"Inventario #{documento_id}"

    return "Inventario sin nombre"


def _normalizar_documento(documento):
    """Normaliza el nombre solamente en memoria, sin modificar Supabase."""
    copia = dict(documento or {})
    copia["nombre"] = _nombre_documento_portable(copia)
    return copia


# ============================================================
# MATERIALES
# ============================================================

def obtener_materiales():
    return supabase.table("materiales").select("*").order("id").execute().data or []


def obtener_material(material_id):
    data = supabase.table("materiales").select("*").eq("id", material_id).limit(1).execute().data or []
    return data[0] if data else None


def crear_material(codigo, material, cantidad=0, unidad=None, categoria=None, ubicacion=None, observaciones=None, archivo_origen=None):
    datos = {"codigo": codigo, "material": material, "cantidad": 0, "unidad": unidad, "categoria": categoria, "ubicacion": ubicacion, "observaciones": observaciones, "archivo_origen": archivo_origen}
    data = supabase.table("materiales").insert(datos).execute().data or []
    return data[0] if data else None


def actualizar_material(material_id, codigo=None, material=None, unidad=None, categoria=None, ubicacion=None, observaciones=None):
    datos = {}
    if codigo is not None: datos["codigo"] = codigo
    if material is not None: datos["material"] = material
    if unidad is not None: datos["unidad"] = unidad
    if categoria is not None: datos["categoria"] = categoria
    if ubicacion is not None: datos["ubicacion"] = ubicacion
    if observaciones is not None: datos["observaciones"] = observaciones
    if not datos: return None
    data = supabase.table("materiales").update(datos).eq("id", material_id).execute().data or []
    return data[0] if data else None


def actualizar_origen(material_id, nombre_archivo):
    data = supabase.table("materiales").update({"archivo_origen": nombre_archivo}).eq("id", material_id).execute().data or []
    return data[0] if data else None


def eliminar_material_del_documento(documento_id, material_id):
    """
    Elimina un material del inventario/documento seleccionado.

    - Elimina el documento_item del documento indicado.
    - Elimina los ajustes específicos de ese documento/material.
    - Si el material ya no pertenece a ningún documento, elimina también
      su registro global en materiales.
    - NO elimina movimientos históricos.
    """
    try:
        documento_id = int(documento_id)
        material_id = int(material_id)
    except (TypeError, ValueError):
        raise Exception("Documento o material inválido.")

    item = obtener_item_documento_por_material(documento_id, material_id)
    if not item:
        raise Exception("El material no pertenece al inventario seleccionado.")

    supabase.table("ajustes_stock").delete().eq(
        "documento_id", documento_id
    ).eq(
        "material_id", material_id
    ).execute()

    supabase.table("documento_items").delete().eq(
        "id", item["id"]
    ).execute()

    otros = supabase.table("documento_items").select("id").eq(
        "material_id", material_id
    ).limit(1).execute().data or []

    material_eliminado = False

    if not otros:
        supabase.table("materiales").delete().eq(
            "id", material_id
        ).execute()
        material_eliminado = True

    return {
        "documento_item_eliminado": True,
        "material_eliminado": material_eliminado,
        "material_id": material_id,
        "documento_id": documento_id,
    }


# ============================================================
# DOCUMENTOS
# ============================================================

def obtener_documentos():
    """
    Obtiene los documentos desde Supabase y garantiza que la UI tenga
    siempre un nombre visible, aunque el registro haya sido creado desde
    otra PC con una ruta local diferente.
    """
    data = (
        supabase.table("documentos")
        .select("*")
        .execute()
        .data
        or []
    )

    documentos = [
        _normalizar_documento(documento)
        for documento in data
    ]

    documentos.sort(
        key=lambda documento: str(
            documento.get("nombre") or ""
        ).casefold()
    )

    return documentos


def obtener_documento(ruta):
    data = supabase.table("documentos").select("*").eq("ruta", str(ruta)).limit(1).execute().data or []
    return _normalizar_documento(data[0]) if data else None


def obtener_documento_por_nombre_ruta(nombre, ruta):
    data = supabase.table("documentos").select("*").eq("nombre", nombre).eq("ruta", str(ruta)).limit(1).execute().data or []
    return _normalizar_documento(data[0]) if data else None


def crear_documento(nombre, ruta, fecha_modificacion_archivo=None):
    datos = {"nombre": nombre, "ruta": str(ruta)}
    if fecha_modificacion_archivo is not None: datos["fecha_modificacion_archivo"] = str(fecha_modificacion_archivo)
    data = supabase.table("documentos").insert(datos).execute().data or []
    return _normalizar_documento(data[0]) if data else None


def actualizar_documento(documento_id, fecha_modificacion_archivo):
    data = supabase.table("documentos").update({"fecha_modificacion_archivo": str(fecha_modificacion_archivo)}).eq("id", documento_id).execute().data or []
    return _normalizar_documento(data[0]) if data else None


# ============================================================
# ITEMS DE DOCUMENTOS
# ============================================================

def _obtener_items_base(documento_id):
    return supabase.table("documento_items").select("*").eq("documento_id", documento_id).order("id").execute().data or []


def obtener_items_documento(documento_id):
    """Devuelve el inventario del documento desde material_ubicaciones."""
    documento_id = int(documento_id)
    filas = (
        supabase.table("material_ubicaciones")
        .select("*")
        .eq("documento_id", documento_id)
        .order("id")
        .execute().data or []
    )
    materiales = obtener_materiales()
    por_id = {m.get("id"): m for m in materiales}
    resultado = []
    for fila in filas:
        material = dict(por_id.get(fila.get("material_id")) or {})
        material.update({
            "id": fila.get("material_id"),
            "material_id": fila.get("material_id"),
            "documento_id": documento_id,
            "material_ubicacion_id": fila.get("id"),
            "cantidad_base": _float(fila.get("cantidad")),
            "cantidad_ajustes": 0.0,
            "cantidad": _float(fila.get("cantidad")),
            "ubicacion": fila.get("ubicacion") or material.get("ubicacion"),
        })
        resultado.append(material)
    return resultado

def obtener_todos_items_documento():
    """Compatibilidad: devuelve filas de material_ubicaciones."""
    return (
        supabase.table("material_ubicaciones")
        .select("*")
        .order("id")
        .execute().data or []
    )

def obtener_item_documento_por_material(documento_id, material_id):
    data = (
        supabase.table("material_ubicaciones")
        .select("*")
        .eq("documento_id", int(documento_id))
        .eq("material_id", int(material_id))
        .order("id")
        .limit(1)
        .execute().data or []
    )
    return data[0] if data else None

def eliminar_items_documento(documento_id):
    supabase.table("material_ubicaciones").delete().eq("documento_id", int(documento_id)).execute()

def crear_item_documento(documento_id, material_id, cantidad, unidad=None, codigo=None, material=None, categoria=None, ubicacion=None, observaciones=None):
    """Compatibilidad: crea/actualiza una ubicación en el inventario DB."""
    documento_id = int(documento_id)
    material_id = int(material_id)
    ubicacion = str(ubicacion or "Sin ubicación").strip() or "Sin ubicación"
    existente = (
        supabase.table("material_ubicaciones")
        .select("*")
        .eq("documento_id", documento_id)
        .eq("material_id", material_id)
        .eq("ubicacion", ubicacion)
        .limit(1).execute().data or []
    )
    datos = {"documento_id": documento_id, "material_id": material_id, "ubicacion": ubicacion, "cantidad": _float(cantidad)}
    if existente:
        data = supabase.table("material_ubicaciones").update(datos).eq("id", existente[0]["id"]).execute().data or []
    else:
        data = supabase.table("material_ubicaciones").insert(datos).execute().data or []
    return data[0] if data else None

def obtener_ajuste_documento_material(documento_id, material_id):
    data = supabase.table("ajustes_stock").select("cantidad").eq("documento_id", documento_id).eq("material_id", material_id).execute().data or []
    return sum(_float(x.get("cantidad")) for x in data)


def obtener_stock_documento_material(documento_id, material_id):
    data = (
        supabase.table("material_ubicaciones")
        .select("cantidad")
        .eq("documento_id", int(documento_id))
        .eq("material_id", int(material_id))
        .execute().data or []
    )
    return sum(_float(x.get("cantidad")) for x in data)

def actualizar_cantidad_documento_item(item_id, nueva_cantidad, usuario=None, observaciones=None, archivo_origen=None, documento_id=None):
    """Compatibilidad histórica: actualiza una fila de material_ubicaciones sin tocar Word."""
    from inventario_db import actualizar_stock_ubicacion_exacta
    return actualizar_stock_ubicacion_exacta(
        fila_id=item_id,
        nueva_cantidad=nueva_cantidad,
        usuario=usuario,
        observaciones=observaciones,
        archivo_origen=archivo_origen,
        documento_id=documento_id,
    )

def actualizar_cantidad_documento_item(item_id, nueva_cantidad, usuario=None, observaciones=None, archivo_origen=None, documento_id=None):
    nueva_cantidad = _float(nueva_cantidad)
    if nueva_cantidad < 0: raise Exception("La cantidad no puede ser negativa.")
    data = supabase.table("documento_items").select("*").eq("id", item_id).limit(1).execute().data or []
    if not data: raise Exception("No se encontró el material dentro del documento.")
    item = data[0]
    material_id = item.get("material_id")
    documento_item_id = item.get("documento_id")
    documento_id = documento_id if documento_id is not None else documento_item_id
    if documento_id is None: raise Exception("No se pudo determinar el documento del material.")
    if documento_item_id is not None and int(documento_id) != int(documento_item_id): raise Exception("El material no pertenece al documento seleccionado.")
    stock_actual = obtener_stock_documento_material(documento_id, material_id)
    diferencia = nueva_cantidad - stock_actual
    if abs(diferencia) < 0.000001: return stock_actual
    documento = supabase.table("documentos").select("*").eq("id", documento_id).limit(1).execute().data or []
    documento = _normalizar_documento(documento[0]) if documento else None
    if not documento: raise Exception("No se encontró el documento seleccionado.")
    if not _actualizar_word_cantidad(documento, item, nueva_cantidad):
        raise Exception("No se pudo actualizar la cantidad en el archivo Word.")
    data = supabase.table("documento_items").update({"cantidad": nueva_cantidad}).eq("id", item_id).execute().data or []
    if not data: raise Exception("No se pudo actualizar documento_items.")
    supabase.table("ajustes_stock").delete().eq("documento_id", documento_id).eq("material_id", material_id).execute()
    tipo = "ENTRADA" if diferencia > 0 else "SALIDA"
    registrar_movimiento(material_id, tipo, abs(diferencia), stock_actual, nueva_cantidad, usuario, observaciones, archivo_origen, documento_id=documento_id)
    return nueva_cantidad


# ============================================================
# AJUSTES GENERALES
# ============================================================

def obtener_ajustes_stock():
    return supabase.table("ajustes_stock").select("*").order("fecha", desc=True).execute().data or []


def obtener_ajustes_material(material_id):
    return supabase.table("ajustes_stock").select("*").eq("material_id", material_id).order("fecha", desc=True).execute().data or []


def obtener_ajuste_total(material_id):
    data = supabase.table("ajustes_stock").select("cantidad").eq("material_id", material_id).is_("documento_id", "null").execute().data or []
    return sum(_float(x.get("cantidad")) for x in data)


def registrar_movimiento(material_id, tipo, cantidad, stock_anterior, stock_nuevo, usuario=None, observaciones=None, archivo_origen=None, documento_id=None):
    datos = {
        "material_id": int(material_id),
        "tipo": _normalizar_tipo(tipo),
        "cantidad": _float(cantidad),
        "stock_anterior": _float(stock_anterior),
        "stock_nuevo": _float(stock_nuevo),
        "usuario": usuario,
        "observaciones": observaciones,
        "archivo_origen": archivo_origen,
        "documento_id": documento_id,
    }
    data = supabase.table("movimientos").insert(datos).execute().data or []
    return data[0] if data else None


def agregar_ajuste_stock(material_id, delta, usuario=None, observaciones=None):
    delta = _float(delta)
    stock_anterior = obtener_stock_general_material(material_id)
    stock_nuevo = stock_anterior + delta
    if stock_nuevo < -0.000001: raise Exception(f"No hay stock suficiente. Stock actual: {stock_anterior:g}")
    if abs(delta) < 0.000001: return stock_anterior
    data = supabase.table("ajustes_stock").insert({"material_id": int(material_id), "documento_id": None, "cantidad": delta, "usuario": usuario, "observaciones": observaciones}).execute().data or []
    if not data: raise Exception("No se pudo guardar el ajuste.")
    registrar_movimiento(material_id, "ENTRADA" if delta > 0 else "SALIDA", abs(delta), stock_anterior, stock_nuevo, usuario, observaciones, None, documento_id=None)
    return stock_nuevo


# ============================================================
# INVENTARIO GENERAL - TODO EN BLOQUE
# ============================================================

def calcular_inventario_general(materiales=None, items=None, ajustes=None):
    """Calcula el inventario exclusivamente desde material_ubicaciones."""
    materiales = obtener_materiales() if materiales is None else materiales
    filas = (
        supabase.table("material_ubicaciones")
        .select("material_id,cantidad")
        .execute().data or []
    ) if items is None else items
    suma = {}
    for fila in filas:
        mid = fila.get("material_id")
        if mid is not None:
            suma[mid] = suma.get(mid, 0.0) + _float(fila.get("cantidad"))
    resultado = []
    for material in materiales:
        fila = dict(material)
        cantidad = suma.get(material.get("id"), 0.0)
        fila["cantidad_documentos"] = cantidad
        fila["cantidad_ajustes"] = 0.0
        fila["cantidad"] = cantidad
        resultado.append(fila)
    return resultado

def obtener_inventario_general():
    return calcular_inventario_general()

def obtener_stock_documentos_material(material_id):
    data = (
        supabase.table("material_ubicaciones")
        .select("cantidad")
        .eq("material_id", int(material_id))
        .execute().data or []
    )
    return sum(_float(x.get("cantidad")) for x in data)

def obtener_stock_general_material(material_id):
    material_id = int(material_id)
    if obtener_material(material_id) is None:
        raise Exception("No se encontró el material.")
    return obtener_stock_documentos_material(material_id)

def obtener_movimientos(limite=100):
    return supabase.table("movimientos").select("*").order("fecha", desc=True).limit(limite).execute().data or []


def obtener_movimientos_material(material_id):
    return supabase.table("movimientos").select("*").eq("material_id", material_id).order("fecha", desc=True).execute().data or []


def modificar_stock(material_id, cantidad, tipo, usuario=None, observaciones=None, archivo_origen=None):
    """Modifica stock en la primera ubicación disponible del material."""
    cantidad = _float(cantidad)
    if cantidad < 0:
        raise Exception("La cantidad no puede ser negativa.")
    tipo = _normalizar_tipo(tipo)
    if tipo not in ("ENTRADA", "SALIDA"):
        raise Exception("Tipo de movimiento inválido.")
    from inventario_db import obtener_ubicaciones_material, actualizar_stock_ubicacion_exacta
    ubicaciones = obtener_ubicaciones_material(material_id)
    if not ubicaciones:
        raise Exception("El material no tiene una ubicación de inventario.")
    fila = ubicaciones[0]
    nueva = _float(fila.get("cantidad")) + (cantidad if tipo == "ENTRADA" else -cantidad)
    if nueva < 0:
        raise Exception("Stock insuficiente.")
    return actualizar_stock_ubicacion_exacta(fila["id"], nueva, usuario, observaciones, archivo_origen, fila.get("documento_id"))

def ajustar_stock(material_id, nuevo_stock, usuario=None, observaciones=None, archivo_origen=None):
    nuevo_stock = _float(nuevo_stock)
    if nuevo_stock < 0:
        raise Exception("El stock no puede ser negativo.")
    actual = obtener_stock_general_material(material_id)
    diferencia = nuevo_stock - actual
    if abs(diferencia) < 0.000001:
        return actual
    return modificar_stock(material_id, abs(diferencia), "ENTRADA" if diferencia > 0 else "SALIDA", usuario, observaciones, archivo_origen)

def buscar_material_por_codigo(codigo, material=None):
    codigo = (codigo or "").strip()
    if not codigo: return None
    materiales = supabase.table("materiales").select("*").eq("codigo", codigo).execute().data or []
    if not materiales: return None
    if material:
        objetivo = material.strip().lower()
        for item in materiales:
            if (item.get("material") or "").strip().lower() == objetivo: return item
    return materiales[0]


def buscar_material_sin_codigo(material, categoria, ubicacion):
    materiales = supabase.table("materiales").select("*").is_("codigo", "null").execute().data or []
    normalizar = lambda x: str(x or "").strip().lower()
    objetivo = (normalizar(material), normalizar(categoria), normalizar(ubicacion))
    for item in materiales:
        actual = (normalizar(item.get("material")), normalizar(item.get("categoria")), normalizar(item.get("ubicacion")))
        if actual == objetivo: return item
    return None


def buscar_material(codigo, material, categoria=None, ubicacion=None):
    return buscar_material_por_codigo(codigo, material) if codigo else buscar_material_sin_codigo(material, categoria, ubicacion)
