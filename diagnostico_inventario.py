from config import supabase
from pathlib import Path

documentos = supabase.table("documentos").select("*").execute().data or []
print(f"Documentos en Supabase: {len(documentos)}")
print("-" * 90)

for d in documentos:
    items = supabase.table("documento_items").select("id").eq("documento_id", d["id"]).execute().data or []
    ruta = Path(str(d.get("ruta") or ""))
    existe_local = ruta.exists()
    nombre = d.get("nombre") or "(sin nombre)"
    print(f"ID {d['id']:<4} | items: {len(items):<4} | word local existe: {str(existe_local):<5} | nombre: {nombre}")
    print(f"       ruta: {ruta}")

print("-" * 90)
print("Listo.")
