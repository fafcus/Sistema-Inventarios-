from pathlib import Path
from datetime import datetime
import re
import unicodedata
import traceback

from docx import Document

from config import supabase


# ============================================================
# CONFIGURACION
# ============================================================

CARPETA_DOCUMENTOS = Path(__file__).resolve().parent / "documentos"


# ============================================================
# UTILIDADES
# ============================================================

def normalizar_texto(valor):
    if valor is None:
        return ""
    texto = str(valor).replace("\xa0", " ")
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = texto.strip().lower()
    return re.sub(r"\s+", " ", texto)


def normalizar_codigo(codigo):
    if codigo is None:
        return ""
    return re.sub(r"[\s\-\.]+", "", str(codigo).strip().upper())


def texto_limpio(valor):
    if valor is None:
        return None
    texto = re.sub(r"\s+", " ", str(valor).replace("\xa0", " ")).strip()
    return texto or None


def convertir_cantidad(valor):
    if valor is None:
        return 0.0
    if isinstance(valor, (int, float)):
        return float(valor)
    texto = str(valor).strip()
    coincidencia = re.search(r"-?\d+(?:[.,]\d+)?", texto)
    if not coincidencia:
        return 0.0
    numero = coincidencia.group(0)
    if "," in numero and "." not in numero:
        numero = numero.replace(",", ".")
    try:
        return float(numero)
    except Exception:
        return 0.0


def clave_material(codigo, material, unidad, categoria, ubicacion):
    return (
        normalizar_codigo(codigo),
        normalizar_texto(material),
        normalizar_texto(unidad),
        normalizar_texto(categoria),
        normalizar_texto(ubicacion),
    )


# ============================================================
# COLUMNAS WORD
# ============================================================

MAPA_COLUMNAS = {
    "codigo": ["codigo", "código", "cod", "nro codigo", "nro. codigo", "n° codigo", "nº codigo", "numero", "número"],
    "material": ["material", "descripcion", "descripción", "elemento", "insumo", "repuesto", "denominacion", "denominación", "detalle"],
    "cantidad": ["cantidad", "cant", "cant.", "stock", "existencia", "existencias", "cantidad existente"],
    "unidad": ["unidad", "un", "u", "unidad de medida", "medida"],
    "categoria": ["categoria", "categoría", "rubro", "tipo", "clasificacion", "clasificación"],
    "ubicacion": ["ubicacion", "ubicación", "lugar", "destino", "sector", "dependencia", "deposito", "depósito", "pañol"],
    "observaciones": ["observaciones", "observacion", "observación", "obs", "comentarios", "comentario", "notas"],
}


def identificar_columna(texto):
    normalizado = normalizar_texto(texto)
    if not normalizado:
        return None
    for nombre, variantes in MAPA_COLUMNAS.items():
        if normalizado in {normalizar_texto(v) for v in variantes}:
            return nombre
    return None


def detectar_encabezados(filas):
    mejor_indice = None
    mejor_puntaje = 0
    mejor_mapa = {}
    for indice, fila in enumerate(filas):
        mapa = {}
        for numero_columna, valor in enumerate(fila):
            columna = identificar_columna(valor)
            if columna and columna not in mapa:
                mapa[columna] = numero_columna
        if len(mapa) > mejor_puntaje:
            mejor_puntaje = len(mapa)
            mejor_indice = indice
            mejor_mapa = mapa
    if mejor_indice is None or ("material" not in mejor_mapa and "cantidad" not in mejor_mapa):
        return None, {}
    return mejor_indice, mejor_mapa


def extraer_filas_tabla(tabla):
    filas = [[texto_limpio(celda.text) or "" for celda in fila.cells] for fila in tabla.rows]
    if not filas:
        return []
    indice_encabezado, mapa = detectar_encabezados(filas)
    if indice_encabezado is None:
        return []
    registros = []
    for fila in filas[indice_encabezado + 1:]:
        if not any(str(valor).strip() for valor in fila):
            continue
        def obtener(nombre):
            indice = mapa.get(nombre)
            return texto_limpio(fila[indice]) if indice is not None and indice < len(fila) else None
        registro = {
            "codigo": obtener("codigo"),
            "material": obtener("material"),
            "cantidad": convertir_cantidad(obtener("cantidad")),
            "unidad": obtener("unidad"),
            "categoria": obtener("categoria"),
            "ubicacion": obtener("ubicacion"),
            "observaciones": obtener("observaciones"),
        }
        if not registro["material"] and not registro["codigo"]:
            continue
        texto_completo = normalizar_texto(" ".join(str(x or "") for x in fila))
        if texto_completo in ("total", "totales", "subtotal"):
            continue
        registros.append(registro)
    return registros


def _tablas_recursivas(contenedor):
    """Devuelve todas las tablas de un documento o celda, incluyendo
    las que están anidadas dentro de celdas de otra tabla."""
    tablas = []
    for tabla in contenedor.tables:
        tablas.append(tabla)
        for fila in tabla.rows:
            for celda in fila.cells:
                tablas.extend(_tablas_recursivas(celda))
    return tablas


def extraer_datos_word(ruta):
    documento = Document(str(ruta))
    filas = []
    tablas = _tablas_recursivas(documento)
    for tabla in tablas:
        filas.extend(extraer_filas_tabla(tabla))
    return {"filas": filas, "tablas": len(tablas)}


def consolidar_filas(filas):
    agrupadas = {}
    for fila in filas:
        clave = clave_material(fila.get("codigo"), fila.get("material"), fila.get("unidad"), fila.get("categoria"), fila.get("ubicacion"))
        if clave not in agrupadas:
            agrupadas[clave] = dict(fila)
        else:
            agrupadas[clave]["cantidad"] += float(fila.get("cantidad") or 0)
            obs_actual = agrupadas[clave].get("observaciones")
            obs_nueva = fila.get("observaciones")
            if obs_nueva and obs_nueva != obs_actual:
                agrupadas[clave]["observaciones"] = f"{obs_actual}; {obs_nueva}" if obs_actual else obs_nueva
    return list(agrupadas.values())


# ============================================================
# CONSULTAS EN BLOQUE
# ============================================================

def cargar_indices_iniciales():
    """Carga materiales y documentos una sola vez."""
    materiales = supabase.table("materiales").select("*").order("id").execute().data or []
    documentos = supabase.table("documentos").select("*").order("id").execute().data or []
    por_clave = {}
    for material in materiales:
        por_clave[clave_material(material.get("codigo"), material.get("material"), material.get("unidad"), material.get("categoria"), material.get("ubicacion"))] = material
    documentos_por_ruta = {(str(d.get("ruta") or ""), str(d.get("nombre") or "")): d for d in documentos}
    return materiales, por_clave, documentos, documentos_por_ruta


def _upsert_filas(tabla, filas, lote=200):
    """Upsert por lotes para evitar cientos de conexiones HTTP."""
    resultado = []
    for inicio in range(0, len(filas), lote):
        bloque = filas[inicio:inicio + lote]
        if not bloque:
            continue
        respuesta = supabase.table(tabla).upsert(bloque).execute().data or []
        resultado.extend(respuesta)
    return resultado


def _actualizar_documentos_en_bloque(documentos):
    if not documentos:
        return []
    return _upsert_filas("documentos", documentos, lote=100)


def _crear_materiales_en_bloque(materiales):
    if not materiales:
        return []
    resultado = []
    for inicio in range(0, len(materiales), 100):
        bloque = materiales[inicio:inicio + 100]
        respuesta = supabase.table("materiales").insert(bloque).execute().data or []
        resultado.extend(respuesta)
    return resultado


def _reemplazar_items_documento(documento_id, items):
    supabase.table("documento_items").delete().eq("documento_id", documento_id).execute()
    if not items:
        return
    _upsert_filas("documento_items", items, lote=200)


# ============================================================
# IMPORTACION OPTIMIZADA
# ============================================================

def importar_todos(reescaneo_completo=False):
    resultado = {
        "archivos": 0,
        "procesados": 0,
        "sin_cambios": 0,
        "nuevos": 0,
        "actualizados": 0,
        "items": 0,
        "errores": [],
        "vacios": 0,
    }

    CARPETA_DOCUMENTOS.mkdir(parents=True, exist_ok=True)
    archivos = sorted(a for a in CARPETA_DOCUMENTOS.glob("*.docx") if not a.name.startswith("~$"))
    resultado["archivos"] = len(archivos)
    if not archivos:
        return resultado

    # --------------------------------------------------------
    # 1. Una sola lectura inicial de Supabase
    # --------------------------------------------------------
    try:
        materiales, por_clave, documentos, documentos_por_ruta = cargar_indices_iniciales()
    except Exception as error:
        resultado["errores"].append(f"Error cargando indices iniciales: {error}")
        traceback.print_exc()
        return resultado

    documentos_a_guardar = []
    trabajos = []

    # --------------------------------------------------------
    # 2. Leer todos los Word localmente antes de escribir
    # --------------------------------------------------------
    for ruta in archivos:
        try:
            fecha = datetime.fromtimestamp(ruta.stat().st_mtime).isoformat()
        except Exception:
            fecha = None

        existente = documentos_por_ruta.get((str(ruta), ruta.name))
        fecha_anterior = str((existente or {}).get("fecha_modificacion_archivo") or "")

        if not reescaneo_completo and existente and fecha_anterior and fecha_anterior == str(fecha or ""):
            resultado["sin_cambios"] += 1
            continue

        try:
            datos = extraer_datos_word(ruta)
            filas = consolidar_filas(datos["filas"])
        except Exception as error:
            resultado["errores"].append(f"{ruta.name}: Error leyendo Word: {error}")
            continue

        documento = dict(existente) if existente else None
        if documento:
            documento["fecha_modificacion_archivo"] = str(fecha) if fecha is not None else None
        else:
            documento = {"nombre": ruta.name, "ruta": str(ruta), "fecha_modificacion_archivo": str(fecha) if fecha is not None else None}
        documentos_a_guardar.append(documento)
        trabajos.append((ruta, documento, filas))

    if not trabajos:
        return resultado

    # --------------------------------------------------------
    # 3. Guardar documentos en bloque y obtener IDs nuevos
    # --------------------------------------------------------
    try:
        documentos_guardados = _actualizar_documentos_en_bloque(documentos_a_guardar)
    except Exception as error:
        resultado["errores"].append(f"Error guardando documentos: {error}")
        traceback.print_exc()
        return resultado

    documentos_por_clave = {(str(d.get("ruta") or ""), str(d.get("nombre") or "")): d for d in documentos_guardados}
    for d in documentos_guardados:
        documentos_por_ruta[(str(d.get("ruta") or ""), str(d.get("nombre") or ""))] = d

    # --------------------------------------------------------
    # 4. Resolver materiales en memoria
    # --------------------------------------------------------
    nuevos_materiales = []
    claves_nuevas = set()

    for ruta, documento, filas in trabajos:
        for fila in filas:
            clave = clave_material(fila.get("codigo"), fila.get("material"), fila.get("unidad"), fila.get("categoria"), fila.get("ubicacion"))
            if clave in por_clave or clave in claves_nuevas:
                continue
            claves_nuevas.add(clave)
            nuevos_materiales.append({
                "codigo": fila.get("codigo"),
                "material": fila.get("material"),
                "cantidad": 0,
                "unidad": fila.get("unidad"),
                "categoria": fila.get("categoria"),
                "ubicacion": fila.get("ubicacion"),
                "observaciones": fila.get("observaciones"),
                "archivo_origen": ruta.name,
            })

    if nuevos_materiales:
        try:
            creados = _crear_materiales_en_bloque(nuevos_materiales)
            for material in creados:
                clave = clave_material(material.get("codigo"), material.get("material"), material.get("unidad"), material.get("categoria"), material.get("ubicacion"))
                por_clave[clave] = material
                materiales.append(material)
            resultado["nuevos"] += len(creados)
        except Exception as error:
            resultado["errores"].append(f"Error creando materiales en bloque: {error}")
            traceback.print_exc()
            return resultado

    # --------------------------------------------------------
    # 5. Actualizar materiales existentes en bloque
    # --------------------------------------------------------
    materiales_a_upsert = []
    vistos = set()
    for ruta, documento, filas in trabajos:
        for fila in filas:
            clave = clave_material(fila.get("codigo"), fila.get("material"), fila.get("unidad"), fila.get("categoria"), fila.get("ubicacion"))
            material = por_clave.get(clave)
            if not material:
                continue
            mid = material.get("id")
            if mid in vistos:
                continue
            vistos.add(mid)
            actualizado = dict(material)
            actualizado.update({
                "codigo": fila.get("codigo"),
                "material": fila.get("material"),
                "unidad": fila.get("unidad"),
                "categoria": fila.get("categoria"),
                "ubicacion": fila.get("ubicacion"),
                "observaciones": fila.get("observaciones"),
            })
            materiales_a_upsert.append(actualizado)

    if materiales_a_upsert:
        try:
            _upsert_filas("materiales", materiales_a_upsert, lote=200)
            resultado["actualizados"] += len(materiales_a_upsert)
        except Exception as error:
            resultado["errores"].append(f"Error actualizando materiales en bloque: {error}")
            traceback.print_exc()

    # --------------------------------------------------------
    # 6. Reemplazar items por documento: pocas consultas
    # --------------------------------------------------------
    for ruta, documento, filas in trabajos:
        try:
            clave_doc = (str(documento.get("ruta") or ""), str(documento.get("nombre") or ""))
            documento_real = documentos_por_clave.get(clave_doc) or documentos_por_ruta.get(clave_doc) or documento
            documento_id = documento_real.get("id")
            if documento_id is None:
                raise Exception("No se obtuvo el ID del documento.")

            items = []
            for fila in filas:
                clave = clave_material(fila.get("codigo"), fila.get("material"), fila.get("unidad"), fila.get("categoria"), fila.get("ubicacion"))
                material = por_clave.get(clave)
                if not material or material.get("id") is None:
                    raise Exception(f"No se pudo resolver el material: {fila.get('material')}")
                items.append({
                    "documento_id": documento_id,
                    "material_id": material["id"],
                    "cantidad": float(fila.get("cantidad") or 0),
                    "unidad": fila.get("unidad"),
                    "codigo": fila.get("codigo"),
                    "material": fila.get("material"),
                    "categoria": fila.get("categoria"),
                    "ubicacion": fila.get("ubicacion"),
                    "observaciones": fila.get("observaciones"),
                })

            _reemplazar_items_documento(documento_id, items)
            resultado["procesados"] += 1
            resultado["items"] += len(items)
            if not items:
                resultado["vacios"] += 1
        except Exception as error:
            resultado["errores"].append(f"{ruta.name}: {error}")
            traceback.print_exc()

    return resultado


# ============================================================
# COMPATIBILIDAD
# ============================================================

def importar_documento(ruta, indice_materiales=None):
    """Compatibilidad con llamadas antiguas. Usa el importador optimizado."""
    resultado = importar_todos(reescaneo_completo=True)
    return {
        "archivo": ruta.name,
        "ruta": str(ruta),
        "nuevos": resultado.get("nuevos", 0),
        "actualizados": resultado.get("actualizados", 0),
        "items": resultado.get("items", 0),
        "errores": resultado.get("errores", []),
        "sin_cambios": False,
    }


# ============================================================
# AUDITORIA DE DUPLICADOS
# ============================================================

def auditar_materiales():
    materiales = supabase.table("materiales").select("*").order("id").execute().data or []
    resultado = {
        "exactos": [],
        "ubicacion_diferente": [],
        "categoria_diferente": [],
        "codigo_mismo_material_diferente": [],
        "posibles_nombres": [],
    }

    grupos = {}
    for material in materiales:
        grupos.setdefault(clave_material(material.get("codigo"), material.get("material"), material.get("unidad"), material.get("categoria"), material.get("ubicacion")), []).append(material)
    for clave, grupo in grupos.items():
        if len(grupo) > 1:
            resultado["exactos"].append({"clave": clave, "materiales": grupo, "cantidad_registros": len(grupo), "cantidad_total": sum(float(x.get("cantidad") or 0) for x in grupo)})

    por_codigo = {}
    for material in materiales:
        codigo = normalizar_codigo(material.get("codigo"))
        if codigo:
            por_codigo.setdefault(codigo, []).append(material)
    for codigo, grupo in por_codigo.items():
        for i in range(len(grupo)):
            for j in range(i + 1, len(grupo)):
                if normalizar_texto(grupo[i].get("material")) != normalizar_texto(grupo[j].get("material")):
                    resultado["codigo_mismo_material_diferente"].append({"codigo": codigo, "a": grupo[i], "b": grupo[j]})

    por_material = {}
    for material in materiales:
        nombre = normalizar_texto(material.get("material"))
        if nombre:
            por_material.setdefault(nombre, []).append(material)
    for nombre, grupo in por_material.items():
        ubicaciones = {}
        categorias = {}
        for material in grupo:
            ubicaciones.setdefault(normalizar_texto(material.get("ubicacion")), []).append(material)
            categorias.setdefault(normalizar_texto(material.get("categoria")), []).append(material)
        if len(ubicaciones) > 1:
            resultado["ubicacion_diferente"].append({"material": nombre, "grupos": list(ubicaciones.values())})
        if len(categorias) > 1:
            resultado["categoria_diferente"].append({"material": nombre, "grupos": list(categorias.values())})

    return resultado


# Alias historico
construir_indice_materiales = lambda: cargar_indices_iniciales()[:3]


def obtener_fecha_modificacion(ruta):
    try:
        return datetime.fromtimestamp(ruta.stat().st_mtime).isoformat()
    except Exception:
        return None
