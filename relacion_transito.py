from __future__ import annotations

from copy import copy
from datetime import datetime
from pathlib import Path
from typing import Iterable, Mapping

import tkinter as tk
from tkinter import ttk, messagebox, simpledialog

from openpyxl import load_workbook
from openpyxl.styles import Alignment

from supabase_db import (
    obtener_materiales,
    obtener_documentos,
    obtener_items_documento,
)

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
    if origen.number_format:
        destino.number_format = origen.number_format
    if origen.alignment:
        destino.alignment = copy(origen.alignment)
    if origen.protection:
        destino.protection = copy(origen.protection)
    if origen.font:
        destino.font = copy(origen.font)
    if origen.fill:
        destino.fill = copy(origen.fill)
    if origen.border:
        destino.border = copy(origen.border)


def _preparar_fila(ws, fila: int, fila_modelo: int = 12) -> None:
    for columna in range(1, 8):
        origen = _celda_escritura(ws, ws.cell(fila_modelo, columna).coordinate)
        destino = _celda_escritura(ws, ws.cell(fila, columna).coordinate)
        _copiar_estilo(origen, destino)
    ws.row_dimensions[fila].height = ws.row_dimensions[fila_modelo].height


def _observaciones_con_ubicacion(material: Mapping) -> str:
    partes = []
    observaciones = _texto(material.get("observaciones"))
    ubicacion = _texto(material.get("ubicacion"))
    archivo = _texto(material.get("archivo_origen"))
    if observaciones:
        partes.append(observaciones)
    if ubicacion:
        partes.append(f"Ubicación: {ubicacion}")
    if archivo:
        partes.append(f"Archivo: {archivo}")
    return " | ".join(partes)


def _cargar_inventario_general() -> list[dict]:
    try:
        materiales = obtener_materiales() or []
        documentos = obtener_documentos() or []
    except Exception as error:
        raise RelacionTransitoError(f"No se pudo cargar el inventario general: {error}") from error

    materiales_por_id = {
        m.get("id"): dict(m) for m in materiales if m.get("id") is not None
    }
    resultado = []

    for documento in documentos:
        documento_id = documento.get("id")
        if documento_id is None:
            continue
        try:
            items = obtener_items_documento(documento_id) or []
        except Exception:
            continue
        for item in items:
            material = materiales_por_id.get(item.get("material_id"), {}).copy()
            if not material:
                continue
            registro = dict(material)
            registro["_documento_id"] = documento_id
            registro["_documento_nombre"] = _texto(documento.get("nombre"))
            registro["_documento_ruta"] = _texto(documento.get("ruta"))
            registro["_stock_disponible"] = _numero(item.get("cantidad"))
            for campo in ("codigo", "material", "unidad", "categoria", "ubicacion", "observaciones"):
                if item.get(campo) is not None:
                    registro[campo] = item.get(campo)
            if not registro.get("archivo_origen"):
                registro["archivo_origen"] = registro["_documento_nombre"]
            resultado.append(registro)

    resultado.sort(key=lambda x: (
        _texto(x.get("material")).lower(),
        _texto(x.get("codigo")).lower(),
        _texto(x.get("_documento_nombre")).lower(),
    ))
    return resultado


def formatear_numero_local(valor):
    try:
        numero = float(valor or 0)
        return str(int(numero)) if numero.is_integer() else f"{numero:g}"
    except (TypeError, ValueError):
        return str(valor or 0)


def _seleccionar_materiales_inventario_general(material_actual=None):
    registros = _cargar_inventario_general()
    if not registros:
        messagebox.showwarning("Relación de Tránsito", "No se encontraron materiales en los inventarios cargados.")
        return None

    ventana = tk.Toplevel()
    ventana.title("Seleccionar materiales para la Relación de Tránsito")
    ventana.geometry("1180x650")
    ventana.minsize(900, 500)
    ventana.grab_set()

    seleccionados = {}
    filas = {}
    resultado = []

    superior = ttk.Frame(ventana, padding=10)
    superior.pack(fill="x")
    ttk.Label(superior, text="Materiales del inventario general", font=("Segoe UI", 12, "bold")).pack(side="left")
    ttk.Label(superior, text="Marcá los materiales. Doble clic sobre CANTIDAD para modificarla.").pack(side="left", padx=18)

    busqueda = tk.StringVar()
    marco_busqueda = ttk.Frame(ventana, padding=(10, 0, 10, 8))
    marco_busqueda.pack(fill="x")
    ttk.Label(marco_busqueda, text="Buscar:").pack(side="left")
    ttk.Entry(marco_busqueda, textvariable=busqueda).pack(side="left", fill="x", expand=True, padx=(8, 0))

    columnas = ("llevar", "cantidad", "codigo", "material", "unidad", "ubicacion", "archivo")
    tabla = ttk.Treeview(ventana, columns=columnas, show="headings", selectmode="browse")
    tabla.pack(side="left", fill="both", expand=True, padx=(10, 0), pady=(0, 10))
    scroll = ttk.Scrollbar(ventana, orient="vertical", command=tabla.yview)
    scroll.pack(side="right", fill="y", padx=(0, 10), pady=(0, 10))
    tabla.configure(yscrollcommand=scroll.set)

    encabezados = {
        "llevar": "LLEVAR", "cantidad": "CANTIDAD", "codigo": "CÓDIGO",
        "material": "MATERIAL", "unidad": "UNIDAD", "ubicacion": "UBICACIÓN",
        "archivo": "ARCHIVO ORIGEN",
    }
    anchos = {"llevar": 70, "cantidad": 90, "codigo": 130, "material": 330,
              "unidad": 100, "ubicacion": 180, "archivo": 220}
    for columna in columnas:
        tabla.heading(columna, text=encabezados[columna])
        tabla.column(columna, width=anchos[columna], anchor="center")

    def coincide(registro, texto):
        if not texto:
            return True
        combinado = " ".join(_texto(registro.get(c)) for c in (
            "codigo", "material", "unidad", "ubicacion", "observaciones",
            "_documento_nombre", "archivo_origen"))
        return texto.lower() in combinado.lower()

    def repintar(*_):
        for item in tabla.get_children():
            tabla.delete(item)
        filas.clear()
        for indice, registro in enumerate(registros):
            if not coincide(registro, busqueda.get().strip()):
                continue
            clave = f"{registro.get('_documento_id')}:{registro.get('id')}:{indice}"
            filas[clave] = registro
            marcado = clave in seleccionados
            cantidad = seleccionados.get(clave, {}).get("cantidad", registro.get("_stock_disponible", 0))
            tabla.insert("", "end", iid=clave, values=(
                "☑" if marcado else "☐",
                formatear_numero_local(cantidad),
                _texto(registro.get("codigo")),
                _texto(registro.get("material")),
                _texto(registro.get("unidad")),
                _texto(registro.get("ubicacion")),
                _texto(registro.get("_documento_nombre")) or _texto(registro.get("archivo_origen")),
            ))

    def alternar(event):
        item_id = tabla.identify_row(event.y)
        columna = tabla.identify_column(event.x)
        if not item_id or columna != "#1":
            return
        registro = filas.get(item_id)
        if not registro:
            return
        if item_id in seleccionados:
            seleccionados.pop(item_id, None)
        else:
            disponible = _numero(registro.get("_stock_disponible"))
            if disponible <= 0:
                messagebox.showwarning("Sin stock", "El material no tiene stock disponible.", parent=ventana)
                return
            seleccionados[item_id] = {"registro": registro, "cantidad": disponible}
        repintar()

    def editar_cantidad(event):
        item_id = tabla.identify_row(event.y)
        columna = tabla.identify_column(event.x)
        if not item_id or columna != "#2" or item_id not in seleccionados:
            return
        registro = seleccionados[item_id]["registro"]
        disponible = float(registro.get("_stock_disponible", 0) or 0)
        actual = float(seleccionados[item_id]["cantidad"] or 0)
        cantidad = simpledialog.askfloat(
            "Cantidad a llevar",
            f"Material: {_texto(registro.get('material'))}\nDisponible: {formatear_numero_local(disponible)}\n\nCantidad a llevar:",
            initialvalue=actual, minvalue=0.0001, maxvalue=disponible, parent=ventana)
        if cantidad is not None:
            seleccionados[item_id]["cantidad"] = cantidad
            repintar()

    def aceptar():
        if not seleccionados:
            messagebox.showwarning("Relación de Tránsito", "Seleccioná al menos un material.", parent=ventana)
            return
        resultado.extend(dict(item["registro"], cantidad=item["cantidad"]) for item in seleccionados.values())
        ventana.destroy()

    tabla.bind("<Button-1>", alternar)
    tabla.bind("<Double-1>", editar_cantidad)
    busqueda.trace_add("write", repintar)

    botones = ttk.Frame(ventana, padding=10)
    botones.pack(fill="x")
    ttk.Button(botones, text="Cancelar", command=ventana.destroy).pack(side="right")
    ttk.Button(botones, text="Generar relación", command=aceptar).pack(side="right", padx=(0, 8))

    repintar()
    ventana.wait_window()
    return resultado


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
    """Encuentra la primera celda escribible inmediatamente después del rótulo.

    Si el rótulo está combinado, se salta todo el rango combinado y comienza
    exactamente en la celda que queda a su derecha. Así se conserva la
    composición original de la plantilla.
    """
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
    if encabezado:
        return encabezado.column
    return 7


def generar_relacion_transito(
    materiales: Iterable[Mapping],
    salida: str | Path,
    tipo_movimiento: str = "",
    destino: str = "",
    transporte: str = "",
    fecha: datetime | str | None = None,
    plantilla: str | Path | None = None,
) -> Path:
    materiales = list(materiales or [])
    if len(materiales) == 1:
        seleccionados = _seleccionar_materiales_inventario_general(materiales[0])
        if seleccionados is None:
            raise RelacionTransitoError("Operación cancelada por el usuario.")
        materiales = seleccionados

    plantilla = Path(plantilla or PLANTILLA_RELACION_TRANSITO)
    salida = Path(salida)
    if not plantilla.exists():
        raise RelacionTransitoError(f"No se encontró la plantilla de Relación de Tránsito: {plantilla}")
    if not materiales:
        raise RelacionTransitoError("No hay materiales para generar la relación de tránsito.")

    try:
        wb = load_workbook(plantilla)
    except Exception as error:
        raise RelacionTransitoError(f"No se pudo abrir la plantilla Excel: {error}") from error
    if "Hoja1" not in wb.sheetnames:
        raise RelacionTransitoError("La plantilla no contiene la hoja 'Hoja1'.")
    ws = wb["Hoja1"]

    # FECHA, TIPO, DESTINO y TRANSPORTE se escriben dinámicamente a la derecha
    # de sus rótulos. No se reemplaza ningún rótulo ni se altera su combinación.
    if fecha is None:
        fecha_texto = datetime.now().strftime("%d/%m/%Y")
    elif isinstance(fecha, datetime):
        fecha_texto = fecha.strftime("%d/%m/%Y")
    else:
        fecha_texto = _texto(fecha)

    _escribir_al_lado_del_rotulo(ws, ["FECHA"], fecha_texto)
    _escribir_al_lado_del_rotulo(ws, ["TIPO DE MOVIMIENTO", "TIPO MOVIMIENTO"], _texto(tipo_movimiento), obligatorio=True)
    _escribir_al_lado_del_rotulo(ws, ["DESTINO"], _texto(destino), obligatorio=True)
    _escribir_al_lado_del_rotulo(ws, ["TRANSPORTE"], _texto(transporte), obligatorio=True)

    fila_inicial = 12
    fila_modelo = 12
    filas_disponibles = max(0, ws.max_row - fila_inicial + 1)
    filas_necesarias = len(materiales)
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

        valores = {
            1: indice,
            2: _numero(material.get("cantidad")),
            3: _texto(material.get("material")),
            4: _texto(material.get("marca")),
            5: _texto(material.get("numero_serie")),
            6: _texto(material.get("numero_parte")) or _texto(material.get("codigo")),
            columna_obs: _observaciones_con_ubicacion(material),
        }
        for columna, valor in valores.items():
            _asignar_valor_fila(ws, fila, columna, valor)

        _celda_escritura(ws, ws.cell(fila, columna_obs).coordinate).alignment = Alignment(
            horizontal="left", vertical="center", wrap_text=True)

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
    return salida


def generar_desde_inventario(
    materiales: Iterable[Mapping],
    carpeta_salida: str | Path,
    tipo_movimiento: str = "",
    destino: str = "",
    transporte: str = "",
    fecha: datetime | str | None = None,
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
    )
