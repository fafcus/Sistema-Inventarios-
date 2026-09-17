import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from pathlib import Path
import threading
import time
import traceback

from config import supabase

from supabase_db import (
    probar_conexion,
    obtener_materiales,
    obtener_material,
    crear_material,
    actualizar_material,

    # SISTEMA DE STOCK
    obtener_inventario_general,
    agregar_ajuste_stock,
    actualizar_cantidad_documento_item,

    obtener_movimientos,
    obtener_documentos,
    obtener_items_documento,
    crear_item_documento,
    buscar_material,
)

import importar_word


# ============================================================
# CONFIGURACIÓN
# ============================================================

CARPETA_DOCUMENTOS = Path(__file__).resolve().parent / "documentos"

NOMBRE_APP = "INVENTARIO MATERIAL NAVAL"

GENERAL = "🏠 INVENTARIO GENERAL"
COLOR_STOCK = "🟢 HAY STOCK"
COLOR_SIN_STOCK = "🔴 SIN STOCK"

INTERVALO_MONITOR = 5000
INTERVALO_SINCRONIZACION = 3000


# ============================================================
# COLORES
# ============================================================

COLOR_FONDO = "#eef3f8"
COLOR_PANEL = "#ffffff"

COLOR_AZUL_OSCURO = "#12304a"
COLOR_AZUL = "#1f5d87"
COLOR_AZUL_CLARO = "#dceaf5"

COLOR_BORDE = "#c7d5e0"

COLOR_TEXTO = "#183247"
COLOR_TEXTO_SECUNDARIO = "#506575"

COLOR_STOCK_FONDO = "#e7f6e9"
COLOR_SIN_STOCK_FONDO = "#fdeaea"


# ============================================================
# VARIABLES GLOBALES
# ============================================================

root = None

selector_inventario = None
tabla = None
tabla_movimientos = None
entrada_busqueda = None

lbl_total_materiales = None
lbl_con_stock = None
lbl_sin_stock = None
lbl_cantidad_total = None

lbl_estado = None
lbl_progreso = None

inventario_seleccionado = GENERAL


# ============================================================
# ESTADO DE IMPORTACIÓN WORD
# ============================================================

importacion_en_curso = False
lock_importacion = threading.Lock()

estado_archivos_word = {}


# ============================================================
# CACHE
# ============================================================

cache_materiales = []
cache_documentos = []
cache_movimientos = []

cache_lock = threading.Lock()


# ============================================================
# ACTUALIZACIÓN
# ============================================================

actualizacion_en_curso = False
lock_actualizacion = threading.Lock()


# ============================================================
# SINCRONIZACIÓN
# ============================================================

sincronizacion_en_curso = False
lock_sincronizacion = threading.Lock()

firma_datos_sincronizados = None

pausar_sincronizacion = False


# ============================================================
# UTILIDADES
# ============================================================

def limpiar_texto(valor):

    if valor is None:
        return ""

    return str(valor).strip()


def formatear_numero(valor):

    try:
        return f"{float(valor or 0):g}"

    except Exception:
        return str(valor or 0)


def obtener_nombre_inventario(documento):

    if not documento:
        return ""

    return documento.get("nombre", "")


def invalidar_cache():

    global cache_materiales
    global cache_documentos
    global cache_movimientos

    with cache_lock:

        cache_materiales = []
        cache_documentos = []
        cache_movimientos = []


# ============================================================
# CARGAR DATOS DE SUPABASE
# ============================================================

def cargar_datos_supabase():

    global cache_materiales
    global cache_documentos
    global cache_movimientos

    try:

        # IMPORTANTE:
        # El inventario general debe venir calculado
        # por obtener_inventario_general().
        materiales = obtener_inventario_general()

    except Exception as error:

        print(
            f"Error obteniendo inventario general: {error}"
        )

        traceback.print_exc()

        try:

            materiales = obtener_materiales()

        except Exception as error2:

            print(
                f"Error obteniendo materiales: {error2}"
            )

            traceback.print_exc()

            materiales = []

    try:

        documentos = obtener_documentos()

    except Exception as error:

        print(
            f"Error obteniendo documentos: {error}"
        )

        documentos = []

    try:

        movimientos = obtener_movimientos(100)

    except Exception as error:

        print(
            f"Error obteniendo movimientos: {error}"
        )

        movimientos = []

    materiales = materiales or []
    documentos = documentos or []
    movimientos = movimientos or []

    with cache_lock:

        cache_materiales = materiales
        cache_documentos = documentos
        cache_movimientos = movimientos

    return (
        materiales,
        documentos,
        movimientos,
    )


def obtener_materiales_cache():

    with cache_lock:
        return list(cache_materiales)


def obtener_documentos_cache():

    with cache_lock:
        return list(cache_documentos)


def obtener_movimientos_cache():

    with cache_lock:
        return list(cache_movimientos)


# ============================================================
# FIRMA DE SINCRONIZACIÓN
# ============================================================

def generar_firma_sincronizacion(
    materiales,
    documentos,
    movimientos
):

    materiales_firma = []

    for material in materiales:

        materiales_firma.append(
            (
                material.get("id"),
                material.get("cantidad"),
                material.get("codigo"),
                material.get("material"),
                material.get("unidad"),
                material.get("categoria"),
                material.get("ubicacion"),
                material.get("observaciones"),
            )
        )

    documentos_firma = []

    for documento in documentos:

        documentos_firma.append(
            (
                documento.get("id"),
                documento.get("nombre"),
                documento.get("ruta"),
                documento.get(
                    "fecha_modificacion_archivo"
                ),
            )
        )

    movimientos_firma = []

    for movimiento in movimientos:

        movimientos_firma.append(
            (
                movimiento.get("id"),
                movimiento.get("material_id"),
                movimiento.get("tipo"),
                movimiento.get("cantidad"),
                movimiento.get("stock_anterior"),
                movimiento.get("stock_nuevo"),
                movimiento.get("fecha"),
                movimiento.get("usuario"),
                movimiento.get("archivo_origen"),
                movimiento.get("observaciones"),
            )
        )

    return (
        tuple(materiales_firma),
        tuple(documentos_firma),
        tuple(movimientos_firma),
    )


# ============================================================
# ESTADÍSTICAS
# ============================================================

def actualizar_estadisticas(materiales):

    total = len(materiales)

    con_stock = 0
    sin_stock = 0
    cantidad_total = 0

    for material in materiales:

        try:

            cantidad = float(
                material.get(
                    "cantidad",
                    0
                ) or 0
            )

        except Exception:

            cantidad = 0

        cantidad_total += cantidad

        if cantidad > 0:

            con_stock += 1

        else:

            sin_stock += 1

    if lbl_total_materiales:

        lbl_total_materiales.config(
            text=f"Materiales: {total}"
        )

    if lbl_con_stock:

        lbl_con_stock.config(
            text=f"Con stock: {con_stock}"
        )

    if lbl_sin_stock:

        lbl_sin_stock.config(
            text=f"Sin stock: {sin_stock}"
        )

    if lbl_cantidad_total:

        lbl_cantidad_total.config(
            text=f"Cantidad total: {cantidad_total:g}"
        )


# ============================================================
# SELECTOR DE INVENTARIOS
# ============================================================

def cargar_selector(documentos=None):

    global inventario_seleccionado

    if documentos is None:
        documentos = obtener_documentos_cache()

    valores = [GENERAL]

    for documento in documentos:

        nombre = obtener_nombre_inventario(
            documento
        )

        if not nombre:
            continue

        valores.append(nombre)

    selector_inventario["values"] = valores

    actual = selector_inventario.get()

    if actual in valores:

        inventario_seleccionado = actual

        return

    selector_inventario.current(0)

    inventario_seleccionado = GENERAL


def cambiar_inventario(event=None):

    global inventario_seleccionado

    inventario_seleccionado = (
        selector_inventario.get()
    )

    entrada_busqueda.delete(
        0,
        tk.END
    )

    actualizar_tabla()
    actualizar_movimientos()


def es_inventario_general():

    return selector_inventario.get() == GENERAL


# ============================================================
# DOCUMENTO ACTUAL
# ============================================================

def obtener_documento_actual():

    seleccionado = selector_inventario.get()

    if seleccionado == GENERAL:
        return None

    documentos = obtener_documentos_cache()

    for documento in documentos:

        if documento.get("nombre") == seleccionado:
            return documento

    return None


def obtener_documento_id_actual():

    documento = obtener_documento_actual()

    if not documento:
        return None

    return documento.get("id")


# ============================================================
# OBTENER MATERIALES SELECCIONADOS
# ============================================================

def obtener_materiales_seleccionados():

    seleccionado = selector_inventario.get()

    materiales = obtener_materiales_cache()

    # ========================================================
    # INVENTARIO GENERAL
    # ========================================================

    if seleccionado == GENERAL:

        return materiales

    # ========================================================
    # INVENTARIO ESPECÍFICO
    # ========================================================

    documento = obtener_documento_actual()

    if not documento:
        return []

    documento_id = documento.get("id")

    if not documento_id:
        return []

    try:

        respuesta = (
            supabase
            .table("documento_items")
            .select(
                "material_id,"
                "cantidad,"
                "unidad,"
                "codigo,"
                "material,"
                "categoria,"
                "ubicacion,"
                "observaciones"
            )
            .eq(
                "documento_id",
                documento_id
            )
            .execute()
        )

        items = respuesta.data or []

    except Exception as error:

        print(
            "Error obteniendo documento_items:",
            error
        )

        return []

    materiales_por_id = {}

    for material in materiales:

        material_id = material.get("id")

        if material_id is not None:

            materiales_por_id[
                material_id
            ] = material

    resultado = []

    for item in items:

        material_id = item.get(
            "material_id"
        )

        material = materiales_por_id.get(
            material_id
        )

        if not material:

            try:

                material = obtener_material(
                    material_id
                )

            except Exception:

                material = None

        if not material:
            continue

        copia = dict(material)

        copia["cantidad"] = item.get(
            "cantidad",
            0
        )

        for campo in (
            "codigo",
            "material",
            "unidad",
            "categoria",
            "ubicacion",
            "observaciones",
        ):

            if item.get(campo) is not None:

                copia[campo] = item.get(
                    campo
                )

        resultado.append(copia)

    return resultado


# ============================================================
# TABLA PRINCIPAL
# ============================================================

def actualizar_tabla():

    if tabla is None:
        return

    for item in tabla.get_children():

        tabla.delete(item)

    materiales = (
        obtener_materiales_seleccionados()
    )

    texto_busqueda = limpiar_texto(
        entrada_busqueda.get()
    ).lower()

    materiales_filtrados = []

    for material in materiales:

        if texto_busqueda:

            texto = " ".join(
                [
                    limpiar_texto(
                        material.get("codigo")
                    ),
                    limpiar_texto(
                        material.get("material")
                    ),
                    limpiar_texto(
                        material.get("categoria")
                    ),
                    limpiar_texto(
                        material.get("ubicacion")
                    ),
                    limpiar_texto(
                        material.get("observaciones")
                    ),
                ]
            ).lower()

            if texto_busqueda not in texto:
                continue

        materiales_filtrados.append(
            material
        )

    for material in materiales_filtrados:

        material_id = material.get("id")

        if material_id is None:
            continue

        cantidad = material.get(
            "cantidad",
            0
        ) or 0

        try:

            cantidad_num = float(
                cantidad
            )

        except Exception:

            cantidad_num = 0

        if cantidad_num > 0:

            estado = COLOR_STOCK
            tag = "stock"

        else:

            estado = COLOR_SIN_STOCK
            tag = "sin_stock"

        tabla.insert(
            "",
            "end",
            iid=str(material_id),
            values=(
                material.get("codigo") or "",
                material.get("material") or "",
                formatear_numero(
                    cantidad_num
                ),
                material.get("unidad") or "",
                material.get("categoria") or "",
                material.get("ubicacion") or "",
                material.get("observaciones") or "",
                estado,
            ),
            tags=(tag,)
        )

    actualizar_estadisticas(
        materiales_filtrados
    )


def buscar(event=None):

    actualizar_tabla()


# ============================================================
# MATERIAL SELECCIONADO
# ============================================================

def obtener_material_seleccionado():

    seleccion = tabla.selection()

    if not seleccion:

        messagebox.showwarning(
            "Selección",
            "Seleccioná un material primero.",
            parent=root
        )

        return None

    try:

        material_id = int(
            seleccion[0]
        )

    except Exception:

        return None

    materiales = obtener_materiales_cache()

    for material in materiales:

        if material.get("id") == material_id:

            return material

    try:

        material = obtener_material(
            material_id
        )

    except Exception as error:

        print(
            "Error obteniendo material:",
            error
        )

        material = None

    if not material:

        messagebox.showerror(
            "Error",
            "No se pudo obtener el material.",
            parent=root
        )

        return None

    return material


# ============================================================
# ITEM DEL DOCUMENTO
# ============================================================

def obtener_item_documento(material_id):

    documento_id = (
        obtener_documento_id_actual()
    )

    if not documento_id:
        return None

    try:

        items = obtener_items_documento(
            documento_id
        )

    except Exception as error:

        print(
            "Error obteniendo items:",
            error
        )

        return None

    for item in items:

        try:

            if int(
                item.get(
                    "material_id",
                    -1
                )
            ) == int(material_id):

                return item

        except Exception:

            continue

    return None


# ============================================================
# ACTUALIZAR CANTIDAD DEL DOCUMENTO
# ============================================================

def actualizar_stock_documento(
    material_id,
    nueva_cantidad,
    tipo_movimiento=None,
    usuario="APP",
    observaciones=None
):

    documento_id = (
        obtener_documento_id_actual()
    )

    if not documento_id:

        raise Exception(
            "No se encontró el documento seleccionado."
        )

    item = obtener_item_documento(
        material_id
    )

    if item is None:

        raise Exception(
            "El material no pertenece al inventario seleccionado."
        )

    resultado = actualizar_cantidad_documento_item(
        item["id"],
        nueva_cantidad,
        usuario=usuario,
        archivo_origen=inventario_seleccionado,
        observaciones=observaciones
    )

    if resultado is None:

        raise Exception(
            "No se pudo actualizar la cantidad."
        )

    return resultado


# ============================================================
# AGREGAR STOCK
# ============================================================

def agregar_stock():

    material = obtener_material_seleccionado()

    if not material:
        return

    material_id = material.get("id")

    nombre = (
        material.get("material")
        or ""
    )

    codigo = (
        material.get("codigo")
        or "-"
    )

    unidad = (
        material.get("unidad")
        or ""
    )

    # ========================================================
    # OBTENER STOCK ACTUAL
    # ========================================================

    if es_inventario_general():

        stock_actual = float(
            material.get(
                "cantidad",
                0
            ) or 0
        )

    else:

        item = obtener_item_documento(
            material_id
        )

        if item is None:

            messagebox.showerror(
                "Error",
                (
                    "El material no pertenece "
                    "al inventario seleccionado."
                ),
                parent=root
            )

            return

        stock_actual = float(
            item.get(
                "cantidad",
                0
            ) or 0
        )

    cantidad = simpledialog.askfloat(
        "Agregar stock",
        (
            f"Material: {nombre}\n"
            f"Código: {codigo}\n"
            f"Stock actual: "
            f"{formatear_numero(stock_actual)} "
            f"{unidad}\n\n"
            f"Cantidad a agregar:"
        ),
        minvalue=0.0001,
        parent=root
    )

    if cantidad is None:
        return

    if cantidad <= 0:
        return

    # ========================================================
    # INVENTARIO GENERAL
    # ========================================================

    if es_inventario_general():

        try:

            nuevo_stock = agregar_ajuste_stock(
                material_id=material_id,
                delta=cantidad,
                usuario="APP",
                observaciones=(
                    "Ingreso manual "
                    "en inventario general"
                )
            )

            print(
                "DEBUG STOCK:",
                "material_id=",
                material_id,
                "anterior=",
                stock_actual,
                "agregado=",
                cantidad,
                "nuevo=",
                nuevo_stock
            )

            invalidar_cache()

            actualizar_todo(
                forzar=True
            )

            messagebox.showinfo(
                "Stock actualizado",
                (
                    f"Material: {nombre}\n\n"
                    f"Stock anterior: "
                    f"{formatear_numero(stock_actual)} "
                    f"{unidad}\n"
                    f"Cantidad agregada: "
                    f"{formatear_numero(cantidad)} "
                    f"{unidad}\n"
                    f"Stock nuevo: "
                    f"{formatear_numero(nuevo_stock)} "
                    f"{unidad}"
                ),
                parent=root
            )

        except Exception as error:

            traceback.print_exc()

            messagebox.showerror(
                "Error",
                (
                    "No se pudo agregar stock:\n\n"
                    f"{error}"
                ),
                parent=root
            )

        return

    # ========================================================
    # INVENTARIO ESPECÍFICO
    # ========================================================

    nueva_cantidad = (
        stock_actual + cantidad
    )

    try:

        actualizar_stock_documento(
            material_id,
            nueva_cantidad,
            tipo_movimiento="ENTRADA",
            usuario="APP",
            observaciones=(
                "Ingreso manual en "
                + inventario_seleccionado
            )
        )

        invalidar_cache()

        actualizar_todo(
            forzar=True
        )

        messagebox.showinfo(
            "Stock actualizado",
            (
                f"Material: {nombre}\n\n"
                f"Inventario: "
                f"{inventario_seleccionado}\n\n"
                f"Stock anterior: "
                f"{formatear_numero(stock_actual)} "
                f"{unidad}\n"
                f"Cantidad agregada: "
                f"{formatear_numero(cantidad)} "
                f"{unidad}\n"
                f"Stock nuevo: "
                f"{formatear_numero(nueva_cantidad)} "
                f"{unidad}"
            ),
            parent=root
        )

    except Exception as error:

        traceback.print_exc()

        messagebox.showerror(
            "Error",
            (
                "No se pudo agregar stock:\n\n"
                f"{error}"
            ),
            parent=root
        )


# ============================================================
# RETIRAR STOCK
# ============================================================

def retirar_stock():

    material = obtener_material_seleccionado()

    if not material:
        return

    material_id = material.get("id")

    nombre = (
        material.get("material")
        or ""
    )

    codigo = (
        material.get("codigo")
        or "-"
    )

    unidad = (
        material.get("unidad")
        or ""
    )

    # ========================================================
    # OBTENER STOCK ACTUAL
    # ========================================================

    if es_inventario_general():

        stock_actual = float(
            material.get(
                "cantidad",
                0
            ) or 0
        )

    else:

        item = obtener_item_documento(
            material_id
        )

        if item is None:

            messagebox.showerror(
                "Error",
                (
                    "El material no pertenece "
                    "al inventario seleccionado."
                ),
                parent=root
            )

            return

        stock_actual = float(
            item.get(
                "cantidad",
                0
            ) or 0
        )

    cantidad = simpledialog.askfloat(
        "Retirar stock",
        (
            f"Material: {nombre}\n"
            f"Código: {codigo}\n"
            f"Stock actual: "
            f"{formatear_numero(stock_actual)} "
            f"{unidad}\n\n"
            f"Cantidad a retirar:"
        ),
        minvalue=0.0001,
        parent=root
    )

    if cantidad is None:
        return

    if cantidad <= 0:
        return

    if cantidad > stock_actual:

        messagebox.showwarning(
            "Stock insuficiente",
            (
                f"No podés retirar "
                f"{formatear_numero(cantidad)} "
                f"{unidad}.\n\n"
                f"Stock disponible: "
                f"{formatear_numero(stock_actual)} "
                f"{unidad}"
            ),
            parent=root
        )

        return

    # ========================================================
    # INVENTARIO GENERAL
    # ========================================================

    if es_inventario_general():

        try:

            nuevo_stock = agregar_ajuste_stock(
                material_id=material_id,
                delta=-cantidad,
                usuario="APP",
                observaciones=(
                    "Retiro manual "
                    "en inventario general"
                )
            )

            print(
                "DEBUG STOCK:",
                "material_id=",
                material_id,
                "anterior=",
                stock_actual,
                "retirado=",
                cantidad,
                "nuevo=",
                nuevo_stock
            )

            invalidar_cache()

            actualizar_todo(
                forzar=True
            )

            messagebox.showinfo(
                "Retiro realizado",
                (
                    f"Material: {nombre}\n\n"
                    f"Stock anterior: "
                    f"{formatear_numero(stock_actual)} "
                    f"{unidad}\n"
                    f"Cantidad retirada: "
                    f"{formatear_numero(cantidad)} "
                    f"{unidad}\n"
                    f"Stock nuevo: "
                    f"{formatear_numero(nuevo_stock)} "
                    f"{unidad}"
                ),
                parent=root
            )

        except Exception as error:

            traceback.print_exc()

            messagebox.showerror(
                "Error",
                (
                    "No se pudo retirar stock:\n\n"
                    f"{error}"
                ),
                parent=root
            )

        return

    # ========================================================
    # INVENTARIO ESPECÍFICO
    # ========================================================

    nueva_cantidad = (
        stock_actual - cantidad
    )

    try:

        actualizar_stock_documento(
            material_id,
            nueva_cantidad,
            tipo_movimiento="SALIDA",
            usuario="APP",
            observaciones=(
                "Retiro manual en "
                + inventario_seleccionado
            )
        )

        invalidar_cache()

        actualizar_todo(
            forzar=True
        )

        messagebox.showinfo(
            "Retiro realizado",
            (
                f"Material: {nombre}\n\n"
                f"Inventario: "
                f"{inventario_seleccionado}\n\n"
                f"Stock anterior: "
                f"{formatear_numero(stock_actual)} "
                f"{unidad}\n"
                f"Cantidad retirada: "
                f"{formatear_numero(cantidad)} "
                f"{unidad}\n"
                f"Stock nuevo: "
                f"{formatear_numero(nueva_cantidad)} "
                f"{unidad}"
            ),
            parent=root
        )

    except Exception as error:

        traceback.print_exc()

        messagebox.showerror(
            "Error",
            (
                "No se pudo retirar stock:\n\n"
                f"{error}"
            ),
            parent=root
        )


# ============================================================
# NUEVO MATERIAL
# ============================================================

def nuevo_material():

    ventana = tk.Toplevel(root)

    ventana.title(
        "Nuevo material"
    )

    ventana.geometry(
        "520x520"
    )

    ventana.transient(root)
    ventana.grab_set()

    campos = [
        ("Código", "codigo"),
        ("Material", "material"),
        ("Cantidad", "cantidad"),
        ("Unidad", "unidad"),
        ("Categoría", "categoria"),
        ("Ubicación", "ubicacion"),
        ("Observaciones", "observaciones"),
    ]

    entradas = {}

    frame = ttk.Frame(
        ventana,
        padding=20
    )

    frame.pack(
        fill="both",
        expand=True
    )

    for fila, (texto, clave) in enumerate(campos):

        ttk.Label(
            frame,
            text=texto
        ).grid(
            row=fila,
            column=0,
            sticky="w",
            padx=5,
            pady=7
        )

        entrada = ttk.Entry(
            frame
        )

        entrada.grid(
            row=fila,
            column=1,
            sticky="ew",
            padx=5,
            pady=7
        )

        entradas[clave] = entrada

    frame.columnconfigure(
        1,
        weight=1
    )

    def guardar():

        nombre = (
            entradas["material"]
            .get()
            .strip()
        )

        if not nombre:

            messagebox.showwarning(
                "Datos",
                "El nombre del material es obligatorio.",
                parent=ventana
            )

            return

        try:

            cantidad = float(
                entradas["cantidad"]
                .get()
                .strip()
                .replace(",", ".")
                or 0
            )

        except ValueError:

            messagebox.showerror(
                "Cantidad",
                "La cantidad debe ser numérica.",
                parent=ventana
            )

            return

        if cantidad < 0:

            messagebox.showerror(
                "Cantidad",
                "La cantidad no puede ser negativa.",
                parent=ventana
            )

            return

        codigo = (
            entradas["codigo"]
            .get()
            .strip()
            or None
        )

        unidad = (
            entradas["unidad"]
            .get()
            .strip()
            or None
        )

        categoria = (
            entradas["categoria"]
            .get()
            .strip()
            or None
        )

        ubicacion = (
            entradas["ubicacion"]
            .get()
            .strip()
            or None
        )

        observaciones = (
            entradas["observaciones"]
            .get()
            .strip()
            or None
        )

        try:

            existente = buscar_material(
                codigo,
                nombre,
                categoria,
                ubicacion
            )

            if existente:

                messagebox.showwarning(
                    "Material existente",
                    (
                        "Ese material ya existe "
                        "en la base de datos."
                    ),
                    parent=ventana
                )

                return

            nuevo = crear_material(
                codigo,
                nombre,
                0,
                unidad,
                categoria,
                ubicacion,
                observaciones,
                (
                    None
                    if es_inventario_general()
                    else inventario_seleccionado
                )
            )

            if not nuevo:

                raise Exception(
                    "No se pudo crear el material."
                )

            if es_inventario_general():

                if cantidad > 0:

                    agregar_ajuste_stock(
                        material_id=nuevo["id"],
                        delta=cantidad,
                        usuario="APP",
                        observaciones=(
                            "Stock inicial "
                            "de material nuevo"
                        )
                    )

            else:

                documento_id = (
                    obtener_documento_id_actual()
                )

                if not documento_id:

                    raise Exception(
                        "No se encontró "
                        "el documento seleccionado."
                    )

                item = crear_item_documento(
                    documento_id,
                    nuevo["id"],
                    cantidad,
                    unidad=unidad,
                    codigo=codigo,
                    material=nombre,
                    categoria=categoria,
                    ubicacion=ubicacion,
                    observaciones=observaciones
                )

                if not item:

                    raise Exception(
                        "No se pudo crear "
                        "el item del inventario."
                    )

            invalidar_cache()

            ventana.destroy()

            actualizar_todo(
                forzar=True
            )

            messagebox.showinfo(
                "Material creado",
                (
                    "Se agregó correctamente:\n\n"
                    f"{nombre}"
                ),
                parent=root
            )

        except Exception as error:

            traceback.print_exc()

            messagebox.showerror(
                "Error",
                (
                    "No se pudo crear el material:\n\n"
                    f"{error}"
                ),
                parent=ventana
            )

    ttk.Button(
        frame,
        text="Guardar",
        command=guardar
    ).grid(
        row=len(campos),
        column=0,
        columnspan=2,
        pady=20
    )


# ============================================================
# EDITAR MATERIAL
# ============================================================

def editar_material():

    material = obtener_material_seleccionado()

    if not material:
        return

    ventana = tk.Toplevel(root)

    ventana.title(
        "Editar material"
    )

    ventana.geometry(
        "520x500"
    )

    ventana.transient(root)
    ventana.grab_set()

    campos = [
        ("Código", "codigo"),
        ("Material", "material"),
        ("Unidad", "unidad"),
        ("Categoría", "categoria"),
        ("Ubicación", "ubicacion"),
        ("Observaciones", "observaciones"),
    ]

    entradas = {}

    frame = ttk.Frame(
        ventana,
        padding=20
    )

    frame.pack(
        fill="both",
        expand=True
    )

    for fila, (texto, clave) in enumerate(campos):

        ttk.Label(
            frame,
            text=texto
        ).grid(
            row=fila,
            column=0,
            sticky="w",
            padx=5,
            pady=7
        )

        entrada = ttk.Entry(
            frame
        )

        entrada.grid(
            row=fila,
            column=1,
            sticky="ew",
            padx=5,
            pady=7
        )

        entrada.insert(
            0,
            material.get(clave) or ""
        )

        entradas[clave] = entrada

    frame.columnconfigure(
        1,
        weight=1
    )

    def guardar():

        nombre = (
            entradas["material"]
            .get()
            .strip()
        )

        if not nombre:

            messagebox.showwarning(
                "Datos",
                "El material no puede quedar vacío.",
                parent=ventana
            )

            return

        try:

            actualizado = actualizar_material(
                material["id"],
                codigo=(
                    entradas["codigo"]
                    .get()
                    .strip()
                    or None
                ),
                material=nombre,
                unidad=(
                    entradas["unidad"]
                    .get()
                    .strip()
                    or None
                ),
                categoria=(
                    entradas["categoria"]
                    .get()
                    .strip()
                    or None
                ),
                ubicacion=(
                    entradas["ubicacion"]
                    .get()
                    .strip()
                    or None
                ),
                observaciones=(
                    entradas["observaciones"]
                    .get()
                    .strip()
                    or None
                )
            )

            if not actualizado:

                raise Exception(
                    "No se pudo actualizar."
                )

            invalidar_cache()

            ventana.destroy()

            actualizar_todo(
                forzar=True
            )

        except Exception as error:

            traceback.print_exc()

            messagebox.showerror(
                "Error",
                (
                    "No se pudo modificar:\n\n"
                    f"{error}"
                ),
                parent=ventana
            )

    ttk.Button(
        frame,
        text="Guardar cambios",
        command=guardar
    ).grid(
        row=len(campos),
        column=0,
        columnspan=2,
        pady=20
    )


# ============================================================
# HISTORIAL
# ============================================================

def actualizar_movimientos():

    if tabla_movimientos is None:
        return

    for item in tabla_movimientos.get_children():

        tabla_movimientos.delete(item)

    movimientos = obtener_movimientos_cache()
    materiales = obtener_materiales_cache()

    materiales_por_id = {}

    for material in materiales:

        material_id = material.get("id")

        if material_id is not None:

            materiales_por_id[
                material_id
            ] = material

    for movimiento in movimientos:

        material_id = movimiento.get(
            "material_id"
        )

        material = materiales_por_id.get(
            material_id
        )

        if material:

            nombre_material = (
                material.get(
                    "material"
                ) or ""
            )

            codigo = (
                material.get(
                    "codigo"
                ) or ""
            )

        else:

            nombre_material = (
                "Material eliminado"
            )

            codigo = ""

        tabla_movimientos.insert(
            "",
            "end",
            values=(
                movimiento.get(
                    "fecha"
                ) or "",
                codigo,
                nombre_material,
                movimiento.get(
                    "tipo"
                ) or "",
                formatear_numero(
                    movimiento.get(
                        "cantidad",
                        0
                    )
                ),
                formatear_numero(
                    movimiento.get(
                        "stock_anterior",
                        0
                    )
                ),
                formatear_numero(
                    movimiento.get(
                        "stock_nuevo",
                        0
                    )
                ),
                movimiento.get(
                    "usuario"
                ) or "",
                movimiento.get(
                    "archivo_origen"
                ) or "",
                movimiento.get(
                    "observaciones"
                ) or "",
            )
        )


# ============================================================
# ACTUALIZACIÓN GENERAL
# ============================================================

def actualizar_todo(forzar=False):

    global actualizacion_en_curso
    global firma_datos_sincronizados

    with lock_actualizacion:

        if actualizacion_en_curso:

            if forzar and root:

                root.after(
                    500,
                    lambda: actualizar_todo(
                        forzar=True
                    )
                )

            return

        actualizacion_en_curso = True

    def trabajo():

        global actualizacion_en_curso
        global firma_datos_sincronizados

        try:

            if lbl_progreso:

                root.after(
                    0,
                    lambda: lbl_progreso.config(
                        text="⏳ Actualizando..."
                    )
                )

            (
                materiales,
                documentos,
                movimientos
            ) = cargar_datos_supabase()

            firma_datos_sincronizados = (
                generar_firma_sincronizacion(
                    materiales,
                    documentos,
                    movimientos
                )
            )

            def refrescar_interfaz():

                global actualizacion_en_curso

                try:

                    cargar_selector(
                        documentos
                    )

                    actualizar_tabla()
                    actualizar_movimientos()

                    if lbl_estado:

                        lbl_estado.config(
                            text="🟢 Sincronizado"
                        )

                    if lbl_progreso:

                        lbl_progreso.config(
                            text="✓ Actualizado"
                        )

                finally:

                    with lock_actualizacion:

                        actualizacion_en_curso = False

            root.after(
                0,
                refrescar_interfaz
            )

        except Exception as error:

            print(
                "Error actualizando:",
                error
            )

            traceback.print_exc()

            def error_interfaz():

                global actualizacion_en_curso

                with lock_actualizacion:

                    actualizacion_en_curso = False

                if lbl_estado:

                    lbl_estado.config(
                        text="🔴 Sin conexión"
                    )

                if lbl_progreso:

                    lbl_progreso.config(
                        text="Error al actualizar"
                    )

            root.after(
                0,
                error_interfaz
            )

    threading.Thread(
        target=trabajo,
        daemon=True
    ).start()


# ============================================================
# SINCRONIZACIÓN AUTOMÁTICA
# ============================================================

def sincronizar_automaticamente():

    global sincronizacion_en_curso
    global firma_datos_sincronizados

    if root is None:
        return

    if importacion_en_curso:
        return

    if pausar_sincronizacion:
        return

    with lock_sincronizacion:

        if sincronizacion_en_curso:
            return

        sincronizacion_en_curso = True

    def trabajo():

        global sincronizacion_en_curso
        global firma_datos_sincronizados
        global cache_materiales
        global cache_documentos
        global cache_movimientos

        try:

            if importacion_en_curso:
                return

            if pausar_sincronizacion:
                return

            materiales = (
                obtener_inventario_general()
            )

            documentos = (
                obtener_documentos()
            )

            movimientos = (
                obtener_movimientos(100)
            )

            materiales = materiales or []
            documentos = documentos or []
            movimientos = movimientos or []

            nueva_firma = (
                generar_firma_sincronizacion(
                    materiales,
                    documentos,
                    movimientos
                )
            )

            cambio_detectado = (
                firma_datos_sincronizados is None
                or nueva_firma
                != firma_datos_sincronizados
            )

            firma_datos_sincronizados = nueva_firma

            if not cambio_detectado:

                root.after(
                    0,
                    lambda: actualizar_estado_sync(
                        True,
                        False
                    )
                )

                return

            with cache_lock:

                cache_materiales = materiales
                cache_documentos = documentos
                cache_movimientos = movimientos

            print(
                "🔄 Cambio detectado en Supabase."
            )

            root.after(
                0,
                actualizar_interfaz_por_sincronizacion
            )

        except Exception as error:

            print(
                "❌ Error en sincronización automática:",
                error
            )

            traceback.print_exc()

            if not importacion_en_curso:

                root.after(
                    0,
                    lambda: actualizar_estado_sync(
                        False,
                        False
                    )
                )

        finally:

            with lock_sincronizacion:

                sincronizacion_en_curso = False

    threading.Thread(
        target=trabajo,
        daemon=True
    ).start()


# ============================================================
# ACTUALIZAR INTERFAZ
# ============================================================

def actualizar_interfaz_por_sincronizacion():

    try:

        cargar_selector(
            obtener_documentos_cache()
        )

        actualizar_tabla()
        actualizar_movimientos()

        if lbl_estado:

            lbl_estado.config(
                text="🟢 Sincronizado"
            )

        if lbl_progreso:

            lbl_progreso.config(
                text="🔄 Cambio detectado — sincronizado"
            )

    except Exception as error:

        print(
            "Error actualizando interfaz:",
            error
        )

        traceback.print_exc()


def actualizar_estado_sync(
    conectado,
    hubo_cambio
):

    if not root:
        return

    if lbl_estado:

        if conectado:

            lbl_estado.config(
                text="🟢 Sincronizado"
            )

        else:

            lbl_estado.config(
                text="🔴 Sin conexión"
            )

    if hubo_cambio and lbl_progreso:

        lbl_progreso.config(
            text="🔄 Datos sincronizados"
        )


# ============================================================
# MONITOR SUPABASE
# ============================================================

def monitor_sincronizacion():

    print(
        "🔄 Monitor de sincronización iniciado."
    )

    while True:

        try:

            sincronizar_automaticamente()

        except Exception as error:

            print(
                "Error en monitor de sincronización:",
                error
            )

            traceback.print_exc()

        time.sleep(
            INTERVALO_SINCRONIZACION / 1000
        )


# ============================================================
# IMPORTACIÓN WORD
# ============================================================

def ejecutar_importacion_word(
    reescaneo_completo=False
):

    global importacion_en_curso
    global pausar_sincronizacion
    global firma_datos_sincronizados

    with lock_importacion:

        if importacion_en_curso:

            print(
                "⚠️ Ya hay una importación Word en curso."
            )

            return

        importacion_en_curso = True

    pausar_sincronizacion = True

    print(
        "🔒 Sincronización automática pausada."
    )

    if lbl_progreso:

        lbl_progreso.config(
            text="⏳ Importando documentos Word..."
        )

    if lbl_estado:

        lbl_estado.config(
            text="🟡 Importando Word..."
        )

    def trabajo():

        global importacion_en_curso
        global pausar_sincronizacion
        global firma_datos_sincronizados
        global cache_materiales
        global cache_documentos
        global cache_movimientos

        resultado = None

        try:

            print()
            print(
                "=" * 70
            )

            if reescaneo_completo:

                print(
                    "INICIANDO REESCANEO COMPLETO..."
                )

                resultado = (
                    importar_word.importar_todos(
                        reescaneo_completo=True
                    )
                )

            else:

                print(
                    "INICIANDO IMPORTACIÓN WORD..."
                )

                resultado = (
                    importar_word.importar_todos(
                        reescaneo_completo=False
                    )
                )

            print(
                "RESULTADO:",
                resultado
            )

            invalidar_cache()

            try:

                materiales = (
                    obtener_inventario_general()
                )

                documentos = (
                    obtener_documentos()
                )

                movimientos = (
                    obtener_movimientos(100)
                )

                materiales = materiales or []
                documentos = documentos or []
                movimientos = movimientos or []

                with cache_lock:

                    cache_materiales = materiales
                    cache_documentos = documentos
                    cache_movimientos = movimientos

                firma_datos_sincronizados = (
                    generar_firma_sincronizacion(
                        materiales,
                        documentos,
                        movimientos
                    )
                )

            except Exception as error_cache:

                print(
                    "⚠️ No se pudo recargar la cache:",
                    error_cache
                )

                traceback.print_exc()

        except Exception as error:

            print(
                "ERROR IMPORTANDO WORD:",
                error
            )

            traceback.print_exc()

            root.after(
                0,
                lambda error=error:
                messagebox.showerror(
                    "Error",
                    (
                        "Ocurrió un error durante "
                        "la importación:\n\n"
                        f"{error}"
                    ),
                    parent=root
                )
            )

        finally:

            pausar_sincronizacion = False
            importacion_en_curso = False

            print(
                "🔓 Sincronización automática reanudada."
            )

            root.after(
                0,
                actualizar_interfaz_por_sincronizacion
            )

            if resultado is not None:

                root.after(
                    150,
                    lambda resultado=resultado:
                    mostrar_resultado_importacion(
                        resultado
                    )
                )

            if lbl_estado:

                root.after(
                    0,
                    lambda: lbl_estado.config(
                        text="🟢 Sincronizado"
                    )
                )

            if lbl_progreso:

                root.after(
                    0,
                    lambda: lbl_progreso.config(
                        text="✓ Word sincronizado"
                    )
                )

    threading.Thread(
        target=trabajo,
        daemon=True
    ).start()


# ============================================================
# RESULTADO IMPORTACIÓN
# ============================================================

def construir_mensaje_importacion(
    resultado
):

    if not isinstance(resultado, dict):
        return str(resultado)

    partes = []

    campos = [
        ("nuevos", "Nuevos"),
        ("modificados", "Modificados"),
        ("actualizados", "Actualizados"),
        ("sin_cambios", "Sin cambios"),
        ("eliminados", "Eliminados"),
        ("vacios", "Vacíos"),
        ("filas", "Filas procesadas"),
        ("items", "Items"),
        ("errores", "Errores"),
    ]

    for clave, nombre in campos:

        if clave in resultado:

            partes.append(
                f"{nombre}: "
                f"{resultado.get(clave, 0)}"
            )

    if partes:

        return "\n".join(partes)

    return str(resultado)


def mostrar_resultado_importacion(
    resultado
):

    if lbl_progreso:

        lbl_progreso.config(
            text="✓ Word sincronizado"
        )

    messagebox.showinfo(
        "Importación finalizada",
        construir_mensaje_importacion(
            resultado
        ),
        parent=root
    )


# ============================================================
# IMPORTACIÓN MANUAL
# ============================================================

def importar_word_manual():

    if importacion_en_curso:

        messagebox.showinfo(
            "Importación",
            "Ya hay una importación en curso.",
            parent=root
        )

        return

    ejecutar_importacion_word(
        reescaneo_completo=False
    )


# ============================================================
# REESCANEO COMPLETO
# ============================================================

def reescaneo_completo():

    if importacion_en_curso:

        messagebox.showinfo(
            "Importación",
            "Ya hay una importación en curso.",
            parent=root
        )

        return

    respuesta = messagebox.askyesno(
        "Reescaneo completo",
        (
            "Se van a revisar nuevamente "
            "todos los archivos Word.\n\n"
            "Esto puede tardar unos minutos.\n\n"
            "¿Continuar?"
        ),
        parent=root
    )

    if not respuesta:
        return

    ejecutar_importacion_word(
        reescaneo_completo=True
    )


# ============================================================
# MONITOR ARCHIVOS WORD
# ============================================================

def obtener_estado_archivos_word():

    estado = {}

    CARPETA_DOCUMENTOS.mkdir(
        exist_ok=True
    )

    for ruta in CARPETA_DOCUMENTOS.glob(
        "*.docx"
    ):

        if ruta.name.startswith("~$"):
            continue

        try:

            estado[
                str(
                    ruta.resolve()
                )
            ] = ruta.stat().st_mtime

        except Exception:

            continue

    return estado


def monitor_word():

    global estado_archivos_word

    print(
        "📄 Monitor de Word iniciado."
    )

    while True:

        try:

            nuevo_estado = (
                obtener_estado_archivos_word()
            )

            if (
                nuevo_estado
                != estado_archivos_word
            ):

                print()
                print(
                    "📄 Cambio detectado en documentos Word."
                )

                estado_archivos_word = (
                    nuevo_estado
                )

                if not importacion_en_curso:

                    ejecutar_importacion_word(
                        reescaneo_completo=False
                    )

        except Exception as error:

            print(
                "Error en monitor Word:",
                error
            )

            traceback.print_exc()

        time.sleep(
            INTERVALO_MONITOR / 1000
        )


# ============================================================
# INTERFAZ
# ============================================================

def crear_interfaz():

    global root

    global selector_inventario
    global tabla
    global tabla_movimientos
    global entrada_busqueda

    global lbl_total_materiales
    global lbl_con_stock
    global lbl_sin_stock
    global lbl_cantidad_total

    global lbl_estado
    global lbl_progreso

    global estado_archivos_word

    root = tk.Tk()

    root.title(
        NOMBRE_APP
    )

    root.geometry(
        "1500x900"
    )

    root.minsize(
        1100,
        700
    )

    root.configure(
        bg=COLOR_FONDO
    )

    # ========================================================
    # ESTILOS
    # ========================================================

    estilo = ttk.Style()

    try:

        estilo.theme_use(
            "clam"
        )

    except Exception:
        pass

    estilo.configure(
        ".",
        font=(
            "Segoe UI",
            10
        )
    )

    estilo.configure(
        "TFrame",
        background=COLOR_FONDO
    )

    estilo.configure(
        "TLabel",
        background=COLOR_FONDO,
        foreground=COLOR_TEXTO
    )

    estilo.configure(
        "Title.TLabel",
        background=COLOR_AZUL_OSCURO,
        foreground="white",
        font=(
            "Segoe UI",
            18,
            "bold"
        )
    )

    estilo.configure(
        "Subtitle.TLabel",
        background=COLOR_AZUL_OSCURO,
        foreground="#dce8f1",
        font=(
            "Segoe UI",
            9
        )
    )

    estilo.configure(
        "TButton",
        padding=(
            12,
            7
        ),
        font=(
            "Segoe UI",
            9,
            "bold"
        )
    )

    estilo.configure(
        "TCombobox",
        padding=5
    )

    estilo.configure(
        "Treeview",
        background="white",
        foreground=COLOR_TEXTO,
        fieldbackground="white",
        rowheight=30,
        font=(
            "Segoe UI",
            10
        ),
        borderwidth=0
    )

    estilo.configure(
        "Treeview.Heading",
        background=COLOR_AZUL_OSCURO,
        foreground="white",
        font=(
            "Segoe UI",
            10,
            "bold"
        ),
        padding=7
    )

    estilo.map(
        "Treeview",
        background=[
            (
                "selected",
                COLOR_AZUL
            )
        ],
        foreground=[
            (
                "selected",
                "white"
            )
        ]
    )

    # ========================================================
    # CABECERA
    # ========================================================

    frame_cabecera = tk.Frame(
        root,
        bg=COLOR_AZUL_OSCURO,
        height=75
    )

    frame_cabecera.pack(
        fill="x"
    )

    frame_cabecera.pack_propagate(
        False
    )

    frame_titulo = tk.Frame(
        frame_cabecera,
        bg=COLOR_AZUL_OSCURO
    )

    frame_titulo.pack(
        side="left",
        padx=20
    )

    ttk.Label(
        frame_titulo,
        text="⚓ INVENTARIO MATERIAL NAVAL",
        style="Title.TLabel"
    ).pack(
        anchor="w"
    )

    ttk.Label(
        frame_titulo,
        text="Sistema de gestión y control de material",
        style="Subtitle.TLabel"
    ).pack(
        anchor="w"
    )

    frame_estado = tk.Frame(
        frame_cabecera,
        bg=COLOR_AZUL_OSCURO
    )

    frame_estado.pack(
        side="right",
        padx=20
    )

    lbl_estado = tk.Label(
        frame_estado,
        text="🟡 Conectando...",
        bg=COLOR_AZUL_OSCURO,
        fg="white",
        font=(
            "Segoe UI",
            10,
            "bold"
        )
    )

    lbl_estado.pack(
        side="right"
    )

    # ========================================================
    # SELECTOR
    # ========================================================

    frame_selector = ttk.Frame(
        root,
        padding=(
            15,
            10
        )
    )

    frame_selector.pack(
        fill="x"
    )

    ttk.Label(
        frame_selector,
        text="Inventario:",
        font=(
            "Segoe UI",
            10,
            "bold"
        )
    ).pack(
        side="left",
        padx=(
            0,
            8
        )
    )

    selector_inventario = ttk.Combobox(
        frame_selector,
        state="readonly",
        width=55
    )

    selector_inventario.pack(
        side="left"
    )

    selector_inventario.bind(
        "<<ComboboxSelected>>",
        cambiar_inventario
    )

    # ========================================================
    # ESTADÍSTICAS
    # ========================================================

    frame_stats = tk.Frame(
        root,
        bg=COLOR_AZUL_CLARO,
        highlightbackground=COLOR_BORDE,
        highlightthickness=1
    )

    frame_stats.pack(
        fill="x",
        padx=15,
        pady=(
            0,
            7
        )
    )

    def crear_stat(texto):

        return tk.Label(
            frame_stats,
            text=texto,
            bg=COLOR_AZUL_CLARO,
            fg=COLOR_TEXTO,
            font=(
                "Segoe UI",
                10,
                "bold"
            ),
            padx=15,
            pady=8
        )

    lbl_total_materiales = crear_stat(
        "Materiales: 0"
    )

    lbl_total_materiales.pack(
        side="left"
    )

    lbl_con_stock = crear_stat(
        "Con stock: 0"
    )

    lbl_con_stock.pack(
        side="left"
    )

    lbl_sin_stock = crear_stat(
        "Sin stock: 0"
    )

    lbl_sin_stock.pack(
        side="left"
    )

    lbl_cantidad_total = crear_stat(
        "Cantidad total: 0"
    )

    lbl_cantidad_total.pack(
        side="left"
    )

    # ========================================================
    # BÚSQUEDA
    # ========================================================

    frame_busqueda = ttk.Frame(
        root,
        padding=(
            15,
            5
        )
    )

    frame_busqueda.pack(
        fill="x"
    )

    ttk.Label(
        frame_busqueda,
        text="Buscar:",
        font=(
            "Segoe UI",
            10,
            "bold"
        )
    ).pack(
        side="left",
        padx=(
            0,
            7
        )
    )

    entrada_busqueda = ttk.Entry(
        frame_busqueda
    )

    entrada_busqueda.pack(
        side="left",
        fill="x",
        expand=True
    )

    entrada_busqueda.bind(
        "<KeyRelease>",
        buscar
    )

    # ========================================================
    # BOTONES
    # ========================================================

    frame_botones = ttk.Frame(
        root,
        padding=(
            15,
            5
        )
    )

    frame_botones.pack(
        fill="x"
    )

    ttk.Button(
        frame_botones,
        text="➕ Nuevo",
        command=nuevo_material
    ).pack(
        side="left",
        padx=3
    )

    ttk.Button(
        frame_botones,
        text="✏️ Editar",
        command=editar_material
    ).pack(
        side="left",
        padx=3
    )

    ttk.Button(
        frame_botones,
        text="📥 Agregar",
        command=agregar_stock
    ).pack(
        side="left",
        padx=3
    )

    ttk.Button(
        frame_botones,
        text="📤 Retirar",
        command=retirar_stock
    ).pack(
        side="left",
        padx=3
    )

    ttk.Button(
        frame_botones,
        text="🔄 Actualizar",
        command=lambda: actualizar_todo(
            forzar=True
        )
    ).pack(
        side="left",
        padx=3
    )

    ttk.Button(
        frame_botones,
        text="📄 Importar Word",
        command=importar_word_manual
    ).pack(
        side="right",
        padx=3
    )

    ttk.Button(
        frame_botones,
        text="🧹 Reescaneo completo",
        command=reescaneo_completo
    ).pack(
        side="right",
        padx=3
    )

    # ========================================================
    # ESTADO
    # ========================================================

    lbl_progreso = ttk.Label(
        root,
        text="Listo",
        foreground=COLOR_TEXTO_SECUNDARIO
    )

    lbl_progreso.pack(
        anchor="w",
        padx=18,
        pady=(
            2,
            2
        )
    )

    # ========================================================
    # TABLA PRINCIPAL
    # ========================================================

    frame_tabla = ttk.Frame(
        root,
        padding=(
            15,
            3
        )
    )

    frame_tabla.pack(
        fill="both",
        expand=True
    )

    columnas = (
        "codigo",
        "material",
        "cantidad",
        "unidad",
        "categoria",
        "ubicacion",
        "observaciones",
        "estado",
    )

    tabla = ttk.Treeview(
        frame_tabla,
        columns=columnas,
        show="headings",
        selectmode="browse"
    )

    encabezados = {
        "codigo": "Código",
        "material": "Material",
        "cantidad": "Cantidad",
        "unidad": "Unidad",
        "categoria": "Categoría",
        "ubicacion": "Ubicación",
        "observaciones": "Observaciones",
        "estado": "Estado",
    }

    anchos = {
        "codigo": 150,
        "material": 300,
        "cantidad": 100,
        "unidad": 100,
        "categoria": 150,
        "ubicacion": 180,
        "observaciones": 300,
        "estado": 150,
    }

    for columna in columnas:

        tabla.heading(
            columna,
            text=encabezados[columna]
        )

        tabla.column(
            columna,
            width=anchos[columna],
            minwidth=70
        )

    scroll_vertical = ttk.Scrollbar(
        frame_tabla,
        orient="vertical",
        command=tabla.yview
    )

    scroll_horizontal = ttk.Scrollbar(
        frame_tabla,
        orient="horizontal",
        command=tabla.xview
    )

    tabla.configure(
        yscrollcommand=scroll_vertical.set,
        xscrollcommand=scroll_horizontal.set
    )

    tabla.grid(
        row=0,
        column=0,
        sticky="nsew"
    )

    scroll_vertical.grid(
        row=0,
        column=1,
        sticky="ns"
    )

    scroll_horizontal.grid(
        row=1,
        column=0,
        sticky="ew"
    )

    frame_tabla.rowconfigure(
        0,
        weight=1
    )

    frame_tabla.columnconfigure(
        0,
        weight=1
    )

    tabla.tag_configure(
        "stock",
        background=COLOR_STOCK_FONDO
    )

    tabla.tag_configure(
        "sin_stock",
        background=COLOR_SIN_STOCK_FONDO
    )

    # ========================================================
    # HISTORIAL
    # ========================================================

    ttk.Label(
        root,
        text="Últimos movimientos",
        font=(
            "Segoe UI",
            12,
            "bold"
        )
    ).pack(
        anchor="w",
        padx=15,
        pady=(
            8,
            3
        )
    )

    frame_movimientos = ttk.Frame(
        root,
        height=180
    )

    frame_movimientos.pack(
        fill="x",
        padx=15,
        pady=(
            0,
            10
        )
    )

    frame_movimientos.pack_propagate(
        False
    )

    columnas_mov = (
        "fecha",
        "codigo",
        "material",
        "tipo",
        "cantidad",
        "anterior",
        "nuevo",
        "usuario",
        "archivo",
        "observaciones",
    )

    tabla_movimientos = ttk.Treeview(
        frame_movimientos,
        columns=columnas_mov,
        show="headings"
    )

    nombres_mov = {
        "fecha": "Fecha",
        "codigo": "Código",
        "material": "Material",
        "tipo": "Tipo",
        "cantidad": "Cantidad",
        "anterior": "Stock anterior",
        "nuevo": "Stock nuevo",
        "usuario": "Usuario",
        "archivo": "Archivo",
        "observaciones": "Observaciones",
    }

    anchos_mov = {
        "fecha": 160,
        "codigo": 130,
        "material": 250,
        "tipo": 100,
        "cantidad": 100,
        "anterior": 110,
        "nuevo": 110,
        "usuario": 100,
        "archivo": 250,
        "observaciones": 250,
    }

    for columna in columnas_mov:

        tabla_movimientos.heading(
            columna,
            text=nombres_mov[columna]
        )

        tabla_movimientos.column(
            columna,
            width=anchos_mov[columna],
            minwidth=80
        )

    scroll_mov_v = ttk.Scrollbar(
        frame_movimientos,
        orient="vertical",
        command=tabla_movimientos.yview
    )

    scroll_mov_h = ttk.Scrollbar(
        frame_movimientos,
        orient="horizontal",
        command=tabla_movimientos.xview
    )

    tabla_movimientos.configure(
        yscrollcommand=scroll_mov_v.set,
        xscrollcommand=scroll_mov_h.set
    )

    tabla_movimientos.grid(
        row=0,
        column=0,
        sticky="nsew"
    )

    scroll_mov_v.grid(
        row=0,
        column=1,
        sticky="ns"
    )

    scroll_mov_h.grid(
        row=1,
        column=0,
        sticky="ew"
    )

    frame_movimientos.rowconfigure(
        0,
        weight=1
    )

    frame_movimientos.columnconfigure(
        0,
        weight=1
    )

    # ========================================================
    # INICIALIZACIÓN
    # ========================================================

    def iniciar():

        try:

            conectado = probar_conexion()

            def actualizar_estado():

                if conectado:

                    lbl_estado.config(
                        text="🟢 Conectado"
                    )

                else:

                    lbl_estado.config(
                        text="🔴 Sin conexión"
                    )

            root.after(
                0,
                actualizar_estado
            )

            actualizar_todo(
                forzar=True
            )

        except Exception as error:

            print(
                "Error inicializando:",
                error
            )

            traceback.print_exc()

            root.after(
                0,
                lambda: lbl_estado.config(
                    text="🔴 Sin conexión"
                )
            )

    threading.Thread(
        target=iniciar,
        daemon=True
    ).start()

    # ========================================================
    # MONITOR WORD
    # ========================================================

    estado_archivos_word = (
        obtener_estado_archivos_word()
    )

    threading.Thread(
        target=monitor_word,
        daemon=True
    ).start()

    # ========================================================
    # MONITOR SUPABASE
    # ========================================================

    threading.Thread(
        target=monitor_sincronizacion,
        daemon=True
    ).start()

    # ========================================================
    # IMPORTACIÓN INICIAL
    # ========================================================

    root.after(
        1500,
        lambda: ejecutar_importacion_word(
            reescaneo_completo=False
        )
    )

    # ========================================================
    # LOOP PRINCIPAL
    # ========================================================

    root.mainloop()


# ============================================================
# EJECUCIÓN
# ============================================================

if __name__ == "__main__":

    crear_interfaz()

