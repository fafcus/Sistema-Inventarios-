import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime

from config import supabase
from permisos_documentos import es_administrador


ESTADOS = ("pendiente", "aprobada", "rechazada")
ROLES = ("consulta", "encargado", "administrador")


def _formatear_fecha(valor):
    if not valor:
        return ""
    texto = str(valor).replace("T", " ")
    return texto[:19]


def _obtener_solicitudes(estado=None):
    consulta = (
        supabase.table("solicitudes_usuarios")
        .select("*")
        .order("fecha_solicitud", desc=True)
    )
    if estado:
        consulta = consulta.eq("estado", estado)
    return consulta.execute().data or []


def _actualizar_solicitud(solicitud_id, estado, admin_nombre, observaciones=None):
    datos = {
        "estado": estado,
        "revisado_por": admin_nombre,
        "fecha_revision": datetime.now().isoformat(),
    }
    if observaciones is not None:
        datos["observaciones"] = observaciones

    data = (
        supabase.table("solicitudes_usuarios")
        .update(datos)
        .eq("id", solicitud_id)
        .execute()
        .data
        or []
    )
    return data[0] if data else None


def _autorizar_usuario(solicitud_id, rol, observaciones=None):
    """
    Autoriza una solicitud mediante la Edge Function de Supabase.

    La Edge Function verifica que el usuario actual sea administrador y usa
    privilegios de servidor para crear/invitar la cuenta de Auth y completar
    el perfil. El service-role nunca se guarda en esta aplicación de escritorio.
    """
    respuesta = supabase.functions.invoke(
        "autorizar_usuario",
        invoke_options={
            "body": {
                "solicitud_id": solicitud_id,
                "rol": rol,
                "observaciones": observaciones,
            }
        },
    )
    return respuesta


def _obtener_usuarios():
    return (
        supabase.table("usuarios")
        .select("id, nombre, email, rol, activo, fecha_creacion")
        .order("nombre")
        .execute()
        .data
        or []
    )


def _usuario_actual_id():
    try:
        usuario = supabase.auth.get_user().user
        return str(usuario.id) if usuario else None
    except Exception:
        return None


def _actualizar_usuario(user_id, rol, activo):
    datos = {
        "rol": str(rol).strip().lower(),
        "activo": bool(activo),
    }
    respuesta = (
        supabase.table("usuarios")
        .update(datos)
        .eq("id", str(user_id))
        .execute()
    )
    return respuesta.data or []


def _desactivar_usuario_por_email(email):
    try:
        supabase.table("usuarios").update({"activo": False}).eq("email", email).execute()
    except Exception:
        pass


def abrir_admin_usuarios(parent, nombre_admin):
    if not es_administrador():
        messagebox.showerror(
            "Usuarios",
            "Solo un administrador puede administrar usuarios.",
            parent=parent,
        )
        return None

    ventana = tk.Toplevel(parent)
    ventana.title("Administración de usuarios")
    ventana.geometry("1100x680")
    ventana.minsize(950, 570)
    ventana.transient(parent)

    titulo = tk.Frame(ventana, bg="#12304a", height=70)
    titulo.pack(fill="x")
    titulo.pack_propagate(False)

    tk.Label(
        titulo,
        text="👥 Administración de usuarios",
        bg="#12304a",
        fg="white",
        font=("Segoe UI", 16, "bold"),
    ).pack(anchor="w", padx=20, pady=(10, 0))
    tk.Label(
        titulo,
        text="Gestioná solicitudes, roles y estado de acceso de los usuarios.",
        bg="#12304a",
        fg="#dce8f1",
        font=("Segoe UI", 9),
    ).pack(anchor="w", padx=20)

    notebook = ttk.Notebook(ventana)
    notebook.pack(fill="both", expand=True, padx=12, pady=12)

    # ========================================================
    # TAB 1: SOLICITUDES
    # ========================================================

    tab_solicitudes = ttk.Frame(notebook, padding=12)
    notebook.add(tab_solicitudes, text="📨 Solicitudes")

    superior = ttk.Frame(tab_solicitudes)
    superior.pack(fill="x")

    filtro = tk.StringVar(value="pendiente")
    ttk.Label(superior, text="Mostrar:").pack(side="left", padx=(0, 7))
    combo = ttk.Combobox(
        superior,
        textvariable=filtro,
        values=("pendiente", "aprobada", "rechazada", "todas"),
        state="readonly",
        width=14,
    )
    combo.pack(side="left")

    lbl_estado = ttk.Label(superior, text="")
    lbl_estado.pack(side="left", padx=15)

    cont = ttk.Frame(tab_solicitudes)
    cont.pack(fill="both", expand=True, pady=(10, 10))

    columnas = ("id", "nombre", "email", "rol", "estado", "fecha", "revisado")
    tabla = ttk.Treeview(
        cont,
        columns=columnas,
        show="headings",
        selectmode="browse",
    )
    encabezados = {
        "id": "ID",
        "nombre": "Nombre",
        "email": "Email",
        "rol": "Rol solicitado",
        "estado": "Estado",
        "fecha": "Solicitud",
        "revisado": "Revisado por",
    }
    anchos = {
        "id": 55,
        "nombre": 190,
        "email": 250,
        "rol": 130,
        "estado": 110,
        "fecha": 150,
        "revisado": 140,
    }
    for col in columnas:
        tabla.heading(col, text=encabezados[col])
        tabla.column(col, width=anchos[col], minwidth=60)

    sy = ttk.Scrollbar(cont, orient="vertical", command=tabla.yview)
    sx = ttk.Scrollbar(cont, orient="horizontal", command=tabla.xview)
    tabla.configure(yscrollcommand=sy.set, xscrollcommand=sx.set)
    tabla.grid(row=0, column=0, sticky="nsew")
    sy.grid(row=0, column=1, sticky="ns")
    sx.grid(row=1, column=0, sticky="ew")
    cont.rowconfigure(0, weight=1)
    cont.columnconfigure(0, weight=1)

    solicitudes = {}

    def cargar_solicitudes():
        try:
            valor = filtro.get()
            estado = None if valor == "todas" else valor
            datos = _obtener_solicitudes(estado)
            solicitudes.clear()

            for item in tabla.get_children():
                tabla.delete(item)

            for solicitud in datos:
                sid = str(solicitud.get("id"))
                solicitudes[sid] = solicitud
                tabla.insert(
                    "",
                    "end",
                    iid=sid,
                    values=(
                        sid,
                        solicitud.get("nombre") or "",
                        solicitud.get("email") or "",
                        solicitud.get("rol_solicitado") or "consulta",
                        solicitud.get("estado") or "",
                        _formatear_fecha(solicitud.get("fecha_solicitud")),
                        solicitud.get("revisado_por") or "",
                    ),
                )

            pendientes = len(_obtener_solicitudes("pendiente"))
            lbl_estado.config(text=f"Solicitudes pendientes: {pendientes}")
        except Exception as error:
            messagebox.showerror(
                "Usuarios",
                f"No se pudieron cargar las solicitudes:\n\n{error}",
                parent=ventana,
            )

    def solicitud_seleccionada():
        seleccion = tabla.selection()
        if not seleccion:
            messagebox.showwarning(
                "Usuarios",
                "Seleccioná una solicitud.",
                parent=ventana,
            )
            return None
        return solicitudes.get(str(seleccion[0]))

    def detalle():
        solicitud = solicitud_seleccionada()
        if not solicitud:
            return

        texto = (
            f"Nombre: {solicitud.get('nombre') or ''}\n"
            f"Email: {solicitud.get('email') or ''}\n"
            f"Rol solicitado: {solicitud.get('rol_solicitado') or ''}\n"
            f"Estado: {solicitud.get('estado') or ''}\n"
            f"Fecha: {_formatear_fecha(solicitud.get('fecha_solicitud'))}\n"
            f"Revisado por: {solicitud.get('revisado_por') or '-'}\n"
            f"Observaciones: {solicitud.get('observaciones') or '-'}"
        )
        messagebox.showinfo("Detalle de solicitud", texto, parent=ventana)

    def aprobar():
        solicitud = solicitud_seleccionada()
        if not solicitud:
            return

        if solicitud.get("estado") != "pendiente":
            messagebox.showinfo(
                "Usuarios",
                "La solicitud ya fue revisada.",
                parent=ventana,
            )
            return

        rol_inicial = str(
            solicitud.get("rol_solicitado") or "consulta"
        ).strip().lower()
        if rol_inicial not in ("consulta", "encargado"):
            rol_inicial = "consulta"

        dialogo = tk.Toplevel(ventana)
        dialogo.title("Autorizar usuario")
        dialogo.geometry("430x230")
        dialogo.transient(ventana)
        dialogo.grab_set()

        frame = ttk.Frame(dialogo, padding=20)
        frame.pack(fill="both", expand=True)

        ttk.Label(
            frame,
            text=f"Autorizar a: {solicitud.get('nombre') or solicitud.get('email')}",
            font=("Segoe UI", 10, "bold"),
        ).pack(anchor="w", pady=(0, 12))

        ttk.Label(frame, text="Rol a asignar:").pack(anchor="w")
        rol_var = tk.StringVar(value=rol_inicial)
        ttk.Combobox(
            frame,
            textvariable=rol_var,
            values=("consulta", "encargado"),
            state="readonly",
        ).pack(fill="x", pady=(5, 12))

        ttk.Label(frame, text="Observaciones (opcional):").pack(anchor="w")
        obs = ttk.Entry(frame)
        obs.pack(fill="x", pady=(5, 15))

        def confirmar():
            rol = rol_var.get().strip().lower()
            if rol not in ("consulta", "encargado"):
                messagebox.showwarning(
                    "Usuarios",
                    "Rol inválido.",
                    parent=dialogo,
                )
                return

            if not messagebox.askyesno(
                "Confirmar autorización",
                f"¿Autorizar a {solicitud.get('email')} como {rol}?",
                parent=dialogo,
            ):
                return

            try:
                boton_autorizar.config(state="disabled")
                _autorizar_usuario(
                    solicitud["id"],
                    rol,
                    obs.get().strip() or None,
                )
                dialogo.destroy()
                cargar_solicitudes()
                cargar_usuarios()
                messagebox.showinfo(
                    "Usuario autorizado",
                    "El usuario fue autorizado correctamente.\n\n"
                    "Se envió un correo de invitación para configurar la contraseña.",
                    parent=ventana,
                )
            except Exception as error:
                boton_autorizar.config(state="normal")
                messagebox.showerror(
                    "Error",
                    f"No se pudo autorizar al usuario:\n\n{error}",
                    parent=dialogo,
                )

        boton_autorizar = ttk.Button(
            frame,
            text="Autorizar",
            command=confirmar,
        )
        boton_autorizar.pack(side="right", padx=4)
        ttk.Button(
            frame,
            text="Cancelar",
            command=dialogo.destroy,
        ).pack(side="right", padx=4)

    def rechazar():
        solicitud = solicitud_seleccionada()
        if not solicitud:
            return

        if solicitud.get("estado") != "pendiente":
            messagebox.showinfo(
                "Usuarios",
                "La solicitud ya fue revisada.",
                parent=ventana,
            )
            return

        if not messagebox.askyesno(
            "Rechazar solicitud",
            f"¿Rechazar la solicitud de {solicitud.get('email')}?",
            parent=ventana,
        ):
            return

        try:
            _desactivar_usuario_por_email(solicitud.get("email"))
            _actualizar_solicitud(
                solicitud["id"],
                "rechazada",
                nombre_admin,
            )
            cargar_solicitudes()
            cargar_usuarios()
        except Exception as error:
            messagebox.showerror(
                "Error",
                f"No se pudo rechazar la solicitud:\n\n{error}",
                parent=ventana,
            )

    botones_solicitudes = ttk.Frame(tab_solicitudes)
    botones_solicitudes.pack(fill="x")

    ttk.Button(
        botones_solicitudes,
        text="🔄 Actualizar",
        command=cargar_solicitudes,
    ).pack(side="left", padx=3)

    ttk.Button(
        botones_solicitudes,
        text="ℹ️ Detalle",
        command=detalle,
    ).pack(side="left", padx=3)

    ttk.Button(
        botones_solicitudes,
        text="❌ Rechazar",
        command=rechazar,
    ).pack(side="right", padx=3)

    ttk.Button(
        botones_solicitudes,
        text="✅ Autorizar",
        command=aprobar,
    ).pack(side="right", padx=3)

    combo.bind("<<ComboboxSelected>>", lambda event: cargar_solicitudes())

    # ========================================================
    # TAB 2: USUARIOS
    # ========================================================

    tab_usuarios = ttk.Frame(notebook, padding=12)
    notebook.add(tab_usuarios, text="👥 Usuarios")

    ayuda = ttk.Label(
        tab_usuarios,
        text=(
            "Desde acá podés cambiar el rol y activar/desactivar el acceso. "
            "El administrador actual no puede desactivarse ni quitarse su propio rol."
        ),
        foreground="#506575",
        wraplength=900,
    )
    ayuda.pack(fill="x", pady=(0, 10))

    cont_usuarios = ttk.Frame(tab_usuarios)
    cont_usuarios.pack(fill="both", expand=True)

    columnas_usuarios = (
        "nombre",
        "email",
        "rol",
        "activo",
        "fecha",
    )
    tabla_usuarios = ttk.Treeview(
        cont_usuarios,
        columns=columnas_usuarios,
        show="headings",
        selectmode="browse",
    )

    encabezados_usuarios = {
        "nombre": "Nombre",
        "email": "Email",
        "rol": "Rol",
        "activo": "Estado",
        "fecha": "Fecha de alta",
    }
    anchos_usuarios = {
        "nombre": 230,
        "email": 300,
        "rol": 150,
        "activo": 120,
        "fecha": 170,
    }

    for col in columnas_usuarios:
        tabla_usuarios.heading(col, text=encabezados_usuarios[col])
        tabla_usuarios.column(
            col,
            width=anchos_usuarios[col],
            minwidth=80,
        )

    sy_usuarios = ttk.Scrollbar(
        cont_usuarios,
        orient="vertical",
        command=tabla_usuarios.yview,
    )
    sx_usuarios = ttk.Scrollbar(
        cont_usuarios,
        orient="horizontal",
        command=tabla_usuarios.xview,
    )
    tabla_usuarios.configure(
        yscrollcommand=sy_usuarios.set,
        xscrollcommand=sx_usuarios.set,
    )

    tabla_usuarios.grid(row=0, column=0, sticky="nsew")
    sy_usuarios.grid(row=0, column=1, sticky="ns")
    sx_usuarios.grid(row=1, column=0, sticky="ew")
    cont_usuarios.rowconfigure(0, weight=1)
    cont_usuarios.columnconfigure(0, weight=1)

    usuarios = {}

    def cargar_usuarios():
        try:
            datos = _obtener_usuarios()
            usuarios.clear()

            for item in tabla_usuarios.get_children():
                tabla_usuarios.delete(item)

            for usuario in datos:
                uid = str(usuario.get("id"))
                usuarios[uid] = usuario
                estado = "ACTIVO" if usuario.get("activo") else "INACTIVO"

                tabla_usuarios.insert(
                    "",
                    "end",
                    iid=uid,
                    values=(
                        usuario.get("nombre") or "",
                        usuario.get("email") or "",
                        usuario.get("rol") or "consulta",
                        estado,
                        _formatear_fecha(usuario.get("fecha_creacion")),
                    ),
                )
        except Exception as error:
            messagebox.showerror(
                "Usuarios",
                f"No se pudieron cargar los usuarios:\n\n{error}",
                parent=ventana,
            )

    def usuario_seleccionado():
        seleccion = tabla_usuarios.selection()
        if not seleccion:
            messagebox.showwarning(
                "Usuarios",
                "Seleccioná un usuario.",
                parent=ventana,
            )
            return None
        return usuarios.get(str(seleccion[0]))

    def editar_usuario():
        usuario = usuario_seleccionado()
        if not usuario:
            return

        uid = str(usuario["id"])
        actual_id = _usuario_actual_id()
        es_propio = uid == str(actual_id or "")

        dialogo = tk.Toplevel(ventana)
        dialogo.title("Editar usuario")
        dialogo.geometry("460x310")
        dialogo.transient(ventana)
        dialogo.grab_set()

        frame = ttk.Frame(dialogo, padding=20)
        frame.pack(fill="both", expand=True)

        ttk.Label(
            frame,
            text=usuario.get("nombre") or usuario.get("email") or "Usuario",
            font=("Segoe UI", 12, "bold"),
        ).pack(anchor="w")

        ttk.Label(
            frame,
            text=usuario.get("email") or "",
            foreground="#506575",
        ).pack(anchor="w", pady=(2, 18))

        ttk.Label(
            frame,
            text="Rol:",
            font=("Segoe UI", 10, "bold"),
        ).pack(anchor="w")

        rol_var = tk.StringVar(value=str(usuario.get("rol") or "consulta"))
        combo_rol = ttk.Combobox(
            frame,
            textvariable=rol_var,
            values=ROLES,
            state="readonly",
        )
        combo_rol.pack(fill="x", pady=(5, 14))

        activo_var = tk.BooleanVar(value=bool(usuario.get("activo")))
        check_activo = ttk.Checkbutton(
            frame,
            text="Usuario activo",
            variable=activo_var,
        )
        check_activo.pack(anchor="w", pady=(0, 15))

        if es_propio:
            combo_rol.configure(state="disabled")
            check_activo.configure(state="disabled")
            ttk.Label(
                frame,
                text="Este es tu usuario actual. No podés cambiar tu propio rol ni desactivarte.",
                foreground="#8a4b08",
                wraplength=400,
            ).pack(anchor="w", pady=(0, 10))

        def guardar():
            nuevo_rol = rol_var.get().strip().lower()
            nuevo_activo = bool(activo_var.get())

            if nuevo_rol not in ROLES:
                messagebox.showwarning(
                    "Usuarios",
                    "Seleccioná un rol válido.",
                    parent=dialogo,
                )
                return

            if es_propio:
                return

            # Evitar dejar al sistema sin ningún administrador activo.
            if (
                usuario.get("rol") == "administrador"
                and usuario.get("activo")
                and (nuevo_rol != "administrador" or not nuevo_activo)
            ):
                try:
                    admins = (
                        supabase.table("usuarios")
                        .select("id")
                        .eq("rol", "administrador")
                        .eq("activo", True)
                        .execute()
                        .data
                        or []
                    )
                    if len(admins) <= 1:
                        messagebox.showwarning(
                            "Usuarios",
                            "No se puede quitar el último administrador activo del sistema.",
                            parent=dialogo,
                        )
                        return
                except Exception as error:
                    messagebox.showerror(
                        "Usuarios",
                        f"No se pudo verificar la cantidad de administradores:\n\n{error}",
                        parent=dialogo,
                    )
                    return

            if not messagebox.askyesno(
                "Confirmar cambios",
                (
                    f"¿Guardar cambios para {usuario.get('email')}?\n\n"
                    f"Rol: {nuevo_rol}\n"
                    f"Estado: {'ACTIVO' if nuevo_activo else 'INACTIVO'}"
                ),
                parent=dialogo,
            ):
                return

            try:
                _actualizar_usuario(uid, nuevo_rol, nuevo_activo)
                dialogo.destroy()
                cargar_usuarios()
                messagebox.showinfo(
                    "Usuarios",
                    "Los datos del usuario fueron actualizados.",
                    parent=ventana,
                )
            except Exception as error:
                messagebox.showerror(
                    "Usuarios",
                    f"No se pudieron guardar los cambios:\n\n{error}",
                    parent=dialogo,
                )

        botones = ttk.Frame(frame)
        botones.pack(fill="x", pady=(8, 0))
        ttk.Button(
            botones,
            text="Cancelar",
            command=dialogo.destroy,
        ).pack(side="right", padx=4)
        ttk.Button(
            botones,
            text="💾 Guardar",
            command=guardar,
        ).pack(side="right", padx=4)

    def ver_detalle_usuario():
        usuario = usuario_seleccionado()
        if not usuario:
            return

        texto = (
            f"Nombre: {usuario.get('nombre') or '-'}\n"
            f"Email: {usuario.get('email') or '-'}\n"
            f"Rol: {usuario.get('rol') or '-'}\n"
            f"Estado: {'Activo' if usuario.get('activo') else 'Inactivo'}\n"
            f"Fecha de alta: {_formatear_fecha(usuario.get('fecha_creacion'))}"
        )
        messagebox.showinfo(
            "Detalle de usuario",
            texto,
            parent=ventana,
        )

    botones_usuarios = ttk.Frame(tab_usuarios)
    botones_usuarios.pack(fill="x", pady=(10, 0))

    ttk.Button(
        botones_usuarios,
        text="🔄 Actualizar",
        command=cargar_usuarios,
    ).pack(side="left", padx=3)

    ttk.Button(
        botones_usuarios,
        text="ℹ️ Detalle",
        command=ver_detalle_usuario,
    ).pack(side="left", padx=3)

    ttk.Button(
        botones_usuarios,
        text="✏️ Editar usuario",
        command=editar_usuario,
    ).pack(side="right", padx=3)

    cargar_solicitudes()
    cargar_usuarios()

    ventana.focus_force()
    return ventana
