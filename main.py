from pathlib import Path
import re

_SOURCE = Path(__file__).with_name("main_original.py")
_source = _SOURCE.read_text(encoding="utf-8")

_new_func = '''def generar_relacion_transito_ui():

    """Abre directamente el selector general de materiales."""

    tipo_movimiento = simpledialog.askstring(
        "Relación de Tránsito",
        "Tipo de movimiento:",
        parent=root,
    )
    if tipo_movimiento is None:
        return

    destino = simpledialog.askstring(
        "Relación de Tránsito",
        "Destino:",
        parent=root,
    )
    if destino is None:
        return

    transporte = simpledialog.askstring(
        "Relación de Tránsito",
        "Transporte:",
        parent=root,
    )
    if transporte is None:
        return

    nombre_archivo = f"RELACION DE TRANSITO_{datetime.now():%Y%m%d_%H%M%S}.xlsx"
    salida = filedialog.asksaveasfilename(
        parent=root,
        title="Guardar Relación de Tránsito",
        defaultextension=".xlsx",
        initialfile=nombre_archivo,
        filetypes=[("Excel", "*.xlsx")],
    )
    if not salida:
        return

    try:
        generar_relacion_transito(
            materiales=[{}],
            salida=salida,
            tipo_movimiento=tipo_movimiento,
            destino=destino,
            transporte=transporte,
        )

        pdf_generado = getattr(generar_relacion_transito, "ultimo_pdf", None)
        mensaje = f"La Relación de Tránsito se generó correctamente.\\n\\nExcel:\\n{salida}"
        if pdf_generado:
            mensaje += f"\\n\\nPDF:\\n{pdf_generado}"

        messagebox.showinfo("Relación de Tránsito", mensaje, parent=root)

    except RelacionTransitoError as error:
        traceback.print_exc()
        messagebox.showerror(
            "Relación de Tránsito",
            f"No se pudo generar la relación:\\n\\n{error}",
            parent=root,
        )
    except Exception as error:
        traceback.print_exc()
        messagebox.showerror(
            "Relación de Tránsito",
            f"Ocurrió un error inesperado:\\n\\n{error}",
            parent=root,
        )


'''

_pattern = r'def generar_relacion_transito_ui\(\):.*?(?=\n# ={10,}\n)'
# Usar una función como reemplazo evita que re.sub interprete los \n del texto
# como saltos de línea reales dentro de los f-strings.
_source, _count = re.subn(
    _pattern,
    lambda _match: _new_func.rstrip(),
    _source,
    count=1,
    flags=re.S,
)
if _count != 1:
    raise RuntimeError("No se encontró generar_relacion_transito_ui en main.py")

exec(compile(_source, str(_SOURCE), "exec"), globals(), globals())
