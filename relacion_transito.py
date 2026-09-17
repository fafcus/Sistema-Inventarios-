from __future__ import annotations

from copy import copy
from datetime import datetime
from pathlib import Path
from typing import Iterable, Mapping

from openpyxl import load_workbook
from openpyxl.styles import Alignment

from config import supabase
from relacion_transito_pdf import convertir_excel_a_pdf, descontar_materiales_relacion, RelacionTransitoPDFError
from relacion_transito_origenes import obtener_origenes_material
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
            raise RelacionTransitoError(f"No se encontró el campo '{textos[0]}' en la plantilla.")
        return False
    _asignar_valor(ws, celda.coordinate, valor)
    return True


def _columna_observaciones(ws):
    encabezado = _buscar_rotulo(ws, ["OBSERVACIONES", "OBSERVACIONES / UBICACIÓN"])
    return encabezado.column if encabezado else 7


def _fuentes_material(material_id):
    try:
        items = (
            supabase.table("documento_items")
            .select("documento_id,ubicacion,observaciones")
            .eq("material_id", int(material_id))
            .execute().data or []
        )
        ids = sorted({int(x["documento_id"]) for x in items if x.get("documento_id") is not None})
        documentos = {}
        if ids:
            docs = supabase.table("documentos").select("id,nombre").in_("id", ids).execute().data or []
            documentos = {int(x["id"]): _texto(x.get("nombre")) for x in docs}
        ubicaciones, origenes, observaciones = [], [], []
        for item in items:
            ubicacion = _texto(item.get("ubicacion"))
            if ubicacion and ubicacion != "-" and ubicacion not in ubicaciones:
                ubicaciones.append(ubicacion)
            origen = documentos.get(int(item["documento_id"])) if item.get("documento_id") is not None else ""
            if origen and origen not in origenes:
                origenes.append(origen)
            obs = _texto(item.get("observaciones"))
            if obs and obs != "-" and obs not in observaciones:
                observaciones.append(obs)
        return ubicaciones, origenes, observaciones
    except Exception:
        return [], [], []


def _enriquecer_material(material):
    """Completa origen/ubicación solo cuando la fila no ya identifica un origen."""
    copia = dict(material)
    if copia.get("id") is None:
        return copia
    if copia.get("_documento_item_id") is not None or copia.get("_documento_id") is not None:
        return copia
    ubicaciones, origenes, observaciones = _fuentes_material(copia["id"])
    if ubicaciones:
        copia["_ubicaciones_fuente"] = ubicaciones
        copia["ubicacion"] = " / ".join(ubicaciones)
    if origenes:
        copia["_origenes_fuente"] = origenes
        copia["archivo_origen"] = " / ".join(origenes)
    if observaciones:
        copia["_observaciones_fuente"] = observaciones
    return copia


def _obtener_filas_origen(material):
    mid = material.get("id")
    if mid is None:
        return []
    try:
        origenes = obtener_origenes_material(int(mid)) or []
    except Exception:
        origenes = []
    filas = []
    for origen in origenes:
        stock = float(origen.get("stock_disponible") or 0)
        if stock <= 0:
            continue
        fila = dict(material)
        fila["_documento_item_id"] = origen.get("documento_item_id")
        fila["_documento_id"] = origen.get("documento_id")
        fila["archivo_origen"] = _texto(origen.get("archivo_origen"))
        fila["ubicacion"] = _texto(origen.get("ubicacion")) or _texto(material.get("ubicacion"))
        fila["_stock_origen"] = stock
        fila["_origen_clave"] = f"{origen.get('documento_id')}:{origen.get('documento_item_id')}"
        filas.append(fila)
    return filas


def _seleccionar_materiales_desde_general(material_inicial):
    """Selector general simple: cada fila representa un origen real del inventario."""
    import tkinter as tk
    from tkinter import ttk, messagebox, simpledialog
    try:
        todos = obtener_materiales() or []
    except Exception as error:
        raise RelacionTransitoError(f"No se pudo cargar el inventario general: {error}") from error
    if not todos:
        raise RelacionTransitoError("No hay materiales cargados en el inventario general.")
    root = tk._default_root
    ventana = tk.Toplevel(root) if root is not None else tk.Tk()
    ventana.title("Materiales a llevar - Inventario general")
    ventana.geometry("1250x650")
    if root is not None:
        ventana.transient(root)
        ventana.grab_set()
    marco = ttk.Frame(ventana, padding=10)
    marco.pack(fill="both", expand=True)
    ttk.Label(marco, text="Seleccioná los materiales que se llevarán en la Relación de Tránsito.", font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(0, 6))
    ttk.Label(marco, text="Cada fila representa un origen: archivo/documento, ubicación y stock disponible.").pack(anchor="w", pady=(0, 8))
    columnas = ("codigo", "material", "unidad", "ubicacion", "origen", "stock")
    tabla = ttk.Treeview(marco, columns=columnas, show="headings", selectmode="extended")
    encabezados = {"codigo": "Código", "material": "Material", "unidad": "Unidad", "ubicacion": "Ubicación", "origen": "Archivo de origen", "stock": "Stock disponible"}
    anchos = {"codigo": 140, "material": 350, "unidad": 90, "ubicacion": 190, "origen": 230, "stock": 120}
    for columna in columnas:
        tabla.heading(columna, text=encabezados[columna])
        tabla.column(columna, width=anchos[columna], anchor="w")
    scroll = ttk.Scrollbar(marco, orient="vertical", command=tabla.yview)
    tabla.configure(yscrollcommand=scroll.set)
    tabla.pack(side="left", fill="both", expand=True)
    scroll.pack(side="right", fill="y")
    por_iid = {}
    contador = 0
    filas_iniciales = []
    for material in todos:
        origenes = _obtener_filas_origen(material)
        if origenes:
            filas_iniciales.extend(origenes)
            continue
        try:
            stock = float(obtener_stock_general_material(material.get("id")) or 0)
        except Exception:
            stock = 0
        if stock > 0:
            fila = dict(material)
            fila["_stock_origen"] = stock
            fila["_origen_clave"] = f"global:{material.get('id')}"
            filas_iniciales.append(fila)
    for material in filas_iniciales:
        contador += 1
        iid = f"r{contador}"
        por_iid[iid] = material
        stock = float(material.get("_stock_origen") or 0)
        tabla.insert("", "end", iid=iid, values=(_texto(material.get("codigo")), _texto(material.get("material")), _texto(material.get("unidad")), _texto(material.get("ubicacion")) or "-", _texto(material.get("archivo_origen")) or "-", _numero(stock)))
    resultado = []
    def aceptar():
        seleccion = tabla.selection()
        if not seleccion:
            messagebox.showwarning("Materiales", "Seleccioná al menos un origen/material.", parent=ventana)
            return
        seleccionados = []
        for iid in seleccion:
            material = por_iid.get(iid)
            if not material:
                continue
            stock = float(material.get("_stock_origen") or 0)
            if stock <= 0:
                messagebox.showwarning("Stock", f"'{_texto(material.get('material'))}' no tiene stock disponible.", parent=ventana)
                return
            cantidad = simpledialog.askfloat("Cantidad a llevar", f"Material: {_texto(material.get('material'))}\nCódigo: {_texto(material.get('codigo'))}\nUbicación: {_texto(material.get('ubicacion')) or '-'}\nOrigen: {_texto(material.get('archivo_origen')) or '-'}\nStock disponible en este origen: {_numero(stock)}\n\nCantidad a llevar:", minvalue=0.0001, maxvalue=stock, parent=ventana)
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
    ventana.wait_window()
    return resultado


def generar_relacion_transito(materiales: Iterable[Mapping], salida: str | Path, tipo_movimiento: str = "", destino: str = "", transporte: str = "", fecha: datetime | str | None = None, plantilla: str | Path | None = None, usuario: str | None = None) -> Path:
    """Genera Excel/PDF y descuenta el stock retirado con trazabilidad."""
    materiales = list(materiales or [])
    if len(materiales) == 1 and not materiales[0].get("_documento_item_id"):
        materiales = _seleccionar_materiales_desde_general(materiales[0])
    plantilla = Path(plantilla or PLANTILLA_RELACION_TRANSITO)
    salida = Path(salida)
    if not plantilla.exists():
        raise RelacionTransitoError(f"No se encontró la plantilla de Relación de Tránsito: {plantilla}")
    if not materiales:
        raise RelacionTransitoError("No hay materiales para generar la relación de tránsito.")
    materiales = [_enriquecer_material(m) for m in materiales]
    for material in materiales:
        if material.get("id") is None:
            raise RelacionTransitoError(f"El material '{material.get('material') or material.get('codigo') or 'sin nombre'}' no tiene ID de base de datos.")
        try:
            cantidad = float(material.get("cantidad") or 0)
        except (TypeError, ValueError):
            raise RelacionTransitoError(f"Cantidad inválida para '{material.get('material') or material.get('codigo') or 'sin nombre'}'.")
        if cantidad <= 0:
            raise RelacionTransitoError(f"La cantidad a retirar debe ser mayor que cero para '{material.get('material') or material.get('codigo') or 'sin nombre'}'.")
        stock_limite = material.get("_stock_origen")
        if stock_limite is None:
            try:
                stock_limite = float(obtener_stock_general_material(material["id"]) or 0)
            except Exception as error:
                raise RelacionTransitoError(f"No se pudo verificar el stock de '{material.get('material') or material.get('codigo')}'.") from error
        else:
            stock_limite = float(stock_limite or 0)
        if cantidad > stock_limite + 1e-9:
            raise RelacionTransitoError(f"Stock insuficiente para '{material.get('material') or material.get('codigo')}'. Disponible en el origen: {_numero(stock_limite)}. Solicitado: {_numero(cantidad)}.")
    try:
        wb = load_workbook(plantilla)
    except Exception as error:
        raise RelacionTransitoError(f"No se pudo abrir la plantilla Excel: {error}") from error
    if "Hoja1" not in wb.sheetnames:
        raise RelacionTransitoError("La plantilla no contiene la hoja 'Hoja1'.")
    ws = wb["Hoja1"]
    fecha_texto = datetime.now().strftime("%d/%m/%Y")
    _escribir_al_lado_del_rotulo(ws, ["FECHA"], fecha_texto)
    _escribir_al_lado_del_rotulo(ws, ["TIPO DE MOVIMIENTO", "TIPO MOVIMIENTO"], _texto(tipo_movimiento), obligatorio=True)
    _escribir_al_lado_del_rotulo(ws, ["DESTINO"], _texto(destino), obligatorio=True)
    _escribir_al_lado_del_rotulo(ws, ["TRANSPORTE"], _texto(transporte), obligatorio=True)
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
        ubicacion = _texto(material.get("ubicacion")) or "Sin ubicación registrada"
        valores = {
            1: indice,
            2: _numero(material.get("cantidad")),
            3: _texto(material.get("material")),
            4: _texto(material.get("marca")),
            5: _texto(material.get("numero_serie")),
            6: _texto(material.get("numero_parte")) or _texto(material.get("codigo")),
            columna_obs: f"Ubicación: {ubicacion}",
        }
        for columna, valor in valores.items():
            _asignar_valor_fila(ws, fila, columna, valor)
        _celda_escritura(ws, ws.cell(fila, columna_obs).coordinate).alignment = Alignment(horizontal="left", vertical="center", wrap_text=True)
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
        raise RelacionTransitoError(f"No se pudo guardar la Relación de Tránsito: {error}") from error
    pdf_salida = salida.with_suffix(".pdf")
    try:
        convertir_excel_a_pdf(salida, pdf_salida)
    except RelacionTransitoPDFError as error:
        raise RelacionTransitoError(str(error)) from error
    try:
        resultado_stock = descontar_materiales_relacion(materiales, usuario=usuario, identificador_relacion=salida.stem)
    except RelacionTransitoPDFError as error:
        raise RelacionTransitoError("La relación Excel y PDF fueron generados, pero no se pudo descontar el stock:\n" f"{error}") from error
    generar_relacion_transito.ultimo_pdf = pdf_salida
    generar_relacion_transito.ultimo_resultado_stock = resultado_stock
    return salida


def generar_desde_inventario(materiales: Iterable[Mapping], carpeta_salida: str | Path, tipo_movimiento: str = "", destino: str = "", transporte: str = "", fecha: datetime | str | None = None, usuario: str | None = None) -> Path:
    carpeta_salida = Path(carpeta_salida)
    marca_fecha = datetime.now().strftime("%Y%m%d_%H%M%S")
    salida = carpeta_salida / f"RELACION DE TRANSITO_{marca_fecha}.xlsx"
    return generar_relacion_transito(materiales=materiales, salida=salida, tipo_movimiento=tipo_movimiento, destino=destino, transporte=transporte, fecha=fecha, usuario=usuario)