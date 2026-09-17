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
    ttk.Label(marco, text=("La solicitud quedará pendiente hasta que un administrador autorice el acceso.\n\n"
                           "No se solicita una contraseña en esta etapa. Si se aprueba, recibirás un correo para configurar tu contraseña.\n\n"
                           "El rol administrador no puede solicitarse desde esta pantalla."), foreground="#506575", wraplength=430).grid(row=3, column=0, columnspan=2, sticky="w", pady=(12, 12))
    estado = ttk.Label(marco, text="", foreground="#506575", wraplength=430)
    estado.grid(row=4, column=0, columnspan=2, sticky="w", pady=(0, 10))

    def enviar():
        boton.config(state="disabled")
        estado.config(text="Registrando solicitud...")
        ventana.update_idletasks()
        try:
            solicitar_acceso(entradas["nombre"].get(), entradas["email"].get(), rol_var.get())
            messagebox.showinfo("Solicitud enviada", "La solicitud fue enviada correctamente.\n\nUn administrador debe autorizar tu acceso. Cuando sea aprobada, recibirás un correo para configurar tu contraseña.", parent=ventana)
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
    """Selecciona materiales de todos los inventarios y genera una relación."""
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
    ventana.geometry("1120x700")
    ventana.minsize(900, 560)
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

    filtros = ttk.Frame(marco)
    filtros.pack(fill="x", pady=(0, 10))

    ttk.Label(filtros, text="Buscar:", font=("Segoe UI", 10, "bold")).pack(side="left")
    busqueda = tk.StringVar()
    entrada_busqueda = ttk.Entry(filtros, textvariable=busqueda, width=38)
    entrada_busqueda.pack(side="left", padx=(8, 18))

    ttk.Label(filtros, text="Tipo:", font=("Segoe UI", 10, "bold")).pack(side="left")
    tipo = tk.StringVar()
    ttk.Entry(filtros, textvariable=tipo, width=18).pack(side="left", padx=(8, 18))

    ttk.Label(filtros, text="Destino:", font=("Segoe UI", 10, "bold")).pack(side="left")
    destino = tk.StringVar()
    ttk.Entry(filtros, textvariable=destino, width=22).pack(side="left", padx=(8, 0))

    marco_tabla = ttk.Frame(marco)
    marco_tabla.pack(fill="both", expand=True)

    columnas = ("codigo", "material", "stock", "llevar", "unidad", "ubicacion", "origen")
    tabla = ttk.Treeview(marco_tabla, columns=columnas, show="headings", selectmode="browse")
    encabezados = {
        "codigo": "Código",
        "material": "Material",
        "stock": "Stock disponible",
        "llevar": "Cantidad a llevar",
        "unidad": "Unidad",
        "ubicacion": "Ubicación",
        "origen": "Archivo origen",
    }
    anchos = {"codigo": 120, "material": 300, "stock": 110, "llevar": 120, "unidad": 100, "ubicacion": 180, "origen": 190}
    for columna in columnas:
        tabla.heading(columna, text=encabezados[columna])
        tabla.column(columna, width=anchos[columna], minwidth=70, anchor="w")

    scroll = ttk.Scrollbar(marco_tabla, orient="vertical", command=tabla.yview)
    tabla.configure(yscrollcommand=scroll.set)
    tabla.pack(side="left", fill="both", expand=True)
    scroll.pack(side="right", fill="y")

    seleccionados = {}
    visibles = []

    def clave_material(material):
        return material.get("id")

    def cantidad_disponible(material):
        return _numero_float(material.get("cantidad"))

    def cantidad_formateada(valor):
        numero = _numero_float(valor)
        return f"{numero:g}"

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
            mid = clave_material(material)
            cantidad = seleccionados.get(mid, cantidad_disponible(material))
            tabla.insert(
                "",
                "end",
                iid=str(mid),
                values=(
                    material.get("codigo") or "",
                    material.get("material") or "",
                    cantidad_formateada(cantidad_disponible(material)),
                    cantidad_formateada(cantidad),
                    material.get("unidad") or "",
                    material.get("ubicacion") or "",
                    material.get("archivo_origen") or "-",
                ),
            )

    def obtener_visible(mid):
        for material in visibles:
            if str(clave_material(material)) == str(mid):
                return material
        return None

    def modificar_cantidad(event=None):
        seleccion = tabla.selection()
        if not seleccion:
            return
        material = obtener_visible(seleccion[0])
        if not material:
            return
        disponible = cantidad_disponible(material)
        actual = seleccionados.get(clave_material(material), disponible)
        dialogo = tk.Toplevel(ventana)
        dialogo.title("Cantidad a llevar")
        dialogo.geometry("430x230")
        dialogo.resizable(False, False)
        dialogo.transient(ventana)
        dialogo.grab_set()
        marco_cantidad = ttk.Frame(dialogo, padding=20)
        marco_cantidad.pack(fill="both", expand=True)
        ttk.Label(marco_cantidad, text=material.get("material") or "Material", font=("Segoe UI", 11, "bold"), wraplength=380).pack(anchor="w")
        ttk.Label(marco_cantidad, text=f"Stock disponible: {cantidad_formateada(disponible)} {material.get('unidad') or ''}").pack(anchor="w", pady=(8, 4))
        entrada = ttk.Entry(marco_cantidad, width=22)
        entrada.insert(0, cantidad_formateada(actual))
        entrada.pack(anchor="w", pady=(4, 10))
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
                    f"No podés llevar {cantidad:g}. El stock disponible es {disponible:g}.",
                    parent=dialogo,
                )
                return
            seleccionados[clave_material(material)] = cantidad
            dialogo.destroy()
            cargar_tabla()
            tabla.selection_set(str(clave_material(material)))
            tabla.focus(str(clave_material(material)))

        botones = ttk.Frame(marco_cantidad)
        botones.pack(fill="x", pady=(6, 0))
        ttk.Button(botones, text="Guardar cantidad", command=aceptar).pack(side="right", padx=(6, 0))
        ttk.Button(botones, text="Cancelar", command=dialogo.destroy).pack(side="right")
        dialogo.bind("<Return>", lambda _event: aceptar())

    tabla.bind("<Double-1>", modificar_cantidad)

    def seleccionar_material():
        seleccion = tabla.selection()
        if not seleccion:
            messagebox.showwarning("Selección", "Seleccioná un material de la lista.", parent=ventana)
            return
        modificar_cantidad()

    def quitar_material():
        seleccion = tabla.selection()
        if not seleccion:
            return
        mid = int(seleccion[0])
        seleccionados.pop(mid, None)
        cargar_tabla()

    def generar():
        if not seleccionados:
            messagebox.showwarning("Relación de Tránsito", "Seleccioná al menos un material.", parent=ventana)
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
                mid = clave_material(material)
                if mid not in seleccionados:
                    continue
                copia = dict(material)
                copia["cantidad"] = seleccionados[mid]
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
                )
                messagebox.showinfo(
                    "Relación de Tránsito",
                    f"La relación se generó correctamente con {len(materiales_relacion)} material(es).\n\nArchivo:\n{salida}",
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
    ttk.Button(botones, text="✏️ Modificar cantidad", command=seleccionar_material).pack(side="left", padx=(0, 8))
    ttk.Button(botones, text="❌ Quitar selección", command=quitar_material).pack(side="left")
    ttk.Button(botones, text="Generar Relación de Tránsito", command=generar).pack(side="right")
    ttk.Button(botones, text="Cerrar", command=ventana.destroy).pack(side="right", padx=(0, 8))

    ttk.Label(
        marco,
        text="Seleccioná un material y modificá su cantidad con doble clic o con el botón. Podés seleccionar materiales de distintos archivos. La relación se genera al finalizar.",
        foreground="#506575",
        wraplength=1000,
    ).pack(fill="x", pady=(8, 0))

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

        boton_permisos = ttk.Button(
            cabecera,
            text="🔐 Permisos",
            command=lambda: abrir_admin_permisos(app.root),
        )
        boton_permisos.pack(side="right", padx=(0, 8))

        boton_usuarios = ttk.Button(
            cabecera,
            text="👥 Usuarios",
            command=lambda: abrir_admin_usuarios(app.root, nombre_admin),
        )
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

    # Permisos generales por rol.
    app.nuevo_material = proteger("crear_material", app.nuevo_material)
    app.editar_material = proteger("editar_material", app.editar_material)
    app.eliminar_material = proteger("eliminar_material", app.eliminar_material)
    app.agregar_stock = proteger("agregar_stock", app.agregar_stock)
    app.retirar_stock = proteger("retirar_stock", app.retirar_stock)
    app.abrir_reportes = proteger("generar_reportes", app.abrir_reportes)
    app.importar_word_manual = proteger("importar_word", app.importar_word_manual)
    app.reescaneo_completo = proteger("reescaneo_completo", app.reescaneo_completo)

    # Segunda capa: permisos particulares del documento seleccionado.
    # El administrador pasa siempre por RLS y por la comprobación del módulo.
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

    # La relación de tránsito ya no depende del material seleccionado en la
    # pantalla principal: se abre su propio selector con todo el inventario.
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
