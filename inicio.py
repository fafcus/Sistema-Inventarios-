import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import traceback
from datetime import datetime

from usuarios_db import iniciar_sesion, cerrar_sesion, tiene_permiso, obtener_nombre_usuario, obtener_rol_usuario, solicitar_acceso
from permisos_documentos import tiene_permiso_documento


def mostrar_solicitud_acceso(parent):
    ventana = tk.Toplevel(parent)
    ventana.title("Solicitar acceso")
    ventana.geometry("500x430")
    ventana.resizable(False, False)
    ventana.transient(parent)
    ventana.grab_set()
    ventana.configure(bg="#eef3f8")

    cabecera = tk.Frame(ventana, bg="#12304a", height=70)
    cabecera.pack(fill="x")
    cabecera.pack_propagate(False)
    tk.Label(cabecera, text="👤 Solicitar acceso", bg="#12304a", fg="white", font=("Segoe UI", 17, "bold")).pack(anchor="w", padx=20, pady=20)

    marco = ttk.Frame(ventana, padding=25)
    marco.pack(fill="both", expand=True)
    entradas = {}
    for fila, (texto, clave) in enumerate((("Nombre y apellido", "nombre"), ("Email", "email"))):
        ttk.Label(marco, text=texto, font=("Segoe UI", 10, "bold")).grid(row=fila, column=0, sticky="w", pady=(5, 3))
        entrada = ttk.Entry(marco, width=45)
        entrada.grid(row=fila, column=1, sticky="ew", pady=(5, 8), padx=(12, 0))
        entradas[clave] = entrada

    ttk.Label(marco, text="Rol solicitado", font=("Segoe UI", 10, "bold")).grid(row=2, column=0, sticky="w", pady=(5, 3))
    rol_var = tk.StringVar(value="consulta")
    ttk.Combobox(marco, textvariable=rol_var, values=("consulta", "encargado"), state="readonly", width=42).grid(row=2, column=1, sticky="ew", pady=(5, 8), padx=(12, 0))
    ttk.Label(
        marco,
        text=("La solicitud quedará pendiente hasta que un administrador autorice el acceso.\n\n"
              "No se solicita una contraseña en esta etapa. Si se aprueba, recibirás un correo para configurar tu contraseña.\n\n"
              "El rol administrador no puede solicitarse desde esta pantalla."),
        foreground="#506575",
        wraplength=430,
    ).grid(row=3, column=0, columnspan=2, sticky="w", pady=(12, 12))
    estado = ttk.Label(marco, text="", foreground="#506575", wraplength=430)
    estado.grid(row=4, column=0, columnspan=2, sticky="w", pady=(0, 10))

    def enviar():
        boton.config(state="disabled")
        estado.config(text="Registrando solicitud...")
        ventana.update_idletasks()
        try:
            solicitar_acceso(entradas["nombre"].get(), entradas["email"].get(), rol_var.get())
            messagebox.showinfo(
                "Solicitud enviada",
                "La solicitud fue enviada correctamente.\n\nUn administrador debe autorizar tu acceso. Cuando sea aprobada, recibirás un correo para configurar tu contraseña.",
                parent=ventana,
            )
            ventana.destroy()
        except Exception as error:
            boton.config(state="normal")
            estado.config(text="No se pudo registrar la solicitud.")
            messagebox.showerror("Solicitud rechazada", str(error), parent=ventana)

    botones = ttk.Frame(marco)
    botones.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(12, 0))
    boton = ttk.Button(botones, text="📨 Enviar solicitud", command=enviar)
    boton.pack(side="right", padx=4)
    ttk.Button(botones, text="Cancelar", command=ventana.destroy).pack(side="right", padx=4)
    marco.columnconfigure(1, weight=1)
    entradas["nombre"].focus_set()


def abrir_selector_relacion_transito(app):
    """Selector completo de materiales para generar una relación de tránsito."""
    materiales = app.obtener_materiales_cache() or []
    materiales = [m for m in materiales if _numero_float(m.get("cantidad")) > 0]

    if not materiales:
        messagebox.showwarning(
            "Relación de Tránsito",
            "No hay materiales con stock disponible en el inventario general.",
            parent=app.root,
        )
        return

    ventana = tk.Toplevel(app.root)
    ventana.title("Generar Relación de Tránsito")
    ventana.geometry("1250x720")
    ventana.minsize(1000, 600)
    ventana.transient(app.root)
    ventana.grab_set()
    ventana.configure(bg="#eef3f8")

    cabecera = tk.Frame(ventana, bg="#12304a", height=72)
    cabecera.pack(fill="x")
    cabecera.pack_propagate(False)
    tk.Label(
        cabecera,
        text="🚚 Selección de materiales para Relación de Tránsito",
        bg="#12304a",
        fg="white",
        font=("Segoe UI", 17, "bold"),
    ).pack(anchor="w", padx=20, pady=20)

    marco = ttk.Frame(ventana, padding=14)
    marco.pack(fill="both", expand=True)

    datos = ttk.Frame(marco)
    datos.pack(fill="x", pady=(0, 10))

    ttk.Label(datos, text="Tipo:", font=("Segoe UI", 10, "bold")).pack(side="left")
    tipo = tk.StringVar()
    ttk.Entry(datos, textvariable=tipo, width=22).pack(side="left", padx=(8, 20))

    ttk.Label(datos, text="Destino:", font=("Segoe UI", 10, "bold")).pack(side="left")
    destino = tk.StringVar()
    ttk.Entry(datos, textvariable=destino, width=28).pack(side="left", padx=(8, 20))

    ttk.Label(datos, text="Buscar:", font=("Segoe UI", 10, "bold")).pack(side="left")
    busqueda = tk.StringVar()
    entrada_busqueda = ttk.Entry(datos, textvariable=busqueda, width=40)
    entrada_busqueda.pack(side="left", padx=(8, 0), fill="x", expand=True)

    ttk.Label(
        marco,
        text="☐ Marcá los materiales que vas a trasladar. Doble clic sobre cualquier material para modificar la cantidad.",
        foreground="#506575",
    ).pack(fill="x", pady=(0, 8))

    generar_pdf = tk.BooleanVar(value=True)
    ttk.Checkbutton(marco, text="Generar también el PDF", variable=generar_pdf).pack(anchor="w", pady=(0, 8))

    marco_tabla = ttk.Frame(marco)
    marco_tabla.pack(fill="both", expand=True)

    columnas = ("seleccionar", "codigo", "material", "stock", "llevar", "unidad", "ubicacion", "origen")
    tabla = ttk.Treeview(marco_tabla, columns=columnas, show="headings", selectmode="browse")
    encabezados = {
        "seleccionar": "✓",
        "codigo": "Código",
        "material": "Material",
        "stock": "Stock disponible",
        "llevar": "Cantidad a llevar",
        "unidad": "Unidad",
        "ubicacion": "Ubicación",
        "origen": "Archivo origen",
    }
    anchos = {
        "seleccionar": 55,
        "codigo": 120,
        "material": 300,
        "stock": 115,
        "llevar": 125,
        "unidad": 100,
        "ubicacion": 180,
        "origen": 210,
    }
    for columna in columnas:
        tabla.heading(columna, text=encabezados[columna])
        anchor = "center" if columna in ("seleccionar", "stock", "llevar") else "w"
        tabla.column(columna, width=anchos[columna], minwidth=55, anchor=anchor)

    scroll_vertical = ttk.Scrollbar(marco_tabla, orient="vertical", command=tabla.yview)
    scroll_horizontal = ttk.Scrollbar(marco_tabla, orient="horizontal", command=tabla.xview)
    tabla.configure(yscrollcommand=scroll_vertical.set, xscrollcommand=scroll_horizontal.set)
    tabla.grid(row=0, column=0, sticky="nsew")
    scroll_vertical.grid(row=0, column=1, sticky="ns")
    scroll_horizontal.grid(row=1, column=0, sticky="ew")
    marco_tabla.rowconfigure(0, weight=1)
    marco_tabla.columnconfigure(0, weight=1)

    seleccionados = {}
    visibles = []

    def cantidad_disponible(material):
        return _numero_float(material.get("cantidad"))

    def cantidad_formateada(valor):
        return f"{_numero_float(valor):g}"

    def material_seleccionado(material):
        return id(material) in seleccionados

    def cargar_tabla(*_):
        for item in tabla.get_children():
            tabla.delete(item)
        visibles.clear()
        texto = busqueda.get().strip().lower()

        for material in materiales:
            combinado = " ".join(
                str(material.get(campo) or "")
                for campo in ("codigo", "material", "ubicacion", "archivo_origen", "categoria")
            ).lower()
            if texto and texto not in combinado:
                continue

            visibles.append(material)
            seleccionado = material_seleccionado(material)
            cantidad = seleccionados.get(id(material), cantidad_disponible(material))
            iid = str(id(material))
            tabla.insert(
                "",
                "end",
                iid=iid,
                values=(
                    "☑" if seleccionado else "☐",
                    material.get("codigo") or "",
                    material.get("material") or "",
                    cantidad_formateada(cantidad_disponible(material)),
                    cantidad_formateada(cantidad),
                    material.get("unidad") or "",
                    material.get("ubicacion") or "",
                    material.get("archivo_origen") or "-",
                ),
            )

    def obtener_material_visible(iid):
        for material in visibles:
            if str(id(material)) == str(iid):
                return material
        return None

    def alternar_seleccion(material):
        clave = id(material)
        if clave in seleccionados:
            seleccionados.pop(clave, None)
        else:
            seleccionados[clave] = cantidad_disponible(material)
        cargar_tabla()
        iid = str(clave)
        if iid in tabla.get_children():
            tabla.selection_set(iid)
            tabla.focus(iid)

    def modificar_cantidad(event=None):
        seleccion = tabla.selection()
        if not seleccion:
            return
        material = obtener_material_visible(seleccion[0])
        if not material:
            return

        disponible = cantidad_disponible(material)
        clave = id(material)
        actual = seleccionados.get(clave, disponible)

        dialogo = tk.Toplevel(ventana)
        dialogo.title("Cantidad a trasladar")
        dialogo.geometry("450x240")
        dialogo.resizable(False, False)
        dialogo.transient(ventana)
        dialogo.grab_set()

        marco_cantidad = ttk.Frame(dialogo, padding=20)
        marco_cantidad.pack(fill="both", expand=True)
        ttk.Label(
            marco_cantidad,
            text=material.get("material") or "Material",
            font=("Segoe UI", 11, "bold"),
            wraplength=400,
        ).pack(anchor="w")
        ttk.Label(
            marco_cantidad,
            text=f"Stock disponible: {cantidad_formateada(disponible)} {material.get('unidad') or ''}",
        ).pack(anchor="w", pady=(8, 4))
        ttk.Label(marco_cantidad, text="Cantidad a trasladar:").pack(anchor="w", pady=(6, 2))

        entrada = ttk.Entry(marco_cantidad, width=24)
        entrada.insert(0, cantidad_formateada(actual))
        entrada.pack(anchor="w", pady=(2, 12))
        entrada.focus_set()
        entrada.select_range(0, "end")

        def aceptar():
            try:
                cantidad = float(entrada.get().replace(",", "."))
            except ValueError:
                messagebox.showerror("Cantidad", "Ingresá una cantidad numérica válida.", parent=dialogo)
                return
            if cantidad <= 0:
                messagebox.showwarning("Cantidad", "La cantidad debe ser mayor que cero.", parent=dialogo)
                return
            if cantidad > disponible:
                messagebox.showwarning(
                    "Stock insuficiente",
                    f"No podés trasladar {cantidad:g}. El stock disponible es {disponible:g}.",
                    parent=dialogo,
                )
                return

            seleccionados[clave] = cantidad
            dialogo.destroy()
            cargar_tabla()
            iid = str(clave)
            if iid in tabla.get_children():
                tabla.selection_set(iid)
                tabla.focus(iid)

        botones_cantidad = ttk.Frame(marco_cantidad)
        botones_cantidad.pack(fill="x")
        ttk.Button(botones_cantidad, text="Guardar", command=aceptar).pack(side="right", padx=(6, 0))
        ttk.Button(botones_cantidad, text="Cancelar", command=dialogo.destroy).pack(side="right")
        dialogo.bind("<Return>", lambda _event: aceptar())

    def click_tabla(event):
        region = tabla.identify("region", event.x, event.y)
        columna = tabla.identify_column(event.x)
        fila = tabla.identify_row(event.y)
        if region != "cell" or not fila:
            return
        if columna != "#1":
            return
        material = obtener_material_visible(fila)
        if material:
            alternar_seleccion(material)

    def doble_click_tabla(event):
        region = tabla.identify("region", event.x, event.y)
        columna = tabla.identify_column(event.x)
        if region != "cell":
            return
        # La palomita se maneja con un clic. En el resto de la fila,
        # doble clic abre directamente la edición de cantidad.
        if columna == "#1":
            return
        modificar_cantidad()

    tabla.bind("<Button-1>", click_tabla)
    tabla.bind("<Double-1>", doble_click_tabla)

    def quitar_seleccion():
        seleccion = tabla.selection()
        if not seleccion:
            messagebox.showwarning("Selección", "Seleccioná un material de la lista.", parent=ventana)
            return
        material = obtener_material_visible(seleccion[0])
        if material:
            seleccionados.pop(id(material), None)
            cargar_tabla()

    def seleccionar_todo():
        for material in visibles:
            seleccionados[id(material)] = seleccionados.get(id(material), cantidad_disponible(material))
        cargar_tabla()

    def deseleccionar_todo():
        for material in visibles:
            seleccionados.pop(id(material), None)
        cargar_tabla()

    def generar():
        if not seleccionados:
            messagebox.showwarning("Relación de Tránsito", "Marcá al menos un material con la palomita.", parent=ventana)
            return
        if not tipo.get().strip() or not destino.get().strip():
            messagebox.showwarning("Datos incompletos", "Completá Tipo y Destino antes de generar.", parent=ventana)
            return

        transporte_var = tk.StringVar()
        transporte_dialogo = tk.Toplevel(ventana)
        transporte_dialogo.title("Transporte")
        transporte_dialogo.geometry("430x190")
        transporte_dialogo.resizable(False, False)
        transporte_dialogo.transient(ventana)
        transporte_dialogo.grab_set()

        marco_transporte = ttk.Frame(transporte_dialogo, padding=20)
        marco_transporte.pack(fill="both", expand=True)
        ttk.Label(marco_transporte, text="Transporte", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        entrada_transporte = ttk.Entry(marco_transporte, textvariable=transporte_var, width=42)
        entrada_transporte.pack(fill="x", pady=(6, 14))
        entrada_transporte.focus_set()

        def confirmar_generacion():
            transporte = transporte_var.get().strip()
            if not transporte:
                messagebox.showwarning("Transporte", "Completá el transporte.", parent=transporte_dialogo)
                return
            transporte_dialogo.destroy()

            materiales_relacion = []
            for material in materiales:
                clave = id(material)
                if clave not in seleccionados:
                    continue
                copia = dict(material)
                copia["cantidad"] = seleccionados[clave]
                materiales_relacion.append(copia)

            nombre_archivo = f"RELACION DE TRANSITO_{datetime.now():%Y%m%d_%H%M%S}.xlsx"
            salida = filedialog.asksaveasfilename(
                parent=ventana,
                title="Guardar Relación de Tránsito",
                defaultextension=".xlsx",
                initialfile=nombre_archivo,
                filetypes=[("Excel", "*.xlsx")],
            )
            if not salida:
                return

            try:
                app.generar_relacion_transito(
                    materiales=materiales_relacion,
                    salida=salida,
                    tipo_movimiento=tipo.get().strip(),
                    destino=destino.get().strip(),
                    transporte=transporte,
                    generar_pdf=generar_pdf.get(),
                )
                messagebox.showinfo(
                    "Relación de Tránsito",
                    f"La relación se generó correctamente con {len(materiales_relacion)} material(es).\n\nExcel:\n{salida}"
                    + (f"\n\nPDF:\n{salida.rsplit('.', 1)[0]}.pdf" if generar_pdf.get() else ""),
                    parent=ventana,
                )
                ventana.destroy()
            except app.RelacionTransitoError as error:
                traceback.print_exc()
                messagebox.showerror("Relación de Tránsito", f"No se pudo generar la relación:\n\n{error}", parent=ventana)
            except Exception as error:
                traceback.print_exc()
                messagebox.showerror("Relación de Tránsito", f"Ocurrió un error inesperado:\n\n{error}", parent=ventana)

        botones_transporte = ttk.Frame(marco_transporte)
        botones_transporte.pack(fill="x")
        ttk.Button(botones_transporte, text="Generar relación", command=confirmar_generacion).pack(side="right", padx=(6, 0))
        ttk.Button(botones_transporte, text="Cancelar", command=transporte_dialogo.destroy).pack(side="right")
        transporte_dialogo.bind("<Return>", lambda _event: confirmar_generacion())

    botones = ttk.Frame(marco)
    botones.pack(fill="x", pady=(10, 0))
    ttk.Button(botones, text="☑ Seleccionar todo", command=seleccionar_todo).pack(side="left", padx=(0, 6))
    ttk.Button(botones, text="☐ Deseleccionar todo", command=deseleccionar_todo).pack(side="left", padx=(0, 6))
    ttk.Button(botones, text="❌ Quitar selección", command=quitar_seleccion).pack(side="left")
    ttk.Button(botones, text="Generar Relación de Tránsito", command=generar).pack(side="right")
    ttk.Button(botones, text="Cerrar", command=ventana.destroy).pack(side="right", padx=(0, 8))

    busqueda.trace_add("write", cargar_tabla)
    cargar_tabla()
    ventana.bind("<Escape>", lambda _event: ventana.destroy())


def _numero_float(valor):
    try:
        return float(valor or 0)
    except (TypeError, ValueError):
        return 0.0


def agregar_boton_administracion(app, nombre_admin):
    try:
        cabecera = app.root.winfo_children()[0]
        boton_permisos = ttk.Button(cabecera, text="🔐 Permisos", command=lambda: abrir_admin_permisos(app.root))
        boton_permisos.pack(side="right", padx=(0, 8))
        boton_usuarios = ttk.Button(cabecera, text="👥 Usuarios", command=lambda: abrir_admin_usuarios(app.root, nombre_admin))
        boton_usuarios.pack(side="right", padx=(0, 12))
        return True
    except Exception:
        traceback.print_exc()
        return False


def abrir_admin_usuarios(parent, nombre_admin):
    try:
        from admin_usuarios import abrir_admin_usuarios as abrir
        return abrir(parent, nombre_admin)
    except Exception as error:
        traceback.print_exc()
        messagebox.showerror("Administración de usuarios", f"No se pudo abrir el panel de usuarios:\n\n{error}", parent=parent)


def abrir_admin_permisos(parent):
    try:
        from permisos_documentos import abrir_admin_permisos as abrir
        return abrir(parent)
    except Exception as error:
        traceback.print_exc()
        messagebox.showerror("Permisos por documento", f"No se pudo abrir el panel de permisos:\n\n{error}", parent=parent)


def ejecutar_aplicacion(datos_usuario):
    import main as app
    perfil = datos_usuario.get("perfil") or {}
    rol = obtener_rol_usuario(datos_usuario)
    nombre = obtener_nombre_usuario(datos_usuario) or perfil.get("email") or "Usuario"
    app.USUARIO_ACTUAL = datos_usuario
    app.USUARIO_NOMBRE = nombre
    app.USUARIO_ROL = rol

    def proteger(nombre_permiso, funcion):
        def wrapper(*args, **kwargs):
            if tiene_permiso(rol, nombre_permiso):
                return funcion(*args, **kwargs)
            messagebox.showwarning("Permiso denegado", "Tu usuario no tiene permiso para realizar esta acción.\n\n" f"Rol actual: {rol}", parent=getattr(app, "root", None))
        wrapper.__name__ = getattr(funcion, "__name__", "accion")
        return wrapper

    def proteger_documento(nombre_permiso, funcion):
        """Aplica una segunda capa de autorización específica del documento."""
        def wrapper(*args, **kwargs):
            try:
                documento_id = app.obtener_documento_id_actual()
            except Exception:
                documento_id = None
            if tiene_permiso_documento(documento_id, nombre_permiso):
                return funcion(*args, **kwargs)
            messagebox.showwarning(
                "Permiso de documento denegado",
                "No tenés permiso para realizar esta acción sobre el documento seleccionado.\n\n"
                f"Permiso requerido: {nombre_permiso}",
                parent=getattr(app, "root", None),
            )
        wrapper.__name__ = getattr(funcion, "__name__", "accion")
        return wrapper

    app.nuevo_material = proteger("crear_material", app.nuevo_material)
    app.editar_material = proteger("editar_material", app.editar_material)
    app.eliminar_material = proteger("eliminar_material", app.eliminar_material)
    app.agregar_stock = proteger("agregar_stock", app.agregar_stock)
    app.retirar_stock = proteger("retirar_stock", app.retirar_stock)
    app.abrir_reportes = proteger("generar_reportes", app.abrir_reportes)
    app.importar_word_manual = proteger("importar_word", app.importar_word_manual)
    app.reescaneo_completo = proteger("reescaneo_completo", app.reescaneo_completo)

    app.nuevo_material = proteger_documento("modificar", app.nuevo_material)
    app.editar_material = proteger_documento("modificar", app.editar_material)
    app.eliminar_material = proteger_documento("eliminar", app.eliminar_material)
    app.agregar_stock = proteger_documento("agregar", app.agregar_stock)
    app.retirar_stock = proteger_documento("retirar", app.retirar_stock)
    app.reescaneo_completo = proteger_documento("importar", app.reescaneo_completo)

    funcion_stock_original = app.actualizar_stock_documento
    def actualizar_stock_con_usuario(*args, **kwargs):
        args = list(args)
        if len(args) >= 4:
            args[3] = nombre
        else:
            kwargs["usuario"] = nombre
        return funcion_stock_original(*args, **kwargs)
    app.actualizar_stock_documento = actualizar_stock_con_usuario

    try:
        import supabase_db
        supabase_db.USUARIO_ACTUAL = nombre
    except Exception:
        pass

    app.generar_relacion_transito_ui = lambda: abrir_selector_relacion_transito(app)

    if rol == "administrador":
        funcion_cabecera_original = app.crear_cabecera
        def crear_cabecera_con_usuarios():
            funcion_cabecera_original()
            agregar_boton_administracion(app, nombre)
        app.crear_cabecera = crear_cabecera_con_usuarios

    app.crear_interfaz()
    try:
        root = app.root
        def cerrar():
            try:
                cerrar_sesion()
            finally:
                root.destroy()
        root.protocol("WM_DELETE_WINDOW", cerrar)
    except Exception:
        pass


def mostrar_login():
    login = tk.Tk()
    login.title("Acceso - Inventario Material Naval")
    login.geometry("430x350")
    login.resizable(False, False)
    login.configure(bg="#eef3f8")
    estilo = ttk.Style(login)
    try:
        estilo.theme_use("clam")
    except Exception:
        pass
    estilo.configure("Login.TFrame", background="#eef3f8")
    estilo.configure("Login.TLabel", background="#eef3f8", foreground="#183247")
    estilo.configure("Login.Title.TLabel", background="#12304a", foreground="white", font=("Segoe UI", 17, "bold"))
    estilo.configure("Login.TButton", padding=(12, 8), font=("Segoe UI", 10, "bold"))
    cabecera = tk.Frame(login, bg="#12304a", height=70)
    cabecera.pack(fill="x")
    cabecera.pack_propagate(False)
    ttk.Label(cabecera, text="⚓ INVENTARIO MATERIAL NAVAL", style="Login.Title.TLabel").pack(anchor="w", padx=20, pady=20)
    marco = ttk.Frame(login, style="Login.TFrame", padding=25)
    marco.pack(fill="both", expand=True)
    ttk.Label(marco, text="Email", style="Login.TLabel", font=("Segoe UI", 10, "bold")).pack(anchor="w")
    entrada_email = ttk.Entry(marco, width=42)
    entrada_email.pack(fill="x", pady=(5, 12))
    ttk.Label(marco, text="Contraseña", style="Login.TLabel", font=("Segoe UI", 10, "bold")).pack(anchor="w")
    entrada_password = ttk.Entry(marco, width=42, show="*")
    entrada_password.pack(fill="x", pady=(5, 12))
    estado = ttk.Label(marco, text="", style="Login.TLabel")
    estado.pack(anchor="w", pady=(0, 8))

    def entrar(event=None):
        email = entrada_email.get().strip()
        password = entrada_password.get()
        if not email or not password:
            messagebox.showwarning("Acceso", "Ingresá el email y la contraseña.", parent=login)
            return
        boton.config(state="disabled")
        estado.config(text="Conectando...")
        login.update_idletasks()
        try:
            datos = iniciar_sesion(email, password)
            login.destroy()
            ejecutar_aplicacion(datos)
        except Exception as error:
            boton.config(state="normal")
            estado.config(text="No se pudo iniciar sesión.")
            messagebox.showerror("Acceso rechazado", str(error), parent=login)
            entrada_password.focus_set()

    boton = ttk.Button(marco, text="🔐 Iniciar sesión", command=entrar, style="Login.TButton")
    boton.pack(fill="x", pady=(2, 7))
    ttk.Button(marco, text="👤 Solicitar acceso", command=lambda: mostrar_solicitud_acceso(login), style="Login.TButton").pack(fill="x")
    login.bind("<Return>", entrar)
    entrada_email.focus_set()
    login.protocol("WM_DELETE_WINDOW", login.destroy)
    login.mainloop()


if __name__ == "__main__":
    try:
        mostrar_login()
    except Exception:
        traceback.print_exc()
        raise
