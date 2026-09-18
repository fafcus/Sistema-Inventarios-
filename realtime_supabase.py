"""Integración Realtime de Supabase para la aplicación Tkinter.

Supabase Realtime en Python utiliza el cliente asíncrono. Este módulo mantiene
el websocket fuera del hilo de Tkinter y entrega los eventos a la UI mediante
root.after().
"""

import asyncio
import inspect
import threading
import traceback

from supabase import acreate_client


TABLAS_INVENTARIO = (
    "materiales",
    "documentos",
    "movimientos",
    "ajustes_stock",
)


def iniciar_realtime(root, session, on_change=None, on_status=None):
    """Inicia una suscripción Realtime y devuelve una función para detenerla."""
    if root is None or session is None:
        return lambda: None

    access_token = getattr(session, "access_token", None)
    refresh_token = getattr(session, "refresh_token", None)
    if not access_token or not refresh_token:
        print("⚠️ Realtime: sesión sin tokens.")
        return lambda: None

    stop_event = threading.Event()
    state = {"client": None}

    def avisar_status(valor):
        if on_status is None:
            return
        try:
            root.after(0, lambda: on_status(valor))
        except Exception:
            pass

    def evento_recibido(payload):
        try:
            table = payload.get("table") if isinstance(payload, dict) else None
            event = payload.get("eventType") if isinstance(payload, dict) else None
            if on_change is not None:
                root.after(0, lambda: on_change(table, event, payload))
        except Exception:
            traceback.print_exc()

    async def ejecutar():
        client = None
        channel = None
        try:
            from config import SUPABASE_URL, SUPABASE_KEY
            client = await acreate_client(SUPABASE_URL, SUPABASE_KEY)
            state["client"] = client

            resultado = client.auth.set_session(access_token, refresh_token)
            if inspect.isawaitable(resultado):
                await resultado

            channel = client.channel("inventario-realtime")
            for tabla in TABLAS_INVENTARIO:
                channel = channel.on_postgres_changes(
                    "*",
                    schema="public",
                    table=tabla,
                    callback=evento_recibido,
                )

            resultado = channel.subscribe()
            if inspect.isawaitable(resultado):
                await resultado

            avisar_status("conectado")

            while not stop_event.is_set():
                await asyncio.sleep(0.5)

        except Exception:
            traceback.print_exc()
            avisar_status("error")
        finally:
            try:
                if client is not None and channel is not None:
                    resultado = client.remove_channel(channel)
                    if inspect.isawaitable(resultado):
                        await resultado
            except Exception:
                pass
            try:
                if client is not None:
                    resultado = client.close()
                    if inspect.isawaitable(resultado):
                        await resultado
            except Exception:
                pass
            state["client"] = None
            avisar_status("detenido")

    def worker():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(ejecutar())
        finally:
            loop.close()

    threading.Thread(
        target=worker,
        name="Supabase-Realtime",
        daemon=True,
    ).start()

    def detener():
        stop_event.set()

    return detener
