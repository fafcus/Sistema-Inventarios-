from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from supabase_db import agregar_ajuste_stock, obtener_stock_general_material, registrar_movimiento
from relacion_transito_origenes import descontar_origen_material, obtener_origenes_material


class RelacionTransitoPDFError(Exception):
    """Error controlado al generar el PDF de una relación de tránsito."""


def _buscar_soffice() -> str | None:
    candidatos = [
        shutil.which("soffice"), shutil.which("libreoffice"),
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
    try:
        resultado = subprocess.run([soffice, "--headless", "--convert-to", "pdf", "--outdir", str(carpeta), str(excel_path)], capture_output=True, text=True, timeout=120, check=False)
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
    if os.name != "nt":
        return None
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
    powershell = shutil.which("powershell") or shutil.which("pwsh")
    if not powershell:
        return None
    script = (
        "$ErrorActionPreference='Stop'; $excel=New-Object -ComObject Excel.Application; "
        "$excel.Visible=$false; $excel.DisplayAlerts=$false; "
        f"$libro=$excel.Workbooks.Open('{str(excel_path.resolve()).replace(chr(39), chr(39)*2)}'); "
        f"$libro.ExportAsFixedFormat(0,'{str(pdf_path.resolve()).replace(chr(39), chr(39)*2)}'); "
        "$libro.Close($false); $excel.Quit();"
    )
    try:
        resultado = subprocess.run([powershell, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", script], capture_output=True, text=True, timeout=120, check=False)
        if resultado.returncode == 0 and pdf_path.exists():
            return pdf_path
    except Exception:
        pass
    return None


def convertir_excel_a_pdf(excel_path: str | Path, pdf_path: str | Path | None = None) -> Path:
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
    raise RelacionTransitoPDFError("No se pudo convertir la relación a PDF. Se necesita LibreOffice o Microsoft Excel instalado en esta PC.")


def _resolver_origen(material):
    """Resuelve el origen real incluso si la UI no entregó todos los IDs."""
    material_id = material.get("id")
    if material_id is None:
        return None

    try:
        origenes = obtener_origenes_material(int(material_id)) or []
    except Exception:
        origenes = []

    documento_item_id = material.get("_documento_item_id")
    documento_id = material.get("_documento_id")
    archivo = str(material.get("archivo_origen") or "").strip().lower()
    ubicacion = str(material.get("ubicacion") or "").strip().lower()

    if documento_item_id is not None:
        for origen in origenes:
            if origen.get("documento_item_id") == documento_item_id:
                return origen

    if documento_id is not None:
        candidatos = [o for o in origenes if o.get("documento_id") == documento_id]
        if len(candidatos) == 1:
            return candidatos[0]
        if candidatos:
            return candidatos[0]

    candidatos = origenes
    if archivo:
        por_archivo = [o for o in candidatos if str(o.get("archivo_origen") or "").strip().lower() == archivo]
        if por_archivo:
            candidatos = por_archivo
    if ubicacion:
        por_ubicacion = [o for o in candidatos if str(o.get("ubicacion") or "").strip().lower() == ubicacion]
        if por_ubicacion:
            candidatos = por_ubicacion

    if len(candidatos) == 1:
        return candidatos[0]

    return None


def descontar_materiales_relacion(materiales, usuario=None, identificador_relacion=None):
    """Descuenta stock conservando el documento/origen seleccionado."""
    materiales = list(materiales or [])
    if not materiales:
        raise RelacionTransitoPDFError("La relación no contiene materiales para descontar.")

    pendientes = []
    for material in materiales:
        material_id = material.get("id")
        if material_id is None:
            raise RelacionTransitoPDFError(f"El material '{material.get('material') or material.get('codigo') or 'sin nombre'}' no tiene ID de base de datos.")
        try:
            cantidad = float(material.get("cantidad") or 0)
        except (TypeError, ValueError):
            raise RelacionTransitoPDFError(f"Cantidad inválida para el material '{material.get('material') or material_id}'.")
        if cantidad <= 0:
            raise RelacionTransitoPDFError(f"La cantidad a retirar debe ser mayor que cero para '{material.get('material') or material_id}'.")
        pendientes.append((material_id, cantidad, material))

    observacion_base = "Salida por Relación de Tránsito"
    if identificador_relacion:
        observacion_base += f": {identificador_relacion}"

    origenes_resueltos = []
    for material_id, cantidad, material in pendientes:
        origen = _resolver_origen(material)
        if origen is not None:
            stock = float(origen.get("stock_disponible") or 0)
        else:
            stock = float(obtener_stock_general_material(material_id) or 0)
            try:
                cantidad_origenes = len(obtener_origenes_material(int(material_id)) or [])
            except Exception:
                cantidad_origenes = 0
            if cantidad_origenes > 1:
                raise RelacionTransitoPDFError(
                    f"No se pudo determinar el origen de '{material.get('material') or material_id}'. "
                    "Seleccioná una ubicación/origen antes de generar la relación."
                )
        if cantidad > stock + 0.000001:
            raise RelacionTransitoPDFError(f"Stock insuficiente para '{material.get('material') or material_id}'. Disponible: {stock:g}. A retirar: {cantidad:g}.")
        origenes_resueltos.append(origen)

    aplicados = []
    try:
        for (material_id, cantidad, material), origen in zip(pendientes, origenes_resueltos):
            observaciones = observacion_base
            if material.get("ubicacion"):
                observaciones += f" | Ubicación: {material.get('ubicacion')}"
            if material.get("archivo_origen"):
                observaciones += f" | Origen: {material.get('archivo_origen')}"

            if origen is not None:
                descontar_origen_material(origen, cantidad, usuario=usuario, observaciones=observaciones)
            else:
                agregar_ajuste_stock(material_id, -cantidad, usuario=usuario, observaciones=observaciones)
            aplicados.append((material_id, cantidad, material, origen))

        return {"materiales": len(aplicados), "cantidad_total": sum(cantidad for _, cantidad, _, _ in aplicados)}
    except Exception as error:
        # Revertir únicamente lo ya aplicado y registrar también el movimiento
        # compensatorio para que el historial quede consistente.
        for material_id, cantidad, material, origen in reversed(aplicados):
            try:
                if origen is not None:
                    from config import supabase
                    documento_id = int(origen.get("documento_id"))
                    actual_origen = _resolver_origen({
                        "id": material_id,
                        "_documento_id": documento_id,
                        "_documento_item_id": origen.get("documento_item_id"),
                    }) or origen
                    stock_actual = float(actual_origen.get("stock_disponible") or 0)
                    supabase.table("ajustes_stock").insert({
                        "material_id": int(material_id),
                        "documento_id": documento_id,
                        "cantidad": cantidad,
                        "usuario": usuario,
                        "observaciones": f"Reversión automática por error en {observacion_base}",
                    }).execute()
                    registrar_movimiento(
                        material_id,
                        "ENTRADA",
                        cantidad,
                        stock_actual,
                        stock_actual + cantidad,
                        usuario,
                        f"Reversión automática por error en {observacion_base}",
                        actual_origen.get("archivo_origen") or material.get("archivo_origen"),
                        documento_id=documento_id,
                    )
                else:
                    stock_actual = float(obtener_stock_general_material(material_id) or 0)
                    agregar_ajuste_stock(material_id, cantidad, usuario=usuario, observaciones=f"Reversión automática por error en {observacion_base}")
            except Exception:
                pass
        raise RelacionTransitoPDFError(f"No se pudo completar el descuento del stock: {error}") from error
