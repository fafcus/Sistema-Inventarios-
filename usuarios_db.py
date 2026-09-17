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

    La contraseña nunca se guarda en la tabla solicitudes_usuarios.
    Supabase Auth se encarga de almacenarla de forma segura.

    La función también tolera un intento anterior que haya llegado a crear
    la cuenta/perfil pero haya fallado antes de insertar la solicitud.
    Esto evita los errores de "duplicate key" al volver a enviar el formulario.
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

    # Primero comprobamos si ya hay una solicitud pendiente.
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
        raise ValueError(
            "Ya existe una solicitud pendiente para ese email. "
            "Esperá la autorización del administrador."
        )

    # Comprobamos el perfil. Si quedó creado por un intento anterior pero
    # está inactivo, lo reutilizamos en lugar de intentar insertarlo otra vez.
    perfiles_existentes = (
        supabase.table("usuarios")
        .select("id, nombre, email, rol, activo")
        .eq("email", email)
        .limit(1)
        .execute()
        .data
        or []
    )

    perfil_existente = perfiles_existentes[0] if perfiles_existentes else None

    if perfil_existente and perfil_existente.get("activo"):
        raise ValueError("Ya existe un usuario activo con ese email.")

    usuario_auth = None

    if perfil_existente:
        # El perfil inactivo indica que la cuenta de Auth probablemente ya fue
        # creada durante un intento anterior. No llamamos sign_up nuevamente.
        auth_id = perfil_existente.get("id")
        if not auth_id:
            raise ValueError("El perfil existente no tiene un identificador válido.")
    else:
        # No hay perfil: creamos la cuenta de Auth por primera vez.
        try:
            respuesta = supabase.auth.sign_up({
                "email": email,
                "password": password,
                "options": {
                    "data": {
                        "nombre": nombre,
                    }
                },
            })
        except Exception as error:
            texto = str(error).lower()
            if "already registered" in texto or "already exists" in texto or "duplicate" in texto:
                raise ValueError(
                    "Ya existe una cuenta de autenticación con ese email. "
                    "Si todavía no fue autorizada, un administrador debe revisar la solicitud."
                ) from error
            raise

        usuario_auth = getattr(respuesta, "user", None)

        if usuario_auth is None:
            raise ValueError("Supabase no pudo crear la cuenta de autenticación.")

        auth_id = usuario_auth.id

        # En algunas configuraciones Supabase puede devolver un usuario ya
        # registrado sin lanzar una excepción. Si no hay identidades nuevas,
        # no intentamos duplicar el perfil.
        identidades = getattr(usuario_auth, "identities", None)
        if identidades == []:
            raise ValueError(
                "Ya existe una cuenta de autenticación con ese email. "
                "Esperá la revisión del administrador."
            )

    try:
        if not perfil_existente:
            perfil = (
                supabase.table("usuarios")
                .insert({
                    "id": auth_id,
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
        else:
            # Actualizamos nombre/rol por si el intento anterior quedó a medio
            # completar. Nunca activamos el usuario desde esta pantalla.
            supabase.table("usuarios").update({
                "nombre": nombre,
                "email": email,
                "rol": rol_solicitado,
                "activo": False,
            }).eq("id", auth_id).execute()

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

    except Exception as error:
        texto = str(error).lower()

        if "duplicate key" in texto or "duplicate" in texto:
            raise ValueError(
                "La cuenta o solicitud ya estaba registrada. "
                "Revisá el panel de administración antes de volver a enviarla."
            ) from error

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
