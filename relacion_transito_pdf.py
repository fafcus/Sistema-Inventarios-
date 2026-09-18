from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

rom __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from supabase_db import (
    agregar_ajuste_stock,
    obtener_stock_general_material,
    obtener_stock_documento_material,
    actualizar_cantidad_documento_item,
)


class RelacionTransitoPDFError(Exception):
    """Error controlado al generar el PDF de una relación de tránsito."""


def _buscar_soffice() -> str | None:
    """Busca LibreOffice/soffice en las rutas habituales de Windows y PATH."""
    candidatos = [
        shutil.which("soffice"),
        shutil.which("libreoffice"),
        os.path.join(os.environ.get("PROGRAMFILES", ""), "LibreOffice", "program", "soffice.exe"),
        os.path.join(os.environ.get("PROGRAMFILES(X86)", ""), "LibreOffice", "program", "soffice.exe"),
    ]
    for candidato in candidatos:
        if candidato and Path(candidato).exists():
            return candidato
    return None


def _convertir_con_libreoffice(excel_path: Path, pdf_path: Path) -> Path | None:
    soffice = _buscar_soffice()
    if not soffice:
        return None

    carpeta = pdf_path.parent
    carpeta.mkdir(parents=True, exist_ok=True)
    comando = [
        soffice,
        "--headless",
        "--convert-to",
        "pdf",
        "--outdir",
        str(carpeta),
        str(excel_path),
    ]
    try:
        resultado = subprocess.run(
            comando,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except Exception:
        return None

    generado = carpeta / f"{excel_path.stem}.pdf"
    if resultado.returncode != 0 or not generado.exists():
        return None

    if generado.resolve() != pdf_path.resolve():
        if pdf_path.exists():
            pdf_path.unlink()
        generado.replace(pdf_path)
    return pdf_path


def _convertir_con_excel_windows(excel_path: Path, pdf_path: Path) -> Path | None:
    """Usa Microsoft Excel instalado en Windows para conservar el formato de la plantilla."""
    if os.name != "nt":
        return None

    # Primera opción: pywin32, si está disponible.
    try:
        import win32com.client  # type: ignore
    except Exception:
        win32com = None
    else:
        excel = None
        libro = None
        try:
            excel = win32com.client.DispatchEx("Excel.Application")
            excel.Visible = False
            excel.DisplayAlerts = False
            libro = excel.Workbooks.Open(str(excel_path.resolve()))
            libro.ExportAsFixedFormat(0, str(pdf_path.resolve()))
            if pdf_path.exists():
                return pdf_path
        except Exception:
            pass
        finally:
            try:
                if libro is not None:
                    libro.Close(False)
            except Exception:
                pass
            try:
                if excel is not None:
                    excel.Quit()
            except Exception:
                pass

    # Segunda opción: PowerShell + COM de Excel, sin instalar pywin32.
    powershell = shutil.which("powershell") or shutil.which("pwsh")
    if not powershell:
        return None

    script = (
        "$ErrorActionPreference='Stop'; "
        "$excel=New-Object -ComObject Excel.Application; "
        "$excel.Visible=$false; $excel.DisplayAlerts=$false; "
        f"$libro=$excel.Workbooks.Open('{str(excel_path.resolve()).replace(chr(39), chr(39)*2)}'); "
        f"$libro.ExportAsFixedFormat(0,'{str(pdf_path.resolve()).replace(chr(39), chr(39)*2)}'); "
        "$libro.Close($false); $excel.Quit();"
    )
    try:
        resultado = subprocess.run(
            [powershell, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", script],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        if resultado.returncode == 0 and pdf_path.exists():
            return pdf_path
    except Exception:
        pass
    return None


def convertir_excel_a_pdf(excel_path: str | Path, pdf_path: str | Path | None = None) -> Path:
    """Convierte la Relación de Tránsito XLSX a PDF manteniendo la plantilla."""
    excel_path = Path(excel_path)
    if not excel_path.exists():
        raise RelacionTransitoPDFError(f"No se encontró el Excel generado: {excel_path}")

    pdf_path = Path(pdf_path) if pdf_path else excel_path.with_suffix(".pdf")
    pdf_path.parent.mkdir(parents=True, exist_ok=True)

    generado = _convertir_con_libreoffice(excel_path, pdf_path)
    if generado:
        return generado

    generado = _convertir_con_excel_windows(excel_path, pdf_path)
    if generado:
        return generado

    raise RelacionTransitoPDFError(
        "No se pudo convertir la relación a PDF. "
        "Se necesita LibreOffice o Microsoft Excel instalado en esta PC."
    )


def descontar_materiales_relacion(materiales, usuario=None, identificador_relacion=None):
    """Descuenta cada salida del origen exacto en material_ubicaciones."""
    from inventario_db import actualizar_stock_ubicacion_exacta
    materiales = list(materiales or [])
    if not materiales:
        raise RelacionTransitoPDFError("La relación no contiene materiales para descontar.")
    pendientes = []
    for material in materiales:
        material_id = material.get("id")
        fila_id = material.get("_material_ubicacion_id")
        if material_id is None or fila_id is None:
            raise RelacionTransitoPDFError(f"El material '{material.get('material') or material.get('codigo') or 'sin nombre'}' no tiene un origen de inventario válido.")
        try:
            cantidad = float(material.get("cantidad") or 0)
        except (TypeError, ValueError):
            raise RelacionTransitoPDFError(f"Cantidad inválida para '{material.get('material') or material_id}'.")
        if cantidad <= 0:
            raise RelacionTransitoPDFError(f"La cantidad a retirar debe ser mayor que cero para '{material.get('material') or material_id}'.")
        stock = float(material.get("_stock_origen") or 0)
        if cantidad > stock + 0.000001:
            raise RelacionTransitoPDFError(f"Stock insuficiente para '{material.get('material') or material_id}'. Disponible: {stock:g}. A retirar: {cantidad:g}.")
        pendientes.append((material_id, fila_id, cantidad, stock, material))
    observacion = "Salida por Relación de Tránsito"
    if identificador_relacion:
        observacion += f": {identificador_relacion}"
    aplicados = []
    try:
        for material_id, fila_id, cantidad, stock, material in pendientes:
            actualizar_stock_ubicacion_exacta(
                fila_id=fila_id,
                nueva_cantidad=stock - cantidad,
                usuario=usuario,
                observaciones=observacion,
                archivo_origen=material.get("archivo_origen"),
                documento_id=material.get("_documento_id"),
            )
            aplicados.append((material_id, cantidad, fila_id))
        return {"materiales": len(aplicados), "cantidad_total": sum(cantidad for _, cantidad, _ in aplicados)}
    except Exception as error:
        raise RelacionTransitoPDFError(f"No se pudo completar el descuento del stock por origen: {error}") from error

