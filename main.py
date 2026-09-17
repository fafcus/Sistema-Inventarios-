import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from pathlib import Path
import threading
import time
import traceback

from config import supabase
from supabase_db import (
    probar_conexion, obtener_materiales, obtener_material, crear_material,
    actualizar_material, obtener_inventario_general, agregar_ajuste_stock,
    actualizar_cantidad_documento_item, obtener_movimientos, obtener_documentos,
    obtener_items_documento, crear_item_documento, buscar_material,
)
import importar_word

CARPETA_DOCUMENTOS = Path(__file__).resolve().parent / "documentos"
NOMBRE_APP = "INVENTARIO MATERIAL NAVAL"
GENERAL = "🏠 INVENTARIO GENERAL"
COLOR_STOCK = "🟢 HAY STOCK"
COLOR_SIN_STOCK = "🔴 SIN STOCK"
INTERVALO_MONITOR = 5000
INTERVALO_SINCRONIZACION = 3000

COLOR_FONDO = "#eef3f8"
COLOR_PANEL = "#ffffff"
COLOR_AZUL_OSCURO = "#12304a"
COLOR_AZUL = "#1f5d87"
COLOR_AZUL_CLARO = "#dceaf5"
COLOR_BORDE = "#c7d5e0"
COLOR_TEXTO = "#183247"
COLOR_TEXTO_SECUNDARIO = "#506575"
COLOR_STOCK_FONDO = "#e7f6e9"
COLOR_SIN_STOCK_FONDO = "#fdeaea"

root = None
selector_inventario = None
tabla = None
tabla_movimientos = None
entrada_busqueda = None
lbl_total_materiales = lbl_con_stock = lbl_sin_stock = lbl_cantidad_total = None
lbl_estado = lbl_progreso = None
inventario_seleccionado = GENERAL

importacion_en_curso = False
lock_importacion = threading.Lock()
estado_archivos_word = {}
cache_materiales = []
cache_documentos = []
cache_movimientos = []
cache_lock = threading.Lock()
actualizacion_en_curso = False
lock_actualizacion = threading.Lock()
sincronizacion_en_curso = False
lock_sincronizacion = threading.Lock()
firma_datos_sincronizados = None
pausar_sincronizacion = False


def limpiar_texto(valor): return "" if valor is None else str(valor).strip()


def formatear_numero(valor):
    try: return f"{float(valor or 0):g}"
    except Exception: return str(valor or 0)


def invalidar_cache():
    global cache_materiales, cache_documentos, cache_movimientos
    with cache_lock: cache_materiales = []; cache_documentos = []; cache_movimientos = []


def cargar_datos_supabase():
    global cache_materiales, cache_documentos, cache_movimientos
    materiales = obtener_inventario_general() or []
    documentos = obtener_documentos() or []
    movimientos = obtener_movimientos(100) or []
    with cache_lock: cache_materiales, cache_documentos, cache_movimientos = materiales, documentos, movimientos
    return materiales, documentos, movimientos


def obtener_materiales_cache():
    with cache_lock: return list(cache_materiales)


def obtener_documentos_cache():
    with cache_lock: return list(cache_documentos)


def obtener_movimientos_cache():
    with cache_lock: return list(cache_movimientos)


def generar_firma_sincronizacion(materiales, documentos, movimientos):
    return (
        tuple((m.get("id"), m.get("cantidad"), m.get("codigo"), m.get("material"), m.get("unidad"), m.get("categoria"), m.get("ubicacion"), m.get("observaciones")) for m in materiales),
        tuple((d.get("id"), d.get("nombre"), d.get("ruta"), d.get("fecha_modificacion_archivo")) for d in documentos),
        tuple((m.get("id"), m.get("material_id"), m.get("tipo"), m.get("cantidad"), m.get("stock_anterior"), m.get("stock_nuevo"), m.get("fecha"), m.get("usuario"), m.get("archivo_origen"), m.get("observaciones")) for m in movimientos),
    )


def actualizar_estadisticas(materiales):
    total = len(materiales); con = sin = 0; total_cantidad = 0
    for m in materiales:
        try: cantidad = float(m.get("cantidad", 0) or 0)
        except Exception: cantidad = 0
        total_cantidad += cantidad
        if cantidad > 0: con += 1
        else: sin += 1
    if lbl_total_materiales: lbl_total_materiales.config(text=f"Materiales: {total}")
    if lbl_con_stock: lbl_con_stock.config(text=f"Con stock: {con}")
    if lbl_sin_stock: lbl_sin_stock.config(text=f"Sin stock: {sin}")
    if lbl_cantidad_total: lbl_cantidad_total.config(text=f"Cantidad total: {total_cantidad:g}")


def obtener_documento_actual():
    nombre = selector_inventario.get()
    if nombre == GENERAL: return None
    for d in obtener_documentos_cache():
        if d.get("nombre") == nombre: return d
    return None


def obtener_documento_id_actual():
    d = obtener_documento_actual()
    return d.get("id") if d else None


def cargar_selector(documentos=None):
    global inventario_seleccionado
    documentos = documentos if documentos is not None else obtener_documentos_cache()
    valores = [GENERAL] + [d.get("nombre") for d in documentos if d.get("nombre")]
    selector_inventario["values"] = valores
    if selector_inventario.get() in valores: inventario_seleccionado = selector_inventario.get()
    else: selector_inventario.current(0); inventario_seleccionado = GENERAL


def cambiar_inventario(event=None):
    global inventario_seleccionado
    inventario_seleccionado = selector_inventario.get(); entrada_busqueda.delete(0, tk.END); actualizar_tabla(); actualizar_movimientos()


def es_inventario_general(): return selector_inventario.get() == GENERAL


def obtener_materiales_seleccionados():
    materiales = obtener_materiales_cache()
    if es_inventario_general(): return materiales
    documento_id = obtener_documento_id_actual()
    if not documento_id: return []
    try: items = obtener_items_documento(documento_id) or []
    except Exception as error: print("Error obteniendo documento_items:", error); return []
    por_id = {m.get("id"): m for m in materiales if m.get("id") is not None}
    resultado = []
    for item in items:
        mid = item.get("material_id"); material = por_id.get(mid)
        if not material:
            try: material = obtener_material(mid)
            except Exception: material = None
        if not material: continue
        copia = dict(material)
        copia["cantidad"] = item.get("cantidad", 0)
        for campo in ("codigo", "material", "unidad", "categoria", "ubicacion", "observaciones"):
            if item.get(campo) is not None: copia[campo] = item.get(campo)
        resultado.append(copia)
    return resultado


def actualizar_tabla():
    if tabla is None: return
    for x in tabla.get_children(): tabla.delete(x)
    materiales = obtener_materiales_seleccionados(); texto = limpiar_texto(entrada_busqueda.get()).lower(); filtrados = []
    for m in materiales:
        if texto:
            combinado = " ".join(limpiar_texto(m.get(c)) for c in ("codigo", "material", "categoria", "ubicacion", "observaciones")).lower()
            if texto not in combinado: continue
        filtrados.append(m)
    for m in filtrados:
        try: cantidad = float(m.get("cantidad", 0) or 0)
        except Exception: cantidad = 0
        estado, tag = (COLOR_STOCK, "stock") if cantidad > 0 else (COLOR_SIN_STOCK, "sin_stock")
        tabla.insert("", "end", iid=str(m.get("id")), values=(m.get("codigo") or "", m.get("material") or "", formatear_numero(cantidad), m.get("unidad") or "", m.get("categoria") or "", m.get("ubicacion") or "", m.get("observaciones") or "", estado), tags=(tag,))
    actualizar_estadisticas(filtrados)


def buscar(event=None): actualizar_tabla()


def obtener_material_seleccionado():
    sel = tabla.selection()
    if not sel: messagebox.showwarning("Selección", "Seleccioná un material primero.", parent=root); return None
    try: mid = int(sel[0])
    except Exception: return None
    for m in obtener_materiales_cache():
        if m.get("id") == mid: return m
    try: return obtener_material(mid)
    except Exception: return None


def obtener_item_documento(material_id):
    did = obtener_documento_id_actual()
    if not did: return None
    try: items = obtener_items_documento(did) or []
    except Exception: return None
    for item in items:
        try:
            if int(item.get("material_id", -1)) == int(material_id): return item
        except Exception: pass
    return None


def actualizar_stock_documento(material_id, nueva_cantidad, tipo_movimiento=None, usuario="APP", observaciones=None):
    item = obtener_item_documento(material_id)
    if item is None: raise Exception("El material no pertenece al inventario seleccionado.")
    return actualizar_cantidad_documento_item(item["id"], nueva_cantidad, usuario=usuario, archivo_origen=inventario_seleccionado, observaciones=observaciones, documento_id=obtener_documento_id_actual())


def agregar_stock():
    material = obtener_material_seleccionado()
    if not material: return
    mid = material["id"]; nombre = material.get("material") or ""; unidad = material.get("unidad") or ""; codigo = material.get("codigo") or "-"
    item = obtener_item_documento(mid) if not es_inventario_general() else None
    if not es_inventario_general() and item is None: messagebox.showerror("Error", "El material no pertenece al inventario seleccionado.", parent=root); return
    stock = float(material.get("cantidad", 0) or 0) if es_inventario_general() else float(item.get("cantidad", 0) or 0)
    cantidad = simpledialog.askfloat("Agregar stock", f"Material: {nombre}\nCódigo: {codigo}\nStock actual: {formatear_numero(stock)} {unidad}\n\nCantidad a agregar:", minvalue=0.0001, parent=root)
    if cantidad is None or cantidad <= 0: return
    try:
        nuevo = agregar_ajuste_stock(mid, cantidad, "APP", "Ingreso manual en inventario general") if es_inventario_general() else actualizar_stock_documento(mid, stock + cantidad, "ENTRADA", "APP", "Ingreso manual en " + inventario_seleccionado)
        invalidar_cache(); actualizar_todo(True)
        valor = nuevo.get("cantidad", stock + cantidad) if isinstance(nuevo, dict) else nuevo
        messagebox.showinfo("Stock actualizado", f"Material: {nombre}\n\nStock anterior: {formatear_numero(stock)} {unidad}\nCantidad agregada: {formatear_numero(cantidad)} {unidad}\nStock nuevo: {formatear_numero(valor)} {unidad}", parent=root)
    except Exception as error: traceback.print_exc(); messagebox.showerror("Error", f"No se pudo agregar stock:\n\n{error}", parent=root)


def retirar_stock():
    material = obtener_material_seleccionado()
    if not material: return
    mid = material["id"]; nombre = material.get("material") or ""; unidad = material.get("unidad") or ""; codigo = material.get("codigo") or "-"
    item = obtener_item_documento(mid) if not es_inventario_general() else None
    if not es_inventario_general() and item is None: messagebox.showerror("Error", "El material no pertenece al inventario seleccionado.", parent=root); return
    stock = float(material.get("cantidad", 0) or 0) if es_inventario_general() else float(item.get("cantidad", 0) or 0)
    cantidad = simpledialog.askfloat("Retirar stock", f"Material: {nombre}\nCódigo: {codigo}\nStock actual: {formatear_numero(stock)} {unidad}\n\nCantidad a retirar:", minvalue=0.0001, parent=root)
    if cantidad is None or cantidad <= 0: return
    if cantidad > stock: messagebox.showwarning("Stock insuficiente", f"No podés retirar {formatear_numero(cantidad)} {unidad}.\n\nStock disponible: {formatear_numero(stock)} {unidad}", parent=root); return
    try:
        nuevo = agregar_ajuste_stock(mid, -cantidad, "APP", "Retiro manual en inventario general") if es_inventario_general() else actualizar_stock_documento(mid, stock - cantidad, "SALIDA", "APP", "Retiro manual en " + inventario_seleccionado)
        invalidar_cache(); actualizar_todo(True)
        valor = nuevo.get("cantidad", stock - cantidad) if isinstance(nuevo, dict) else nuevo
        messagebox.showinfo("Retiro realizado", f"Material: {nombre}\n\nStock anterior: {formatear_numero(stock)} {unidad}\nCantidad retirada: {formatear_numero(cantidad)} {unidad}\nStock nuevo: {formatear_numero(valor)} {unidad}", parent=root)
    except Exception as error: traceback.print_exc(); messagebox.showerror("Error", f"No se pudo retirar stock:\n\n{error}", parent=root)


def nuevo_material():
    ventana=tk.Toplevel(root); ventana.title("Nuevo material"); ventana.geometry("520x520"); ventana.transient(root); ventana.grab_set(); campos=[("Código","codigo"),("Material","material"),("Cantidad","cantidad"),("Unidad","unidad"),("Categoría","categoria"),("Ubicación","ubicacion"),("Observaciones","observaciones")]; entradas={}; frame=ttk.Frame(ventana,padding=20); frame.pack(fill="both",expand=True)
    for fila,(texto,clave) in enumerate(campos): ttk.Label(frame,text=texto).grid(row=fila,column=0,sticky="w",padx=5,pady=7); e=ttk.Entry(frame); e.grid(row=fila,column=1,sticky="ew",padx=5,pady=7); entradas[clave]=e
    frame.columnconfigure(1,weight=1)
    def guardar():
        nombre=entradas["material"].get().strip()
        if not nombre: messagebox.showwarning("Datos","El nombre del material es obligatorio.",parent=ventana); return
        try: cantidad=float(entradas["cantidad"].get().strip().replace(",",".") or 0)
        except ValueError: messagebox.showerror("Cantidad","La cantidad debe ser numérica.",parent=ventana); return
        if cantidad<0: messagebox.showerror("Cantidad","La cantidad no puede ser negativa.",parent=ventana); return
        datos={k:entradas[k].get().strip() or None for k in ("codigo","unidad","categoria","ubicacion","observaciones")}
        try:
            if buscar_material(datos["codigo"],nombre,datos["categoria"],datos["ubicacion"]): messagebox.showwarning("Material existente","Ese material ya existe en la base de datos.",parent=ventana); return
            nuevo=crear_material(datos["codigo"],nombre,0,datos["unidad"],datos["categoria"],datos["ubicacion"],datos["observaciones"],None if es_inventario_general() else inventario_seleccionado)
            if not nuevo: raise Exception("No se pudo crear el material.")
            if es_inventario_general():
                if cantidad>0: agregar_ajuste_stock(nuevo["id"],cantidad,"APP","Stock inicial de material nuevo")
            else:
                did=obtener_documento_id_actual()
                if not did: raise Exception("No se encontró el documento seleccionado.")
                if not crear_item_documento(did,nuevo["id"],cantidad,unidad=datos["unidad"],codigo=datos["codigo"],material=nombre,categoria=datos["categoria"],ubicacion=datos["ubicacion"],observaciones=datos["observaciones"]): raise Exception("No se pudo crear el item del inventario.")
            invalidar_cache(); ventana.destroy(); actualizar_todo(True); messagebox.showinfo("Material creado",f"Se agregó correctamente:\n\n{nombre}",parent=root)
        except Exception as error: traceback.print_exc(); messagebox.showerror("Error",f"No se pudo crear el material:\n\n{error}",parent=ventana)
    ttk.Button(frame,text="Guardar",command=guardar).grid(row=len(campos),column=0,columnspan=2,pady=20)


def editar_material():
    material=obtener_material_seleccionado()
    if not material:return
    ventana=tk.Toplevel(root); ventana.title("Editar material"); ventana.geometry("520x500"); ventana.transient(root); ventana.grab_set(); campos=[("Código","codigo"),("Material","material"),("Unidad","unidad"),("Categoría","categoria"),("Ubicación","ubicacion"),("Observaciones","observaciones")]; entradas={}; frame=ttk.Frame(ventana,padding=20); frame.pack(fill="both",expand=True)
    for fila,(texto,clave) in enumerate(campos): ttk.Label(frame,text=texto).grid(row=fila,column=0,sticky="w",padx=5,pady=7); e=ttk.Entry(frame); e.grid(row=fila,column=1,sticky="ew",padx=5,pady=7); e.insert(0,material.get(clave) or ""); entradas[clave]=e
    frame.columnconfigure(1,weight=1)
    def guardar():
        nombre=entradas["material"].get().strip()
        if not nombre: messagebox.showwarning("Datos","El material no puede quedar vacío.",parent=ventana); return
        try:
            if not actualizar_material(material["id"],codigo=entradas["codigo"].get().strip() or None,material=nombre,unidad=entradas["unidad"].get().strip() or None,categoria=entradas["categoria"].get().strip() or None,ubicacion=entradas["ubicacion"].get().strip() or None,observaciones=entradas["observaciones"].get().strip() or None): raise Exception("No se pudo actualizar.")
            invalidar_cache(); ventana.destroy(); actualizar_todo(True)
        except Exception as error: traceback.print_exc(); messagebox.showerror("Error",f"No se pudo modificar:\n\n{error}",parent=ventana)
    ttk.Button(frame,text="Guardar cambios",command=guardar).grid(row=len(campos),column=0,columnspan=2,pady=20)


def actualizar_movimientos():
    if tabla_movimientos is None:return
    for x in tabla_movimientos.get_children():tabla_movimientos.delete(x)
    materiales={m.get("id"):m for m in obtener_materiales_cache()}
    for mov in obtener_movimientos_cache():
        m=materiales.get(mov.get("material_id")); tabla_movimientos.insert("","end",values=(mov.get("fecha") or "",m.get("codigo") if m else "",m.get("material") if m else "Material eliminado",mov.get("tipo") or "",formatear_numero(mov.get("cantidad",0)),formatear_numero(mov.get("stock_anterior",0)),formatear_numero(mov.get("stock_nuevo",0)),mov.get("usuario") or "",mov.get("archivo_origen") or "",mov.get("observaciones") or ""))


def actualizar_todo(forzar=False):
    global actualizacion_en_curso, firma_datos_sincronizados
    with lock_actualizacion:
        if actualizacion_en_curso:return
        actualizacion_en_curso=True
    def trabajo():
        global actualizacion_en_curso, firma_datos_sincronizados
        try:
            if lbl_progreso:root.after(0,lambda:lbl_progreso.config(text="⏳ Actualizando..."))
            materiales,documentos,movimientos=cargar_datos_supabase(); firma_datos_sincronizados=generar_firma_sincronizacion(materiales,documentos,movimientos)
            def refrescar():
                global actualizacion_en_curso
                try:
                    cargar_selector(documentos); actualizar_tabla(); actualizar_movimientos()
                    if lbl_estado:lbl_estado.config(text="🟢 Sincronizado")
                    if lbl_progreso:lbl_progreso.config(text="✓ Actualizado")
                finally:
                    with lock_actualizacion:actualizacion_en_curso=False
            root.after(0,refrescar)
        except Exception as error:
            traceback.print_exc()
            def fallo():
                global actualizacion_en_curso
                with lock_actualizacion:actualizacion_en_curso=False
                if lbl_estado:lbl_estado.config(text="🔴 Sin conexión")
                if lbl_progreso:lbl_progreso.config(text="Error al actualizar")
            root.after(0,fallo)
    threading.Thread(target=trabajo,daemon=True).start()


def sincronizar_automaticamente():
    global sincronizacion_en_curso, firma_datos_sincronizados, cache_materiales, cache_documentos, cache_movimientos
    if root is None or importacion_en_curso or pausar_sincronizacion:return
    with lock_sincronizacion:
        if sincronizacion_en_curso:return
        sincronizacion_en_curso=True
    def trabajo():
        global sincronizacion_en_curso, firma_datos_sincronizados, cache_materiales, cache_documentos, cache_movimientos
        try:
            with lock_actualizacion:
                if actualizacion_en_curso:return
            materiales=obtener_inventario_general() or []; documentos=obtener_documentos() or []; movimientos=obtener_movimientos(100) or []
            firma=generar_firma_sincronizacion(materiales,documentos,movimientos)
            cambio=firma_datos_sincronizados is None or firma!=firma_datos_sincronizados; firma_datos_sincronizados=firma
            if cambio:
                with cache_lock:cache_materiales,cache_documentos,cache_movimientos=materiales,documentos,movimientos
                root.after(0,actualizar_interfaz_por_sincronizacion)
            else:root.after(0,lambda:actualizar_estado_sync(True,False))
        except Exception as error:
            print("❌ Error en sincronización automática:",error); traceback.print_exc(); root.after(0,lambda:actualizar_estado_sync(False,False))
        finally:
            with lock_sincronizacion:sincronizacion_en_curso=False
    threading.Thread(target=trabajo,daemon=True).start()


def actualizar_interfaz_por_sincronizacion():
    try:
        cargar_selector(obtener_documentos_cache()); actualizar_tabla(); actualizar_movimientos()
        if lbl_estado:lbl_estado.config(text="🟢 Sincronizado")
        if lbl_progreso:lbl_progreso.config(text="🔄 Cambio detectado — sincronizado")
    except Exception:traceback.print_exc()


def actualizar_estado_sync(conectado,hubo_cambio):
    if lbl_estado:lbl_estado.config(text="🟢 Sincronizado" if conectado else "🔴 Sin conexión")
    if hubo_cambio and lbl_progreso:lbl_progreso.config(text="🔄 Datos sincronizados")


def monitor_sincronizacion():
    print("🔄 Monitor de sincronización iniciado.")
    while True:
        try:sincronizar_automaticamente()
        except Exception:traceback.print_exc()
        time.sleep(INTERVALO_SINCRONIZACION/1000)


def ejecutar_importacion_word(reescaneo_completo=False):
    global importacion_en_curso,pausar_sincronizacion,firma_datos_sincronizados,cache_materiales,cache_documentos,cache_movimientos
    with lock_importacion:
        if importacion_en_curso:return
        importacion_en_curso=True
    pausar_sincronizacion=True
    if lbl_progreso:lbl_progreso.config(text="⏳ Importando documentos Word...")
    if lbl_estado:lbl_estado.config(text="🟡 Importando Word...")
    def trabajo():
        global importacion_en_curso,pausar_sincronizacion,firma_datos_sincronizados,cache_materiales,cache_documentos,cache_movimientos
        resultado=None
        try:
            resultado=importar_word.importar_todos(reescaneo_completo=reescaneo_completo); invalidar_cache()
            materiales=obtener_inventario_general() or []; documentos=obtener_documentos() or []; movimientos=obtener_movimientos(100) or []
            with cache_lock:cache_materiales,cache_documentos,cache_movimientos=materiales,documentos,movimientos
            firma_datos_sincronizados=generar_firma_sincronizacion(materiales,documentos,movimientos); print("RESULTADO:",resultado)
        except Exception as error:
            traceback.print_exc(); root.after(0,lambda error=error:messagebox.showerror("Error",f"Ocurrió un error durante la importación:\n\n{error}",parent=root))
        finally:
            pausar_sincronizacion=False; importacion_en_curso=False; root.after(0,actualizar_interfaz_por_sincronizacion)
            if resultado is not None:root.after(150,lambda:mostrar_resultado_importacion(resultado))
    threading.Thread(target=trabajo,daemon=True).start()


def construir_mensaje_importacion(resultado):
    if not isinstance(resultado,dict):return str(resultado)
    campos=[("nuevos","Nuevos"),("modificados","Modificados"),("actualizados","Actualizados"),("sin_cambios","Sin cambios"),("eliminados","Eliminados"),("vacios","Vacíos"),("filas","Filas procesadas"),("items","Items"),("errores","Errores")]
    return "\n".join(f"{n}: {resultado.get(k,0)}" for k,n in campos if k in resultado) or str(resultado)


def mostrar_resultado_importacion(resultado):
    if lbl_progreso:lbl_progreso.config(text="✓ Word sincronizado")
    messagebox.showinfo("Importación finalizada",construir_mensaje_importacion(resultado),parent=root)


def importar_word_manual():
    if importacion_en_curso:messagebox.showinfo("Importación","Ya hay una importación en curso.",parent=root);return
    ejecutar_importacion_word(False)


def reescaneo_completo():
    if importacion_en_curso:messagebox.showinfo("Importación","Ya hay una importación en curso.",parent=root);return
    if not messagebox.askyesno("Reescaneo completo","Se van a revisar nuevamente todos los archivos Word.\n\nEsto puede tardar unos minutos.\n\n¿Continuar?",parent=root):return
    ejecutar_importacion_word(True)


def obtener_estado_archivos_word():
    estado={};CARPETA_DOCUMENTOS.mkdir(exist_ok=True)
    for ruta in CARPETA_DOCUMENTOS.glob("*.docx"):
        if ruta.name.startswith("~$"):continue
        try:estado[str(ruta.resolve())]=ruta.stat().st_mtime
        except Exception:pass
    return estado


def monitor_word():
    global estado_archivos_word
    print("📄 Monitor de Word iniciado.")
    while True:
        try:
            nuevo=obtener_estado_archivos_word()
            if nuevo!=estado_archivos_word:
                estado_archivos_word=nuevo
                if not importacion_en_curso:ejecutar_importacion_word(False)
        except Exception:traceback.print_exc()
        time.sleep(INTERVALO_MONITOR/1000)


def crear_interfaz():
    global root,selector_inventario,tabla,tabla_movimientos,entrada_busqueda,lbl_total_materiales,lbl_con_stock,lbl_sin_stock,lbl_cantidad_total,lbl_estado,lbl_progreso,estado_archivos_word
    root=tk.Tk();root.title(NOMBRE_APP);root.geometry("1500x900");root.minsize(1100,700);root.configure(bg=COLOR_FONDO)
    estilo=ttk.Style()
    try:estilo.theme_use("clam")
    except Exception:pass
    estilo.configure(".",font=("Segoe UI",10));estilo.configure("TFrame",background=COLOR_FONDO);estilo.configure("TLabel",background=COLOR_FONDO,foreground=COLOR_TEXTO);estilo.configure("Title.TLabel",background=COLOR_AZUL_OSCURO,foreground="white",font=("Segoe UI",18,"bold"));estilo.configure("Subtitle.TLabel",background=COLOR_AZUL_OSCURO,foreground="#dce8f1",font=("Segoe UI",9));estilo.configure("TButton",padding=(12,7),font=("Segoe UI",9,"bold"));estilo.configure("TCombobox",padding=5);estilo.configure("Treeview",background="white",foreground=COLOR_TEXTO,fieldbackground="white",rowheight=30,font=("Segoe UI",10),borderwidth=0);estilo.configure("Treeview.Heading",background=COLOR_AZUL_OSCURO,foreground="white",font=("Segoe UI",10,"bold"),padding=7);estilo.map("Treeview",background=[("selected",COLOR_AZUL)],foreground=[("selected","white")])
    cab=tk.Frame(root,bg=COLOR_AZUL_OSCURO,height=75);cab.pack(fill="x");cab.pack_propagate(False);tit=tk.Frame(cab,bg=COLOR_AZUL_OSCURO);tit.pack(side="left",padx=20);ttk.Label(tit,text="⚓ INVENTARIO MATERIAL NAVAL",style="Title.TLabel").pack(anchor="w");ttk.Label(tit,text="Sistema de gestión y control de material",style="Subtitle.TLabel").pack(anchor="w");est=tk.Frame(cab,bg=COLOR_AZUL_OSCURO);est.pack(side="right",padx=20);lbl_estado=tk.Label(est,text="🟡 Conectando...",bg=COLOR_AZUL_OSCURO,fg="white",font=("Segoe UI",10,"bold"));lbl_estado.pack(side="right")
    fs=ttk.Frame(root,padding=(15,10));fs.pack(fill="x");ttk.Label(fs,text="Inventario:",font=("Segoe UI",10,"bold")).pack(side="left",padx=(0,8));selector_inventario=ttk.Combobox(fs,state="readonly",width=55);selector_inventario.pack(side="left");selector_inventario.bind("<<ComboboxSelected>>",cambiar_inventario)
    stats=tk.Frame(root,bg=COLOR_AZUL_CLARO,highlightbackground=COLOR_BORDE,highlightthickness=1);stats.pack(fill="x",padx=15,pady=(0,7))
    def stat(t):return tk.Label(stats,text=t,bg=COLOR_AZUL_CLARO,fg=COLOR_TEXTO,font=("Segoe UI",10,"bold"),padx=15,pady=8)
    lbl_total_materiales=stat("Materiales: 0");lbl_total_materiales.pack(side="left");lbl_con_stock=stat("Con stock: 0");lbl_con_stock.pack(side="left");lbl_sin_stock=stat("Sin stock: 0");lbl_sin_stock.pack(side="left");lbl_cantidad_total=stat("Cantidad total: 0");lbl_cantidad_total.pack(side="left")
    fb=ttk.Frame(root,padding=(15,5));fb.pack(fill="x");ttk.Label(fb,text="Buscar:",font=("Segoe UI",10,"bold")).pack(side="left",padx=(0,7));entrada_busqueda=ttk.Entry(fb);entrada_busqueda.pack(side="left",fill="x",expand=True);entrada_busqueda.bind("<KeyRelease>",buscar)
    buttons=ttk.Frame(root,padding=(15,5));buttons.pack(fill="x")
    for text,cmd in (("➕ Nuevo",nuevo_material),("✏️ Editar",editar_material),("📥 Agregar",agregar_stock),("📤 Retirar",retirar_stock),("🔄 Actualizar",lambda:actualizar_todo(True))):ttk.Button(buttons,text=text,command=cmd).pack(side="left",padx=3)
    ttk.Button(buttons,text="📄 Importar Word",command=importar_word_manual).pack(side="right",padx=3);ttk.Button(buttons,text="🧹 Reescaneo completo",command=reescaneo_completo).pack(side="right",padx=3)
    lbl_progreso=ttk.Label(root,text="Listo",foreground=COLOR_TEXTO_SECUNDARIO);lbl_progreso.pack(anchor="w",padx=18,pady=(2,2))
    ft=ttk.Frame(root,padding=(15,3));ft.pack(fill="both",expand=True);cols=("codigo","material","cantidad","unidad","categoria","ubicacion","observaciones","estado");tabla=ttk.Treeview(ft,columns=cols,show="headings",selectmode="browse");heads={"codigo":"Código","material":"Material","cantidad":"Cantidad","unidad":"Unidad","categoria":"Categoría","ubicacion":"Ubicación","observaciones":"Observaciones","estado":"Estado"};widths={"codigo":150,"material":300,"cantidad":100,"unidad":100,"categoria":150,"ubicacion":180,"observaciones":300,"estado":150}
    for c in cols:tabla.heading(c,text=heads[c]);tabla.column(c,width=widths[c],minwidth=70)
    sv=ttk.Scrollbar(ft,orient="vertical",command=tabla.yview);sh=ttk.Scrollbar(ft,orient="horizontal",command=tabla.xview);tabla.configure(yscrollcommand=sv.set,xscrollcommand=sh.set);tabla.grid(row=0,column=0,sticky="nsew");sv.grid(row=0,column=1,sticky="ns");sh.grid(row=1,column=0,sticky="ew");ft.rowconfigure(0,weight=1);ft.columnconfigure(0,weight=1);tabla.tag_configure("stock",background=COLOR_STOCK_FONDO);tabla.tag_configure("sin_stock",background=COLOR_SIN_STOCK_FONDO)
    ttk.Label(root,text="Últimos movimientos",font=("Segoe UI",12,"bold")).pack(anchor="w",padx=15,pady=(8,3));fm=ttk.Frame(root,height=180);fm.pack(fill="x",padx=15,pady=(0,10));fm.pack_propagate(False);mc=("fecha","codigo","material","tipo","cantidad","anterior","nuevo","usuario","archivo","observaciones");tabla_movimientos=ttk.Treeview(fm,columns=mc,show="headings");mh={"fecha":"Fecha","codigo":"Código","material":"Material","tipo":"Tipo","cantidad":"Cantidad","anterior":"Stock anterior","nuevo":"Stock nuevo","usuario":"Usuario","archivo":"Archivo","observaciones":"Observaciones"};mw={"fecha":160,"codigo":130,"material":250,"tipo":100,"cantidad":100,"anterior":110,"nuevo":110,"usuario":100,"archivo":250,"observaciones":250}
    for c in mc:tabla_movimientos.heading(c,text=mh[c]);tabla_movimientos.column(c,width=mw[c],minwidth=80)
    smv=ttk.Scrollbar(fm,orient="vertical",command=tabla_movimientos.yview);smh=ttk.Scrollbar(fm,orient="horizontal",command=tabla_movimientos.xview);tabla_movimientos.configure(yscrollcommand=smv.set,xscrollcommand=smh.set);tabla_movimientos.grid(row=0,column=0,sticky="nsew");smv.grid(row=0,column=1,sticky="ns");smh.grid(row=1,column=0,sticky="ew");fm.rowconfigure(0,weight=1);fm.columnconfigure(0,weight=1)
    def iniciar():
        try:
            conectado=probar_conexion();root.after(0,lambda:lbl_estado.config(text="🟢 Conectado" if conectado else "🔴 Sin conexión"));actualizar_todo(True)
        except Exception:root.after(0,lambda:lbl_estado.config(text="🔴 Sin conexión"))
    threading.Thread(target=iniciar,daemon=True).start();estado_archivos_word=obtener_estado_archivos_word();threading.Thread(target=monitor_word,daemon=True).start();threading.Thread(target=monitor_sincronizacion,daemon=True).start();root.after(1500,lambda:ejecutar_importacion_word(False));root.mainloop()

if __name__ == "__main__":crear_interfaz()
