"""Reportes del sistema de inventarios.

La lógica de generación de reportes está separada de la interfaz principal.
El módulo recibe la aplicación como dependencia para reutilizar su estado.
"""

from pathlib import Path
from datetime import datetime
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import traceback

# ============================================================
# REPORTES - UTILIDADES
# ============================================================

def obtener_movimientos_del_inventario(app):

    movimientos = app.obtener_movimientos_cache()

    nombre_archivo = (
        app.inventario_seleccionado or ""
    )

    resultado = []

    for movimiento in movimientos:

        if (
            nombre_archivo
            and movimiento.get("archivo_origen")
            and movimiento.get("archivo_origen")
            != nombre_archivo
        ):
            continue

        # Si existe documento_id, preferimos esa relación.
        documento_id = movimiento.get(
            "documento_id"
        )

        documento_actual_id = (
            app.obtener_documento_id_actual()
        )

        if (
            documento_actual_id is not None
            and documento_id is not None
        ):

            try:

                if int(documento_id) != int(
                    documento_actual_id
                ):
                    continue

            except Exception:
                pass

        resultado.append(movimiento)

    return resultado


def convertir_fecha_movimiento(valor):

    if not valor:
        return None

    texto = str(valor).strip()

    # ISO con fecha y hora
    try:

        return datetime.fromisoformat(
            texto.replace("Z", "+00:00")
        )

    except Exception:
        pass

    # ISO solamente fecha
    try:

        return datetime.strptime(
            texto[:10],
            "%Y-%m-%d"
        )

    except Exception:
        pass

    return None


def movimiento_dentro_de_fechas(
    movimiento,
    fecha_desde,
    fecha_hasta,
):

    fecha = convertir_fecha_movimiento(
        movimiento.get("fecha")
    )

    if fecha is None:
        return False

    # Quitamos timezone si solamente estamos
    # comparando fechas.
    fecha_solo = fecha.date()

    if fecha_desde:

        if fecha_solo < fecha_desde:
            return False

    if fecha_hasta:

        if fecha_solo > fecha_hasta:
            return False

    return True


# ============================================================
# REPORTE DE INVENTARIO
# ============================================================

def generar_reporte_inventario_excel(app):

    documento = app.obtener_documento_actual()

    if not documento:

        messagebox.showerror(
            "Reportes",
            "No se encontró el inventario seleccionado.",
            parent=app.root,
        )

        return

    try:

        from openpyxl import Workbook
        from openpyxl.styles import Font, Alignment

    except ImportError:

        messagebox.showerror(
            "Reportes",
            "Falta instalar openpyxl.\n\n"
            "Ejecutá:\n\n"
            "pip install openpyxl",
            parent=app.root,
        )

        return

    materiales = app.obtener_materiales_seleccionados()

    nombre_documento = (
        documento.get("nombre")
        or "inventario"
    )

    nombre_base = Path(
        nombre_documento
    ).stem

    fecha_actual = datetime.now().strftime(
        "%Y-%m-%d_%H-%M"
    )

    ruta = filedialog.asksaveasfilename(
        parent=app.root,
        title="Guardar reporte de inventario",
        defaultextension=".xlsx",
        initialfile=(
            f"Reporte_Inventario_"
            f"{nombre_base}_"
            f"{fecha_actual}.xlsx"
        ),
        filetypes=[
            (
                "Excel",
                "*.xlsx",
            ),
            (
                "Todos los archivos",
                "*.*",
            ),
        ],
    )

    if not ruta:
        return

    try:

        wb = Workbook()

        ws = wb.active
        ws.title = "Inventario"

        # ----------------------------------------------------
        # CABECERA
        # ----------------------------------------------------

        ws["A1"] = "INVENTARIO MATERIAL NAVAL"

        ws["A1"].font = Font(
            bold=True,
            size=16,
        )

        ws["A2"] = "Inventario:"
        ws["B2"] = nombre_documento

        ws["A3"] = "Fecha del reporte:"
        ws["B3"] = datetime.now().strftime(
            "%d/%m/%Y %H:%M"
        )

        # ----------------------------------------------------
        # ENCABEZADOS
        # ----------------------------------------------------

        encabezados = [
            "Código",
            "Material",
            "Cantidad",
            "Unidad",
            "Categoría",
            "Ubicación",
            "Observaciones",
            "Estado",
        ]

        fila_encabezado = 5

        for columna, encabezado in enumerate(
            encabezados,
            start=1,
        ):

            celda = ws.cell(
                row=fila_encabezado,
                column=columna,
            )

            celda.value = encabezado

            celda.font = Font(
                bold=True
            )

            celda.alignment = Alignment(
                horizontal="center"
            )

        # ----------------------------------------------------
        # DATOS
        # ----------------------------------------------------

        fila = fila_encabezado + 1

        for material in materiales:

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

            estado = (
                "HAY STOCK"
                if cantidad > 0
                else "SIN STOCK"
            )

            valores = [
                material.get("codigo") or "",
                material.get("material") or "",
                cantidad,
                material.get("unidad") or "",
                material.get("categoria") or "",
                material.get("ubicacion") or "",
                material.get("observaciones") or "",
                estado,
            ]

            for columna, valor in enumerate(
                valores,
                start=1,
            ):

                ws.cell(
                    row=fila,
                    column=columna,
                    value=valor,
                )

            fila += 1

        # ----------------------------------------------------
        # ANCHOS
        # ----------------------------------------------------

        anchos = {
            "A": 18,
            "B": 40,
            "C": 14,
            "D": 14,
            "E": 20,
            "F": 25,
            "G": 40,
            "H": 15,
        }

        for columna, ancho in anchos.items():

            ws.column_dimensions[
                columna
            ].width = ancho

        ws.freeze_panes = "A6"

        # ----------------------------------------------------
        # RESUMEN
        # ----------------------------------------------------

        fila_resumen = fila + 2

        total_materiales = len(
            materiales
        )

        con_stock = 0
        sin_stock = 0
        cantidad_total = 0

        for material in materiales:

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

            cantidad_total += cantidad

            if cantidad > 0:
                con_stock += 1
            else:
                sin_stock += 1

        ws.cell(
            row=fila_resumen,
            column=1,
            value="Resumen",
        ).font = Font(
            bold=True
        )

        ws.cell(
            row=fila_resumen + 1,
            column=1,
            value="Total materiales",
        )

        ws.cell(
            row=fila_resumen + 1,
            column=2,
            value=total_materiales,
        )

        ws.cell(
            row=fila_resumen + 2,
            column=1,
            value="Con stock",
        )

        ws.cell(
            row=fila_resumen + 2,
            column=2,
            value=con_stock,
        )

        ws.cell(
            row=fila_resumen + 3,
            column=1,
            value="Sin stock",
        )

        ws.cell(
            row=fila_resumen + 3,
            column=2,
            value=sin_stock,
        )

        ws.cell(
            row=fila_resumen + 4,
            column=1,
            value="Cantidad total",
        )

        ws.cell(
            row=fila_resumen + 4,
            column=2,
            value=cantidad_total,
        )

        wb.save(ruta)

        messagebox.showinfo(
            "Reporte generado",
            "El reporte de inventario se generó correctamente.\n\n"
            f"Archivo:\n{ruta}",
            parent=app.root,
        )

    except Exception as error:

        traceback.print_exc()

        messagebox.showerror(
            "Error",
            "No se pudo generar el reporte:\n\n"
            f"{error}",
            parent=app.root,
        )


# ============================================================
# REPORTE DE MOVIMIENTOS
# ============================================================

def generar_reporte_movimientos_excel(
    ventana=None,
    fecha_desde=None,
    fecha_hasta=None,
):

    documento = app.obtener_documento_actual()

    if not documento:

        messagebox.showerror(
            "Reportes",
            "No se encontró el inventario seleccionado.",
            parent=app.root,
        )

        return

    try:

        from openpyxl import Workbook
        from openpyxl.styles import Font, Alignment

    except ImportError:

        messagebox.showerror(
            "Reportes",
            "Falta instalar openpyxl.\n\n"
            "Ejecutá:\n\n"
            "pip install openpyxl",
            parent=app.root,
        )

        return

    movimientos = (
        obtener_movimientos_del_inventario()
    )

    movimientos_filtrados = []

    for movimiento in movimientos:

        if movimiento_dentro_de_fechas(
            movimiento,
            fecha_desde,
            fecha_hasta,
        ):

            movimientos_filtrados.append(
                movimiento
            )

    nombre_documento = (
        documento.get("nombre")
        or "inventario"
    )

    nombre_base = Path(
        nombre_documento
    ).stem

    fecha_actual = datetime.now().strftime(
        "%Y-%m-%d_%H-%M"
    )

    ruta = filedialog.asksaveasfilename(
        parent=ventana or app.root,
        title="Guardar reporte de movimientos",
        defaultextension=".xlsx",
        initialfile=(
            f"Reporte_Movimientos_"
            f"{nombre_base}_"
            f"{fecha_actual}.xlsx"
        ),
        filetypes=[
            (
                "Excel",
                "*.xlsx",
            ),
            (
                "Todos los archivos",
                "*.*",
            ),
        ],
    )

    if not ruta:
        return

    try:

        wb = Workbook()

        ws = wb.active
        ws.title = "Movimientos"

        # ----------------------------------------------------
        # CABECERA
        # ----------------------------------------------------

        ws["A1"] = (
            "HISTORIAL DE MOVIMIENTOS"
        )

        ws["A1"].font = Font(
            bold=True,
            size=16,
        )

        ws["A2"] = "Inventario:"
        ws["B2"] = nombre_documento

        ws["A3"] = "Generado:"
        ws["B3"] = datetime.now().strftime(
            "%d/%m/%Y %H:%M"
        )

        ws["A4"] = "Desde:"
        ws["B4"] = (
            fecha_desde.strftime("%d/%m/%Y")
            if fecha_desde
            else "Todos"
        )

        ws["A5"] = "Hasta:"
        ws["B5"] = (
            fecha_hasta.strftime("%d/%m/%Y")
            if fecha_hasta
            else "Todos"
        )

        # ----------------------------------------------------
        # ENCABEZADOS
        # ----------------------------------------------------

        encabezados = [
            "Fecha",
            "Código",
            "Material",
            "Tipo",
            "Cantidad",
            "Stock anterior",
            "Stock nuevo",
            "Usuario",
            "Archivo",
            "Observaciones",
        ]

        fila_encabezado = 7

        for columna, encabezado in enumerate(
            encabezados,
            start=1,
        ):

            celda = ws.cell(
                row=fila_encabezado,
                column=columna,
            )

            celda.value = encabezado

            celda.font = Font(
                bold=True
            )

            celda.alignment = Alignment(
                horizontal="center"
            )

        # ----------------------------------------------------
        # MATERIALES
        # ----------------------------------------------------

        materiales_por_id = {
            m.get("id"): m
            for m in app.obtener_materiales_cache()
        }

        fila = fila_encabezado + 1

        total_entradas = 0
        total_salidas = 0

        for movimiento in movimientos_filtrados:

            material = materiales_por_id.get(
                movimiento.get(
                    "material_id"
                )
            )

            tipo = (
                movimiento.get("tipo")
                or ""
            )

            try:

                cantidad = float(
                    movimiento.get(
                        "cantidad",
                        0,
                    )
                    or 0
                )

            except Exception:

                cantidad = 0

            if tipo.upper() in (
                "ENTRADA",
                "INGRESO",
                "ALTA",
            ):

                total_entradas += cantidad

            elif tipo.upper() in (
                "SALIDA",
                "RETIRO",
               "BAJA",
            ):

                total_salidas += cantidad

            valores = [
                movimiento.get("fecha") or "",
                (
                    material.get("codigo")
                    if material
                    else ""
                ),
                (
                    material.get("material")
                    if material
                    else "Material eliminado"
                ),
                tipo,
                cantidad,
                movimiento.get(
                    "stock_anterior"
                ) or 0,
                movimiento.get(
                    "stock_nuevo"
                ) or 0,
                movimiento.get("usuario") or "",
                movimiento.get(
                    "archivo_origen"
                ) or "",
                movimiento.get(
                    "observaciones"
                ) or "",
            ]

            for columna, valor in enumerate(
                valores,
                start=1,
            ):

                ws.cell(
                    row=fila,
                    column=columna,
                    value=valor,
                )

            fila += 1

        # ----------------------------------------------------
        # ANCHOS
        # ----------------------------------------------------

        anchos = {
            "A": 25,
            "B": 18,
            "C": 40,
            "D": 15,
            "E": 14,
            "F": 18,
            "G": 18,
            "H": 15,
            "I": 35,
            "J": 40,
        }

        for columna, ancho in anchos.items():

            ws.column_dimensions[
                columna
            ].width = ancho

        ws.freeze_panes = "A8"

        # ----------------------------------------------------
        # RESUMEN
        # ----------------------------------------------------

        fila_resumen = fila + 2

        ws.cell(
            row=fila_resumen,
            column=1,
            value="Resumen",
        ).font = Font(
            bold=True
        )

        ws.cell(
            row=fila_resumen + 1,
            column=1,
            value="Movimientos registrados",
        )

        ws.cell(
            row=fila_resumen + 1,
            column=2,
            value=len(
                movimientos_filtrados
            ),
        )

        ws.cell(
            row=fila_resumen + 2,
            column=1,
            value="Total entradas",
        )

        ws.cell(
            row=fila_resumen + 2,
            column=2,
            value=total_entradas,
        )

        ws.cell(
            row=fila_resumen + 3,
            column=1,
            value="Total salidas",
        )

        ws.cell(
            row=fila_resumen + 3,
            column=2,
            value=total_salidas,
        )

        wb.save(ruta)

        if ventana is not None:

            try:
                ventana.destroy()
            except Exception:
                pass

        messagebox.showinfo(
            "Reporte generado",
            "El reporte de movimientos se generó correctamente.\n\n"
            f"Movimientos incluidos: "
            f"{len(movimientos_filtrados)}\n\n"
            f"Archivo:\n{ruta}",
            parent=app.root,
        )

    except Exception as error:

        traceback.print_exc()

        messagebox.showerror(
            "Error",
            "No se pudo generar el reporte:\n\n"
            f"{error}",
            parent=ventana or app.root,
        )


# ============================================================
# VENTANA DE REPORTES
# ============================================================

def abrir_reportes(app):

    if not app.inventario_seleccionado:

        messagebox.showwarning(
            "Reportes",
            "Primero seleccioná un inventario.",
            parent=app.root,
        )

        return

    ventana = tk.Toplevel(app.root)

    ventana.title(
        "Reportes"
    )

    ventana.geometry(
        "560x470"
    )

    ventana.transient(app.root)
    ventana.grab_set()

    marco = ttk.Frame(
        ventana,
        padding=25,
    )

    marco.pack(
        fill="both",
        expand=True,
    )

    ttk.Label(
        marco,
        text="📊 Reportes",
        font=(
            "Segoe UI",
            18,
            "bold",
        ),
    ).pack(
        pady=(5, 8)
    )

    ttk.Label(
        marco,
        text=(
            f"Inventario: "
            f"{app.inventario_seleccionado}"
        ),
        foreground=app.COLOR_AZUL,
        font=(
            "Segoe UI",
            10,
            "bold",
        ),
    ).pack(
        pady=(0, 20)
    )

    # ========================================================
    # REPORTE INVENTARIO
    # ========================================================

    ttk.Label(
        marco,
        text="Inventario actual",
        font=(
            "Segoe UI",
            11,
            "bold",
        ),
    ).pack(
        anchor="w"
    )

    ttk.Label(
        marco,
        text=(
            "Genera un Excel con todos los materiales "
            "del inventario seleccionado."
        ),
        foreground=app.COLOR_TEXTO_SECUNDARIO,
    ).pack(
        anchor="w",
        pady=(2, 7),
    )

    ttk.Button(
        marco,
        text="📦 Generar reporte de inventario",
        command=lambda: generar_reporte_inventario_excel(app),
    ).pack(
        fill="x",
        pady=(0, 18),
        ipady=4,
    )

    # ========================================================
    # REPORTE MOVIMIENTOS
    # ========================================================

    ttk.Label(
        marco,
        text="Movimientos",
        font=(
            "Segoe UI",
            11,
            "bold",
        ),
    ).pack(
        anchor="w"
    )

    ttk.Label(
        marco,
        text=(
            "Podés generar el historial completo "
            "o seleccionar un período."
        ),
        foreground=app.COLOR_TEXTO_SECUNDARIO,
    ).pack(
        anchor="w",
        pady=(2, 8),
    )

    frame_fechas = ttk.Frame(
        marco
    )

    frame_fechas.pack(
        fill="x",
        pady=(0, 10),
    )

    ttk.Label(
        frame_fechas,
        text="Desde:",
    ).grid(
        row=0,
        column=0,
        sticky="w",
        padx=(0, 5),
    )

    entrada_desde = ttk.Entry(
        frame_fechas,
        width=15,
    )

    entrada_desde.grid(
        row=0,
        column=1,
        sticky="w",
        padx=(0, 15),
    )

    ttk.Label(
        frame_fechas,
        text="Hasta:",
    ).grid(
        row=0,
        column=2,
        sticky="w",
        padx=(0, 5),
    )

    entrada_hasta = ttk.Entry(
        frame_fechas,
        width=15,
    )

    entrada_hasta.grid(
        row=0,
        column=3,
        sticky="w",
    )

    ttk.Label(
        marco,
        text="Formato: DD/MM/AAAA",
        foreground=app.COLOR_TEXTO_SECUNDARIO,
    ).pack(
        anchor="w",
        pady=(0, 8),
    )

    def generar_movimientos():

        texto_desde = (
            entrada_desde
            .get()
            .strip()
        )

        texto_hasta = (
            entrada_hasta
            .get()
            .strip()
        )

        fecha_desde = None
        fecha_hasta = None

        if texto_desde:

            try:

                fecha_desde = datetime.strptime(
                    texto_desde,
                    "%d/%m/%Y",
                ).date()

            except ValueError:

                messagebox.showerror(
                    "Fecha",
                    "La fecha 'Desde' no es válida.\n\n"
                    "Usá el formato DD/MM/AAAA.",
                    parent=ventana,
                )

                return

        if texto_hasta:

            try:

                fecha_hasta = datetime.strptime(
                    texto_hasta,
                    "%d/%m/%Y",
                ).date()

            except ValueError:

                messagebox.showerror(
                    "Fecha",
                    "La fecha 'Hasta' no es válida.\n\n"
                    "Usá el formato DD/MM/AAAA.",
                    parent=ventana,
                )

                return

        if (
            fecha_desde
            and fecha_hasta
            and fecha_desde > fecha_hasta
        ):

            messagebox.showerror(
                "Fechas",
                "La fecha 'Desde' no puede ser posterior "
                "a la fecha 'Hasta'.",
                parent=ventana,
            )

            return

        generar_reporte_movimientos_excel(
            app,
            ventana=ventana,
            fecha_desde=fecha_desde,
            fecha_hasta=fecha_hasta,
        )

    ttk.Button(
        marco,
        text="📜 Generar reporte de movimientos",
        command=generar_movimientos,
    ).pack(
        fill="x",
        pady=(0, 18),
        ipady=4,
    )

    ttk.Button(
        marco,
        text="Cerrar",
        command=ventana.destroy,
    ).pack(
        pady=(0, 5)
    )
