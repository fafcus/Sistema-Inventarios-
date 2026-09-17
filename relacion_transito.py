from __future__ import annotations

from copy import copy
from datetime import datetime
from pathlib import Path
from typing import Iterable, Mapping

from openpyxl import load_workbook
from openpyxl.styles import Alignment

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


def _observaciones_con_ubicacion(material: Mapping) -> str:
    """Genera las observaciones de la relación sin copiar las observaciones del material.

    Se conserva únicamente la información útil para identificar dónde se encuentra
    el material y de qué inventario/documento proviene.
    """
    partes = []
    ubicacion = _texto(material.get("ubicacion"))
    archivo = _texto(material.get("archivo_origen"))

    if ubicacion:
        partes.append(f"Ubicación: {ubicacion}")
    if archivo:
        partes.append(f"Archivo: {archivo}")

    return " | ".join(partes)


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


def generar_relacion_transito(
    materiales: Iterable[Mapping],
    salida: str | Path,
    tipo_movimiento: str = "",
    destino: str = "",
    transporte: str = "",
    fecha: datetime | str | None = None,
    plantilla: str | Path | None = None,
) -> Path:
    """Genera la Relación de Tránsito usando la plantilla oficial del proyecto.

    La fecha se carga automáticamente con la fecha del momento de generación.
    El parámetro fecha se mantiene por compatibilidad con llamadas anteriores,
    pero no permite reemplazar la fecha automática.
    """
    materiales = list(materiales or [])
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

    try:
        wb = load_workbook(plantilla)
    except Exception as error:
        raise RelacionTransitoError(
            f"No se pudo abrir la plantilla Excel: {error}"
        ) from error

    if "Hoja1" not in wb.sheetnames:
        raise RelacionTransitoError("La plantilla no contiene la hoja 'Hoja1'.")

    ws = wb["Hoja1"]

    # La fecha siempre se toma automáticamente del momento en que se genera
    # la relación, con formato DD/MM/AAAA.
    fecha_texto = datetime.now().strftime("%d/%m/%Y")

    # Los datos se escriben a la derecha de sus rótulos, sin moverlos ni
    # modificar la estructura de la plantilla.
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

    # Se conservan los ajustes visuales que ya tenía la relación.
    ws.freeze_panes = "A12"
    ws.sheet_view.showGridLines = False

    salida.parent.mkdir(parents=True, exist_ok=True)
    try:
        wb.save(salida)
    except Exception as error:
        raise RelacionTransitoError(
            f"No se pudo guardar la Relación de Tránsito: {error}"
        ) from error

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
