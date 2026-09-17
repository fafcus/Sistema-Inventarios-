"""
usuarios_db.py

Autenticación y gestión básica de perfiles/roles para el Sistema de Inventarios.

Utiliza Supabase Auth para las credenciales y la tabla public.usuarios para
obtener el nombre, rol y estado del usuario.
"""

from config import supabase


ROLES_VALIDOS = {
    "administrador",
    "encargado",
    "consulta",
}


PERMISOS = {
    "administrador": {
        "ver_inventario",
        "ver_historial",
        "generar_reportes",
        "crear_material",
        "editar_material",
        "eliminar_material",
        "agregar_stock",
        "retirar_stock",
        "importar_word",
        "reescaneo_completo",
        "administrar_usuarios",
    },
    "encargado": {
        "ver_inventario",
        "ver_historial",
        "generar_reportes",
        "crear_material",
        "editar_material",
        "eliminar_material",
        "agregar_stock",
        "retirar_stock",
        "importar_word",
        "reescaneo_completo",
    },
    "consulta": {
        "ver_inventario",
        "ver_historial",
        "generar_reportes",
    },
}


def iniciar_sesion(email, password):
    """
    Inicia sesión mediante Supabase Auth y devuelve el perfil de la tabla
    usuarios junto con la sesión autenticada.

    Devuelve:
        dict con user, session y perfil
    o None si las credenciales son incorrectas o el usuario no está activo.
    """
    email = (email or "").strip()

    if not email or not password:
        raise ValueError("Ingresá el email y la contraseña.")

    respuesta = supabase.auth.sign_in_with_password({
        "email": email,
        "password": password,
    })

    usuario_auth = getattr(respuesta, "user", None)
    sesion = getattr(respuesta, "session", None)

    if usuario_auth is None or sesion is None:
        raise ValueError("No se pudo iniciar la sesión.")

    perfil_respuesta = (
        supabase.table("usuarios")
        .select("id, nombre, email, rol, activo, fecha_creacion")
        .eq("id", usuario_auth.id)
        .limit(1)
        .execute()
    )

    perfiles = perfil_respuesta.data or []

    if not perfiles:
        supabase.auth.sign_out()
        raise ValueError("El usuario está autenticado, pero no tiene un perfil configurado.")

    perfil = perfiles[0]
    rol = str(perfil.get("rol") or "consulta").strip().lower()

    if rol not in ROLES_VALIDOS:
        supabase.auth.sign_out()
        raise ValueError(f"El rol '{rol}' no es válido.")

    if not perfil.get("activo", False):
        supabase.auth.sign_out()
        raise ValueError("El usuario está desactivado.")

    perfil["rol"] = rol

    return {
        "user": usuario_auth,
        "session": sesion,
        "perfil": perfil,
    }


def cerrar_sesion():
    """Cierra la sesión actual de Supabase."""
    try:
        supabase.auth.sign_out()
    except Exception:
        pass


def obtener_usuario_actual():
    """
    Obtiene el usuario actualmente autenticado y su perfil.

    Devuelve None si no existe una sesión válida.
    """
    try:
        usuario_auth = supabase.auth.get_user().user

        if usuario_auth is None:
            return None

        respuesta = (
            supabase.table("usuarios")
            .select("id, nombre, email, rol, activo, fecha_creacion")
            .eq("id", usuario_auth.id)
            .limit(1)
            .execute()
        )

        perfiles = respuesta.data or []
        if not perfiles:
            return None

        perfil = perfiles[0]
        rol = str(perfil.get("rol") or "consulta").strip().lower()

        if rol not in ROLES_VALIDOS or not perfil.get("activo", False):
            return None

        perfil["rol"] = rol

        return {
            "user": usuario_auth,
            "perfil": perfil,
        }

    except Exception:
        return None


def tiene_permiso(rol, permiso):
    """Devuelve True si el rol posee el permiso indicado."""
    rol = str(rol or "").strip().lower()
    return permiso in PERMISOS.get(rol, set())


def obtener_permisos(rol):
    """Devuelve una copia del conjunto de permisos del rol."""
    rol = str(rol or "").strip().lower()
    return set(PERMISOS.get(rol, set()))


def obtener_nombre_usuario(datos_usuario):
    """Obtiene un nombre legible a partir de los datos de sesión."""
    if not datos_usuario:
        return ""

    perfil = datos_usuario.get("perfil") or {}
    nombre = str(perfil.get("nombre") or "").strip()

    if nombre:
        return nombre

    email = str(perfil.get("email") or "").strip()
    return email


def obtener_rol_usuario(datos_usuario):
    """Obtiene el rol normalizado del usuario actual."""
    if not datos_usuario:
        return None

    perfil = datos_usuario.get("perfil") or {}
    rol = str(perfil.get("rol") or "").strip().lower()

    return rol if rol in ROLES_VALIDOS else None
