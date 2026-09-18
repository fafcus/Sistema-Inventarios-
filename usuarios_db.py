"""
usuarios_db.py

Autenticación y gestión de perfiles/roles para el Sistema de Inventarios.
"""

from config import supabase


ROLES_VALIDOS = {
    "administrador",
    "encargado",
    "consulta",
}

ROLES_SOLICITABLES = {
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
    }
}


def iniciar_sesion(email, password):
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
        raise ValueError("El usuario está desactivado o todavía no fue autorizado por un administrador.")

    perfil["rol"] = rol

    return {
        "user": usuario_auth,
        "session": sesion,
        "perfil": perfil,
    }


def solicitar_acceso(nombre, email, rol_solicitado):
    """
    Registra una solicitud de acceso mediante una función RPC segura.

    La pantalla de login es pública, por lo que no debe leer ni escribir
    directamente las tablas protegidas por RLS. La validación y el INSERT
    se realizan dentro de crear_solicitud_acceso(), que es SECURITY DEFINER.

    No crea una cuenta de Supabase Auth ni solicita/almacena contraseñas.
    La cuenta de autenticación se crea únicamente cuando un administrador
    aprueba la solicitud mediante la Edge Function.
    """
    nombre = (nombre or "").strip()
    email = (email or "").strip().lower()
    rol_solicitado = (rol_solicitado or "consulta").strip().lower()

    if not nombre:
        raise ValueError("Ingresá tu nombre.")
    if not email or "@" not in email:
        raise ValueError("Ingresá un email válido.")
    if rol_solicitado not in ROLES_SOLICITABLES:
        raise ValueError("El rol solicitado no es válido.")

    try:
        respuesta = supabase.rpc(
            "crear_solicitud_acceso",
            {
                "p_nombre": nombre,
                "p_email": email,
                "p_rol": rol_solicitado,
            },
        ).execute()

        solicitud = respuesta.data

    except Exception as error:
        texto = str(error).lower()

        if "ya existe una solicitud pendiente" in texto:
            raise ValueError(
                "Ya existe una solicitud pendiente para ese email. "
                "Esperá la autorización del administrador."
            ) from error

        if "ya existe un usuario activo" in texto:
            raise ValueError(
                "Ya existe un usuario activo con ese email."
            ) from error

        if "crear_solicitud_acceso" in texto and "does not exist" in texto:
            raise ValueError(
                "Falta crear la función crear_solicitud_acceso en Supabase. "
                "Ejecutá el SQL de configuración de solicitudes de acceso."
            ) from error

        raise ValueError(
            f"No se pudo registrar la solicitud: {error}"
        ) from error

    if not solicitud:
        raise ValueError("No se pudo registrar la solicitud de acceso.")

    # Supabase puede devolver una lista para funciones que retornan TABLE/row.
    if isinstance(solicitud, list):
        if not solicitud:
            raise ValueError("No se pudo registrar la solicitud de acceso.")
        return solicitud[0]

    return solicitud


def obtener_solicitudes_pendientes():
    return (
        supabase.table("solicitudes_usuarios")
        .select("*")
        .eq("estado", "pendiente")
        .order("fecha_solicitud", desc=True)
        .execute()
        .data
        or []
    )


def contar_solicitudes_pendientes():
    datos = obtener_solicitudes_pendientes()
    return len(datos)


def cerrar_sesion():
    try:
        supabase.auth.sign_out()
    except Exception:
        pass


def obtener_usuario_actual():
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
    rol = str(rol or "").strip().lower()
    return permiso in PERMISOS.get(rol, set())


def obtener_permisos(rol):
    rol = str(rol or "").strip().lower()
    return set(PERMISOS.get(rol, set()))


def obtener_nombre_usuario(datos_usuario):
    if not datos_usuario:
        return ""

    perfil = datos_usuario.get("perfil") or {}
    nombre = str(perfil.get("nombre") or "").strip()

    if nombre:
        return nombre

    email = str(perfil.get("email") or "").strip()
    return email


def obtener_rol_usuario(datos_usuario):
    if not datos_usuario:
        return None

    perfil = datos_usuario.get("perfil") or {}
    rol = str(perfil.get("rol") or "").strip().lower()

    return rol if rol in ROLES_VALIDOS else None
