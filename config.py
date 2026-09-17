import httpx
from supabase import create_client
from supabase.lib.client_options import ClientOptions


SUPABASE_URL = "https://fhcdgungwwtleuioryrp.supabase.co"
SUPABASE_KEY = "sb_publishable_1DBt3sgPyZijNHN9vR9RKg_Y40VjqR7"


# Supabase habilita HTTP/2 automáticamente en versiones recientes.
# En Windows + Python 3.14 puede producir errores de socket como:
# [WinError 10035] No se puede completar de forma inmediata una operación
# de desbloqueo de socket.
#
# Usamos HTTP/1.1 explícitamente y un único cliente HTTP reutilizable.
http_client = httpx.Client(
    http2=False,
    timeout=httpx.Timeout(
        30.0,
        connect=15.0,
        read=30.0,
        write=30.0,
        pool=30.0,
    ),
    limits=httpx.Limits(
        max_connections=10,
        max_keepalive_connections=5,
    ),
)


supabase = create_client(
    SUPABASE_URL,
    SUPABASE_KEY,
    options=ClientOptions(
        httpx_client=http_client,
        postgrest_client_timeout=30,
        storage_client_timeout=30,
        function_client_timeout=30,
    ),
)
