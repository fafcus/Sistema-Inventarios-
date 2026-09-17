from __future__ import annotations

from copy import copy
from datetime import datetime
from pathlib import Path
from typing import Iterable, Mapping

from openpyxl import load_workbook
from openpyxl.styles import Alignment

from relacion_transito_pdf import (
    convertir_excel_a_pdf,
    descontar_materiales_relacion,
    RelacionTransitoPDFError,
)
from supabase_db import obtener_materiales, obtener_stock_general_material

BASE_DIR = Path(__file__).resolve().parent
PLANTILLA_RELACION_TRANSITO = BASE_DIR / "plantillas" / "RELACION DE TRANSITO.xlsx"


class RelacionTransitoError(Exception):
    """Error controlado al generar una Relación de Tránsito."""


def _texto(valor) -> str:
    return "" if valor is None else str(valor).strip()


def _numero(valor):
    try:
        numero = float(valor or 0)
        return int(numero) if numero.is_integer() else numero
    except (TypeError, ValueError):
        return valor if valor is not None else ""


def _celda_escritura(ws, referencia: str):
    """Devuelve la celda superior izquierda si la referencia está combinada."""
    celda = ws[referencia]
    for rango in ws.merged_cells.ranges:
        if celda.coordinate in rango:
            return ws.cell(rango.min_row, rango.min_col)
    return celda


def _asignar_valor(ws, referencia: str, valor) -> None:
    _celda_escritura(ws, referencia).value = valor


def _asignar_valor_fila(ws, fila: int, columna: int, valor) -> None:
    _asignar_valor(ws, ws.cell(fila, columna).coordinate, valor)


def _copiar_estilo(origen, destino) -> None:
    if origen.has_style:
        destino._style = copy(origen._style)
    destino.number_format = origen.number_format
    destino.alignment = copy(origen.alignment)
    destino.protection = copy(origen.protection)
    destino.font = copy(origen.font)
    destino.fill = copy(origen.fill)
    destino.border = copy(origen.border)


def _preparar_fila(ws, fila: int, fila_modelo: int = 12) -> None:
    for columna in range(1, 8):
        origen = _celda_escritura(ws, ws.cell(fila_modelo, columna).coordinate)
        destino = _celda_escritura(ws, ws.cell(fila, columna).coordinate)
        _copiar_estilo(origen, destino)
    ws.row_dimensions[fila].height = ws.row_dimensions[fila_modelo].height


def _buscar_rotulo(ws, textos, max_row=None, max_col=None):
    """Busca un rótulo de la plantilla por texto, sin asumir coordenadas."""
    textos = [t.upper() for t in textos]
    max_row = max_row or ws.max_row
    max_col = max_col or ws.max_column
    for fila in ws.iter_rows(min_row=1, max_row=max_row, min_col=1, max_col=max_col):
        for celda in fila:
            valor = _texto(celda.value).upper()
            if any(valor == texto or valor.startswith(texto) for texto in textos):
                return celda
    return None


def _celda_al_lado_del_rotulo(ws, textos):
    """Encuentra la celda inmediatamente a la derecha del rótulo, respetando merges."""
    rotulo = _buscar_rotulo(ws, textos)
    if rotulo is None:
        return None

    fin_columna = rotulo.column
    for rango in ws.merged_cells.ranges:
        if rotulo.coordinate in rango:
            fin_columna = rango.max_col
            break

    return ws.cell(rotulo.row, fin_columna + 1)


def _escribir_al_lado_del_rotulo(ws, textos, valor, obligatorio=False):
    celda = _celda_al_lado_del_rotulo(ws, textos)
    if celda is None:
        if obligatorio:
            raise RelacionTransitoError(
                f"No se encontró el campo '{textos[0]}' en la plantilla."
            )
        return False

    _asignar_valor(ws, celda.coordinate, valor)
    return True


def _columna_observaciones(ws):
    encabezado = _buscar_rotulo(
        ws,
        ["OBSERVACIONES", "OBSERVACIONES / UBICACIÓN"],
    )
    if encabezado:
        return encabezado.column
    return 7


def _seleccionar_materiales_desde_general(material_inicial):
    """Permite elegir varios materiales desde el inventario general.

    Se activa cuando la UI antigua entrega solamente un material. Así no es
    necesario cambiar el resto de la aplicación: la Relación de Tránsito pasa
    a poder armarse con materiales provenientes de cualquiera de los archivos
    importados en la base general.
    """
    import tkinter as tk
    from tkinter import ttk, messagebox, simpledialog

    try:
        todos = obtener_materiales() or []
    except Exception as error:
        raise RelacionTransitoError(
            f"No se pudo cargar el inventario general: {error}"
        ) from error

    if not todos:
        raise RelacionTransitoError("No hay materiales cargados en el inventario general.")

    root = tk._default_root
    ventana = tk.Toplevel(root) if root is not None else tk.Tk()
    ventana.title("Materiales a llevar - Inventario general")
    ventana.geometry("1100x600")
    ventana.transient(root)
    ventana.grab_set()

    marco = ttk.Frame(ventana, padding=10)
    marco.pack(fill="both", expand=True)

    ttk.Label(
        marco,
        text="Seleccioná los materiales que se llevarán en la Relación de Tránsito.",
        font=("Segoe UI", 11, "bold"),
    ).pack(anchor="w", pady=(0, 8))

    ttk.Label(
        marco,
        text="La lista proviene del inventario general, por lo que incluye materiales de todos los archivos importados.",
    ).pack(anchor="w", pady=(0, 8))

    columnas = ("codigo", "material", "unidad", "ubicacion", "stock")
    tabla = ttk.Treeview(marco, columns=columnas, show="headings", selectmode="extended")
    encabezados = {
        "codigo": "Código",
        "material": "Material",
        "unidad": "Unidad",
        "ubicacion": "Ubicación",
        "stock": "Stock disponible",
    }
    anchos = {"codigo": 150, "material": 420, "unidad": 100, "ubicacion": 180, "stock": 130}
    for columna in columnas:
        tabla.heading(columna, text=encabezados[columna])
        tabla.column(columna, width=anchos[columna], anchor="w")

    scroll = ttk.Scrollbar(marco, orient="vertical", command=tabla.yview)
    tabla.configure(yscrollcommand=scroll.set)
    tabla.pack(side="left", fill="both", expand=True)
    scroll.pack(side="right", fill="y")

    por_id = {}
    for material in todos:
        mid = material.get("id")
        if mid is None:
            continue
        por_id[str(mid)] = material
        try:
            stock = float(obtener_stock_general_material(mid) or 0)
        except Exception:
            stock = 0
        tabla.insert(
            "",
            "end",
            iid=str(mid),
            values=(
                _texto(material.get("codigo")),
                _texto(material.get("material")),
                _texto(material.get("unidad")),
                _texto(material.get("ubicacion")) or "-",
                _numero(stock),
            ),
        )

    resultado = []

    def aceptar():
        seleccion = tabla.selection()
        if not seleccion:
            messagebox.showwarning(
                "Materiales",
                "Seleccioná al menos un material.",
                parent=ventana,
            )
            return

        seleccionados = []
        for iid in seleccion:
            material = por_id.get(iid)
            if not material:
                continue
            try:
                stock = float(obtener_stock_general_material(material.get("id")) or 0)
            except Exception:
                stock = 0
            if stock <= 0:
                messagebox.showwarning(
                    "Stock",
                    f"'{_texto(material.get('material'))}' no tiene stock disponible.",
                    parent=ventana,
                )
                return

            cantidad = simpledialog.askfloat(
                "Cantidad a llevar",
                f"Material: {_texto(material.get('material'))}\n"
                f"Código: {_texto(material.get('codigo'))}\n"
                f"Ubicación: {_texto(material.get('ubicacion')) or '-'}\n"
                f"Stock disponible: {_numero(stock)}\n\n"
                "Cantidad a llevar:",
                minvalue=0.0001,
                maxvalue=stock,
                parent=ventana,
            )
            if cantidad is None:
                return

            copia = dict(material)
            copia["cantidad"] = cantidad
            copia["_stock_general"] = stock
            seleccionados.append(copia)

        resultado.extend(seleccionados)
        ventana.destroy()

    def cancelar():
        ventana.destroy()

    botones = ttk.Frame(marco)
    botones.pack(fill="x", pady=(10, 0))
    ttk.Button(botones, text="Generar con seleccionados", command=aceptar).pack(side="right", padx=(5, 0))
    ttk.Button(botones, text="Cancelar", command=cancelar).pack(side="right")

    if material_inicial and material_inicial.get("id") is not None:
        iid = str(material_inicial.get("id"))
        if iid in por_id:
            tabla.selection_set(iid)
            tabla.focus(iid)
            tabla.see(iid)

    ventana.wait_window()

    return resultado


def generar_relacion_transito(
    materiales: Iterable[Mapping],
    salida: str | Path,
    tipo_movimiento: str = "",
    destino: str = "",
    transporte: str = "",
    fecha: datetime | str | None = None,
    plantilla: str | Path | None = None,
    usuario: str | None = None,
) -> Path:
    """Genera la Relación de Tránsito, su PDF y descuenta el stock retirado."""
    materiales = list(materiales or [])

    # La interfaz actual de main.py entrega inicialmente un solo material.
    # En ese caso abrimos el selector contra el inventario general para que
    # la relación pueda contener materiales de todos los archivos importados.
    if len(materiales) == 1 and materiales[0].get("_documento_item_id") is not None:
        materiales = _seleccionar_materiales_desde_general(materiales[0])

    plantilla = Path(plantilla or PLANTILLA_RELACION_TRANSITO)
    salida = Path(salida)

    if not plantilla.exists():
        raise RelacionTransitoError(
            f"No se encontró la plantilla de Relación de Tránsito: {plantilla}"
        )
    if not materiales:
        raise RelacionTransitoError(
            "No hay materiales para generar la relación de tránsito."
        )

    for material in materiales:
        if material.get("id") is None:
            raise RelacionTransitoError(
                f"El material '{material.get('material') or material.get('codigo') or 'sin nombre'}' "
                "no tiene ID de base de datos."
            )
        try:
            cantidad = float(material.get("cantidad") or 0)
        except (TypeError, ValueError):
            raise RelacionTransitoError(
                f"Cantidad inválida para '{material.get('material') or material.get('codigo') or 'sin nombre'}'."
            )
        if cantidad <= 0:
            raise RelacionTransitoError(
                f"La cantidad a retirar debe ser mayor que cero para '{material.get('material') or material.get('codigo') or 'sin nombre'}'."
            )

    try:
        wb = load_workbook(plantilla)
    except Exception as error:
        raise RelacionTransitoError(
            f"No se pudo abrir la plantilla Excel: {error}"
        ) from error

    if "Hoja1" not in wb.sheetnames:
        raise RelacionTransitoError("La plantilla no contiene la hoja 'Hoja1'.")

    ws = wb["Hoja1"]
    fecha_texto = datetime.now().strftime("%d/%m/%Y")

    _escribir_al_lado_del_rotulo(ws, ["FECHA"], fecha_texto)
    _escribir_al_lado_del_rotulo(
        ws,
        ["TIPO DE MOVIMIENTO", "TIPO MOVIMIENTO"],
        _texto(tipo_movimiento),
        obligatorio=True,
    )
    _escribir_al_lado_del_rotulo(
        ws,
        ["DESTINO"],
        _texto(destino),
        obligatorio=True,
    )
    _escribir_al_lado_del_rotulo(
        ws,
        ["TRANSPORTE"],
        _texto(transporte),
        obligatorio=True,
    )

    fila_inicial = 12
    fila_modelo = 12
    filas_necesarias = len(materiales)
    filas_disponibles = max(0, ws.max_row - fila_inicial + 1)

    if filas_necesarias > filas_disponibles:
        filas_extra = filas_necesarias - filas_disponibles
        ws.insert_rows(ws.max_row + 1, amount=filas_extra)
        for fila in range(ws.max_row - filas_extra + 1, ws.max_row + 1):
            _preparar_fila(ws, fila, fila_modelo)

    columna_obs = _columna_observaciones(ws)

    for indice, material in enumerate(materiales, start=1):
        fila = fila_inicial + indice - 1

        if fila != fila_modelo:
            _preparar_fila(ws, fila, fila_modelo)

        ubicacion = _texto(material.get("ubicacion"))
        observaciones = f"Ubicación: {ubicacion}" if ubicacion else ""

        valores = {
            1: indice,
            2: _numero(material.get("cantidad")),
            3: _texto(material.get("material")),
            4: _texto(material.get("marca")),
            5: _texto(material.get("numero_serie")),
            6: _texto(material.get("numero_parte")) or _texto(material.get("codigo")),
            columna_obs: observaciones,
        }

        for columna, valor in valores.items():
            _asignar_valor_fila(ws, fila, columna, valor)

        _celda_escritura(
            ws,
            ws.cell(fila, columna_obs).coordinate,
        ).alignment = Alignment(
            horizontal="left",
            vertical="center",
            wrap_text=True,
        )

    ultima_fila = fila_inicial + filas_necesarias - 1
    for fila in range(ultima_fila + 1, ws.max_row + 1):
        for columna in range(1, min(ws.max_column, 7) + 1):
            _asignar_valor_fila(ws, fila, columna, None)

    ws.freeze_panes = "A12"
    ws.sheet_view.showGridLines = False

    salida.parent.mkdir(parents=True, exist_ok=True)
    try:
        wb.save(salida)
    except Exception as error:
        raise RelacionTransitoError(
            f"No se pudo guardar la Relación de Tránsito: {error}"
        ) from error

    pdf_salida = salida.with_suffix(".pdf")
    try:
        convertir_excel_a_pdf(salida, pdf_salida)
    except RelacionTransitoPDFError as error:
        raise RelacionTransitoError(str(error)) from error

    try:
        resultado_stock = descontar_materiales_relacion(
            materiales,
            usuario=usuario,
            identificador_relacion=salida.stem,
        )
    except RelacionTransitoPDFError as error:
        raise RelacionTransitoError(
            f"La relación Excel y PDF fueron generados, pero no se pudo descontar el stock:\n{error}"
        ) from error

    generar_relacion_transito.ultimo_pdf = pdf_salida
    generar_relacion_transito.ultimo_resultado_stock = resultado_stock

    return salida


def generar_desde_inventario(
    materiales: Iterable[Mapping],
    carpeta_salida: str | Path,
    tipo_movimiento: str = "",
    destino: str = "",
    transporte: str = "",
    fecha: datetime | str | None = None,
    usuario: str | None = None,
) -> Path:
    carpeta_salida = Path(carpeta_salida)
    marca_fecha = datetime.now().strftime("%Y%m%d_%H%M%S")
    salida = carpeta_salida / f"RELACION DE TRANSITO_{marca_fecha}.xlsx"

    return generar_relacion_transito(
        materiales=materiales,
        salida=salida,
        tipo_movimiento=tipo_movimiento,
        destino=destino,
        transporte=transporte,
        fecha=fecha,
        usuario=usuario,
    )
