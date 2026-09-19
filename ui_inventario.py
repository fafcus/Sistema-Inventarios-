"""Construcción de la pantalla principal del inventario.

Este módulo contiene únicamente el armado visual de la pantalla. La lógica
y el estado siguen viviendo en main_original.py; se sincronizan mediante
el módulo de aplicación recibido como argumento.
"""

import tkinter as tk
import sys
from tkinter import ttk

from usuarios_db import tiene_permiso
from permisos_documentos import tiene_permiso_documento

_NOMBRES = ["root","tabla","tabla_movimientos","entrada_busqueda","lbl_total_materiales","lbl_con_stock","lbl_sin_stock","lbl_cantidad_total","lbl_progreso","marco_contenido","marco_selector","inventario_seleccionado","inventario_seleccionado_id","USUARIO_ROL","obtener_documento_id_actual","COLOR_FONDO","COLOR_PANEL","COLOR_AZUL_OSCURO","COLOR_AZUL","COLOR_AZUL_CLARO","COLOR_BORDE","COLOR_TEXTO","COLOR_TEXTO_SECUNDARIO","COLOR_STOCK_FONDO","COLOR_SIN_STOCK_FONDO","COLOR_STOCK","COLOR_SIN_STOCK","buscar","actualizar_tabla","nuevo_material","editar_material","eliminar_material","agregar_stock","retirar_stock","abrir_reportes","generar_relacion_transito_ui","actualizar_todo","cargar_inventario_seleccionado","volver_a_seleccion"]
_ESTADO = ["root","tabla","tabla_movimientos","entrada_busqueda","lbl_total_materiales","lbl_con_stock","lbl_sin_stock","lbl_cantidad_total","lbl_progreso","marco_contenido","marco_selector"]

def _construir_pantalla_inventario():

    global marco_contenido
    global marco_selector

    global tabla
    global tabla_movimientos
    global entrada_busqueda

    global lbl_total_materiales
    global lbl_con_stock
    global lbl_sin_stock
    global lbl_cantidad_total
    global lbl_progreso

    if marco_selector is not None:

        try:
            marco_selector.destroy()
        except Exception:
            pass

        marco_selector = None

    if marco_contenido is not None:

        try:
            marco_contenido.destroy()
        except Exception:
            pass

    tabla = None
    tabla_movimientos = None
    entrada_busqueda = None

    marco_contenido = tk.Frame(
        root,
        bg=COLOR_FONDO,
    )

    marco_contenido.pack(
        fill="both",
        expand=True,
    )

    fs = ttk.Frame(
        marco_contenido,
        padding=(15, 10),
    )

    fs.pack(
        fill="x"
    )

    ttk.Label(
        fs,
        text="Inventario:",
        font=("Segoe UI", 10, "bold"),
    ).pack(
        side="left",
        padx=(0, 8),
    )

    ttk.Label(
        fs,
        text=inventario_seleccionado or "",
        font=("Segoe UI", 10, "bold"),
        foreground=COLOR_AZUL,
    ).pack(
        side="left"
    )

    ttk.Button(
        fs,
        text="📂 Cambiar inventario",
        command=volver_a_seleccion,
    ).pack(
        side="right"
    )

    stats = tk.Frame(
        marco_contenido,
        bg=COLOR_AZUL_CLARO,
        highlightbackground=COLOR_BORDE,
        highlightthickness=1,
    )

    stats.pack(
        fill="x",
        padx=15,
        pady=(0, 7),
    )

    def stat(t):

        return tk.Label(
            stats,
            text=t,
            bg=COLOR_AZUL_CLARO,
            fg=COLOR_TEXTO,
            font=("Segoe UI", 10, "bold"),
            padx=15,
            pady=8,
        )

    lbl_total_materiales = stat(
        "Materiales: 0"
    )

    lbl_total_materiales.pack(
        side="left"
    )

    lbl_con_stock = stat(
        "Con stock: 0"
    )

    lbl_con_stock.pack(
        side="left"
    )

    lbl_sin_stock = stat(
        "Sin stock: 0"
    )

    lbl_sin_stock.pack(
        side="left"
    )

    lbl_cantidad_total = stat(
        "Cantidad total: 0"
    )

    lbl_cantidad_total.pack(
        side="left"
    )

    fb = ttk.Frame(
        marco_contenido,
        padding=(15, 5),
    )

    fb.pack(
        fill="x"
    )

    ttk.Label(
        fb,
        text="Buscar:",
        font=("Segoe UI", 10, "bold"),
    ).pack(
        side="left",
        padx=(0, 7),
    )

    entrada_busqueda = ttk.Entry(
        fb
    )

    entrada_busqueda.pack(
        side="left",
        fill="x",
        expand=True,
    )

    entrada_busqueda.bind(
        "<KeyRelease>",
        buscar,
    )

    # ========================================================
    # BOTONES
    # ========================================================

    buttons = ttk.Frame(
        marco_contenido,
        padding=(15, 5),
    )

    buttons.pack(
        fill="x"
    )

    rol_actual = str(USUARIO_ROL or "").strip().lower()
    try:
        documento_id_actual = obtener_documento_id_actual()
    except Exception:
        documento_id_actual = None

    def puede(permiso_rol, permiso_documento=None):
        if rol_actual == "administrador":
            return True
        if not tiene_permiso(rol_actual, permiso_rol):
            return False
        if permiso_documento and not tiene_permiso_documento(documento_id_actual, permiso_documento):
            return False
        return True

    acciones = (
        ("➕ Nuevo", nuevo_material, puede("crear_material", "modificar")),
        ("✏️ Editar", editar_material, puede("editar_material", "modificar")),
        ("🗑️ Eliminar", eliminar_material, puede("eliminar_material", "eliminar")),
        ("📥 Agregar", agregar_stock, puede("agregar_stock", "agregar")),
        ("📤 Retirar", retirar_stock, puede("retirar_stock", "retirar")),
        ("📊 Reportes", abrir_reportes, puede("generar_reportes")),
        ("📋 Relación de Tránsito", generar_relacion_transito_ui, puede("generar_relacion_transito")),
        ("🔄 Actualizar", lambda: actualizar_todo(True), True),
    )

    for text, cmd, permitido in acciones:
        if not permitido:
            continue

        ttk.Button(
            buttons,
            text=text,
            command=cmd,
        ).pack(
            side="left",
            padx=3,
        )

    lbl_progreso = ttk.Label(
        marco_contenido,
        text="Cargando inventario...",
        foreground=COLOR_TEXTO_SECUNDARIO,
    )

    lbl_progreso.pack(
        anchor="w",
        padx=18,
        pady=(2, 2),
    )

    ft = ttk.Frame(
        marco_contenido,
        padding=(15, 3),
    )

    ft.pack(
        fill="both",
        expand=True,
    )

    cols = (
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
        ft,
        columns=cols,
        show="headings",
        selectmode="browse",
    )

    heads = {
        "codigo": "Código",
        "material": "Material",
        "cantidad": "Cantidad",
        "unidad": "Unidad",
        "categoria": "Categoría",
        "ubicacion": "Ubicación",
        "observaciones": "Observaciones",
        "estado": "Estado",
    }

    widths = {
        "codigo": 150,
        "material": 300,
        "cantidad": 100,
        "unidad": 100,
        "categoria": 150,
        "ubicacion": 180,
        "observaciones": 300,
        "estado": 150,
    }

    for c in cols:

        tabla.heading(
            c,
            text=heads[c],
        )

        tabla.column(
            c,
            width=widths[c],
            minwidth=70,
        )

    sv = ttk.Scrollbar(
        ft,
        orient="vertical",
        command=tabla.yview,
    )

    sh = ttk.Scrollbar(
        ft,
        orient="horizontal",
        command=tabla.xview,
    )

    tabla.configure(
        yscrollcommand=sv.set,
        xscrollcommand=sh.set,
    )

    tabla.grid(
        row=0,
        column=0,
        sticky="nsew",
    )

    sv.grid(
        row=0,
        column=1,
        sticky="ns",
    )

    sh.grid(
        row=1,
        column=0,
        sticky="ew",
    )

    ft.rowconfigure(
        0,
        weight=1,
    )

    ft.columnconfigure(
        0,
        weight=1,
    )

    tabla.tag_configure(
        "stock",
        background=COLOR_STOCK_FONDO,
    )

    tabla.tag_configure(
        "sin_stock",
        background=COLOR_SIN_STOCK_FONDO,
    )

    ttk.Label(
        marco_contenido,
        text="Últimos movimientos",
        font=("Segoe UI", 12, "bold"),
    ).pack(
        anchor="w",
        padx=15,
        pady=(8, 3),
    )

    fm = ttk.Frame(
        marco_contenido,
        height=180,
    )

    fm.pack(
        fill="x",
        padx=15,
        pady=(0, 10),
    )

    fm.pack_propagate(False)

    mc = (
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
        fm,
        columns=mc,
        show="headings",
    )

    mh = {
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

    mw = {
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

    for c in mc:

        tabla_movimientos.heading(
            c,
            text=mh[c],
        )

        tabla_movimientos.column(
            c,
            width=mw[c],
            minwidth=80,
        )

    smv = ttk.Scrollbar(
        fm,
        orient="vertical",
        command=tabla_movimientos.yview,
    )

    smh = ttk.Scrollbar(
        fm,
        orient="horizontal",
        command=tabla_movimientos.xview,
    )

    tabla_movimientos.configure(
        yscrollcommand=smv.set,
        xscrollcommand=smh.set,
    )

    tabla_movimientos.grid(
        row=0,
        column=0,
        sticky="nsew",
    )

    smv.grid(
        row=0,
        column=1,
        sticky="ns",
    )

    smh.grid(
        row=1,
        column=0,
        sticky="ew",
    )

    fm.rowconfigure(
        0,
        weight=1,
    )

    fm.columnconfigure(
        0,
        weight=1,
    )

    root.after(
        100,
        cargar_inventario_seleccionado,
    )


# ============================================================
# CREAR INTERFAZ
# ============================================================


def construir_pantalla_inventario(app):
    """Construye la pantalla usando el estado y callbacks de la aplicación."""
    modulo = globals()

    for nombre in _NOMBRES:
        if hasattr(app, nombre):
            modulo[nombre] = getattr(app, nombre)

    _construir_pantalla_inventario()

    for nombre in _ESTADO:
        setattr(app, nombre, modulo.get(nombre))
