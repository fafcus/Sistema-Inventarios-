import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};

function respuesta(body: Record<string, unknown>, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { ...corsHeaders, "Content-Type": "application/json" },
  });
}

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") {
    return new Response("ok", { headers: corsHeaders });
  }

  if (req.method !== "POST") {
    return respuesta({ error: "Método no permitido." }, 405);
  }

  const supabaseUrl = Deno.env.get("SUPABASE_URL");
  const publishableKeysRaw = Deno.env.get("SUPABASE_PUBLISHABLE_KEYS");
  const secretKeysRaw = Deno.env.get("SUPABASE_SECRET_KEYS");

  if (!supabaseUrl || !publishableKeysRaw || !secretKeysRaw) {
    return respuesta({ error: "Faltan las claves de Supabase en el entorno de la Edge Function." }, 500);
  }

  let publishableKey: string;
  let secretKey: string;

  try {
    publishableKey = JSON.parse(publishableKeysRaw)["default"];
    secretKey = JSON.parse(secretKeysRaw)["default"];
  } catch {
    return respuesta({ error: "No se pudieron interpretar las claves de Supabase." }, 500);
  }

  if (!publishableKey || !secretKey) {
    return respuesta({ error: "No existe una clave 'default' de Supabase." }, 500);
  }

  const authorization = req.headers.get("Authorization") || "";
  const token = authorization.replace(/^Bearer\s+/i, "").trim();

  if (!token) {
    return respuesta({ error: "Se requiere autenticación." }, 401);
  }

  const authClient = createClient(supabaseUrl, publishableKey, {
    auth: { persistSession: false, autoRefreshToken: false },
  });

  const adminClient = createClient(supabaseUrl, secretKey, {
    auth: { persistSession: false, autoRefreshToken: false },
  });

  try {
    const { data: authData, error: authError } = await authClient.auth.getUser(token);

    if (authError || !authData.user) {
      return respuesta({ error: "Sesión no válida." }, 401);
    }

    const { data: adminProfile, error: profileError } = await adminClient
      .from("usuarios")
      .select("id, rol, activo")
      .eq("id", authData.user.id)
      .maybeSingle();

    if (profileError) {
      return respuesta({ error: profileError.message }, 500);
    }

    if (!adminProfile || !adminProfile.activo || String(adminProfile.rol).toLowerCase() !== "administrador") {
      return respuesta({ error: "No tenés permisos para autorizar usuarios." }, 403);
    }

    const body = await req.json();
    const solicitudId = Number(body.solicitud_id);
    const rol = String(body.rol || "consulta").trim().toLowerCase();
    const observaciones = body.observaciones ? String(body.observaciones).trim() : null;

    if (!Number.isInteger(solicitudId) || solicitudId <= 0) {
      return respuesta({ error: "Solicitud inválida." }, 400);
    }

    if (!["consulta", "encargado"].includes(rol)) {
      return respuesta({ error: "El rol solicitado no es válido." }, 400);
    }

    const { data: solicitud, error: solicitudError } = await adminClient
      .from("solicitudes_usuarios")
      .select("id, nombre, email, rol_solicitado, estado")
      .eq("id", solicitudId)
      .maybeSingle();

    if (solicitudError) {
      return respuesta({ error: solicitudError.message }, 500);
    }

    if (!solicitud) {
      return respuesta({ error: "No se encontró la solicitud." }, 404);
    }

    if (solicitud.estado !== "pendiente") {
      return respuesta({ error: "La solicitud ya fue revisada." }, 409);
    }

    const email = String(solicitud.email).trim().toLowerCase();
    let authUserId: string | null = null;
    let usuarioExistente = false;
    let correoEnviado = false;
    let correoPendiente = false;

    const { data: usersPage, error: usersError } = await adminClient.auth.admin.listUsers({
      page: 1,
      perPage: 1000,
    });

    if (usersError) {
      return respuesta({ error: usersError.message }, 500);
    }

    const usuarioEncontrado = usersPage.users.find(
      (user) => String(user.email || "").toLowerCase() === email,
    );

    if (usuarioEncontrado) {
      authUserId = usuarioEncontrado.id;
      usuarioExistente = true;
    } else {
      const { data: inviteData, error: inviteError } = await adminClient.auth.admin.inviteUserByEmail(email, {
        data: { nombre: solicitud.nombre },
      });

      if (inviteData?.user) {
        authUserId = inviteData.user.id;
        correoEnviado = true;
      } else if (inviteError) {
        const mensaje = inviteError.message || "No se pudo crear la cuenta de autenticación.";
        const mensajeNormalizado = mensaje.toLowerCase();

        // Si Supabase bloquea el envío de emails por rate limit, creamos
        // igualmente la cuenta de Auth sin enviar correo. La solicitud puede
        // quedar aprobada y el administrador podrá enviar el acceso después
        // cuando se restablezca el límite de emails.
        if (
          mensajeNormalizado.includes("email rate limit") ||
          mensajeNormalizado.includes("rate limit exceeded") ||
          mensajeNormalizado.includes("rate limit")
        ) {
          const { data: createData, error: createError } = await adminClient.auth.admin.createUser({
            email,
            email_confirm: false,
            user_metadata: { nombre: solicitud.nombre },
          });

          if (createError || !createData.user) {
            return respuesta({
              ok: false,
              codigo: "EMAIL_RATE_LIMIT",
              pendiente: true,
              error: "Supabase alcanzó el límite de emails y tampoco pudo crear la cuenta de autenticación. La solicitud sigue pendiente. Intentá nuevamente más tarde.",
            }, 429);
          }

          authUserId = createData.user.id;
          correoPendiente = true;
        } else {
          return respuesta({ error: mensaje }, 500);
        }
      }
    }

    const { error: perfilError2 } = await adminClient
      .from("usuarios")
      .upsert({
        id: authUserId,
        nombre: solicitud.nombre,
        email,
        rol,
        activo: true,
      }, { onConflict: "id" });

    if (perfilError2) {
      if (!usuarioExistente && authUserId && correoPendiente) {
        await adminClient.auth.admin.deleteUser(authUserId);
      }
      return respuesta({ error: perfilError2.message }, 500);
    }

    const { data: solicitudActualizada, error: updateError } = await adminClient
      .from("solicitudes_usuarios")
      .update({
        estado: "aprobada",
        revisado_por: authData.user.email || authData.user.id,
        fecha_revision: new Date().toISOString(),
        observaciones,
      })
      .eq("id", solicitudId)
      .eq("estado", "pendiente")
      .select("*")
      .maybeSingle();

    if (updateError) {
      return respuesta({ error: updateError.message }, 500);
    }

    if (!solicitudActualizada) {
      return respuesta({ error: "No se pudo actualizar el estado de la solicitud." }, 500);
    }

    let mensaje = "Usuario existente asociado y autorizado.";

    if (correoEnviado) {
      mensaje = "Usuario autorizado y correo de invitación enviado.";
    } else if (correoPendiente) {
      mensaje = "Usuario autorizado. Supabase alcanzó el límite de emails, por lo que el correo de invitación quedó pendiente de envío. La solicitud ya no está pendiente.";
    }

    return respuesta({
      ok: true,
      usuario_id: authUserId,
      solicitud: solicitudActualizada,
      correo_enviado: correoEnviado,
      correo_pendiente: correoPendiente,
      mensaje,
    });
  } catch (error) {
    return respuesta({ error: error instanceof Error ? error.message : String(error) }, 500);
  }
});
