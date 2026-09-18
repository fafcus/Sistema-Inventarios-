from __future__ import annotations

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
    """Descuenta cada salida del origen exacto elegido en la relación.

    Si la fila identifica un documento_item, se descuenta de ese origen y se
    actualiza también el Word asociado. Los materiales sin origen explícito
    mantienen el comportamiento de ajuste global como respaldo.
    """
    materiales = list(materiales or [])
    if not materiales:
        raise RelacionTransitoPDFError("La relación no contiene materiales para descontar.")

    pendientes = []
    for material in materiales:
        material_id = material.get("id")
        if material_id is None:
            raise RelacionTransitoPDFError(
                f"El material '{material.get('material') or material.get('codigo') or 'sin nombre'}' "
                "no tiene ID de base de datos."
            )

        try:
            cantidad = float(material.get("cantidad") or 0)
        except (TypeError, ValueError):
            raise RelacionTransitoPDFError(
                f"Cantidad inválida para el material '{material.get('material') or material_id}'."
            )

        if cantidad <= 0:
            raise RelacionTransitoPDFError(
                f"La cantidad a retirar debe ser mayor que cero para '{material.get('material') or material_id}'."
            )

        documento_item_id = material.get("_documento_item_id")
        documento_id = material.get("_documento_id")

        try:
            if documento_item_id is not None and documento_id is not None:
                stock = float(obtener_stock_documento_material(documento_id, material_id) or 0)
                origen = str(material.get("archivo_origen") or documento_id)
            else:
                stock = float(obtener_stock_general_material(material_id) or 0)
                origen = "stock global"
        except Exception as error:
            raise RelacionTransitoPDFError(
                f"No se pudo verificar el stock de '{material.get('material') or material_id}': {error}"
            ) from error

        if cantidad > stock + 0.000001:
            raise RelacionTransitoPDFError(
                f"Stock insuficiente para '{material.get('material') or material_id}'. "
                f"Disponible en {origen}: {stock:g}. A retirar: {cantidad:g}."
            )

        pendientes.append((material_id, cantidad, stock, material, documento_item_id, documento_id))

    observacion_base = "Salida por Relación de Tránsito"
    if identificador_relacion:
        observacion_base += f": {identificador_relacion}"

    aplicados = []
    try:
        for material_id, cantidad, stock, material, documento_item_id, documento_id in pendientes:
            if documento_item_id is not None and documento_id is not None:
                nueva_cantidad = stock - cantidad
                actualizar_cantidad_documento_item(
                    documento_item_id,
                    nueva_cantidad,
                    usuario=usuario,
                    observaciones=observacion_base,
                    archivo_origen=material.get("archivo_origen"),
                    documento_id=documento_id,
                )
            else:
                agregar_ajuste_stock(
                    material_id,
                    -cantidad,
                    usuario=usuario,
                    observaciones=observacion_base,
                )
            aplicados.append((material_id, cantidad, documento_item_id, documento_id))

        return {
            "materiales": len(aplicados),
            "cantidad_total": sum(cantidad for _, cantidad, _, _ in aplicados),
        }
    except Exception as error:
        # No hacemos una reversión ciega: el origen puede haber sido actualizado
        # parcialmente en el Word/DB. El error queda visible para no ocultar
        # una posible inconsistencia y evitar duplicar movimientos.
        raise RelacionTransitoPDFError(
            f"No se pudo completar el descuento del stock por origen: {error}"
        ) from error

