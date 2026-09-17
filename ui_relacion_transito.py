"""Interfaz de selección para Relación de Tránsito.

Mantiene la interfaz que se utilizaba desde inicio.py, pero separa
la UI de autenticación para que el proyecto tenga responsabilidades claras.
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import traceback
from datetime import datetime


def _numero_float(valor):
    try:
        return float(valor or 0)
    except (TypeError, ValueError):
        return 0.0


def abrir_selector_relacion_transito(app):
    """Selector completo de materiales para generar una relación de tránsito."""
    materiales = app.obtener_materiales_cache() or []
    materiales = [m for m in materiales if _numero_float(m.get("cantidad")) > 0]

    if not materiales:
        messagebox.showwarning(
            "Relación de Tránsito",
            "No hay materiales con stock disponible en el inventario general.",
            parent=app.root,
        )
        return

    ventana = tk.Toplevel(app.root)
    ventana.title("Generar Relación de Tránsito")
    ventana.geometry("1250x720")
    ventana.minsize(1000, 600)
    ventana.transient(app.root)
    ventana.grab_set()
    ventana.configure(bg="#eef3f8")

    cabecera = tk.Frame(ventana, bg="#12304a", height=72)
    cabecera.pack(fill="x")
    cabecera.pack_propagate(False)
    tk.Label(
        cabecera,
        text="🚚 Selección de materiales para Relación de Tránsito",
        bg="#12304a",
        fg="white",
        font=("Segoe UI", 17, "bold"),
    ).pack(anchor="w", padx=20, pady=20)

    marco = ttk.Frame(ventana, padding=14)
    marco.pack(fill="both", expand=True)

    datos = ttk.Frame(marco)
    datos.pack(fill="x", pady=(0, 10))

    ttk.Label(datos, text="Tipo:", font=("Segoe UI", 10, "bold")).pack(side="left")
    tipo = tk.StringVar()
    ttk.Entry(datos, textvariable=tipo, width=22).pack(side="left", padx=(8, 20))

    ttk.Label(datos, text="Destino:", font=("Segoe UI", 10, "bold")).pack(side="left")
    destino = tk.StringVar()
    ttk.Entry(datos, textvariable=destino, width=28).pack(side="left", padx=(8, 20))

    ttk.Label(datos, text="Buscar:", font=("Segoe UI", 10, "bold")).pack(side="left")
    busqueda = tk.StringVar()
    entrada_busqueda = ttk.Entry(datos, textvariable=busqueda, width=40)
    entrada_busqueda.pack(side="left", padx=(8, 0), fill="x", expand=True)

    ttk.Label(
        marco,
        text="☐ Marcá los materiales que vas a trasladar. Doble clic sobre cualquier material para modificar la cantidad.",
        foreground="#506575",
    ).pack(fill="x", pady=(0, 8))

    generar_pdf = tk.BooleanVar(value=True)
    ttk.Checkbutton(marco, text="Generar también el PDF", variable=generar_pdf).pack(anchor="w", pady=(0, 8))

    marco_tabla = ttk.Frame(marco)
    marco_tabla.pack(fill="both", expand=True)

    columnas = ("seleccionar", "codigo", "material", "stock", "llevar", "unidad", "ubicacion", "origen")
    tabla = ttk.Treeview(marco_tabla, columns=columnas, show="headings", selectmode="browse")
    encabezados = {
        "seleccionar": "✓",
        "codigo": "Código",
        "material": "Material",
        "stock": "Stock disponible",
        "llevar": "Cantidad a llevar",
        "unidad": "Unidad",
        "ubicacion": "Ubicación",
        "origen": "Archivo origen",
    }
    anchos = {
        "seleccionar": 55,
        "codigo": 120,
        "material": 300,
        "stock": 115,
        "llevar": 125,
        "unidad": 100,
        "ubicacion": 180,
        "origen": 210,
    }
    for columna in columnas:
        tabla.heading(columna, text=encabezados[columna])
        anchor = "center" if columna in ("seleccionar", "stock", "llevar") else "w"
        tabla.column(columna, width=anchos[columna], minwidth=55, anchor=anchor)

    scroll_vertical = ttk.Scrollbar(marco_tabla, orient="vertical", command=tabla.yview)
    scroll_horizontal = ttk.Scrollbar(marco_tabla, orient="horizontal", command=tabla.xview)
    tabla.configure(yscrollcommand=scroll_vertical.set, xscrollcommand=scroll_horizontal.set)
    tabla.grid(row=0, column=0, sticky="nsew")
    scroll_vertical.grid(row=0, column=1, sticky="ns")
    scroll_horizontal.grid(row=1, column=0, sticky="ew")
    marco_tabla.rowconfigure(0, weight=1)
    marco_tabla.columnconfigure(0, weight=1)

    seleccionados = {}
    visibles = []

    def cantidad_disponible(material):
        return _numero_float(material.get("cantidad"))

    def cantidad_formateada(valor):
        return f"{_numero_float(valor):g}"

    def material_seleccionado(material):
        return id(material) in seleccionados

    def cargar_tabla(*_):
        for item in tabla.get_children():
            tabla.delete(item)
        visibles.clear()
        texto = busqueda.get().strip().lower()

        for material in materiales:
            combinado = " ".join(
                str(material.get(campo) or "")
                for campo in ("codigo", "material", "ubicacion", "archivo_origen", "categoria")
            ).lower()
            if texto and texto not in combinado:
                continue

            visibles.append(material)
            seleccionado = material_seleccionado(material)
            cantidad = seleccionados.get(id(material), cantidad_disponible(material))
            iid = str(id(material))
            tabla.insert(
                "",
                "end",
                iid=iid,
                values=(
                    "☑" if seleccionado else "☐",
                    material.get("codigo") or "",
                    material.get("material") or "",
                    cantidad_formateada(cantidad_disponible(material)),
                    cantidad_formateada(cantidad),
                    material.get("unidad") or "",
                    material.get("ubicacion") or "",
                    material.get("archivo_origen") or "-",
                ),
            )

    def obtener_material_visible(iid):
        for material in visibles:
            if str(id(material)) == str(iid):
                return material
        return None

    def alternar_seleccion(material):
        clave = id(material)
        if clave in seleccionados:
            seleccionados.pop(clave, None)
        else:
            seleccionados[clave] = cantidad_disponible(material)
        cargar_tabla()
        iid = str(clave)
        if iid in tabla.get_children():
            tabla.selection_set(iid)
            tabla.focus(iid)

    def modificar_cantidad(event=None):
        seleccion = tabla.selection()
        if not seleccion:
            return
        material = obtener_material_visible(seleccion[0])
        if not material:
            return

        disponible = cantidad_disponible(material)
        clave = id(material)
        actual = seleccionados.get(clave, disponible)

        dialogo = tk.Toplevel(ventana)
        dialogo.title("Cantidad a trasladar")
        dialogo.geometry("450x240")
        dialogo.resizable(False, False)
        dialogo.transient(ventana)
        dialogo.grab_set()

        marco_cantidad = ttk.Frame(dialogo, padding=20)
        marco_cantidad.pack(fill="both", expand=True)
        ttk.Label(
            marco_cantidad,
            text=material.get("material") or "Material",
            font=("Segoe UI", 11, "bold"),
            wraplength=400,
        ).pack(anchor="w")
        ttk.Label(
            marco_cantidad,
            text=f"Stock disponible: {cantidad_formateada(disponible)} {material.get('unidad') or ''}",
        ).pack(anchor="w", pady=(8, 4))
        ttk.Label(marco_cantidad, text="Cantidad a trasladar:").pack(anchor="w", pady=(6, 2))

        entrada = ttk.Entry(marco_cantidad, width=24)
        entrada.insert(0, cantidad_formateada(actual))
        entrada.pack(anchor="w", pady=(2, 12))
        entrada.focus_set()
        entrada.select_range(0, "end")

        def aceptar():
            try:
                cantidad = float(entrada.get().replace(",", "."))
            except ValueError:
                messagebox.showerror("Cantidad", "Ingresá una cantidad numérica válida.", parent=dialogo)
                return
            if cantidad <= 0:
                messagebox.showwarning("Cantidad", "La cantidad debe ser mayor que cero.", parent=dialogo)
                return
            if cantidad > disponible:
                messagebox.showwarning(
                    "Stock insuficiente",
                    f"No podés trasladar {cantidad:g}. El stock disponible es {disponible:g}.",
                    parent=dialogo,
                )
                return

            seleccionados[clave] = cantidad
            dialogo.destroy()
            cargar_tabla()
            iid = str(clave)
            if iid in tabla.get_children():
                tabla.selection_set(iid)
                tabla.focus(iid)

        botones_cantidad = ttk.Frame(marco_cantidad)
        botones_cantidad.pack(fill="x")
        ttk.Button(botones_cantidad, text="Guardar", command=aceptar).pack(side="right", padx=(6, 0))
        ttk.Button(botones_cantidad, text="Cancelar", command=dialogo.destroy).pack(side="right")
        dialogo.bind("<Return>", lambda _event: aceptar())

    def click_tabla(event):
        region = tabla.identify("region", event.x, event.y)
        columna = tabla.identify_column(event.x)
        fila = tabla.identify_row(event.y)
        if region != "cell" or not fila:
            return
        if columna != "#1":
            return
        material = obtener_material_visible(fila)
        if material:
            alternar_seleccion(material)

    def doble_click_tabla(event):
        region = tabla.identify("region", event.x, event.y)
        columna = tabla.identify_column(event.x)
        if region != "cell":
            return
        # La palomita se maneja con un clic. En el resto de la fila,
        # doble clic abre directamente la edición de cantidad.
        if columna == "#1":
            return
        modificar_cantidad()

    tabla.bind("<Button-1>", click_tabla)
    tabla.bind("<Double-1>", doble_click_tabla)

    def quitar_seleccion():
        seleccion = tabla.selection()
        if not seleccion:
            messagebox.showwarning("Selección", "Seleccioná un material de la lista.", parent=ventana)
            return
        material = obtener_material_visible(seleccion[0])
        if material:
            seleccionados.pop(id(material), None)
            cargar_tabla()

    def seleccionar_todo():
        for material in visibles:
            seleccionados[id(material)] = seleccionados.get(id(material), cantidad_disponible(material))
        cargar_tabla()

    def deseleccionar_todo():
        for material in visibles:
            seleccionados.pop(id(material), None)
        cargar_tabla()

    def generar():
        if not seleccionados:
            messagebox.showwarning("Relación de Tránsito", "Marcá al menos un material con la palomita.", parent=ventana)
            return
        if not tipo.get().strip() or not destino.get().strip():
            messagebox.showwarning("Datos incompletos", "Completá Tipo y Destino antes de generar.", parent=ventana)
            return

        transporte_var = tk.StringVar()
        transporte_dialogo = tk.Toplevel(ventana)
        transporte_dialogo.title("Transporte")
        transporte_dialogo.geometry("430x190")
        transporte_dialogo.resizable(False, False)
        transporte_dialogo.transient(ventana)
        transporte_dialogo.grab_set()

        marco_transporte = ttk.Frame(transporte_dialogo, padding=20)
        marco_transporte.pack(fill="both", expand=True)
        ttk.Label(marco_transporte, text="Transporte", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        entrada_transporte = ttk.Entry(marco_transporte, textvariable=transporte_var, width=42)
        entrada_transporte.pack(fill="x", pady=(6, 14))
        entrada_transporte.focus_set()

        def confirmar_generacion():
            transporte = transporte_var.get().strip()
            if not transporte:
                messagebox.showwarning("Transporte", "Completá el transporte.", parent=transporte_dialogo)
                return
            transporte_dialogo.destroy()

            materiales_relacion = []
            for material in materiales:
                clave = id(material)
                if clave not in seleccionados:
                    continue
                copia = dict(material)
                copia["cantidad"] = seleccionados[clave]
                materiales_relacion.append(copia)

            nombre_archivo = f"RELACION DE TRANSITO_{datetime.now():%Y%m%d_%H%M%S}.xlsx"
            salida = filedialog.asksaveasfilename(
                parent=ventana,
                title="Guardar Relación de Tránsito",
                defaultextension=".xlsx",
                initialfile=nombre_archivo,
                filetypes=[("Excel", "*.xlsx")],
            )
            if not salida:
                return

            try:
                app.generar_relacion_transito(
                    materiales=materiales_relacion,
                    salida=salida,
                    tipo_movimiento=tipo.get().strip(),
                    destino=destino.get().strip(),
                    transporte=transporte,
                    generar_pdf=generar_pdf.get(),
                )
                messagebox.showinfo(
                    "Relación de Tránsito",
                    f"La relación se generó correctamente con {len(materiales_relacion)} material(es).\n\nExcel:\n{salida}"
                    + (f"\n\nPDF:\n{salida.rsplit('.', 1)[0]}.pdf" if generar_pdf.get() else ""),
                    parent=ventana,
                )
                ventana.destroy()
            except app.RelacionTransitoError as error:
                traceback.print_exc()
                messagebox.showerror("Relación de Tránsito", f"No se pudo generar la relación:\n\n{error}", parent=ventana)
            except Exception as error:
                traceback.print_exc()
                messagebox.showerror("Relación de Tránsito", f"Ocurrió un error inesperado:\n\n{error}", parent=ventana)

        botones_transporte = ttk.Frame(marco_transporte)
        botones_transporte.pack(fill="x")
        ttk.Button(botones_transporte, text="Generar relación", command=confirmar_generacion).pack(side="right", padx=(6, 0))
        ttk.Button(botones_transporte, text="Cancelar", command=transporte_dialogo.destroy).pack(side="right")
        transporte_dialogo.bind("<Return>", lambda _event: confirmar_generacion())

    botones = ttk.Frame(marco)
    botones.pack(fill="x", pady=(10, 0))
    ttk.Button(botones, text="☑ Seleccionar todo", command=seleccionar_todo).pack(side="left", padx=(0, 6))
    ttk.Button(botones, text="☐ Deseleccionar todo", command=deseleccionar_todo).pack(side="left", padx=(0, 6))
    ttk.Button(botones, text="❌ Quitar selección", command=quitar_seleccion).pack(side="left")
    ttk.Button(botones, text="Generar Relación de Tránsito", command=generar).pack(side="right")
    ttk.Button(botones, text="Cerrar", command=ventana.destroy).pack(side="right", padx=(0, 8))

    busqueda.trace_add("write", cargar_tabla)
    cargar_tabla()
    ventana.bind("<Escape>", lambda _event: ventana.destroy())


