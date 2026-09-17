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


def valor(v):
    return str(v or "").strip()


def ejecutar():
    print("============================================")
    print("REPARACION DE MATERIALES")
    print("============================================")

    materiales = (
        supabase.table("materiales")
        .select("*")
        .order("id")
        .execute()
        .data
        or []
    )

    grupos = {}
    for m in materiales:
        grupos.setdefault(identidad(m), []).append(m)

    fusionados = 0
    items_reasignados = 0
    items_eliminados_duplicados = 0
    ajustes_reasignados = 0
    movimientos_reasignados = 0

    for clave, grupo in grupos.items():
        if not clave[0] or len(grupo) < 2:
            continue

        grupo = sorted(grupo, key=lambda x: int(x.get("id") or 0))
        canonico = grupo[0]
        cid = canonico["id"]

        print()
        print(f"Material: {canonico.get('material')}")
        print(f"IDs involucrados: {[m.get('id') for m in grupo]}")

        # Si alguno tiene código y el canónico no, conservar el código.
        con_codigo = next((m for m in grupo if codigo(m.get("codigo"))), None)
        if con_codigo and not codigo(canonico.get("codigo")):
            supabase.table("materiales").update({
                "codigo": con_codigo.get("codigo"),
                "archivo_origen": con_codigo.get("archivo_origen") or canonico.get("archivo_origen"),
            }).eq("id", cid).execute()
            canonico["codigo"] = con_codigo.get("codigo")
            print(f"  Código conservado: {con_codigo.get('codigo')}")

        for duplicado in grupo[1:]:
            did = duplicado["id"]
            if did == cid:
                continue

            print(f"  Fusionando ID {did} -> {cid}")

            # ---------------------------------------------------------
            # DOCUMENTO_ITEMS
            # ---------------------------------------------------------
            # Existe una restricción UNIQUE(documento_id, material_id).
            # Por eso no podemos reasignar directamente si el documento
            # ya tiene un item del material canónico.
            items_dup = (
                supabase.table("documento_items")
                .select("*")
                .eq("material_id", did)
                .execute()
                .data
                or []
            )

            for item_dup in items_dup:
                documento_id = item_dup.get("documento_id")

                existente = (
                    supabase.table("documento_items")
                    .select("*")
                    .eq("documento_id", documento_id)
                    .eq("material_id", cid)
                    .limit(1)
                    .execute()
                    .data
                    or []
                )

                if existente:
                    item_can = existente[0]

                    # Conservamos el registro canónico para evitar duplicar
                    # cantidades. Si el duplicado tiene un código o datos de
                    # texto más completos, los copiamos al registro existente.
                    cambios = {}
                    for campo in (
                        "codigo",
                        "material",
                        "unidad",
                        "categoria",
                        "ubicacion",
                        "observaciones",
                    ):
                        actual = valor(item_can.get(campo))
                        nuevo = valor(item_dup.get(campo))
                        if not actual and nuevo:
                            cambios[campo] = item_dup.get(campo)

                    if cambios:
                        supabase.table("documento_items").update(cambios).eq(
                            "id", item_can["id"]
                        ).execute()

                    # Los dos registros representan el mismo material dentro
                    # del mismo documento. NO sumamos cantidades: eso sería
                    # justamente lo que puede inflar el inventario general.
                    supabase.table("documento_items").delete().eq(
                        "id", item_dup["id"]
                    ).execute()
                    items_eliminados_duplicados += 1
                    print(
                        f"    Item duplicado eliminado: documento {documento_id}, "
                        f"cantidad duplicada {item_dup.get('cantidad')}"
                    )
                else:
                    supabase.table("documento_items").update({
                        "material_id": cid
                    }).eq("id", item_dup["id"]).execute()
                    items_reasignados += 1

            # ---------------------------------------------------------
            # AJUSTES DE STOCK
            # ---------------------------------------------------------
            ajustes = (
                supabase.table("ajustes_stock")
                .select("id")
                .eq("material_id", did)
                .execute()
                .data
                or []
            )
            if ajustes:
                supabase.table("ajustes_stock").update({
                    "material_id": cid
                }).eq("material_id", did).execute()
                ajustes_reasignados += len(ajustes)

            # ---------------------------------------------------------
            # MOVIMIENTOS
            # ---------------------------------------------------------
            movimientos = (
                supabase.table("movimientos")
                .select("id")
                .eq("material_id", did)
                .execute()
                .data
                or []
            )
            if movimientos:
                supabase.table("movimientos").update({
                    "material_id": cid
                }).eq("material_id", did).execute()
                movimientos_reasignados += len(movimientos)

            # Finalmente eliminamos el material duplicado.
            supabase.table("materiales").delete().eq("id", did).execute()
            fusionados += 1

    print()
    print("============================================")
    print("REPARACION FINALIZADA")
    print("============================================")
    print(f"Materiales fusionados:           {fusionados}")
    print(f"Items reasignados:               {items_reasignados}")
    print(f"Items duplicados eliminados:    {items_eliminados_duplicados}")
    print(f"Ajustes reasignados:             {ajustes_reasignados}")
    print(f"Movimientos reasignados:         {movimientos_reasignados}")
    print()
    print("Ahora ejecutá desde la aplicación:")
    print("🧹 Reescaneo completo")
    print("============================================")


if __name__ == "__main__":
    ejecutar()
