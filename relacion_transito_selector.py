from __future__ import annotations

import threading
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog

from config import supabase
from supabase_db import obtener_materiales


class SelectorRelacionTransitoError(Exception):
    pass


def _float(value, default=0.0):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return float(default)


def _texto(value):
    return "" if value is None else str(value).strip()


def _nombre_documento(doc):
    if not isinstance(doc, dict):
        return ""
    for key in ("nombre", "nombre_archivo", "archivo_origen", "archivo", "ruta"):
        value = _texto(doc.get(key))
        if value:
            return value.replace("\\", "/").rsplit("/", 1)[-1]
    if doc.get("id") is not None:
        return f"Inventario #{doc['id']}"
    return "Inventario sin nombre"


def _cargar_filas_bulk():
    """Carga todos los orígenes con pocas consultas, evitando N consultas por material."""
    materiales = obtener_materiales() or []
    if not materiales:
        return []

    materiales_por_id = {}
    for material in materiales:
        if material.get("id") is not None:
            materiales_por_id[int(material["id"])] = material

    items = (
        supabase.table("documento_items")
        .select("*")
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
        documentos = {
            int(doc["id"]): doc
            for doc in docs
            if doc.get("id") is not None
        }

    ajustes_por_documento_material = {}
    if documento_ids:
        ajustes = (
            supabase.table("ajustes_stock")
            .select("documento_id,material_id,cantidad")
            .in_("documento_id", documento_ids)
            .execute()
            .data
            or []
        )
        for ajuste in ajustes:
            did = ajuste.get("documento_id")
            mid = ajuste.get("material_id")
            if did is None or mid is None:
                continue
            key = (int(did), int(mid))
            ajustes_por_documento_material[key] = (
                ajustes_por_documento_material.get(key, 0.0)
                + _float(ajuste.get("cantidad"))
            )

    filas = []
    for item in items:
        mid = item.get("material_id")
        did = item.get("documento_id")
        if mid is None or did is None:
            continue

        mid = int(mid)
        did = int(did)
        material = materiales_por_id.get(mid)
        if not material:
            continue

        stock = _float(item.get("cantidad")) + ajustes_por_documento_material.get((did, mid), 0.0)
        if stock <= 0.000001:
            continue

        filas.append({
            **material,
            "_documento_item_id": item.get("id"),
            "_documento_id": did,
            "_origen_clave": f"{did}:{item.get('id')}",
            "archivo_origen": _nombre_documento(documentos.get(did, {})),
            "ubicacion": _texto(item.get("ubicacion")) or _texto(material.get("ubicacion")) or "-",
            "observaciones": _texto(item.get("observaciones")) or _texto(material.get("observaciones")),
            "_stock_origen": stock,
            "_cantidad_transito": 0.0,
            "_seleccionado": False,
        })

    filas.sort(key=lambda x: (
        _texto(x.get("codigo")).casefold(),
        _texto(x.get("material")).casefold(),
        _texto(x.get("archivo_origen")).casefold(),
        _texto(x.get("ubicacion")).casefold(),
        int(x.get("_documento_item_id") or 0),
    ))
    return filas


def seleccionar_materiales_general(parent=None):
    """Selector general de Relación de Tránsito.

    Una sola ventana, checkbox por fila y edición de cantidad con doble clic.
    La carga contra Supabase se realiza en segundo plano para no congelar Tkinter.
    """
    root = parent or tk._default_root
    ventana = tk.Toplevel(root) if root is not None else tk.Tk()
    ventana.title("Relación de Tránsito - Seleccionar materiales")
    ventana.geometry("1450x760")
    ventana.minsize(1050, 560)
    if root is not None:
        ventana.transient(root)
        ventana.grab_set()

    marco = ttk.Frame(ventana, padding=10)
    marco.pack(fill="both", expand=True)

    ttk.Label(
        marco,
        text="Materiales a llevar",
        font=("Segoe UI", 13, "bold"),
    ).pack(anchor="w")
    ttk.Label(
        marco,
        text="Marcá los materiales con la casilla. Doble clic sobre una fila para modificar la cantidad.",
    ).pack(anchor="w", pady=(2, 8))

    estado = tk.StringVar(value="Cargando inventario general...")
    ttk.Label(marco, textvariable=estado).pack(anchor="w", pady=(0, 6))

    contenedor = ttk.Frame(marco)
    contenedor.pack(fill="both", expand=True)

    columnas = (
        "sel", "codigo", "material", "unidad", "ubicacion",
        "origen", "stock", "cantidad",
    )
    tabla = ttk.Treeview(contenedor, columns=columnas, show="headings", selectmode="none")
    titulos = {
        "sel": "Seleccionar",
        "codigo": "Código",
        "material": "Material",
        "unidad": "Unidad",
        "ubicacion": "Ubicación",
        "origen": "Archivo de origen",
        "stock": "Stock disponible",
        "cantidad": "Cantidad",
    }
    anchos = {
        "sel": 85, "codigo": 135, "material": 360, "unidad": 95,
        "ubicacion": 180, "origen": 260, "stock": 125, "cantidad": 110,
    }
    for columna in columnas:
        tabla.heading(columna, text=titulos[columna])
        tabla.column(
            columna,
            width=anchos[columna],
            minwidth=55,
            anchor="center" if columna in ("sel", "stock", "cantidad") else "w",
            stretch=columna in ("material", "ubicacion", "origen"),
        )

    scroll_y = ttk.Scrollbar(contenedor, orient="vertical", command=tabla.yview)
    scroll_x = ttk.Scrollbar(contenedor, orient="horizontal", command=tabla.xview)
    tabla.configure(yscrollcommand=scroll_y.set, xscrollcommand=scroll_x.set)
    tabla.grid(row=0, column=0, sticky="nsew")
    scroll_y.grid(row=0, column=1, sticky="ns")
    scroll_x.grid(row=1, column=0, sticky="ew")
    contenedor.rowconfigure(0, weight=1)
    contenedor.columnconfigure(0, weight=1)

    pie = ttk.Frame(marco)
    pie.pack(fill="x", pady=(8, 0))
    seleccionados_var = tk.StringVar(value="Seleccionados: 0")
    ttk.Label(pie, textvariable=seleccionados_var).pack(side="left")

    resultado = {"materiales": None}
    filas_por_iid = {}
    carga_completa = {"ok": False}
    filas_pendientes = []
    cerrar_solicitado = {"value": False}

    def actualizar_contador():
        cantidad = sum(1 for fila in filas_por_iid.values() if fila.get("_seleccionado"))
        seleccionados_var.set(f"Seleccionados: {cantidad}")

    def refrescar_fila(iid, fila):
        tabla.item(iid, values=(
            "☑" if fila.get("_seleccionado") else "☐",
            _texto(fila.get("codigo")),
            _texto(fila.get("material")),
            _texto(fila.get("unidad")),
            _texto(fila.get("ubicacion")) or "-",
            _texto(fila.get("archivo_origen")) or "-",
            _numero_visual(fila.get("_stock_origen")),
            _numero_visual(fila.get("_cantidad_transito")) if fila.get("_seleccionado") else "-",
        ))

    def insertar_lote():
        if not ventana.winfo_exists():
            return
        lote = 150
        fin = min(len(filas_pendientes), lote)
        for _ in range(fin):
            fila = filas_pendientes.pop(0)
            iid = tabla.insert("", "end", values=(
                "☐", _texto(fila.get("codigo")), _texto(fila.get("material")),
                _texto(fila.get("unidad")), _texto(fila.get("ubicacion")) or "-",
                _texto(fila.get("archivo_origen")) or "-",
                _numero_visual(fila.get("_stock_origen")), "-",
            ))
            filas_por_iid[iid] = fila
        if filas_pendientes:
            ventana.after(1, insertar_lote)
        else:
            carga_completa["ok"] = True
            estado.set(f"Inventario cargado: {len(filas_por_iid)} orígenes con stock disponible.")
            boton_generar.state(["!disabled"])
            actualizar_contador()
            if cerrar_solicitado["value"]:
                ventana.destroy()

    def carga_terminada(filas, error):
        if not ventana.winfo_exists():
            return
        if error:
            estado.set("No se pudo cargar el inventario.")
            messagebox.showerror(
                "Relación de Tránsito",
                f"No se pudo cargar el inventario general:\n\n{error}",
                parent=ventana,
            )
            boton_generar.state(["disabled"])
            return
        filas_pendientes.extend(filas)
        estado.set(f"Preparando {len(filas)} orígenes...")
        insertar_lote()

    def cargar_en_hilo():
        try:
            filas = _cargar_filas_bulk()
            error = None
        except Exception as exc:
            filas = []
            error = exc
        ventana.after(0, carga_terminada, filas, error)

    def toggle_checkbox(event):
        if not carga_completa["ok"]:
            return
        iid = tabla.identify_row(event.y)
        columna = tabla.identify_column(event.x)
        if not iid or columna != "#1":
            return
        fila = filas_por_iid.get(iid)
        if not fila:
            return
        fila["_seleccionado"] = not fila.get("_seleccionado", False)
        if fila["_seleccionado"]:
            stock = _float(fila.get("_stock_origen"))
            fila["_cantidad_transito"] = min(1.0, stock) if stock > 0 else 0.0
        else:
            fila["_cantidad_transito"] = 0.0
        refrescar_fila(iid, fila)
        actualizar_contador()

    def editar_cantidad(event):
        if not carga_completa["ok"]:
            return
        iid = tabla.identify_row(event.y)
        columna = tabla.identify_column(event.x)
        if not iid:
            return
        # El doble clic en la casilla solamente alterna la selección; no abre diálogo.
        if columna == "#1":
            return
        fila = filas_por_iid.get(iid)
        if not fila:
            return
        if not fila.get("_seleccionado"):
            fila["_seleccionado"] = True
        stock = _float(fila.get("_stock_origen"))
        actual = _float(fila.get("_cantidad_transito")) or min(1.0, stock)
        cantidad = simpledialog.askfloat(
            "Cantidad",
            f"Cantidad a llevar:\nStock disponible: {_numero_visual(stock)}",
            initialvalue=actual,
            minvalue=0.000001,
            maxvalue=stock,
            parent=ventana,
        )
        if cantidad is None:
            return
        if cantidad > stock + 0.000001:
            messagebox.showwarning(
                "Cantidad inválida",
                f"La cantidad no puede superar el stock disponible ({_numero_visual(stock)}).",
                parent=ventana,
            )
            return
        fila["_cantidad_transito"] = float(cantidad)
        refrescar_fila(iid, fila)
        actualizar_contador()

    def generar():
        if not carga_completa["ok"]:
            return
        seleccion = []
        for fila in filas_por_iid.values():
            if not fila.get("_seleccionado"):
                continue
            cantidad = _float(fila.get("_cantidad_transito"))
            stock = _float(fila.get("_stock_origen"))
            if cantidad <= 0:
                messagebox.showwarning(
                    "Cantidad requerida",
                    f"Ingresá una cantidad válida para:\n{_texto(fila.get('material'))}",
                    parent=ventana,
                )
                return
            if cantidad > stock + 0.000001:
                messagebox.showwarning(
                    "Stock insuficiente",
                    f"{_texto(fila.get('material'))}: cantidad {cantidad} supera el stock {stock}.",
                    parent=ventana,
                )
                return
            item = dict(fila)
            item["cantidad"] = cantidad
            seleccion.append(item)

        if not seleccion:
            messagebox.showwarning(
                "Sin materiales",
                "Seleccioná al menos un material para continuar.",
                parent=ventana,
            )
            return

        resultado["materiales"] = seleccion
        ventana.destroy()

    def cancelar():
        resultado["materiales"] = None
        ventana.destroy()

    def al_cerrar():
        if not carga_completa["ok"] and filas_pendientes:
            cerrar_solicitado["value"] = True
            return
        cancelar()

    boton_cancelar = ttk.Button(pie, text="Cancelar", command=cancelar)
    boton_cancelar.pack(side="right", padx=(6, 0))
    boton_generar = ttk.Button(pie, text="Generar Relación de Tránsito", command=generar)
    boton_generar.pack(side="right")
    boton_generar.state(["disabled"])

    tabla.bind("<ButtonRelease-1>", toggle_checkbox)
    tabla.bind("<Double-1>", editar_cantidad)
    ventana.protocol("WM_DELETE_WINDOW", al_cerrar)

    threading.Thread(target=cargar_en_hilo, daemon=True).start()

    if root is not None:
        root.wait_window(ventana)
    else:
        ventana.mainloop()

    return resultado["materiales"]


def _numero_visual(value):
    numero = _float(value)
    if abs(numero - round(numero)) < 0.000001:
        return str(int(round(numero)))
    return f"{numero:g}"
