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


from ui_relacion_transito import abrir_selector_relacion_transito

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
