from config import supabase
import re
import unicodedata


def norm(v):
    if v is None:
        return ""
    s = unicodedata.normalize("NFKD", str(v).replace("\xa0", " "))
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", s.strip().lower())


def codigo(v):
    return re.sub(r"[\s\-.]+", "", str(v or "").strip().upper())


def identidad(m):
    return (
        norm(m.get("material")),
        norm(m.get("unidad")),
        norm(m.get("categoria")),
        norm(m.get("ubicacion")),
    )


def ejecutar():
    materiales = supabase.table("materiales").select("*").order("id").execute().data or []
    grupos = {}
    for m in materiales:
        grupos.setdefault(identidad(m), []).append(m)

    fusionados = 0
    items_reasignados = 0
    ajustes_reasignados = 0
    movimientos_reasignados = 0

    for clave, grupo in grupos.items():
        if not clave[0] or len(grupo) < 2:
            continue

        grupo = sorted(grupo, key=lambda x: int(x.get("id") or 0))
        canonico = grupo[0]

        # Si uno de los duplicados tiene código y el canónico no, conservar ese código.
        con_codigo = next((m for m in grupo if codigo(m.get("codigo"))), None)
        if con_codigo and not codigo(canonico.get("codigo")):
            supabase.table("materiales").update({
                "codigo": con_codigo.get("codigo"),
                "archivo_origen": con_codigo.get("archivo_origen") or canonico.get("archivo_origen"),
            }).eq("id", canonico["id"]).execute()

        for duplicado in grupo[1:]:
            did = duplicado["id"]
            cid = canonico["id"]

            supabase.table("documento_items").update({"material_id": cid}).eq("material_id", did).execute()
            supabase.table("ajustes_stock").update({"material_id": cid}).eq("material_id", did).execute()
            supabase.table("movimientos").update({"material_id": cid}).eq("material_id", did).execute()

            supabase.table("materiales").delete().eq("id", did).execute()
            fusionados += 1

    print("============================================")
    print("REPARACION DE MATERIALES FINALIZADA")
    print("============================================")
    print(f"Materiales fusionados: {fusionados}")
    print(f"Items reasignados:     {items_reasignados}")
    print(f"Ajustes reasignados:   {ajustes_reasignados}")
    print(f"Movimientos tratados:  {movimientos_reasignados}")
    print("Ahora ejecutá un reescaneo completo desde la aplicación.")


if __name__ == "__main__":
    ejecutar()
