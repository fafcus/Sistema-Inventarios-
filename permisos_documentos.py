"""
Permisos por documento.

La interfaz de esta aplicación usa este módulo para la restricción visual y
para comprobar permisos antes de ejecutar acciones. La protección real de
los datos se completa con las políticas RLS de Supabase incluidas en
supabase/permisos_documentos.sql.
"""

import tkinter as tk
from tkinter import ttk, messagebox

from config import supabase


PERMISOS_DOCUMENTO = (
    ("ver", "Ver"),
    ("agregar", "Agregar stock"),
    ("modificar", "Modificar"),
    ("importar", "Importar"),
    ("retirar", "Retirar stock"),
    ("eliminar", "Eliminar"),
)

CAMPOS_DB = {
    "ver": "puede_ver",
    "agregar": "puede_agregar",
    "modificar": "puede_modificar",
    "importar": "puede_importar",
    "retirar": "puede_retirar",
    "eliminar": "puede_eliminar",
}


def _usuario_auth_id():
    try:
        usuario = supabase.auth.get_user().user
        return str(usuario.id) if usuario else None
    except Exception:
        return None


def es_administrador():
    uid = _usuario_auth_id()
    if not uid:
        return False
    try:
        datos = (
            supabase.table("usuarios")
            .select("rol, activo")
            .eq("id", uid)
            .limit(1)
            .execute()
            .data
            or []
        )
        return bool(datos and datos[0].get("activo") and datos[0].get("rol") == "administrador")
    except Exception:
        return False


def tiene_permiso_documento(documento_id, permiso, user_id=None):
    """Comprueba un permiso específico para un documento."""
    if not documento_id:
        return False

    permiso = str(permiso or "").strip().lower()
    if permiso not in CAMPOS_DB:
        return False

    uid = str(user_id or _usuario_auth_id() or "").strip()
    if not uid:
        return False

    if user_id is None and es_administrador():
        return True

    try:
        campo = CAMPOS_DB[permiso]
        datos = (
            supabase.table("documento_permisos")
            .select(campo)
            .eq("documento_id", int(documento_id))
            .eq("user_id", uid)
            .limit(1)
            .execute()
            .data
            or []
        )
        return bool(datos and datos[0].get(campo) is True)
    except Exception as error:
        print(f"Error comprobando permiso de documento: {error}")
        return False


def obtener_permisos_documento(documento_id, user_id):
    resultado = {clave: False for clave, _ in PERMISOS_DOCUMENTO}
    if not documento_id or not user_id:
        return resultado

    try:
        datos = (
            supabase.table("documento_permisos")
            .select("puede_ver, puede_agregar, puede_modificar, puede_importar, puede_retirar, puede_eliminar")
            .eq("documento_id", int(documento_id))
            .eq("user_id", str(user_id))
            .limit(1)
            .execute()
            .data
            or []
        )
        if datos:
            fila = datos[0]
            for clave, campo in CAMPOS_DB.items():
                resultado[clave] = bool(fila.get(campo, False))
    except Exception as error:
        print(f"Error obteniendo permisos del documento: {error}")

    return resultado


def guardar_permisos_documento(documento_id, user_id, permisos):
    if not es_administrador():
        raise PermissionError("Solo un administrador puede modificar los permisos de documentos.")

    datos = {
        "documento_id": int(documento_id),
        "user_id": str(user_id),
        "puede_ver": bool(permisos.get("ver", False)),
        "puede_agregar": bool(permisos.get("agregar", False)),
        "puede_modificar": bool(permisos.get("modificar", False)),
        "puede_importar": bool(permisos.get("importar", False)),
        "puede_retirar": bool(permisos.get("retirar", False)),
        "puede_eliminar": bool(permisos.get("eliminar", False)),
    }
    respuesta = (
        supabase.table("documento_permisos")
        .upsert(datos, on_conflict="documento_id,user_id")
        .execute()
    )
    return respuesta.data or []


def abrir_admin_permisos(parent):
    if not es_administrador():
        messagebox.showerror("Permisos", "Solo un administrador puede administrar los permisos.", parent=parent)
        return None

    ventana = tk.Toplevel(parent)
    ventana.title("Permisos por documento")
    ventana.geometry("900x620")
    ventana.minsize(780, 520)
    ventana.transient(parent)

    cabecera = tk.Frame(ventana, bg="#12304a", height=70)
    cabecera.pack(fill="x")
    cabecera.pack_propagate(False)
    tk.Label(cabecera, text="🔐 Permisos por documento", bg="#12304a", fg="white", font=("Segoe UI", 16, "bold")).pack(anchor="w", padx=20, pady=(10, 0))
    tk.Label(cabecera, text="Definí qué puede hacer cada usuario en cada inventario/documento.", bg="#12304a", fg="#dce8f1", font=("Segoe UI", 9)).pack(anchor="w", padx=20)

    marco = ttk.Frame(ventana, padding=15)
    marco.pack(fill="both", expand=True)

    ttk.Label(marco, text="Usuario:", font=("Segoe UI", 10, "bold")).grid(row=0, column=0, sticky="w", pady=5)
    usuario_var = tk.StringVar()
    combo_usuario = ttk.Combobox(marco, textvariable=usuario_var, state="readonly", width=48)
    combo_usuario.grid(row=0, column=1, sticky="ew", padx=(10, 0), pady=5)

    ttk.Label(marco, text="Documento:", font=("Segoe UI", 10, "bold")).grid(row=1, column=0, sticky="w", pady=5)
    documento_var = tk.StringVar()
    combo_documento = ttk.Combobox(marco, textvariable=documento_var, state="readonly", width=48)
    combo_documento.grid(row=1, column=1, sticky="ew", padx=(10, 0), pady=5)

    usuario_map = {}
    documento_map = {}

    permisos_frame = ttk.LabelFrame(marco, text="Permisos", padding=15)
    permisos_frame.grid(row=2, column=0, columnspan=2, sticky="nsew", pady=(20, 10))
    variables = {}
    for fila, (clave, texto) in enumerate(PERMISOS_DOCUMENTO):
        var = tk.BooleanVar(value=False)
        variables[clave] = var
        ttk.Checkbutton(permisos_frame, text=texto, variable=var).grid(row=fila, column=0, sticky="w", pady=5)

    estado = ttk.Label(marco, text="Seleccioná un usuario y un documento.", foreground="#506575", wraplength=650)
    estado.grid(row=3, column=0, columnspan=2, sticky="w", pady=8)

    def cargar_catalogos():
        try:
            usuarios = (
                supabase.table("usuarios")
                .select("id, nombre, email, rol, activo")
                .eq("activo", True)
                .order("nombre")
                .execute()
                .data
                or []
            )
            documentos = (
                supabase.table("documentos")
                .select("id, nombre, ruta")
                .order("nombre")
                .execute()
                .data
                or []
            )

            usuario_map.clear()
            documento_map.clear()

            valores_usuarios = []
            for u in usuarios:
                etiqueta = f"{u.get('nombre') or u.get('email') or 'Usuario'} — {u.get('email') or ''}"
                usuario_map[etiqueta] = str(u["id"])
                valores_usuarios.append(etiqueta)

            valores_documentos = []
            for d in documentos:
                etiqueta = f"{d.get('nombre') or 'Documento'}  [ID {d.get('id')}]"
                documento_map[etiqueta] = d["id"]
                valores_documentos.append(etiqueta)

            combo_usuario["values"] = valores_usuarios
            combo_documento["values"] = valores_documentos

            if valores_usuarios:
                combo_usuario.current(0)
            if valores_documentos:
                combo_documento.current(0)
            cargar_permisos()
        except Exception as error:
            messagebox.showerror("Permisos", f"No se pudieron cargar usuarios/documentos:\n\n{error}", parent=ventana)

    def cargar_permisos(event=None):
        uid = usuario_map.get(usuario_var.get())
        did = documento_map.get(documento_var.get())
        for var in variables.values():
            var.set(False)
        if not uid or not did:
            estado.config(text="Seleccioná un usuario y un documento.")
            return
        datos = obtener_permisos_documento(did, uid)
        for clave, var in variables.items():
            var.set(datos.get(clave, False))
        estado.config(text="Permisos cargados. Los cambios se aplican al guardar.")

    def guardar():
        uid = usuario_map.get(usuario_var.get())
        did = documento_map.get(documento_var.get())
        if not uid or not did:
            messagebox.showwarning("Permisos", "Seleccioná un usuario y un documento.", parent=ventana)
            return
        permisos = {clave: var.get() for clave, var in variables.items()}
        if not any(permisos.values()):
            if not messagebox.askyesno("Sin permisos", "El usuario quedará sin acceso a este documento. ¿Continuar?", parent=ventana):
                return
        try:
            guardar_permisos_documento(did, uid, permisos)
            estado.config(text="Permisos guardados correctamente.")
            messagebox.showinfo("Permisos", "Los permisos del documento fueron actualizados.", parent=ventana)
        except Exception as error:
            messagebox.showerror("Permisos", f"No se pudieron guardar los permisos:\n\n{error}", parent=ventana)

    combo_usuario.bind("<<ComboboxSelected>>", cargar_permisos)
    combo_documento.bind("<<ComboboxSelected>>", cargar_permisos)

    botones = ttk.Frame(marco)
    botones.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(8, 0))
    ttk.Button(botones, text="🔄 Actualizar", command=cargar_catalogos).pack(side="left", padx=4)
    ttk.Button(botones, text="💾 Guardar permisos", command=guardar).pack(side="right", padx=4)
    ttk.Button(botones, text="Cerrar", command=ventana.destroy).pack(side="right", padx=4)

    marco.columnconfigure(1, weight=1)
    marco.rowconfigure(2, weight=1)
    cargar_catalogos()
    ventana.focus_force()
    return ventana
