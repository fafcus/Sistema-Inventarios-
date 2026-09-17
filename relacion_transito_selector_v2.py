from __future__ import annotations

import threading
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog

from config import supabase
from supabase_db import obtener_materiales


def _float(v, default=0.0):
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return float(default)


def _txt(v):
    return "" if v is None else str(v).strip()


def _doc_name(doc):
    for k in ("nombre", "nombre_archivo", "archivo_origen", "archivo", "ruta"):
        v = _txt(doc.get(k)) if isinstance(doc, dict) else ""
        if v:
            return v.replace("\\", "/").rsplit("/", 1)[-1]
    return f"Inventario #{doc.get('id')}" if isinstance(doc, dict) and doc.get("id") is not None else "Inventario sin nombre"


def _visual(v):
    n = _float(v)
    return str(int(round(n))) if abs(n-round(n)) < 0.000001 else f"{n:g}"


def _cargar_bulk():
    materiales = obtener_materiales() or []
    por_id = {int(m["id"]): m for m in materiales if m.get("id") is not None}
    if not por_id:
        return []

    items = supabase.table("documento_items").select("*").order("id").execute().data or []
    if not items:
        return []

    dids = sorted({int(i["documento_id"]) for i in items if i.get("documento_id") is not None})
    docs = supabase.table("documentos").select("*").in_("id", dids).execute().data or [] if dids else []
    docs = {int(d["id"]): d for d in docs if d.get("id") is not None}

    ajustes = supabase.table("ajustes_stock").select("documento_id,material_id,cantidad").in_("documento_id", dids).execute().data or []
    ajustes_map = {}
    for a in ajustes:
        if a.get("documento_id") is None or a.get("material_id") is None:
            continue
        key = (int(a["documento_id"]), int(a["material_id"]))
        ajustes_map[key] = ajustes_map.get(key, 0.0) + _float(a.get("cantidad"))

    filas = []
    for item in items:
        mid, did = item.get("material_id"), item.get("documento_id")
        if mid is None or did is None or int(mid) not in por_id:
            continue
        mid, did = int(mid), int(did)
        stock = _float(item.get("cantidad")) + ajustes_map.get((did, mid), 0.0)
        if stock <= 0.000001:
            continue
        m = por_id[mid]
        filas.append({
            **m,
            "_documento_item_id": item.get("id"),
            "_documento_id": did,
            "_origen_clave": f"{did}:{item.get('id')}",
            "archivo_origen": _doc_name(docs.get(did, {})),
            "ubicacion": _txt(item.get("ubicacion")) or _txt(m.get("ubicacion")) or "-",
            "observaciones": _txt(item.get("observaciones")) or _txt(m.get("observaciones")),
            "_stock_origen": stock,
            "_cantidad_transito": 0.0,
            "_seleccionado": False,
        })

    filas.sort(key=lambda x: (_txt(x.get("codigo")).casefold(), _txt(x.get("material")).casefold(),
                             _txt(x.get("archivo_origen")).casefold(), _txt(x.get("ubicacion")).casefold(),
                             int(x.get("_documento_item_id") or 0)))
    return filas


def seleccionar_materiales_general(parent=None):
    root = parent or tk._default_root
    ventana = tk.Toplevel(root) if root else tk.Tk()
    ventana.title("Relación de Tránsito - Seleccionar materiales")
    ventana.geometry("1450x780")
    ventana.minsize(1050, 560)
    if root:
        ventana.transient(root)
        ventana.grab_set()

    marco = ttk.Frame(ventana, padding=10)
    marco.pack(fill="both", expand=True)
    ttk.Label(marco, text="Materiales a llevar", font=("Segoe UI", 13, "bold")).pack(anchor="w")
    ttk.Label(marco, text="Marcá la casilla para seleccionar. Doble clic en una fila para modificar la cantidad.").pack(anchor="w", pady=(2,8))

    busqueda = tk.StringVar()
    barra = ttk.Frame(marco)
    barra.pack(fill="x", pady=(0,8))
    ttk.Label(barra, text="Buscar:").pack(side="left")
    entrada = ttk.Entry(barra, textvariable=busqueda)
    entrada.pack(side="left", fill="x", expand=True, padx=8)
    ttk.Button(barra, text="Limpiar", command=lambda: busqueda.set("")).pack(side="right")

    estado = tk.StringVar(value="Cargando inventario general...")
    ttk.Label(marco, textvariable=estado).pack(anchor="w", pady=(0,6))

    cont = ttk.Frame(marco)
    cont.pack(fill="both", expand=True)
    cols = ("sel","codigo","material","unidad","ubicacion","origen","stock","cantidad")
    tabla = ttk.Treeview(cont, columns=cols, show="headings", selectmode="none")
    tit = {"sel":"Seleccionar","codigo":"Código","material":"Material","unidad":"Unidad","ubicacion":"Ubicación","origen":"Archivo de origen","stock":"Stock disponible","cantidad":"Cantidad"}
    widths = {"sel":85,"codigo":135,"material":360,"unidad":95,"ubicacion":180,"origen":260,"stock":125,"cantidad":110}
    for c in cols:
        tabla.heading(c, text=tit[c])
        tabla.column(c, width=widths[c], minwidth=55, anchor="center" if c in ("sel","stock","cantidad") else "w",
                     stretch=c in ("material","ubicacion","origen"))
    sy = ttk.Scrollbar(cont, orient="vertical", command=tabla.yview)
    sx = ttk.Scrollbar(cont, orient="horizontal", command=tabla.xview)
    tabla.configure(yscrollcommand=sy.set, xscrollcommand=sx.set)
    tabla.grid(row=0,column=0,sticky="nsew"); sy.grid(row=0,column=1,sticky="ns"); sx.grid(row=1,column=0,sticky="ew")
    cont.rowconfigure(0,weight=1); cont.columnconfigure(0,weight=1)

    pie = ttk.Frame(marco); pie.pack(fill="x", pady=(8,0))
    seleccionados = tk.StringVar(value="Seleccionados: 0")
    ttk.Label(pie,textvariable=seleccionados).pack(side="left")
    resultado = {"materiales": None}
    todas = []
    filas_iid = {}
    cargada = {"ok": False}

    def contar():
        n = sum(1 for f in filas_iid.values() if f.get("_seleccionado"))
        seleccionados.set(f"Seleccionados: {n}")

    def values(f):
        return ("☑" if f.get("_seleccionado") else "☐", _txt(f.get("codigo")), _txt(f.get("material")),
                _txt(f.get("unidad")), _txt(f.get("ubicacion")) or "-", _txt(f.get("archivo_origen")) or "-",
                _visual(f.get("_stock_origen")), _visual(f.get("_cantidad_transito")) if f.get("_seleccionado") else "-")

    def render():
        if not ventana.winfo_exists(): return
        filtro = busqueda.get().strip().casefold()
        for iid in list(filas_iid):
            tabla.delete(iid)
        filas_iid.clear()
        visibles = []
        for f in todas:
            texto = " ".join(_txt(f.get(k)) for k in ("codigo","material","unidad","ubicacion","archivo_origen","observaciones")).casefold()
            if not filtro or filtro in texto:
                visibles.append(f)
        for f in visibles:
            iid = tabla.insert("", "end", values=values(f))
            filas_iid[iid] = f
        estado.set(f"Mostrando {len(visibles)} de {len(todas)} orígenes con stock disponible.")
        contar()

    def toggle(event):
        if not cargada["ok"]: return
        iid = tabla.identify_row(event.y); col = tabla.identify_column(event.x)
        if not iid or col != "#1": return
        f = filas_iid.get(iid)
        if not f: return
        f["_seleccionado"] = not f.get("_seleccionado", False)
        if f["_seleccionado"]:
            f["_cantidad_transito"] = min(1.0, _float(f["_stock_origen"]))
        else:
            f["_cantidad_transito"] = 0.0
        tabla.item(iid, values=values(f)); contar()

    def editar(event):
        if not cargada["ok"]: return
        iid = tabla.identify_row(event.y); col = tabla.identify_column(event.x)
        if not iid or col == "#1": return
        f = filas_iid.get(iid)
        if not f: return
        f["_seleccionado"] = True
        stock = _float(f["_stock_origen"])
        actual = _float(f["_cantidad_transito"]) or min(1.0, stock)
        cantidad = simpledialog.askfloat("Cantidad", f"Cantidad a llevar:\\nStock disponible: {_visual(stock)}",
                                         initialvalue=actual, minvalue=0.000001, maxvalue=stock, parent=ventana)
        if cantidad is not None:
            f["_cantidad_transito"] = float(cantidad)
            tabla.item(iid, values=values(f)); contar()

    def generar():
        seleccion = []
        for f in todas:
            if not f.get("_seleccionado"): continue
            q, stock = _float(f.get("_cantidad_transito")), _float(f.get("_stock_origen"))
            if q <= 0 or q > stock + 0.000001:
                messagebox.showwarning("Cantidad inválida", f"{_txt(f.get('material'))}: cantidad inválida o superior al stock.", parent=ventana)
                return
            x = dict(f); x["cantidad"] = q; seleccion.append(x)
        if not seleccion:
            messagebox.showwarning("Sin materiales","Seleccioná al menos un material.",parent=ventana); return
        resultado["materiales"] = seleccion
        ventana.destroy()

    def cargar_fin(filas, error):
        if not ventana.winfo_exists(): return
        if error:
            estado.set("Error al cargar inventario.")
            messagebox.showerror("Relación de Tránsito", f"No se pudo cargar el inventario:\\n\\n{error}", parent=ventana)
            return
        todas.extend(filas); cargada["ok"] = True; render(); boton.state(["!disabled"]); entrada.focus_set()

    def cargar():
        try: filas, error = _cargar_bulk(), None
        except Exception as e: filas, error = [], e
        ventana.after(0, cargar_fin, filas, error)

    def cancelar():
        resultado["materiales"] = None
        ventana.destroy()

    entrada.bind("<KeyRelease>", lambda e: render())
    tabla.bind("<ButtonRelease-1>", toggle)
    tabla.bind("<Double-1>", editar)
    boton = ttk.Button(pie,text="Generar Relación de Tránsito",command=generar,state="disabled")
    boton.pack(side="right")
    ttk.Button(pie,text="Cancelar",command=cancelar).pack(side="right",padx=(6,0))
    ventana.protocol("WM_DELETE_WINDOW", cancelar)
    threading.Thread(target=cargar, daemon=True).start()
    if root: root.wait_window(ventana)
    else: ventana.mainloop()
    return resultado["materiales"]
