import sys
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog, filedialog
from pathlib import Path
from copy import deepcopy
from datetime import datetime
import threading
import time
import queue
import traceback
from word_document_utils import _agregar_fila_word, _eliminar_fila_word

from supabase_db import (
    probar_conexion,
    obtener_materiales,
    obtener_material,
    crear_material,
    actualizar_material,
    actualizar_cantidad_documento_item,
    obtener_movimientos,
    obtener_documentos,
    obtener_items_documento,
    crear_item_documento,
    buscar_material,
    eliminar_material_del_documento,
)
import importar_word
import reportes
from relacion_transito import RelacionTransitoError, generar_relacion_transito
from realtime_supabase import iniciar_realtime
from ui_relacion_transito import abrir_selector_relacion_transito
from ui_inventario import construir_pantalla_inventario as construir_pantalla_inventario_ui

# ============================================================
# CONFIGURACIÓN
# ============================================================

CARPETA_DOCUMENTOS = Path(__file__).resolve().parent / "documentos"

NOMBRE_APP = "INVENTARIO MATERIAL NAVAL"

COLOR_STOCK = "🟢 HAY STOCK"
COLOR_SIN_STOCK = "🔴 SIN STOCK"

INTERVALO_MONITOR = 5000
INTERVALO_SINCRONIZACION = 3000

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

# Usuario autenticado (configurado por inicio.py)
USUARIO_ACTUAL = None
USUARIO_NOMBRE = "Usuario"
USUARIO_ROL = "consulta"


def ejecutar_en_ui(funcion, *args, **kwargs):
    """Encola una función para ejecutarla en el hilo principal de Tkinter."""
    cola_ui.put((funcion, args, kwargs))


def procesar_cola_ui():
    """Ejecuta callbacks de UI pendientes desde el hilo principal."""
    try:
        while True:
            funcion, args, kwargs = cola_ui.get_nowait()
            try:
                funcion(*args, **kwargs)
            except Exception:
                traceback.print_exc()
    except queue.Empty:
        pass
    if root is not None:
        try:
            root.after(50, procesar_cola_ui)
        except Exception:
            pass

cola_ui = queue.Queue()

tabla = None
tabla_movimientos = None
entrada_busqueda = None

lbl_total_materiales = None
lbl_con_stock = None
lbl_sin_stock = None
lbl_cantidad_total = None

lbl_estado = None
lbl_progreso = None

# Inventario seleccionado
inventario_seleccionado = None
inventario_seleccionado_id = None

marco_contenido = None
marco_selector = None

importacion_en_curso = False
lock_importacion = threading.Lock()

estado_archivos_word = {}

cache_materiales = []
cache_documentos = []
cache_movimientos = []

cache_lock = threading.Lock()

actualizacion_en_curso = False
lock_actualizacion = threading.Lock()

sincronizacion_en_curso = False
lock_sincronizacion = threading.Lock()

firma_datos_sincronizados = None

pausar_sincronizacion = False

# Realtime de Supabase
detener_realtime = lambda: None
realtime_refresh_pendiente = None

# Estado de la carga inicial de documentos/materiales.
datos_iniciales_cargados = False
error_carga_inicial = None


# ============================================================
# UTILIDADES
# ============================================================

def limpiar_texto(valor):
    return "" if valor is None else str(valor).strip()


def formatear_numero(valor):
    try:
        return f"{float(valor or 0):g}"
    except Exception:
        return str(valor or 0)


# ============================================================
# CACHE
# ============================================================

def invalidar_cache():
    global cache_materiales
    global cache_documentos
    global cache_movimientos

    with cache_lock:
        cache_materiales = []
        cache_documentos = []
        cache_movimientos = []


def cargar_datos_supabase():
    global cache_materiales
    global cache_documentos
    global cache_movimientos

    materiales = obtener_materiales() or []
    documentos = obtener_documentos() or []
    movimientos = obtener_movimientos(100) or []

    with cache_lock:
        cache_materiales = materiales
        cache_documentos = documentos
        cache_movimientos = movimientos

    return materiales, documentos, movimientos


def obtener_materiales_cache():
    with cache_lock:
        return list(cache_materiales)


def obtener_documentos_cache():
    with cache_lock:
        return list(cache_documentos)


def obtener_movimientos_cache():
    with cache_lock:
        return list(cache_movimientos)


def generar_firma_sincronizacion(
    materiales,
    documentos,
    movimientos
):
    return (
        tuple(
            (
                m.get("id"),
                m.get("codigo"),
                m.get("material"),
                m.get("unidad"),
                m.get("categoria"),
                m.get("ubicacion"),
                m.get("observaciones"),
            )
            for m in materiales
        ),
        tuple(
            (
                d.get("id"),
                d.get("nombre"),
                d.get("ruta"),
                d.get("fecha_modificacion_archivo"),
            )
            for d in documentos
        ),
        tuple(
            (
                m.get("id"),
                m.get("material_id"),
                m.get("tipo"),
                m.get("cantidad"),
                m.get("stock_anterior"),
                m.get("stock_nuevo"),
                m.get("fecha"),
                m.get("usuario"),
                m.get("archivo_origen"),
                m.get("observaciones"),
            )
            for m in movimientos
        ),
    )


# ============================================================
# ESTADÍSTICAS
# ============================================================

def actualizar_estadisticas(materiales):
    total = len(materiales)

    con = 0
    sin = 0
    total_cantidad = 0

    for m in materiales:
        try:
            cantidad = float(m.get("cantidad", 0) or 0)
        except Exception:
            cantidad = 0

        total_cantidad += cantidad

        if cantidad > 0:
            con += 1
        else:
            sin += 1

    if lbl_total_materiales:
        try:
            lbl_total_materiales.config(
                text=f"Materiales: {total}"
            )
        except Exception:
            pass

    if lbl_con_stock:
        try:
            lbl_con_stock.config(
                text=f"Con stock: {con}"
            )
        except Exception:
            pass

    if lbl_sin_stock:
        try:
            lbl_sin_stock.config(
                text=f"Sin stock: {sin}"
            )
        except Exception:
            pass

    if lbl_cantidad_total:
        try:
            lbl_cantidad_total.config(
                text=f"Cantidad total: {total_cantidad:g}"
            )
        except Exception:
            pass


# ============================================================
# DOCUMENTO / INVENTARIO ACTUAL
# ============================================================

def obtener_documento_actual():
    """
    Devuelve EXACTAMENTE el documento seleccionado.

    Primero busca por ID.
    El nombre queda solamente como respaldo.
    """

    global inventario_seleccionado_id
    global inventario_seleccionado

    documentos = obtener_documentos_cache()

    # --------------------------------------------------------
    # 1. BUSCAR POR ID
    # --------------------------------------------------------

    if inventario_seleccionado_id is not None:

        for documento in documentos:

            if documento.get("id") == inventario_seleccionado_id:
                return documento

    # --------------------------------------------------------
    # 2. RESPALDO: BUSCAR POR NOMBRE
    # --------------------------------------------------------

    if inventario_seleccionado:

        for documento in documentos:

            if documento.get("nombre") == inventario_seleccionado:
                return documento

    return None


def obtener_documento_id_actual():

    documento = obtener_documento_actual()

    if not documento:
        return None

    return documento.get("id")


# ============================================================
# MATERIALES DEL INVENTARIO ACTUAL
# ============================================================

def obtener_materiales_seleccionados():

    documento_id = obtener_documento_id_actual()

    if not documento_id:
        return []

    try:
        items = obtener_items_documento(documento_id) or []

    except Exception as error:
        print(
            "Error obteniendo documento_items:",
            error
        )
        return []

    materiales = obtener_materiales_cache()

    por_id = {
        m.get("id"): m
        for m in materiales
        if m.get("id") is not None
    }

    resultado = []

    for item in items:

        mid = item.get("material_id")

        material = por_id.get(mid)

        if not material:

            try:
                material = obtener_material(mid)

            except Exception:
                material = None

        if not material:
            continue

        copia = dict(material)

        copia["cantidad"] = item.get(
            "cantidad",
            0
        )

        copia["_documento_item_id"] = item.get("id")

        for campo in (
            "codigo",
            "material",
            "unidad",
            "categoria",
            "ubicacion",
            "observaciones",
        ):

            if item.get(campo) is not None:
                copia[campo] = item.get(campo)

        resultado.append(copia)

    return resultado


# ============================================================
# TABLA PRINCIPAL
# ============================================================

def actualizar_tabla():

    if tabla is None:
        return

    try:
        for x in tabla.get_children():
            tabla.delete(x)
    except Exception:
        return

    materiales = obtener_materiales_seleccionados()

    texto = ""

    if entrada_busqueda:

        try:
            texto = limpiar_texto(
                entrada_busqueda.get()
            ).lower()
        except Exception:
            texto = ""

    filtrados = []

    for m in materiales:

        if texto:

            combinado = " ".join(
                limpiar_texto(
                    m.get(c)
                )
                for c in (
                    "codigo",
                    "material",
                    "categoria",
                    "ubicacion",
                    "observaciones",
                )
            ).lower()

            if texto not in combinado:
                continue

        filtrados.append(m)

    for m in filtrados:

        try:
            cantidad = float(
                m.get("cantidad", 0) or 0
            )

        except Exception:
            cantidad = 0

        if cantidad > 0:
            estado = COLOR_STOCK
            tag = "stock"

        else:
            estado = COLOR_SIN_STOCK
            tag = "sin_stock"

        try:

            tabla.insert(
                "",
                "end",
                iid=str(m.get("id")),
                values=(
                    m.get("codigo") or "",
                    m.get("material") or "",
                    formatear_numero(cantidad),
                    m.get("unidad") or "",
                    m.get("categoria") or "",
                    m.get("ubicacion") or "",
                    m.get("observaciones") or "",
                    estado,
                ),
                tags=(tag,),
            )

        except Exception:
            pass

    actualizar_estadisticas(
        filtrados
    )


def buscar(event=None):
    actualizar_tabla()


# ============================================================
# MATERIAL SELECCIONADO
# ============================================================

def obtener_material_seleccionado():

    if tabla is None:
        return None

    try:
        sel = tabla.selection()

    except Exception:
        return None

    if not sel:

        messagebox.showwarning(
            "Selección",
            "Seleccioná un material primero.",
            parent=root,
        )

        return None

    try:
        mid = int(sel[0])

    except Exception:
        return None

    for m in obtener_materiales_seleccionados():

        if m.get("id") == mid:
            return m

    try:
        return obtener_material(mid)

    except Exception:
        return None


# ============================================================
# ITEM DEL DOCUMENTO
# ============================================================

def obtener_item_documento(material_id):

    documento_id = obtener_documento_id_actual()

    if not documento_id:
        return None

    try:
        items = obtener_items_documento(
            documento_id
        ) or []

    except Exception:
        return None

    for item in items:

        try:

            if int(
                item.get("material_id", -1)
            ) == int(material_id):

                return item

        except Exception:
            pass

    return None


# ============================================================
# ACTUALIZAR STOCK
# ============================================================

def actualizar_stock_documento(
    material_id,
    nueva_cantidad,
    tipo_movimiento=None,
    usuario="APP",
    observaciones=None,
):

    item = obtener_item_documento(
        material_id
    )

    if item is None:

        raise Exception(
            "El material no pertenece al inventario seleccionado."
        )

    return actualizar_cantidad_documento_item(
        item["id"],
        nueva_cantidad,
        usuario=usuario,
        archivo_origen=inventario_seleccionado,
        observaciones=observaciones,
        documento_id=obtener_documento_id_actual(),
    )


# ============================================================
# AGREGAR STOCK
# ============================================================

def agregar_stock():

    material = obtener_material_seleccionado()

    if not material:
        return

    mid = material["id"]

    nombre = material.get("material") or ""
    unidad = material.get("unidad") or ""
    codigo = material.get("codigo") or "-"

    item = obtener_item_documento(mid)

    if item is None:

        messagebox.showerror(
            "Error",
            "El material no pertenece al inventario seleccionado.",
            parent=root,
        )

        return

    stock = float(
        item.get("cantidad", 0) or 0
    )

    cantidad = simpledialog.askfloat(
        "Agregar stock",
        f"Inventario: {inventario_seleccionado}\n"
        f"Material: {nombre}\n"
        f"Código: {codigo}\n"
        f"Stock actual: {formatear_numero(stock)} {unidad}\n\n"
        f"Cantidad a agregar:",
        minvalue=0.0001,
        parent=root,
    )

    if cantidad is None or cantidad <= 0:
        return

    try:

        nuevo = actualizar_stock_documento(
            mid,
            stock + cantidad,
            "ENTRADA",
            "APP",
            "Ingreso manual en "
            + inventario_seleccionado,
        )

        invalidar_cache()
        actualizar_todo(True)

        valor = (
            nuevo.get(
                "cantidad",
                stock + cantidad,
            )
            if isinstance(nuevo, dict)
            else stock + cantidad
        )

        messagebox.showinfo(
            "Stock actualizado",
            f"Material: {nombre}\n\n"
            f"Stock anterior: {formatear_numero(stock)} {unidad}\n"
            f"Cantidad agregada: {formatear_numero(cantidad)} {unidad}\n"
            f"Stock nuevo: {formatear_numero(valor)} {unidad}",
            parent=root,
        )

    except Exception as error:

        traceback.print_exc()

        messagebox.showerror(
            "Error",
            f"No se pudo agregar stock:\n\n{error}",
            parent=root,
        )


# ============================================================
# RETIRAR STOCK
# ============================================================

def retirar_stock():

    material = obtener_material_seleccionado()

    if not material:
        return

    mid = material["id"]

    nombre = material.get("material") or ""
    unidad = material.get("unidad") or ""
    codigo = material.get("codigo") or "-"

    item = obtener_item_documento(mid)

    if item is None:

        messagebox.showerror(
            "Error",
            "El material no pertenece al inventario seleccionado.",
            parent=root,
        )

        return

    stock = float(
        item.get("cantidad", 0) or 0
    )

    cantidad = simpledialog.askfloat(
        "Retirar stock",
        f"Inventario: {inventario_seleccionado}\n"
        f"Material: {nombre}\n"
        f"Código: {codigo}\n"
        f"Stock actual: {formatear_numero(stock)} {unidad}\n\n"
        f"Cantidad a retirar:",
        minvalue=0.0001,
        parent=root,
    )

    if cantidad is None or cantidad <= 0:
        return

    if cantidad > stock:

        messagebox.showwarning(
            "Stock insuficiente",
            f"No podés retirar "
            f"{formatear_numero(cantidad)} {unidad}.\n\n"
            f"Stock disponible: "
            f"{formatear_numero(stock)} {unidad}",
            parent=root,
        )

        return

    try:

        nuevo = actualizar_stock_documento(
            mid,
            stock - cantidad,
            "SALIDA",
            "APP",
            "Retiro manual en "
            + inventario_seleccionado,
        )

        invalidar_cache()
        actualizar_todo(True)

        valor = (
            nuevo.get(
                "cantidad",
                stock - cantidad,
            )
            if isinstance(nuevo, dict)
            else stock - cantidad
        )

        messagebox.showinfo(
            "Retiro realizado",
            f"Material: {nombre}\n\n"
            f"Stock anterior: {formatear_numero(stock)} {unidad}\n"
            f"Cantidad retirada: {formatear_numero(cantidad)} {unidad}\n"
            f"Stock nuevo: {formatear_numero(valor)} {unidad}",
            parent=root,
        )

    except Exception as error:

        traceback.print_exc()

        messagebox.showerror(
            "Error",
            f"No se pudo retirar stock:\n\n{error}",
            parent=root,
        )


# ============================================================
# NUEVO MATERIAL
# ============================================================

def nuevo_material():

    if not inventario_seleccionado:
        return

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
        padding=20,
    )

    frame.pack(
        fill="both",
        expand=True,
    )

    for fila, (texto, clave) in enumerate(campos):

        ttk.Label(
            frame,
            text=texto,
        ).grid(
            row=fila,
            column=0,
            sticky="w",
            padx=5,
            pady=7,
        )

        e = ttk.Entry(frame)

        e.grid(
            row=fila,
            column=1,
            sticky="ew",
            padx=5,
            pady=7,
        )

        entradas[clave] = e

    frame.columnconfigure(
        1,
        weight=1,
    )

    def guardar():

        global importacion_en_curso

        nombre = (
            entradas["material"]
            .get()
            .strip()
        )

        if not nombre:

            messagebox.showwarning(
                "Datos",
                "El nombre del material es obligatorio.",
                parent=ventana,
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
                parent=ventana,
            )

            return

        if cantidad < 0:

            messagebox.showerror(
                "Cantidad",
                "La cantidad no puede ser negativa.",
                parent=ventana,
            )

            return

        datos = {
            k: entradas[k].get().strip() or None
            for k in (
                "codigo",
                "unidad",
                "categoria",
                "ubicacion",
                "observaciones",
            )
        }

        datos["material"] = nombre
        datos["cantidad"] = cantidad

        try:

            if buscar_material(
                datos["codigo"],
                nombre,
                datos["categoria"],
                datos["ubicacion"],
            ):

                messagebox.showwarning(
                    "Material existente",
                    "Ese material ya existe en la base de datos.",
                    parent=ventana,
                )

                return

            documento = obtener_documento_actual()

            if not documento:

                raise Exception(
                    "No se encontró el documento seleccionado."
                )

            with lock_importacion:

                if importacion_en_curso:

                    messagebox.showinfo(
                        "Importación",
                        "Hay una importación de Word en curso. "
                        "Esperá a que termine.",
                        parent=ventana,
                    )

                    return

                importacion_en_curso = True

            try:

                _agregar_fila_word(
                    documento,
                    datos,
                )

                nuevo = crear_material(
                    datos["codigo"],
                    nombre,
                    0,
                    datos["unidad"],
                    datos["categoria"],
                    datos["ubicacion"],
                    datos["observaciones"],
                    inventario_seleccionado,
                )

                if not nuevo:

                    raise Exception(
                        "No se pudo crear el material "
                        "en la base de datos."
                    )

                if not crear_item_documento(
                    documento["id"],
                    nuevo["id"],
                    cantidad,
                    unidad=datos["unidad"],
                    codigo=datos["codigo"],
                    material=nombre,
                    categoria=datos["categoria"],
                    ubicacion=datos["ubicacion"],
                    observaciones=datos["observaciones"],
                ):

                    raise Exception(
                        "No se pudo crear el item del inventario."
                    )

                try:

                    from supabase_db import actualizar_documento

                    actualizar_documento(
                        documento["id"],
                        Path(
                            str(
                                documento["ruta"]
                            )
                        ).stat().st_mtime,
                    )

                except Exception:
                    pass

            finally:

                importacion_en_curso = False

            invalidar_cache()

            ventana.destroy()

            actualizar_todo(True)

            messagebox.showinfo(
                "Material creado",
                f"Se agregó correctamente a "
                f"{inventario_seleccionado}:\n\n"
                f"{nombre}\n"
                f"Cantidad: "
                f"{formatear_numero(cantidad)}",
                parent=root,
            )

        except Exception as error:

            traceback.print_exc()

            messagebox.showerror(
                "Error",
                f"No se pudo crear el material:\n\n{error}",
                parent=ventana,
            )

    ttk.Button(
        frame,
        text="Guardar",
        command=guardar,
    ).grid(
        row=len(campos),
        column=0,
        columnspan=2,
        pady=20,
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
        padding=20,
    )

    frame.pack(
        fill="both",
        expand=True,
    )

    for fila, (texto, clave) in enumerate(campos):

        ttk.Label(
            frame,
            text=texto,
        ).grid(
            row=fila,
            column=0,
            sticky="w",
            padx=5,
            pady=7,
        )

        e = ttk.Entry(frame)

        e.grid(
            row=fila,
            column=1,
            sticky="ew",
            padx=5,
            pady=7,
        )

        e.insert(
            0,
            material.get(clave) or "",
        )

        entradas[clave] = e

    frame.columnconfigure(
        1,
        weight=1,
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
                parent=ventana,
            )

            return

        try:

            if not actualizar_material(
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
                ),
            ):

                raise Exception(
                    "No se pudo actualizar."
                )

            invalidar_cache()

            ventana.destroy()

            actualizar_todo(True)

        except Exception as error:

            traceback.print_exc()

            messagebox.showerror(
                "Error",
                f"No se pudo modificar:\n\n{error}",
                parent=ventana,
            )

    ttk.Button(
        frame,
        text="Guardar cambios",
        command=guardar,
    ).grid(
        row=len(campos),
        column=0,
        columnspan=2,
        pady=20,
    )


# ============================================================
# ELIMINAR MATERIAL
# ============================================================

def eliminar_material():

    global importacion_en_curso
    global estado_archivos_word

    material = obtener_material_seleccionado()

    if not material:
        return

    documento = obtener_documento_actual()

    if not documento:

        messagebox.showerror(
            "Error",
            "No se encontró el inventario seleccionado.",
            parent=root,
        )

        return

    material_id = material.get("id")

    if material_id is None:

        messagebox.showerror(
            "Error",
            "El material seleccionado no tiene un ID válido.",
            parent=root,
        )

        return

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

    try:

        cantidad = float(
            material.get(
                "cantidad",
                0,
            )
            or 0
        )

    except Exception:

        cantidad = 0

    confirmar = messagebox.askyesno(
        "Eliminar material",

        f"¿Eliminar este material del inventario "
        f"y del archivo Word?\n\n"

        f"Código: {codigo}\n"
        f"Material: {nombre}\n"
        f"Cantidad: "
        f"{formatear_numero(cantidad)} "
        f"{unidad}\n\n"

        f"El material será eliminado del inventario "
        f"seleccionado y del Word.\n\n"

        f"El historial de movimientos se conservará.",

        parent=root,
    )

    if not confirmar:
        return

    with lock_importacion:

        if importacion_en_curso:

            messagebox.showinfo(
                "Importación",
                "Hay una importación de Word en curso. "
                "Esperá a que termine.",
                parent=root,
            )

            return

        importacion_en_curso = True

    try:

        ruta = _eliminar_fila_word(
            documento,
            material,
        )

        resultado = (
            eliminar_material_del_documento(
                documento["id"],
                material_id,
            )
        )

        try:

            from supabase_db import (
                actualizar_documento
            )

            if ruta.exists():

                actualizar_documento(
                    documento["id"],
                    ruta.stat().st_mtime,
                )

        except Exception:

            pass

        try:

            estado_archivos_word[
                str(ruta.resolve())
            ] = ruta.stat().st_mtime

        except Exception:

            pass

        invalidar_cache()

        actualizar_todo(True)

        if (
            isinstance(resultado, dict)
            and resultado.get(
                "material_eliminado"
            )
        ):

            mensaje = (
                f"Se eliminó correctamente:\n\n"
                f"{nombre}\n\n"
                f"✓ Eliminado del Word\n"
                f"✓ Eliminado del inventario\n"
                f"✓ Eliminado de la base general\n"
                f"✓ Historial de movimientos conservado"
            )

        else:

            mensaje = (
                f"Se eliminó correctamente:\n\n"
                f"{nombre}\n\n"
                f"✓ Eliminado del Word\n"
                f"✓ Eliminado del inventario seleccionado\n"
                f"✓ El material continúa en otros inventarios\n"
                f"✓ Historial de movimientos conservado"
            )

        messagebox.showinfo(
            "Material eliminado",
            mensaje,
            parent=root,
        )

    except Exception as error:

        traceback.print_exc()

        messagebox.showerror(
            "Error",
            f"No se pudo eliminar el material:\n\n"
            f"{error}",
            parent=root,
        )

    finally:

        importacion_en_curso = False


# ============================================================
# MOVIMIENTOS
# ============================================================

def actualizar_movimientos():

    if tabla_movimientos is None:
        return

    try:

        for x in tabla_movimientos.get_children():
            tabla_movimientos.delete(x)

    except Exception:
        return

    materiales = {
        m.get("id"): m
        for m in obtener_materiales_cache()
    }

    nombre_archivo = (
        inventario_seleccionado or ""
    )

    for mov in obtener_movimientos_cache():

        if (
            nombre_archivo
            and mov.get("archivo_origen")
            and mov.get("archivo_origen")
            != nombre_archivo
        ):
            continue

        m = materiales.get(
            mov.get("material_id")
        )

        try:

            tabla_movimientos.insert(
                "",
                "end",
                values=(
                    mov.get("fecha") or "",
                    m.get("codigo") if m else "",
                    m.get("material")
                    if m
                    else "Material eliminado",
                    mov.get("tipo") or "",
                    formatear_numero(
                        mov.get("cantidad", 0)
                    ),
                    formatear_numero(
                        mov.get("stock_anterior", 0)
                    ),
                    formatear_numero(
                        mov.get("stock_nuevo", 0)
                    ),
                    mov.get("usuario") or "",
                    mov.get("archivo_origen") or "",
                    mov.get("observaciones") or "",
                ),
            )

        except Exception:
            pass


# ============================================================
# REPORTES
# ============================================================

def obtener_movimientos_del_inventario():
    return reportes.obtener_movimientos_del_inventario(__import__("sys").modules[__name__])


def generar_reporte_inventario_excel():
    return reportes.generar_reporte_inventario_excel(__import__("sys").modules[__name__])


def generar_reporte_movimientos_excel(ventana=None, fecha_desde=None, fecha_hasta=None):
    return reportes.generar_reporte_movimientos_excel(
        __import__("sys").modules[__name__],
        ventana=ventana,
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
    )


def abrir_reportes():
    return reportes.abrir_reportes(__import__("sys").modules[__name__])


# ============================================================
# ACTUALIZAR TODO
# ============================================================

def actualizar_todo(forzar=False):

    global actualizacion_en_curso
    global firma_datos_sincronizados

    with lock_actualizacion:

        if actualizacion_en_curso:
            return

        actualizacion_en_curso = True

    def trabajo():

        global actualizacion_en_curso
        global firma_datos_sincronizados

        try:

            if lbl_progreso:

                ejecutar_en_ui(lambda: lbl_progreso.config(text="⏳ Actualizando..."))

            (
                materiales,
                documentos,
                movimientos,
            ) = cargar_datos_supabase()

            firma_datos_sincronizados = (
                generar_firma_sincronizacion(
                    materiales,
                    documentos,
                    movimientos,
                )
            )

            def refrescar():

                global actualizacion_en_curso

                try:

                    refrescar_pantalla_seleccion()

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

            ejecutar_en_ui(refrescar)

        except Exception:

            traceback.print_exc()

            def fallo():

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

            ejecutar_en_ui(fallo)

    threading.Thread(
        target=trabajo,
        daemon=True,
    ).start()


# ============================================================
# SINCRONIZACIÓN AUTOMÁTICA
# ============================================================

def sincronizar_automaticamente():

    global sincronizacion_en_curso
    global firma_datos_sincronizados
    global cache_materiales
    global cache_documentos
    global cache_movimientos

    if (
        root is None
        or importacion_en_curso
        or pausar_sincronizacion
    ):
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

            with lock_actualizacion:

                if actualizacion_en_curso:
                    return

            materiales = (
                obtener_materiales()
                or []
            )

            documentos = (
                obtener_documentos()
                or []
            )

            movimientos = (
                obtener_movimientos(100)
                or []
            )

            firma = (
                generar_firma_sincronizacion(
                    materiales,
                    documentos,
                    movimientos,
                )
            )

            cambio = (
                firma_datos_sincronizados is None
                or firma
                != firma_datos_sincronizados
            )

            firma_datos_sincronizados = firma

            if cambio:

                with cache_lock:

                    cache_materiales = materiales
                    cache_documentos = documentos
                    cache_movimientos = movimientos

                ejecutar_en_ui(actualizar_interfaz_por_sincronizacion)

            else:

                ejecutar_en_ui(actualizar_estado_sync, True, False)

        except Exception as error:

            print(
                "❌ Error en sincronización automática:",
                error,
            )

            traceback.print_exc()

            ejecutar_en_ui(actualizar_estado_sync, False, False)

        finally:

            with lock_sincronizacion:
                sincronizacion_en_curso = False

    threading.Thread(
        target=trabajo,
        daemon=True,
    ).start()


def actualizar_interfaz_por_sincronizacion():

    try:

        refrescar_pantalla_seleccion()

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

    except Exception:

        traceback.print_exc()


def actualizar_estado_sync(
    conectado,
    hubo_cambio,
):

    if lbl_estado:

        lbl_estado.config(
            text=(
                "🟢 Sincronizado"
                if conectado
                else "🔴 Sin conexión"
            )
        )

    if (
        hubo_cambio
        and lbl_progreso
    ):

        lbl_progreso.config(
            text="🔄 Datos sincronizados"
        )


def monitor_sincronizacion():

    print(
        "🔄 Monitor de sincronización iniciado."
    )

    while True:

        try:
            sincronizar_automaticamente()

        except Exception:
            traceback.print_exc()

        time.sleep(
            INTERVALO_SINCRONIZACION
            / 1000
        )


# ============================================================
# IMPORTACIÓN WORD
# ============================================================

def ejecutar_importacion_word(
    reescaneo_completo=False,
    mostrar_resultado=True,
):

    global importacion_en_curso
    global pausar_sincronizacion
    global firma_datos_sincronizados
    global cache_materiales
    global cache_documentos
    global cache_movimientos

    with lock_importacion:

        if importacion_en_curso:
            return

        importacion_en_curso = True

    pausar_sincronizacion = True

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

            resultado = (
                importar_word.importar_todos(
                    reescaneo_completo=
                    reescaneo_completo
                )
            )

            invalidar_cache()

            materiales = (
                obtener_materiales()
                or []
            )

            documentos = (
                obtener_documentos()
                or []
            )

            movimientos = (
                obtener_movimientos(100)
                or []
            )

            with cache_lock:

                cache_materiales = materiales
                cache_documentos = documentos
                cache_movimientos = movimientos

            firma_datos_sincronizados = (
                generar_firma_sincronizacion(
                    materiales,
                    documentos,
                    movimientos,
                )
            )

            print(
                "RESULTADO:",
                resultado,
            )

        except Exception as error:

            traceback.print_exc()

            ejecutar_en_ui(
                lambda error=error:
                messagebox.showerror(
                    "Error",
                    "Ocurrió un error durante "
                    "la importación:\n\n"
                    f"{error}",
                    parent=root,
                )
            )

        finally:

            pausar_sincronizacion = False
            importacion_en_curso = False

            ejecutar_en_ui(actualizar_interfaz_por_sincronizacion)

            if resultado is not None and mostrar_resultado:
                ejecutar_en_ui(mostrar_resultado_importacion, resultado)

    threading.Thread(
        target=trabajo,
        daemon=True,
    ).start()


def construir_mensaje_importacion(
    resultado
):

    if not isinstance(
        resultado,
        dict,
    ):
        return str(resultado)

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

    return "\n".join(
        f"{nombre}: "
        f"{resultado.get(clave, 0)}"
        for clave, nombre in campos
        if clave in resultado
    ) or str(resultado)


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
        parent=root,
    )


def importar_word_manual():

    if importacion_en_curso:

        messagebox.showinfo(
            "Importación",
            "Ya hay una importación en curso.",
            parent=root,
        )

        return

    ejecutar_importacion_word(False)


def reescaneo_completo():

    if importacion_en_curso:

        messagebox.showinfo(
            "Importación",
            "Ya hay una importación en curso.",
            parent=root,
        )

        return

    if not messagebox.askyesno(
        "Reescaneo completo",
        "Se van a revisar nuevamente "
        "todos los archivos Word.\n\n"
        "Esto puede tardar unos minutos.\n\n"
        "¿Continuar?",
        parent=root,
    ):
        return

    ejecutar_importacion_word(True)


# ============================================================
# MONITOR DE WORD
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
                str(ruta.resolve())
            ] = ruta.stat().st_mtime

        except Exception:
            pass

    return estado


def monitor_word():

    global estado_archivos_word

    print(
        "📄 Monitor de Word iniciado."
    )

    while True:

        try:

            nuevo = (
                obtener_estado_archivos_word()
            )

            if nuevo != estado_archivos_word:

                estado_archivos_word = nuevo

                if not importacion_en_curso:

                    ejecutar_importacion_word(
                        False
                    )

        except Exception:
            traceback.print_exc()

        time.sleep(
            INTERVALO_MONITOR
            / 1000
        )


# ============================================================
# ESTILO
# ============================================================

def aplicar_estilo():

    estilo = ttk.Style()

    try:
        estilo.theme_use("clam")

    except Exception:
        pass

    estilo.configure(
        ".",
        font=("Segoe UI", 10),
    )

    estilo.configure(
        "TFrame",
        background=COLOR_FONDO,
    )

    estilo.configure(
        "TLabel",
        background=COLOR_FONDO,
        foreground=COLOR_TEXTO,
    )

    estilo.configure(
        "Title.TLabel",
        background=COLOR_AZUL_OSCURO,
        foreground="white",
        font=("Segoe UI", 18, "bold"),
    )

    estilo.configure(
        "Subtitle.TLabel",
        background=COLOR_AZUL_OSCURO,
        foreground="#dce8f1",
        font=("Segoe UI", 9),
    )

    estilo.configure(
        "TButton",
        padding=(12, 7),
        font=("Segoe UI", 9, "bold"),
    )

    estilo.configure(
        "Treeview",
        background="white",
        foreground=COLOR_TEXTO,
        fieldbackground="white",
        rowheight=30,
        font=("Segoe UI", 10),
        borderwidth=0,
    )

    estilo.configure(
        "Treeview.Heading",
        background=COLOR_AZUL_OSCURO,
        foreground="white",
        font=("Segoe UI", 10, "bold"),
        padding=7,
    )

    estilo.map(
        "Treeview",
        background=[
            ("selected", COLOR_AZUL)
        ],
        foreground=[
            ("selected", "white")
        ],
    )


# ============================================================
# CABECERA
# ============================================================

def crear_cabecera():

    cab = tk.Frame(
        root,
        bg=COLOR_AZUL_OSCURO,
        height=75,
    )

    cab.pack(fill="x")
    cab.pack_propagate(False)

    tit = tk.Frame(
        cab,
        bg=COLOR_AZUL_OSCURO,
    )

    tit.pack(
        side="left",
        padx=20,
    )

    ttk.Label(
        tit,
        text="⚓ INVENTARIO MATERIAL NAVAL",
        style="Title.TLabel",
    ).pack(anchor="w")

    ttk.Label(
        tit,
        text="Sistema de gestión y control de material",
        style="Subtitle.TLabel",
    ).pack(anchor="w")

    est = tk.Frame(
        cab,
        bg=COLOR_AZUL_OSCURO,
    )

    est.pack(
        side="right",
        padx=20,
    )

    global lbl_estado

    lbl_estado = tk.Label(
        est,
        text="🟡 Conectando...",
        bg=COLOR_AZUL_OSCURO,
        fg="white",
        font=("Segoe UI", 10, "bold"),
    )

    lbl_estado.pack(
        side="right"
    )

# ============================================================
# CREAR INTERFAZ
# ============================================================

def iniciar_realtime_ui():
    """Conecta Supabase Realtime y refresca la UI cuando hay cambios."""
    global detener_realtime
    global realtime_refresh_pendiente

    session = globals().get("REALTIME_SESSION")
    if root is None or session is None:
        return

    def programar_actualizacion(tabla, evento, payload):
        global realtime_refresh_pendiente
        if realtime_refresh_pendiente is not None:
            try:
                root.after_cancel(realtime_refresh_pendiente)
            except Exception:
                pass
        realtime_refresh_pendiente = root.after(350, actualizar_por_realtime)

    def actualizar_por_realtime():
        global realtime_refresh_pendiente
        realtime_refresh_pendiente = None
        actualizar_todo(forzar=True)

    def estado_realtime(estado):
        if lbl_estado is None:
            return
        if estado == "conectado":
            lbl_estado.config(text="🟢 Conectado · Realtime")
        elif estado == "error":
            lbl_estado.config(text="🟡 Conectado · Realtime no disponible")

    detener_realtime = iniciar_realtime(
        root,
        session,
        on_change=programar_actualizacion,
        on_status=estado_realtime,
    )


def crear_interfaz():

    global root
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
        700,
    )

    root.configure(
        bg=COLOR_FONDO
    )

    root.after(50, procesar_cola_ui)

    iniciar_realtime_ui()

    aplicar_estilo()

    crear_cabecera()

    # El login puede registrar una función para agregar controles antes
    # de entrar al mainloop. Así no queda bloqueada por root.mainloop().
    try:
        hook_admin = globals().get("ADMIN_UI_HOOK")
        if callable(hook_admin):
            hook_admin()
    except Exception:
        traceback.print_exc()

    mostrar_pantalla_seleccion()

    def iniciar():

        global datos_iniciales_cargados
        global error_carga_inicial

        try:

            conectado = probar_conexion()

            ejecutar_en_ui(lambda: lbl_estado.config(text=("🟢 Conectado" if conectado else "🔴 Sin conexión")))

            cargar_datos_supabase()

            datos_iniciales_cargados = True
            error_carga_inicial = None

            ejecutar_en_ui(refrescar_pantalla_seleccion)

        except Exception as error:

            datos_iniciales_cargados = False
            error_carga_inicial = error

            traceback.print_exc()

            ejecutar_en_ui(lambda: lbl_estado.config(text="🔴 Sin conexión"))

            root.after(
                0,
                refrescar_pantalla_seleccion,
            )

    threading.Thread(
        target=iniciar,
        daemon=True,
    ).start()

    estado_archivos_word = (
        obtener_estado_archivos_word()
    )

    threading.Thread(
        target=monitor_word,
        daemon=True,
    ).start()

    threading.Thread(
        target=monitor_sincronizacion,
        daemon=True,
    ).start()

    root.after(
        1500,
        lambda:
        ejecutar_importacion_word(
            False,
            mostrar_resultado=False,
        ),
    )

    root.mainloop()


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    crear_interfaz()
