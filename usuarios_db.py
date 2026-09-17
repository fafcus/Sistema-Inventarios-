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
    # Consulta puede modificar cantidades de stock, pero no administrar
    # materiales, importar Word ni administrar usuarios.
    "consulta": {
        "ver_inventario",
        "ver_historial",
        "generar_reportes",
        "agregar_stock",
        "retirar_stock",
    },
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


def solicitar_acceso(nombre, email, password, password_confirmacion, rol_solicitado):
    """
    Registra una solicitud de acceso.

    La contraseña NO se guarda en solicitudes_usuarios. Se crea mediante
    Supabase Auth y queda administrada por el sistema de autenticación.
    El perfil se crea inicialmente inactivo y el administrador debe aprobarlo.
    """
    nombre = (nombre or "").strip()
    email = (email or "").strip().lower()
    password = password or ""
    password_confirmacion = password_confirmacion or ""
    rol_solicitado = (rol_solicitado or "consulta").strip().lower()

    if not nombre:
        raise ValueError("Ingresá tu nombre.")
    if not email or "@" not in email:
        raise ValueError("Ingresá un email válido.")
    if rol_solicitado not in ROLES_SOLICITABLES:
        raise ValueError("El rol solicitado no es válido.")
    if len(password) < 6:
        raise ValueError("La contraseña debe tener al menos 6 caracteres.")
    if password != password_confirmacion:
        raise ValueError("Las contraseñas no coinciden.")

    existentes = (
        supabase.table("usuarios")
        .select("id, activo")
        .eq("email", email)
        .limit(1)
        .execute()
        .data
        or []
    )

    if existentes:
        if existentes[0].get("activo"):
            raise ValueError("Ya existe un usuario activo con ese email.")
        raise ValueError("Ya existe una cuenta o solicitud asociada a ese email. Esperá la revisión del administrador.")

    pendientes = (
        supabase.table("solicitudes_usuarios")
        .select("id, estado")
        .eq("email", email)
        .eq("estado", "pendiente")
        .limit(1)
        .execute()
        .data
        or []
    )

    if pendientes:
        raise ValueError("Ya existe una solicitud pendiente para ese email.")

    respuesta = supabase.auth.sign_up({
        "email": email,
        "password": password,
        "options": {
            "data": {
                "nombre": nombre,
            }
        },
    })

    usuario_auth = getattr(respuesta, "user", None)

    if usuario_auth is None:
        raise ValueError("Supabase no pudo crear la cuenta de autenticación.")

    try:
        perfil = (
            supabase.table("usuarios")
            .insert({
                "id": usuario_auth.id,
                "nombre": nombre,
                "email": email,
                "rol": rol_solicitado,
                "activo": False,
            })
            .execute()
            .data
            or []
        )

        if not perfil:
            raise ValueError("No se pudo crear el perfil pendiente.")

        solicitud = (
            supabase.table("solicitudes_usuarios")
            .insert({
                "nombre": nombre,
                "email": email,
                "rol_solicitado": rol_solicitado,
                "estado": "pendiente",
            })
            .execute()
            .data
            or []
        )

        if not solicitud:
            raise ValueError("No se pudo registrar la solicitud de acceso.")

    except Exception:
        # El usuario de Auth no se elimina desde el cliente porque esa
        # operación requiere privilegios administrativos. El perfil queda
        # inactivo y el administrador puede revisar la cuenta si fuese necesario.
        raise
    finally:
        try:
            supabase.auth.sign_out()
        except Exception:
            pass

    return solicitud[0]


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
