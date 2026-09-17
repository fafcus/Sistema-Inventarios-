import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime

from config import supabase


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


def _desactivar_usuario_por_email(email):
    try:
        supabase.table("usuarios").update({"activo": False}).eq("email", email).execute()
    except Exception:
        pass


def abrir_admin_usuarios(parent, nombre_admin):
    ventana = tk.Toplevel(parent)
    ventana.title("Administración de usuarios")
    ventana.geometry("1050x620")
    ventana.minsize(900, 520)
    ventana.transient(parent)

    titulo = tk.Frame(ventana, bg="#12304a", height=65)
    titulo.pack(fill="x")
    titulo.pack_propagate(False)

    tk.Label(titulo, text="👥 Administración de usuarios", bg="#12304a", fg="white", font=("Segoe UI", 16, "bold")).pack(anchor="w", padx=20, pady=(10, 0))
    tk.Label(titulo, text="Revisá las solicitudes y autorizá el acceso al sistema.", bg="#12304a", fg="#dce8f1", font=("Segoe UI", 9)).pack(anchor="w", padx=20)

    superior = ttk.Frame(ventana, padding=12)
    superior.pack(fill="x")
    filtro = tk.StringVar(value="pendiente")
    ttk.Label(superior, text="Mostrar:").pack(side="left", padx=(0, 7))
    combo = ttk.Combobox(superior, textvariable=filtro, values=("pendiente", "aprobada", "rechazada", "todas"), state="readonly", width=14)
    combo.pack(side="left")
    lbl_estado = ttk.Label(superior, text="")
    lbl_estado.pack(side="left", padx=15)

    cont = ttk.Frame(ventana, padding=(12, 0, 12, 12))
    cont.pack(fill="both", expand=True)
    columnas = ("id", "nombre", "email", "rol", "estado", "fecha", "revisado")
    tabla = ttk.Treeview(cont, columns=columnas, show="headings", selectmode="browse")
    encabezados = {"id": "ID", "nombre": "Nombre", "email": "Email", "rol": "Rol solicitado", "estado": "Estado", "fecha": "Solicitud", "revisado": "Revisado por"}
    anchos = {"id": 55, "nombre": 190, "email": 250, "rol": 130, "estado": 110, "fecha": 150, "revisado": 140}
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

    def cargar():
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
                tabla.insert("", "end", iid=sid, values=(sid, solicitud.get("nombre") or "", solicitud.get("email") or "", solicitud.get("rol_solicitado") or "consulta", solicitud.get("estado") or "", _formatear_fecha(solicitud.get("fecha_solicitud")), solicitud.get("revisado_por") or ""))
            pendientes = len(_obtener_solicitudes("pendiente"))
            lbl_estado.config(text=f"Solicitudes pendientes: {pendientes}")
        except Exception as error:
            messagebox.showerror("Usuarios", f"No se pudieron cargar las solicitudes:\n\n{error}", parent=ventana)

    def seleccionada():
        seleccion = tabla.selection()
        if not seleccion:
            messagebox.showwarning("Usuarios", "Seleccioná una solicitud.", parent=ventana)
            return None
        return solicitudes.get(str(seleccion[0]))

    def detalle():
        solicitud = seleccionada()
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
        solicitud = seleccionada()
        if not solicitud:
            return
        if solicitud.get("estado") != "pendiente":
            messagebox.showinfo("Usuarios", "La solicitud ya fue revisada.", parent=ventana)
            return

        rol_inicial = str(solicitud.get("rol_solicitado") or "consulta").strip().lower()
        if rol_inicial not in ("consulta", "encargado"):
            rol_inicial = "consulta"

        dialogo = tk.Toplevel(ventana)
        dialogo.title("Autorizar usuario")
        dialogo.geometry("430x230")
        dialogo.transient(ventana)
        dialogo.grab_set()

        frame = ttk.Frame(dialogo, padding=20)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text=f"Autorizar a: {solicitud.get('nombre') or solicitud.get('email')}", font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(0, 12))
        ttk.Label(frame, text="Rol a asignar:").pack(anchor="w")
        rol_var = tk.StringVar(value=rol_inicial)
        ttk.Combobox(frame, textvariable=rol_var, values=("consulta", "encargado"), state="readonly").pack(fill="x", pady=(5, 12))
        ttk.Label(frame, text="Observaciones (opcional):").pack(anchor="w")
        obs = ttk.Entry(frame)
        obs.pack(fill="x", pady=(5, 15))

        def confirmar():
            rol = rol_var.get().strip().lower()
            if rol not in ("consulta", "encargado"):
                messagebox.showwarning("Usuarios", "Rol inválido.", parent=dialogo)
                return
            if not messagebox.askyesno("Confirmar autorización", f"¿Autorizar a {solicitud.get('email')} como {rol}?", parent=dialogo):
                return
            try:
                boton_autorizar.config(state="disabled")
                _autorizar_usuario(solicitud["id"], rol, obs.get().strip() or None)
                dialogo.destroy()
                cargar()
                messagebox.showinfo("Usuario autorizado", "El usuario fue autorizado correctamente.\n\nSe envió un correo de invitación para configurar la contraseña.", parent=ventana)
            except Exception as error:
                boton_autorizar.config(state="normal")
                messagebox.showerror("Error", f"No se pudo autorizar al usuario:\n\n{error}", parent=dialogo)

        boton_autorizar = ttk.Button(frame, text="Autorizar", command=confirmar)
        boton_autorizar.pack(side="right", padx=4)
        ttk.Button(frame, text="Cancelar", command=dialogo.destroy).pack(side="right", padx=4)

    def rechazar():
        solicitud = seleccionada()
        if not solicitud:
            return
        if solicitud.get("estado") != "pendiente":
            messagebox.showinfo("Usuarios", "La solicitud ya fue revisada.", parent=ventana)
            return
        if not messagebox.askyesno("Rechazar solicitud", f"¿Rechazar la solicitud de {solicitud.get('email')}?", parent=ventana):
            return
        try:
            _desactivar_usuario_por_email(solicitud.get("email"))
            _actualizar_solicitud(solicitud["id"], "rechazada", nombre_admin)
            cargar()
        except Exception as error:
            messagebox.showerror("Error", f"No se pudo rechazar la solicitud:\n\n{error}", parent=ventana)

    botones = ttk.Frame(ventana, padding=(12, 0, 12, 12))
    botones.pack(fill="x")
    ttk.Button(botones, text="🔄 Actualizar", command=cargar).pack(side="left", padx=3)
    ttk.Button(botones, text="ℹ️ Detalle", command=detalle).pack(side="left", padx=3)
    ttk.Button(botones, text="❌ Rechazar", command=rechazar).pack(side="right", padx=3)
    ttk.Button(botones, text="✅ Autorizar", command=aprobar).pack(side="right", padx=3)
    combo.bind("<<ComboboxSelected>>", lambda event: cargar())
    cargar()
    ventana.focus_force()
    return ventana
