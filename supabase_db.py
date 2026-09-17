from config import supabase


# ============================================================
# UTILIDADES
# ============================================================

def _float(valor, default=0.0):
    try:
        return float(valor or 0)
    except (TypeError, ValueError):
        return float(default)


def _normalizar_tipo(tipo):
    tipo = str(tipo or "").strip().upper()

    if tipo == "AGREGAR":
        return "ENTRADA"

    if tipo == "RETIRAR":
        return "SALIDA"

    return tipo


# ============================================================
# MATERIALES
# ============================================================

def obtener_materiales():
    respuesta = (
        supabase
        .table("materiales")
        .select("*")
        .order("id")
        .execute()
    )

    return respuesta.data or []


def obtener_material(material_id):
    respuesta = (
        supabase
        .table("materiales")
        .select("*")
        .eq("id", material_id)
        .limit(1)
        .execute()
    )

    if respuesta.data:
        return respuesta.data[0]

    return None


def crear_material(
    codigo,
    material,
    cantidad=0,
    unidad=None,
    categoria=None,
    ubicacion=None,
    observaciones=None,
    archivo_origen=None
):
    datos = {
        "codigo": codigo,
        "material": material,
        "cantidad": 0,
        "unidad": unidad,
        "categoria": categoria,
        "ubicacion": ubicacion,
        "observaciones": observaciones,
        "archivo_origen": archivo_origen
    }

    respuesta = (
        supabase
        .table("materiales")
        .insert(datos)
        .execute()
    )

    if respuesta.data:
        return respuesta.data[0]

    return None


def actualizar_material(
    material_id,
    codigo=None,
    material=None,
    unidad=None,
    categoria=None,
    ubicacion=None,
    observaciones=None
):
    datos = {}

    if codigo is not None:
        datos["codigo"] = codigo

    if material is not None:
        datos["material"] = material

    if unidad is not None:
        datos["unidad"] = unidad

    if categoria is not None:
        datos["categoria"] = categoria

    if ubicacion is not None:
        datos["ubicacion"] = ubicacion

    if observaciones is not None:
        datos["observaciones"] = observaciones

    if not datos:
        return None

    respuesta = (
        supabase
        .table("materiales")
        .update(datos)
        .eq("id", material_id)
        .execute()
    )

    if respuesta.data:
        return respuesta.data[0]

    return None


def actualizar_origen(material_id, nombre_archivo):
    respuesta = (
        supabase
        .table("materiales")
        .update({
            "archivo_origen": nombre_archivo
        })
        .eq("id", material_id)
        .execute()
    )

    if respuesta.data:
        return respuesta.data[0]

    return None


# ============================================================
# DOCUMENTOS
# ============================================================

def obtener_documentos():
    respuesta = (
        supabase
        .table("documentos")
        .select("*")
        .order("nombre")
        .execute()
    )

    return respuesta.data or []


def obtener_documento(ruta):
    respuesta = (
        supabase
        .table("documentos")
        .select("*")
        .eq("ruta", str(ruta))
        .limit(1)
        .execute()
    )

    if respuesta.data:
        return respuesta.data[0]

    return None


def obtener_documento_por_nombre_ruta(nombre, ruta):
    respuesta = (
        supabase
        .table("documentos")
        .select("*")
        .eq("nombre", nombre)
        .eq("ruta", str(ruta))
        .limit(1)
        .execute()
    )

    if respuesta.data:
        return respuesta.data[0]

    return None


def crear_documento(
    nombre,
    ruta,
    fecha_modificacion_archivo=None
):
    datos = {
        "nombre": nombre,
        "ruta": str(ruta)
    }

    if fecha_modificacion_archivo is not None:
        datos["fecha_modificacion_archivo"] = str(
            fecha_modificacion_archivo
        )

    respuesta = (
        supabase
        .table("documentos")
        .insert(datos)
        .execute()
    )

    if respuesta.data:
        return respuesta.data[0]

    return None


def actualizar_documento(
    documento_id,
    fecha_modificacion_archivo
):
    respuesta = (
        supabase
        .table("documentos")
        .update({
            "fecha_modificacion_archivo": str(
                fecha_modificacion_archivo
            )
        })
        .eq("id", documento_id)
        .execute()
    )

    if respuesta.data:
        return respuesta.data[0]

    return None


# ============================================================
# ITEMS DE DOCUMENTOS
# ============================================================

def obtener_items_documento(documento_id):
    respuesta = (
        supabase
        .table("documento_items")
        .select(
            """
            *,
            materiales (
                codigo,
                material,
                cantidad,
                unidad,
                categoria,
                ubicacion,
                observaciones
            )
            """
        )
        .eq("documento_id", documento_id)
        .order("id")
        .execute()
    )

    return respuesta.data or []


def obtener_todos_items_documento():
    respuesta = (
        supabase
        .table("documento_items")
        .select("*")
        .order("id")
        .execute()
    )

    return respuesta.data or []


def obtener_item_documento_por_material(
    documento_id,
    material_id
):
    respuesta = (
        supabase
        .table("documento_items")
        .select("*")
        .eq("documento_id", documento_id)
        .eq("material_id", material_id)
        .limit(1)
        .execute()
    )

    if respuesta.data:
        return respuesta.data[0]

    return None


def eliminar_items_documento(documento_id):
    (
        supabase
        .table("documento_items")
        .delete()
        .eq("documento_id", documento_id)
        .execute()
    )


def crear_item_documento(
    documento_id,
    material_id,
    cantidad,
    unidad=None,
    codigo=None,
    material=None,
    categoria=None,
    ubicacion=None,
    observaciones=None
):
    """
    Crea o actualiza un item proveniente del Word.

    documento_items.cantidad representa la cantidad
    proveniente del documento original.

    Los cambios manuales se guardan aparte en
    ajustes_stock y quedan asociados al documento.
    """

    datos = {
        "documento_id": documento_id,
        "material_id": material_id,
        "cantidad": _float(cantidad),
        "unidad": unidad,
        "codigo": codigo,
        "material": material,
        "categoria": categoria,
        "ubicacion": ubicacion,
        "observaciones": observaciones
    }

    existente = obtener_item_documento_por_material(
        documento_id,
        material_id
    )

    if existente:
        respuesta = (
            supabase
            .table("documento_items")
            .update(datos)
            .eq("id", existente["id"])
            .execute()
        )

        if respuesta.data:
            return respuesta.data[0]

        return None

    respuesta = (
        supabase
        .table("documento_items")
        .insert(datos)
        .execute()
    )

    if respuesta.data:
        return respuesta.data[0]

    return None


# ============================================================
# AJUSTES DE UN INVENTARIO ESPECÍFICO
# ============================================================

def obtener_ajuste_documento_material(
    documento_id,
    material_id
):
    """
    Obtiene la suma de ajustes manuales correspondientes
    exclusivamente a un documento y material.
    """

    respuesta = (
        supabase
        .table("ajustes_stock")
        .select("cantidad")
        .eq("documento_id", documento_id)
        .eq("material_id", material_id)
        .execute()
    )

    ajustes = respuesta.data or []

    return sum(
        _float(ajuste.get("cantidad"))
        for ajuste in ajustes
    )


def obtener_stock_documento_material(
    documento_id,
    material_id
):
    """
    Stock real de un material dentro de UN documento.

    Stock =
        cantidad original del documento
        +
        ajustes manuales de ese documento
    """

    item = obtener_item_documento_por_material(
        documento_id,
        material_id
    )

    if item is None:
        return 0.0

    cantidad_original = _float(
        item.get("cantidad")
    )

    ajuste = obtener_ajuste_documento_material(
        documento_id,
        material_id
    )

    return cantidad_original + ajuste


def actualizar_cantidad_documento_item(
    item_id,
    nueva_cantidad,
    usuario=None,
    observaciones=None,
    archivo_origen=None,
    documento_id=None
):
    """
    Modificación manual del stock de un inventario específico.

    NO modifica documento_items.cantidad.

    La cantidad original del Word permanece intacta.

    El cambio se guarda en ajustes_stock asociado
    al documento correspondiente.
    """

    nueva_cantidad = _float(
        nueva_cantidad
    )

    if nueva_cantidad < 0:
        raise Exception(
            "La cantidad no puede ser negativa."
        )

    # --------------------------------------------------------
    # BUSCAR ITEM
    # --------------------------------------------------------

    respuesta = (
        supabase
        .table("documento_items")
        .select("*")
        .eq("id", item_id)
        .limit(1)
        .execute()
    )

    if not respuesta.data:
        raise Exception(
            "No se encontró el material dentro del documento."
        )

    item = respuesta.data[0]

    material_id = item.get("material_id")

    if material_id is None:
        raise Exception(
            "El item no tiene material asociado."
        )

    # --------------------------------------------------------
    # OBTENER DOCUMENTO
    # --------------------------------------------------------

    documento_item_id = item.get(
        "documento_id"
    )

    if documento_id is None:
        documento_id = documento_item_id

    if documento_id is None:
        raise Exception(
            "No se pudo determinar el documento del material."
        )

    # Verificación de seguridad:
    # el documento recibido debe coincidir con el item.
    if (
        documento_item_id is not None
        and int(documento_id) != int(documento_item_id)
    ):
        raise Exception(
            "El material no pertenece al documento seleccionado."
        )

    # --------------------------------------------------------
    # STOCK REAL DEL DOCUMENTO
    # --------------------------------------------------------

    stock_actual = obtener_stock_documento_material(
        documento_id,
        material_id
    )

    # --------------------------------------------------------
    # DIFERENCIA
    # --------------------------------------------------------

    diferencia = (
        nueva_cantidad -
        stock_actual
    )

    if abs(diferencia) < 0.000001:
        return stock_actual

    stock_nuevo = (
        stock_actual +
        diferencia
    )

    if stock_nuevo < -0.000001:
        raise Exception(
            "El stock no puede quedar negativo."
        )

    # --------------------------------------------------------
    # GUARDAR AJUSTE
    # --------------------------------------------------------

    respuesta = (
        supabase
        .table("ajustes_stock")
        .insert({
            "material_id": int(material_id),
            "documento_id": int(documento_id),
            "cantidad": diferencia,
            "usuario": usuario,
            "observaciones": observaciones
        })
        .execute()
    )

    if not respuesta.data:
        raise Exception(
            "No se pudo guardar el ajuste de stock."
        )

    # --------------------------------------------------------
    # MOVIMIENTO
    # --------------------------------------------------------

    tipo = (
        "ENTRADA"
        if diferencia > 0
        else "SALIDA"
    )

    registrar_movimiento(
        material_id=material_id,
        tipo=tipo,
        cantidad=abs(diferencia),
        stock_anterior=stock_actual,
        stock_nuevo=stock_nuevo,
        usuario=usuario,
        observaciones=observaciones,
        archivo_origen=archivo_origen
    )

    return stock_nuevo


# ============================================================
# AJUSTES MANUALES
# ============================================================

def obtener_ajustes_stock():
    respuesta = (
        supabase
        .table("ajustes_stock")
        .select("*")
        .order("fecha", desc=True)
        .execute()
    )

    return respuesta.data or []


def obtener_ajustes_material(material_id):
    respuesta = (
        supabase
        .table("ajustes_stock")
        .select("*")
        .eq("material_id", material_id)
        .order("fecha", desc=True)
        .execute()
    )

    return respuesta.data or []


def obtener_ajuste_total(material_id):
    """
    Obtiene solamente ajustes generales.

    Los ajustes específicos de documentos NO se incluyen
    aquí porque ya están asociados a su documento.
    """

    respuesta = (
        supabase
        .table("ajustes_stock")
        .select("cantidad")
        .eq("material_id", material_id)
        .is_("documento_id", "null")
        .execute()
    )

    ajustes = respuesta.data or []

    return sum(
        _float(
            ajuste.get("cantidad")
        )
        for ajuste in ajustes
    )


# ============================================================
# MOVIMIENTOS
# ============================================================

def registrar_movimiento(
    material_id,
    tipo,
    cantidad,
    stock_anterior,
    stock_nuevo,
    usuario=None,
    observaciones=None,
    archivo_origen=None
):
    datos = {
        "material_id": int(material_id),
        "tipo": _normalizar_tipo(tipo),
        "cantidad": _float(cantidad),
        "stock_anterior": _float(stock_anterior),
        "stock_nuevo": _float(stock_nuevo),
        "usuario": usuario,
        "observaciones": observaciones,
        "archivo_origen": archivo_origen
    }

    respuesta = (
        supabase
        .table("movimientos")
        .insert(datos)
        .execute()
    )

    if respuesta.data:
        return respuesta.data[0]

    return None


def agregar_ajuste_stock(
    material_id,
    delta,
    usuario=None,
    observaciones=None
):
    """
    Ajuste MANUAL del inventario general.

    Estos ajustes tienen documento_id = NULL.
    """

    delta = _float(delta)

    if abs(delta) < 0.000001:
        return obtener_stock_general_material(
            material_id
        )

    stock_anterior = (
        obtener_stock_general_material(
            material_id
        )
    )

    stock_nuevo = (
        stock_anterior +
        delta
    )

    if stock_nuevo < -0.000001:
        raise Exception(
            "No hay stock suficiente. "
            f"Stock actual: {stock_anterior:g}"
        )

    respuesta = (
        supabase
        .table("ajustes_stock")
        .insert({
            "material_id": int(material_id),
            "documento_id": None,
            "cantidad": delta,
            "usuario": usuario,
            "observaciones": observaciones
        })
        .execute()
    )

    if not respuesta.data:
        raise Exception(
            "No se pudo guardar el ajuste."
        )

    tipo = (
        "ENTRADA"
        if delta > 0
        else "SALIDA"
    )

    registrar_movimiento(
        material_id=material_id,
        tipo=tipo,
        cantidad=abs(delta),
        stock_anterior=stock_anterior,
        stock_nuevo=stock_nuevo,
        usuario=usuario,
        observaciones=observaciones,
        archivo_origen=None
    )

    return stock_nuevo


# ============================================================
# INVENTARIO GENERAL
# ============================================================

def calcular_inventario_general(
    materiales=None,
    items=None,
    ajustes=None
):
    if materiales is None:
        materiales = obtener_materiales()

    if items is None:
        items = obtener_todos_items_documento()

    if ajustes is None:
        ajustes = obtener_ajustes_stock()

    suma_documentos = {}
    suma_ajustes_generales = {}

    # --------------------------------------------------------
    # SUMA DE TODOS LOS DOCUMENTOS
    # --------------------------------------------------------

    for item in items:

        material_id = item.get(
            "material_id"
        )

        if material_id is None:
            continue

        cantidad = _float(
            item.get("cantidad")
        )

        suma_documentos[material_id] = (
            suma_documentos.get(
                material_id,
                0.0
            )
            + cantidad
        )

    # --------------------------------------------------------
    # SOLAMENTE AJUSTES GENERALES
    # --------------------------------------------------------

    for ajuste in ajustes:

        # IMPORTANTE:
        # Si tiene documento_id, pertenece a un
        # inventario específico y NO se suma nuevamente
        # al inventario general.
        if ajuste.get("documento_id") is not None:
            continue

        material_id = ajuste.get(
            "material_id"
        )

        if material_id is None:
            continue

        cantidad = _float(
            ajuste.get("cantidad")
        )

        suma_ajustes_generales[material_id] = (
            suma_ajustes_generales.get(
                material_id,
                0.0
            )
            + cantidad
        )

    # --------------------------------------------------------
    # CONSTRUCCIÓN
    # --------------------------------------------------------

    resultado = []

    for material in materiales:

        material_id = material.get(
            "id"
        )

        cantidad_documentos = (
            suma_documentos.get(
                material_id,
                0.0
            )
        )

        cantidad_ajustes = (
            suma_ajustes_generales.get(
                material_id,
                0.0
            )
        )

        fila = dict(material)

        fila["cantidad_documentos"] = (
            cantidad_documentos
        )

        fila["cantidad_ajustes"] = (
            cantidad_ajustes
        )

        fila["cantidad"] = (
            cantidad_documentos
            +
            cantidad_ajustes
        )

        resultado.append(
            fila
        )

    return resultado


def obtener_inventario_general():
    return calcular_inventario_general()


def obtener_stock_documentos_material(
    material_id
):
    items = obtener_todos_items_documento()

    return sum(
        _float(
            item.get("cantidad")
        )
        for item in items
        if item.get("material_id") == material_id
    )


def obtener_stock_general_material(
    material_id
):
    material_id = int(
        material_id
    )

    material = obtener_material(
        material_id
    )

    if material is None:
        raise Exception(
            "No se encontró el material."
        )

    stock_documentos = (
        obtener_stock_documentos_material(
            material_id
        )
    )

    stock_ajustes = (
        obtener_ajuste_total(
            material_id
        )
    )

    return (
        stock_documentos
        +
        stock_ajustes
    )


# ============================================================
# MOVIMIENTOS
# ============================================================

def obtener_movimientos(limite=100):
    respuesta = (
        supabase
        .table("movimientos")
        .select(
            """
            *,
            materiales (
                codigo,
                material,
                unidad
            )
            """
        )
        .order(
            "fecha",
            desc=True
        )
        .limit(limite)
        .execute()
    )

    return respuesta.data or []


def obtener_movimientos_material(
    material_id
):
    respuesta = (
        supabase
        .table("movimientos")
        .select("*")
        .eq(
            "material_id",
            material_id
        )
        .order(
            "fecha",
            desc=True
        )
        .execute()
    )

    return respuesta.data or []


# ============================================================
# COMPATIBILIDAD
# ============================================================

def modificar_stock(
    material_id,
    cantidad,
    tipo,
    usuario=None,
    observaciones=None,
    archivo_origen=None
):
    cantidad = _float(
        cantidad
    )

    if cantidad < 0:
        raise Exception(
            "La cantidad no puede ser negativa."
        )

    tipo = _normalizar_tipo(
        tipo
    )

    if tipo == "ENTRADA":
        delta = cantidad

    elif tipo == "SALIDA":
        delta = -cantidad

    else:
        raise Exception(
            "Tipo de movimiento inválido."
        )

    return agregar_ajuste_stock(
        material_id=material_id,
        delta=delta,
        usuario=usuario,
        observaciones=observaciones
    )


def ajustar_stock(
    material_id,
    nuevo_stock,
    usuario=None,
    observaciones=None,
    archivo_origen=None
):
    nuevo_stock = _float(
        nuevo_stock
    )

    if nuevo_stock < 0:
        raise Exception(
            "El stock no puede ser negativo."
        )

    stock_actual = (
        obtener_stock_general_material(
            material_id
        )
    )

    diferencia = (
        nuevo_stock -
        stock_actual
    )

    if abs(diferencia) < 0.000001:
        return stock_actual

    return agregar_ajuste_stock(
        material_id=material_id,
        delta=diferencia,
        usuario=usuario,
        observaciones=observaciones
    )


# ============================================================
# BÚSQUEDA
# ============================================================

def buscar_material_por_codigo(
    codigo,
    material=None
):
    codigo = (
        codigo or ""
    ).strip()

    if not codigo:
        return None

    respuesta = (
        supabase
        .table("materiales")
        .select("*")
        .eq("codigo", codigo)
        .execute()
    )

    materiales = (
        respuesta.data or []
    )

    if not materiales:
        return None

    if material:

        material_normalizado = (
            material.strip().lower()
        )

        for item in materiales:

            nombre = (
                item.get("material") or ""
            ).strip().lower()

            if nombre == material_normalizado:
                return item

    return materiales[0]


def buscar_material_sin_codigo(
    material,
    categoria,
    ubicacion
):
    materiales = (
        supabase
        .table("materiales")
        .select("*")
        .is_("codigo", "null")
        .execute()
        .data
        or []
    )

    def normalizar(valor):
        return str(
            valor or ""
        ).strip().lower()

    material_buscar = normalizar(
        material
    )

    categoria_buscar = normalizar(
        categoria
    )

    ubicacion_buscar = normalizar(
        ubicacion
    )

    for existente in materiales:

        if (
            normalizar(
                existente.get("material")
            )
            == material_buscar

            and

            normalizar(
                existente.get("categoria")
            )
            == categoria_buscar

            and

            normalizar(
                existente.get("ubicacion")
            )
            == ubicacion_buscar
        ):
            return existente

    return None


def buscar_material(
    codigo,
    material,
    categoria,
    ubicacion
):
    if codigo:
        return buscar_material_por_codigo(
            codigo,
            material
        )

    return buscar_material_sin_codigo(
        material,
        categoria,
        ubicacion
    )


def buscar_materiales(texto):
    texto = (
        texto or ""
    ).strip()

    if not texto:
        return obtener_inventario_general()

    materiales = (
        obtener_inventario_general()
    )

    texto = texto.lower()

    resultado = []

    for material in materiales:

        valores = [
            material.get("codigo"),
            material.get("material"),
            material.get("categoria"),
            material.get("ubicacion"),
            material.get("observaciones")
        ]

        if any(
            texto in str(
                valor or ""
            ).lower()
            for valor in valores
        ):
            resultado.append(
                material
            )

    return resultado


# ============================================================
# ESTADÍSTICAS
# ============================================================

def obtener_estadisticas():
    materiales = (
        obtener_inventario_general()
    )

    total_materiales = len(
        materiales
    )

    con_stock = sum(
        1
        for material in materiales
        if _float(
            material.get("cantidad")
        ) > 0
    )

    sin_stock = (
        total_materiales -
        con_stock
    )

    cantidad_total = sum(
        _float(
            material.get("cantidad")
        )
        for material in materiales
    )

    return {
        "total_materiales": total_materiales,
        "con_stock": con_stock,
        "sin_stock": sin_stock,
        "cantidad_total": cantidad_total
    }


# ============================================================
# CONEXIÓN
# ============================================================

def probar_conexion():
    try:

        respuesta = (
            supabase
            .table("materiales")
            .select("id")
            .limit(1)
            .execute()
        )

        return respuesta.data is not None

    except Exception:
        return False