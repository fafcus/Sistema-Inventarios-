import tkinter as tk
from tkinter import ttk, messagebox
import traceback

from usuarios_db import (
    iniciar_sesion,
    cerrar_sesion,
    tiene_permiso,
    obtener_nombre_usuario,
    obtener_rol_usuario,
)


def ejecutar_aplicacion(datos_usuario):
    import main as app

    perfil = datos_usuario.get("perfil") or {}
    rol = obtener_rol_usuario(datos_usuario)
    nombre = (
        obtener_nombre_usuario(datos_usuario)
        or perfil.get("email")
        or "Usuario"
    )

    # Contexto de sesión disponible para el resto de la aplicación.
    app.USUARIO_ACTUAL = datos_usuario
    app.USUARIO_NOMBRE = nombre
    app.USUARIO_ROL = rol

    def proteger(nombre_permiso, funcion):
        """Protege una acción existente sin modificar la interfaz actual."""
        def wrapper(*args, **kwargs):
            if tiene_permiso(rol, nombre_permiso):
                return funcion(*args, **kwargs)

            messagebox.showwarning(
                "Permiso denegado",
                "Tu usuario no tiene permiso para realizar esta acción.\n\n"
                f"Rol actual: {rol}",
                parent=getattr(app, "root", None),
            )

        wrapper.__name__ = getattr(funcion, "__name__", "accion")
        return wrapper

    # Los botones existentes conservarán exactamente su diseño.
    app.nuevo_material = proteger(
        "crear_material",
        app.nuevo_material,
    )
    app.editar_material = proteger(
        "editar_material",
        app.editar_material,
    )
    app.eliminar_material = proteger(
        "eliminar_material",
        app.eliminar_material,
    )
    app.agregar_stock = proteger(
        "agregar_stock",
        app.agregar_stock,
    )
    app.retirar_stock = proteger(
        "retirar_stock",
        app.retirar_stock,
    )
    app.abrir_reportes = proteger(
        "generar_reportes",
        app.abrir_reportes,
    )
    app.importar_word_manual = proteger(
        "importar_word",
        app.importar_word_manual,
    )
    app.reescaneo_completo = proteger(
        "reescaneo_completo",
        app.reescaneo_completo,
    )

    # Actualizar/sincronizar solamente consulta datos y queda disponible.

    # Los movimientos manuales usarán el nombre real del usuario logueado.
    funcion_stock_original = app.actualizar_stock_documento

    def actualizar_stock_con_usuario(*args, **kwargs):
        kwargs["usuario"] = nombre
        return funcion_stock_original(*args, **kwargs)

    app.actualizar_stock_documento = actualizar_stock_con_usuario

    # Dejamos el usuario disponible para futuras operaciones internas.
    try:
        import supabase_db
        supabase_db.USUARIO_ACTUAL = nombre
    except Exception:
        pass

    app.crear_interfaz()

    # Al cerrar la ventana se cierra también la sesión Supabase.
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
    login.geometry("430x300")
    login.resizable(False, False)
    login.configure(bg="#eef3f8")

    estilo = ttk.Style(login)

    try:
        estilo.theme_use("clam")
    except Exception:
        pass

    estilo.configure(
        "Login.TFrame",
        background="#eef3f8",
    )

    estilo.configure(
        "Login.TLabel",
        background="#eef3f8",
        foreground="#183247",
    )

    estilo.configure(
        "Login.Title.TLabel",
        background="#12304a",
        foreground="white",
        font=("Segoe UI", 17, "bold"),
    )

    estilo.configure(
        "Login.TButton",
        padding=(12, 8),
        font=("Segoe UI", 10, "bold"),
    )

    cabecera = tk.Frame(
        login,
        bg="#12304a",
        height=70,
    )

    cabecera.pack(fill="x")
    cabecera.pack_propagate(False)

    ttk.Label(
        cabecera,
        text="⚓ INVENTARIO MATERIAL NAVAL",
        style="Login.Title.TLabel",
    ).pack(
        anchor="w",
        padx=20,
        pady=20,
    )

    marco = ttk.Frame(
        login,
        style="Login.TFrame",
        padding=25,
    )

    marco.pack(
        fill="both",
        expand=True,
    )

    ttk.Label(
        marco,
        text="Email",
        style="Login.TLabel",
        font=("Segoe UI", 10, "bold"),
    ).pack(anchor="w")

    entrada_email = ttk.Entry(
        marco,
        width=42,
    )

    entrada_email.pack(
        fill="x",
        pady=(5, 12),
    )

    ttk.Label(
        marco,
        text="Contraseña",
        style="Login.TLabel",
        font=("Segoe UI", 10, "bold"),
    ).pack(anchor="w")

    entrada_password = ttk.Entry(
        marco,
        width=42,
        show="*",
    )

    entrada_password.pack(
        fill="x",
        pady=(5, 15),
    )

    estado = ttk.Label(
        marco,
        text="",
        style="Login.TLabel",
    )

    estado.pack(
        anchor="w",
        pady=(0, 8),
    )

    def entrar(event=None):
        email = entrada_email.get().strip()
        password = entrada_password.get()

        if not email or not password:
            messagebox.showwarning(
                "Acceso",
                "Ingresá el email y la contraseña.",
                parent=login,
            )
            return

        boton.config(state="disabled")
        estado.config(text="Conectando...")
        login.update_idletasks()

        try:
            datos = iniciar_sesion(
                email,
                password,
            )

            login.destroy()
            ejecutar_aplicacion(datos)

        except Exception as error:
            boton.config(state="normal")
            estado.config(
                text="No se pudo iniciar sesión."
            )

            messagebox.showerror(
                "Acceso rechazado",
                str(error),
                parent=login,
            )

            entrada_password.focus_set()

    boton = ttk.Button(
        marco,
        text="🔐 Iniciar sesión",
        command=entrar,
        style="Login.TButton",
    )

    boton.pack(
        fill="x",
        pady=(2, 0),
    )

    login.bind(
        "<Return>",
        entrar,
    )

    entrada_email.focus_set()

    login.protocol(
        "WM_DELETE_WINDOW",
        login.destroy,
    )

    login.mainloop()


if __name__ == "__main__":
    try:
        mostrar_login()
    except Exception:
        traceback.print_exc()
        raise
