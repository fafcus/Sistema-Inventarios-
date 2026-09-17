from config import supabase
from pathlib import Path
import re


def _float(valor, default=0.0):
    try:
        return float(valor or 0)
    except (TypeError, ValueError):
        return float(default)


def _normalizar_tipo(tipo):
    tipo = str(tipo or "").strip().upper()
    return {"AGREGAR": "ENTRADA", "RETIRAR": "SALIDA"}.get(tipo, tipo)


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


# ============================================================
# DOCUMENTOS
# ============================================================

def obtener_documentos():
    return supabase.table("documentos").select("*").order("nombre").execute().data or []


def obtener_documento(ruta):
    data = supabase.table("documentos").select("*").eq("ruta", str(ruta)).limit(1).execute().data or []
    return data[0] if data else None


def obtener_documento_por_nombre_ruta(nombre, ruta):
    data = supabase.table("documentos").select("*").eq("nombre", nombre).eq("ruta", str(ruta)).limit(1).execute().data or []
    return data[0] if data else None


def crear_documento(nombre, ruta, fecha_modificacion_archivo=None):
    datos = {"nombre": nombre, "ruta": str(ruta)}
    if fecha_modificacion_archivo is not None: datos["fecha_modificacion_archivo"] = str(fecha_modificacion_archivo)
    data = supabase.table("documentos").insert(datos).execute().data or []
    return data[0] if data else None


def actualizar_documento(documento_id, fecha_modificacion_archivo):
    data = supabase.table("documentos").update({"fecha_modificacion_archivo": str(fecha_modificacion_archivo)}).eq("id", documento_id).execute().data or []
    return data[0] if data else None


# ============================================================
# ITEMS DE DOCUMENTOS
# ============================================================

def _obtener_items_base(documento_id):
    return supabase.table("documento_items").select("*").eq("documento_id", documento_id).order("id").execute().data or []


def obtener_items_documento(documento_id):
    """Devuelve los items del documento con el stock efectivo (base + ajustes)."""
    items = _obtener_items_base(documento_id)
    ajustes = supabase.table("ajustes_stock").select("material_id,cantidad").eq("documento_id", documento_id).execute().data or []
    ajustes_por_material = {}
    for ajuste in ajustes:
        mid = ajuste.get("material_id")
        ajustes_por_material[mid] = ajustes_por_material.get(mid, 0.0) + _float(ajuste.get("cantidad"))
    for item in items:
        item["cantidad_base"] = _float(item.get("cantidad"))
        item["cantidad_ajustes"] = ajustes_por_material.get(item.get("material_id"), 0.0)
        item["cantidad"] = item["cantidad_base"] + item["cantidad_ajustes"]
    return items


def obtener_todos_items_documento():
    return supabase.table("documento_items").select("*").order("id").execute().data or []


def obtener_item_documento_por_material(documento_id, material_id):
    data = supabase.table("documento_items").select("*").eq("documento_id", documento_id).eq("material_id", material_id).limit(1).execute().data or []
    return data[0] if data else None


def eliminar_items_documento(documento_id):
    supabase.table("documento_items").delete().eq("documento_id", documento_id).execute()


def crear_item_documento(documento_id, material_id, cantidad, unidad=None, codigo=None, material=None, categoria=None, ubicacion=None, observaciones=None):
    datos = {"documento_id": documento_id, "material_id": material_id, "cantidad": _float(cantidad), "unidad": unidad, "codigo": codigo, "material": material, "categoria": categoria, "ubicacion": ubicacion, "observaciones": observaciones}
    existente = obtener_item_documento_por_material(documento_id, material_id)
    if existente:
        data = supabase.table("documento_items").update(datos).eq("id", existente["id"]).execute().data or []
    else:
        data = supabase.table("documento_items").insert(datos).execute().data or []
    return data[0] if data else None


# ============================================================
# AJUSTES ESPECÍFICOS
# ============================================================

def obtener_ajuste_documento_material(documento_id, material_id):
    data = supabase.table("ajustes_stock").select("cantidad").eq("documento_id", documento_id).eq("material_id", material_id).execute().data or []
    return sum(_float(x.get("cantidad")) for x in data)


def obtener_stock_documento_material(documento_id, material_id):
    item = obtener_item_documento_por_material(documento_id, material_id)
    if item is None: return 0.0
    return _float(item.get("cantidad")) + obtener_ajuste_documento_material(documento_id, material_id)


def _actualizar_word_cantidad(documento, item, nueva_cantidad):
    """Actualiza la celda Cantidad del registro correspondiente en el DOCX."""
    try:
        from docx import Document
    except Exception:
        return False
    ruta = documento.get("ruta") if documento else None
    if not ruta: return False
    ruta = Path(str(ruta))
    if not ruta.exists(): return False
    doc = Document(str(ruta))
    codigo_obj = str(item.get("codigo") or "").strip().lower()
    material_obj = str(item.get("material") or "").strip().lower()
    cantidad_col = None
    encontrado = False
    for tabla in doc.tables:
        if not tabla.rows: continue
        encabezado = [str(c.text or "").strip().lower() for c in tabla.rows[0].cells]
        cantidad_col = None
        for i, texto in enumerate(encabezado):
            if texto in ("cantidad", "cant", "cant.", "stock", "existencia", "existencias"):
                cantidad_col = i; break
        if cantidad_col is None: continue
        for fila in tabla.rows[1:]:
            valores = [str(c.text or "").strip().lower() for c in fila.cells]
            if not valores: continue
            coincide = False
            if codigo_obj and codigo_obj in valores: coincide = True
            if not coincide and material_obj:
                coincide = any(material_obj == v or material_obj in v for v in valores)
            if coincide and cantidad_col < len(fila.cells):
                fila.cells[cantidad_col].text = f"{_float(nueva_cantidad):g}"
                encontrado = True
                break
        if encontrado: break
    if not encontrado: return False
    doc.save(str(ruta))
    try:
        actualizar_documento(documento.get("id"), ruta.stat().st_mtime)
    except Exception:
        pass
    return True


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
    documento = documento[0] if documento else None
    if not documento: raise Exception("No se encontró el documento seleccionado.")
    # Primero se intenta actualizar físicamente el Word. Si no existe el archivo, no se toca la base para evitar inconsistencias.
    if not _actualizar_word_cantidad(documento, item, nueva_cantidad):
        raise Exception("No se pudo actualizar la cantidad en el archivo Word.")
    # La nueva cantidad pasa a ser la base. Se eliminan ajustes específicos anteriores.
    data = supabase.table("documento_items").update({"cantidad": nueva_cantidad}).eq("id", item_id).execute().data or []
    if not data: raise Exception("No se pudo actualizar documento_items.")
    supabase.table("ajustes_stock").delete().eq("documento_id", documento_id).eq("material_id", material_id).execute()
    tipo = "ENTRADA" if diferencia > 0 else "SALIDA"
    registrar_movimiento(
        material_id,
        tipo,
        abs(diferencia),
        stock_actual,
        nueva_cantidad,
        usuario,
        observaciones,
        archivo_origen,
        documento_id=documento_id,
    )
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
    materiales = obtener_materiales() if materiales is None else materiales
    items = obtener_todos_items_documento() if items is None else items
    ajustes = obtener_ajustes_stock() if ajustes is None else ajustes
    suma_documentos = {}
    suma_ajustes = {}
    for item in items:
        mid = item.get("material_id")
        if mid is not None: suma_documentos[mid] = suma_documentos.get(mid, 0.0) + _float(item.get("cantidad"))
    for ajuste in ajustes:
        if ajuste.get("documento_id") is not None: continue
        mid = ajuste.get("material_id")
        if mid is not None: suma_ajustes[mid] = suma_ajustes.get(mid, 0.0) + _float(ajuste.get("cantidad"))
    resultado = []
    for material in materiales:
        fila = dict(material)
        mid = material.get("id")
        fila["cantidad_documentos"] = suma_documentos.get(mid, 0.0)
        fila["cantidad_ajustes"] = suma_ajustes.get(mid, 0.0)
        fila["cantidad"] = fila["cantidad_documentos"] + fila["cantidad_ajustes"]
        resultado.append(fila)
    return resultado


def obtener_inventario_general():
    # Exactamente tres consultas, independientemente de que haya 10 o 10.000 materiales.
    materiales = obtener_materiales()
    items = obtener_todos_items_documento()
    ajustes = obtener_ajustes_stock()
    return calcular_inventario_general(materiales, items, ajustes)


def obtener_stock_documentos_material(material_id):
    items = obtener_todos_items_documento()
    return sum(_float(i.get("cantidad")) for i in items if i.get("material_id") == material_id)


def obtener_stock_general_material(material_id):
    # Ruta usada por una operación manual: pocas consultas y sin N consultas por cada material.
    material_id = int(material_id)
    if obtener_material(material_id) is None: raise Exception("No se encontró el material.")
    return obtener_stock_documentos_material(material_id) + obtener_ajuste_total(material_id)


# ============================================================
# MOVIMIENTOS
# ============================================================

def obtener_movimientos(limite=100):
    return supabase.table("movimientos").select("*").order("fecha", desc=True).limit(limite).execute().data or []


def obtener_movimientos_material(material_id):
    return supabase.table("movimientos").select("*").eq("material_id", material_id).order("fecha", desc=True).execute().data or []


def modificar_stock(material_id, cantidad, tipo, usuario=None, observaciones=None, archivo_origen=None):
    cantidad = _float(cantidad)
    if cantidad < 0: raise Exception("La cantidad no puede ser negativa.")
    tipo = _normalizar_tipo(tipo)
    if tipo == "ENTRADA": delta = cantidad
    elif tipo == "SALIDA": delta = -cantidad
    else: raise Exception("Tipo de movimiento inválido.")
    return agregar_ajuste_stock(material_id, delta, usuario, observaciones)


def ajustar_stock(material_id, nuevo_stock, usuario=None, observaciones=None, archivo_origen=None):
    nuevo_stock = _float(nuevo_stock)
    if nuevo_stock < 0: raise Exception("El stock no puede ser negativo.")
    actual = obtener_stock_general_material(material_id)
    return actual if abs(nuevo_stock - actual) < 0.000001 else agregar_ajuste_stock(material_id, nuevo_stock - actual, usuario, observaciones)


# ============================================================
# BÚSQUEDA
# ============================================================

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
