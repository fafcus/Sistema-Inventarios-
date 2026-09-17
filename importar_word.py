from pathlib import Path
from datetime import datetime
import re
import unicodedata
import traceback

from docx import Document

from config import supabase

from supabase_db import (
    obtener_materiales,
    obtener_documentos,
    obtener_documento_por_nombre_ruta,
    crear_documento,
    actualizar_documento,
    crear_material,
    actualizar_material,
    crear_item_documento,
    eliminar_items_documento,
)


# ============================================================
# CONFIGURACIÓN
# ============================================================

CARPETA_DOCUMENTOS = (
    Path(__file__).resolve().parent / "documentos"
)


# ============================================================
# NORMALIZACIÓN
# ============================================================

def normalizar_texto(valor):
    """
    Normaliza texto para comparar valores.

    Ejemplo:

        '  DEFENSAS  '
        'Defensas'
        'defensas'

    -> 'defensas'
    """

    if valor is None:
        return ""

    texto = str(valor)

    texto = texto.replace("\xa0", " ")

    texto = unicodedata.normalize(
        "NFKD",
        texto
    )

    texto = "".join(
        caracter
        for caracter in texto
        if not unicodedata.combining(caracter)
    )

    texto = texto.strip().lower()

    texto = re.sub(
        r"\s+",
        " ",
        texto
    )

    return texto


def normalizar_codigo(codigo):
    """
    Normaliza códigos únicamente para comparación.

    NO modifica el código que se guarda en Supabase.
    """

    if codigo is None:
        return ""

    codigo = str(codigo).strip().upper()

    if not codigo:
        return ""

    # Eliminar espacios, guiones y puntos.
    codigo = re.sub(
        r"[\s\-\.]+",
        "",
        codigo
    )

    return codigo


def texto_limpio(valor):
    if valor is None:
        return None

    texto = str(valor)

    texto = texto.replace(
        "\xa0",
        " "
    )

    texto = re.sub(
        r"\s+",
        " ",
        texto
    ).strip()

    if not texto:
        return None

    return texto


def convertir_cantidad(valor):
    """
    Convierte cantidades de Word a float.

    Soporta:

        10
        10.5
        10,5
        '10 unidades'
        '10,50'
    """

    if valor is None:
        return 0.0

    if isinstance(valor, (int, float)):
        return float(valor)

    texto = str(valor).strip()

    if not texto:
        return 0.0

    # Eliminar unidades o texto posterior.
    coincidencia = re.search(
        r"-?\d+(?:[.,]\d+)?",
        texto
    )

    if not coincidencia:
        return 0.0

    numero = coincidencia.group(0)

    # Si usa coma decimal.
    if "," in numero and "." not in numero:
        numero = numero.replace(
            ",",
            "."
        )

    try:
        return float(numero)

    except Exception:
        return 0.0


# ============================================================
# ENCABEZADOS
# ============================================================

MAPA_COLUMNAS = {
    "codigo": [
        "codigo",
        "código",
        "cod",
        "nro codigo",
        "nro. codigo",
        "n° codigo",
        "nº codigo",
        "numero",
        "número",
    ],

    "material": [
        "material",
        "descripcion",
        "descripción",
        "elemento",
        "insumo",
        "repuesto",
        "denominacion",
        "denominación",
        "detalle",
    ],

    "cantidad": [
        "cantidad",
        "cant",
        "cant.",
        "stock",
        "existencia",
        "existencias",
        "cantidad existente",
    ],

    "unidad": [
        "unidad",
        "un",
        "u",
        "unidad de medida",
        "medida",
    ],

    "categoria": [
        "categoria",
        "categoría",
        "rubro",
        "tipo",
        "clasificacion",
        "clasificación",
    ],

    "ubicacion": [
        "ubicacion",
        "ubicación",
        "lugar",
        "destino",
        "sector",
        "dependencia",
        "deposito",
        "depósito",
        "pañol",
    ],

    "observaciones": [
        "observaciones",
        "observacion",
        "observación",
        "obs",
        "comentarios",
        "comentario",
        "notas",
    ],
}


def identificar_columna(texto):
    """
    Devuelve el nombre interno de una columna.
    """

    normalizado = normalizar_texto(texto)

    if not normalizado:
        return None

    for nombre, variantes in MAPA_COLUMNAS.items():

        for variante in variantes:

            if normalizado == normalizar_texto(
                variante
            ):
                return nombre

    return None


def detectar_encabezados(filas):
    """
    Busca automáticamente una fila que parezca
    ser el encabezado de la tabla.
    """

    mejor_indice = None
    mejor_puntaje = 0
    mejor_mapa = {}

    for indice, fila in enumerate(filas):

        mapa = {}

        for numero_columna, valor in enumerate(fila):

            columna = identificar_columna(
                valor
            )

            if columna and columna not in mapa:
                mapa[columna] = numero_columna

        puntaje = len(mapa)

        if puntaje > mejor_puntaje:

            mejor_puntaje = puntaje
            mejor_indice = indice
            mejor_mapa = mapa

    # Necesitamos al menos material o cantidad
    # para considerar que encontramos encabezados.

    if (
        mejor_indice is None
        or (
            "material" not in mejor_mapa
            and "cantidad" not in mejor_mapa
        )
    ):
        return None, {}

    return mejor_indice, mejor_mapa


# ============================================================
# TABLAS WORD
# ============================================================

def leer_tabla(tabla):
    """
    Convierte una tabla de python-docx a una lista
    de listas de texto.
    """

    filas = []

    for fila in tabla.rows:

        valores = []

        for celda in fila.cells:

            valores.append(
                texto_limpio(
                    celda.text
                )
                or ""
            )

        filas.append(valores)

    return filas


def extraer_filas_tabla(tabla):
    """
    Extrae los registros de una tabla Word.
    """

    filas = leer_tabla(tabla)

    if not filas:
        return []

    indice_encabezado, mapa = (
        detectar_encabezados(filas)
    )

    registros = []

    if indice_encabezado is None:

        return registros

    for fila in filas[
        indice_encabezado + 1:
    ]:

        # Ignorar filas completamente vacías.
        if not any(
            str(valor).strip()
            for valor in fila
        ):
            continue

        def obtener(nombre):

            indice = mapa.get(
                nombre
            )

            if indice is None:
                return None

            if indice >= len(fila):
                return None

            return texto_limpio(
                fila[indice]
            )

        registro = {
            "codigo": obtener(
                "codigo"
            ),

            "material": obtener(
                "material"
            ),

            "cantidad": convertir_cantidad(
                obtener("cantidad")
            ),

            "unidad": obtener(
                "unidad"
            ),

            "categoria": obtener(
                "categoria"
            ),

            "ubicacion": obtener(
                "ubicacion"
            ),

            "observaciones": obtener(
                "observaciones"
            ),
        }

        # ----------------------------------------------------
        # FILTROS
        # ----------------------------------------------------

        if not registro["material"]:

            # Si no hay material pero hay código,
            # dejamos pasar el registro.
            if not registro["codigo"]:
                continue

        # Evitar filas que sean títulos o separadores.

        texto_completo = normalizar_texto(
            " ".join(
                str(x or "")
                for x in fila
            )
        )

        if texto_completo in (
            "total",
            "totales",
            "subtotal",
        ):
            continue

        registros.append(
            registro
        )

    return registros


# ============================================================
# EXTRACCIÓN COMPLETA DEL WORD
# ============================================================

def extraer_datos_word(ruta):
    """
    Lee todas las tablas del DOCX.

    Devuelve:

        {
            "filas": [...],
            "tablas": cantidad
        }
    """

    documento = Document(
        str(ruta)
    )

    filas = []

    for tabla in documento.tables:

        registros = extraer_filas_tabla(
            tabla
        )

        filas.extend(
            registros
        )

    return {
        "filas": filas,
        "tablas": len(
            documento.tables
        )
    }


# ============================================================
# CLAVE DE MATERIAL
# ============================================================

def clave_material(
    codigo,
    material,
    unidad,
    categoria,
    ubicacion
):
    """
    Clave utilizada para determinar si una fila
    representa el mismo material.

    La cantidad NO forma parte de la clave.
    """

    codigo_normalizado = normalizar_codigo(
        codigo
    )

    material_normalizado = normalizar_texto(
        material
    )

    unidad_normalizada = normalizar_texto(
        unidad
    )

    categoria_normalizada = normalizar_texto(
        categoria
    )

    ubicacion_normalizada = normalizar_texto(
        ubicacion
    )

    return (
        codigo_normalizado,
        material_normalizado,
        unidad_normalizada,
        categoria_normalizada,
        ubicacion_normalizada,
    )


# ============================================================
# CONSOLIDAR FILAS DEL MISMO DOCUMENTO
# ============================================================

def consolidar_filas(filas):
    """
    Si un mismo material aparece varias veces dentro
    del mismo Word con la misma clave, suma cantidades.

    NO mezcla ubicaciones ni categorías diferentes.
    """

    agrupadas = {}

    for fila in filas:

        clave = clave_material(
            fila.get("codigo"),
            fila.get("material"),
            fila.get("unidad"),
            fila.get("categoria"),
            fila.get("ubicacion"),
        )

        if clave not in agrupadas:

            agrupadas[clave] = dict(
                fila
            )

        else:

            agrupadas[
                clave
            ]["cantidad"] += float(
                fila.get(
                    "cantidad"
                )
                or 0
            )

            # Conservar observaciones.

            obs_actual = (
                agrupadas[
                    clave
                ].get(
                    "observaciones"
                )
            )

            obs_nueva = (
                fila.get(
                    "observaciones"
                )
            )

            if (
                obs_nueva
                and obs_nueva != obs_actual
            ):

                if obs_actual:

                    agrupadas[
                        clave
                    ]["observaciones"] = (
                        f"{obs_actual}; "
                        f"{obs_nueva}"
                    )

                else:

                    agrupadas[
                        clave
                    ]["observaciones"] = (
                        obs_nueva
                    )

    return list(
        agrupadas.values()
    )


# ============================================================
# ÍNDICE DE MATERIALES
# ============================================================

def construir_indice_materiales():
    """
    Carga los materiales actuales de Supabase
    y crea índices para búsquedas rápidas.
    """

    materiales = obtener_materiales()

    por_clave = {}

    por_codigo = {}

    for material in materiales:

        clave = clave_material(
            material.get("codigo"),
            material.get("material"),
            material.get("unidad"),
            material.get("categoria"),
            material.get("ubicacion"),
        )

        por_clave[
            clave
        ] = material

        codigo = normalizar_codigo(
            material.get("codigo")
        )

        if codigo:

            por_codigo.setdefault(
                codigo,
                []
            ).append(
                material
            )

    return (
        materiales,
        por_clave,
        por_codigo
    )


# ============================================================
# BUSCAR MATERIAL SEGURO
# ============================================================

def buscar_material_importacion(
    fila,
    por_clave,
    por_codigo
):
    """
    Busca un material existente.

    Prioridad:

    1. Coincidencia exacta de:
       código + material + unidad +
       categoría + ubicación

    2. Si no hay código:
       coincidencia exacta de material +
       unidad + categoría + ubicación.

    3. Si hay código pero el nombre difiere,
       NO mezcla automáticamente.
    """

    clave = clave_material(
        fila.get("codigo"),
        fila.get("material"),
        fila.get("unidad"),
        fila.get("categoria"),
        fila.get("ubicacion"),
    )

    existente = por_clave.get(
        clave
    )

    if existente:
        return existente

    # --------------------------------------------------------
    # Sin código
    # --------------------------------------------------------

    if not normalizar_codigo(
        fila.get("codigo")
    ):

        return None

    # --------------------------------------------------------
    # Con código
    #
    # No usamos solamente el código porque pueden existir
    # materiales diferentes con el mismo código.
    # --------------------------------------------------------

    return None


# ============================================================
# FECHA DE ARCHIVO
# ============================================================

def obtener_fecha_modificacion(ruta):
    try:

        timestamp = ruta.stat().st_mtime

        return datetime.fromtimestamp(
            timestamp
        ).isoformat()

    except Exception:

        return None


# ============================================================
# PROCESAR UN DOCUMENTO
# ============================================================

def importar_documento(
    ruta,
    indice_materiales=None
):
    """
    Importa un único Word.

    Devuelve estadísticas.
    """

    resultado = {
        "archivo": ruta.name,
        "ruta": str(ruta),
        "nuevos": 0,
        "actualizados": 0,
        "items": 0,
        "errores": [],
        "sin_cambios": False,
    }

    fecha_modificacion = (
        obtener_fecha_modificacion(
            ruta
        )
    )

    # --------------------------------------------------------
    # DOCUMENTO
    # --------------------------------------------------------

    documento = (
        obtener_documento_por_nombre_ruta(
            ruta.name,
            ruta
        )
    )

    if documento is None:

        documento = crear_documento(
            nombre=ruta.name,
            ruta=ruta,
            fecha_modificacion_archivo=(
                fecha_modificacion
            ),
        )

    else:

        fecha_anterior = str(
            documento.get(
                "fecha_modificacion_archivo"
            )
            or ""
        )

        fecha_actual = str(
            fecha_modificacion
            or ""
        )

        # Si el archivo no cambió, no reprocesamos.

        if (
            fecha_anterior
            and fecha_anterior == fecha_actual
        ):

            resultado[
                "sin_cambios"
            ] = True

            return resultado

        actualizar_documento(
            documento["id"],
            fecha_modificacion
        )

    if documento is None:

        resultado[
            "errores"
        ].append(
            "No se pudo crear/obtener el documento."
        )

        return resultado

    # --------------------------------------------------------
    # LEER WORD
    # --------------------------------------------------------

    try:

        datos = extraer_datos_word(
            ruta
        )

    except Exception as e:

        resultado[
            "errores"
        ].append(
            f"Error leyendo Word: {e}"
        )

        return resultado

    filas = consolidar_filas(
        datos["filas"]
    )

    resultado[
        "items"
    ] = len(filas)

    if not filas:

        return resultado

    # --------------------------------------------------------
    # ELIMINAR ITEMS ANTERIORES
    #
    # IMPORTANTE:
    # documento_items representa el contenido actual
    # del Word.
    #
    # No tocamos todavía materiales.cantidad aquí.
    # --------------------------------------------------------

    eliminar_items_documento(
        documento["id"]
    )

    # --------------------------------------------------------
    # RECARGAR ÍNDICE DE MATERIALES
    # --------------------------------------------------------

    if indice_materiales is None:

        (
            materiales,
            por_clave,
            por_codigo
        ) = construir_indice_materiales()

    else:

        (
            materiales,
            por_clave,
            por_codigo
        ) = indice_materiales

    # --------------------------------------------------------
    # PROCESAR CADA FILA
    # --------------------------------------------------------

    for fila in filas:

        try:

            existente = buscar_material_importacion(
                fila,
                por_clave,
                por_codigo
            )

            # ------------------------------------------------
            # MATERIAL EXISTENTE
            # ------------------------------------------------

            if existente:

                material_id = existente[
                    "id"
                ]

                actualizar_material(
                    material_id=material_id,
                    codigo=fila.get(
                        "codigo"
                    ),
                    material=fila.get(
                        "material"
                    ),
                    unidad=fila.get(
                        "unidad"
                    ),
                    categoria=fila.get(
                        "categoria"
                    ),
                    ubicacion=fila.get(
                        "ubicacion"
                    ),
                    observaciones=fila.get(
                        "observaciones"
                    ),
                )

                resultado[
                    "actualizados"
                ] += 1

            # ------------------------------------------------
            # MATERIAL NUEVO
            # ------------------------------------------------

            else:

                nuevo = crear_material(
                    codigo=fila.get(
                        "codigo"
                    ),
                    material=fila.get(
                        "material"
                    ),
                    cantidad=0,
                    unidad=fila.get(
                        "unidad"
                    ),
                    categoria=fila.get(
                        "categoria"
                    ),
                    ubicacion=fila.get(
                        "ubicacion"
                    ),
                    observaciones=fila.get(
                        "observaciones"
                    ),
                    archivo_origen=ruta.name,
                )

                if nuevo is None:

                    raise Exception(
                        "No se pudo crear el material."
                    )

                material_id = nuevo[
                    "id"
                ]

                resultado[
                    "nuevos"
                ] += 1

                # Actualizar índices.

                nuevo_clave = clave_material(
                    nuevo.get("codigo"),
                    nuevo.get("material"),
                    nuevo.get("unidad"),
                    nuevo.get("categoria"),
                    nuevo.get("ubicacion"),
                )

                por_clave[
                    nuevo_clave
                ] = nuevo

                codigo_nuevo = (
                    normalizar_codigo(
                        nuevo.get("codigo")
                    )
                )

                if codigo_nuevo:

                    por_codigo.setdefault(
                        codigo_nuevo,
                        []
                    ).append(
                        nuevo
                    )

            # ------------------------------------------------
            # DOCUMENTO ITEM
            # ------------------------------------------------

            crear_item_documento(
                documento_id=documento["id"],
                material_id=material_id,
                cantidad=fila.get(
                    "cantidad"
                ) or 0,
                unidad=fila.get(
                    "unidad"
                ),
                codigo=fila.get(
                    "codigo"
                ),
                material=fila.get(
                    "material"
                ),
                categoria=fila.get(
                    "categoria"
                ),
                ubicacion=fila.get(
                    "ubicacion"
                ),
                observaciones=fila.get(
                    "observaciones"
                ),
            )

        except Exception as e:

            mensaje = (
                f"{ruta.name}: "
                f"{fila.get('material') or 'SIN MATERIAL'}: "
                f"{e}"
            )

            resultado[
                "errores"
            ].append(
                mensaje
            )

    return resultado


# ============================================================
# IMPORTAR TODOS LOS WORD
# ============================================================

def importar_todos(
    reescaneo_completo=False
):
    """
    Función utilizada directamente por main.py.

    Ejemplo:

        importar_word.importar_todos()

    o:

        importar_word.importar_todos(
            reescaneo_completo=True
        )
    """

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

    CARPETA_DOCUMENTOS.mkdir(
        parents=True,
        exist_ok=True
    )

    archivos = sorted(
        CARPETA_DOCUMENTOS.glob(
            "*.docx"
        )
    )

    # Ignorar archivos temporales de Word.

    archivos = [
        archivo
        for archivo in archivos
        if not archivo.name.startswith(
            "~$"
        )
    ]

    resultado[
        "archivos"
    ] = len(archivos)

    if not archivos:

        return resultado

    # --------------------------------------------------------
    # ÍNDICE INICIAL
    # --------------------------------------------------------

    indice_materiales = (
        construir_indice_materiales()
    )

    # --------------------------------------------------------
    # IMPORTACIÓN
    # --------------------------------------------------------

    for ruta in archivos:

        try:

            info = importar_documento(
                ruta,
                indice_materiales
            )

            if info[
                "sin_cambios"
            ]:

                resultado[
                    "sin_cambios"
                ] += 1

                continue

            resultado[
                "procesados"
            ] += 1

            resultado[
                "nuevos"
            ] += info[
                "nuevos"
            ]

            resultado[
                "actualizados"
            ] += info[
                "actualizados"
            ]

            resultado[
                "items"
            ] += info[
                "items"
            ]

            if info[
                "items"
            ] == 0:

                resultado[
                    "vacios"
                ] += 1

            resultado[
                "errores"
            ].extend(
                info[
                    "errores"
                ]
            )

        except Exception as e:

            resultado[
                "errores"
            ].append(
                f"{ruta.name}: {e}"
            )

            traceback.print_exc()

    return resultado


# ============================================================
# AUDITORÍA DE DUPLICADOS
# ============================================================

def clave_auditoria(material):
    """
    Clave exacta utilizada por la auditoría.

    La cantidad queda fuera porque debe sumarse.
    """

    return clave_material(
        material.get("codigo"),
        material.get("material"),
        material.get("unidad"),
        material.get("categoria"),
        material.get("ubicacion"),
    )


def auditar_materiales():
    """
    Analiza materiales existentes en Supabase.

    NO MODIFICA NADA.

    Devuelve:

        {
            "exactos": [],
            "ubicacion_diferente": [],
            "categoria_diferente": [],
            "codigo_mismo_material_diferente": [],
            "posibles_nombres": []
        }
    """

    materiales = obtener_materiales()

    resultado = {
        "exactos": [],
        "ubicacion_diferente": [],
        "categoria_diferente": [],
        "codigo_mismo_material_diferente": [],
        "posibles_nombres": [],
    }

    # --------------------------------------------------------
    # DUPLICADOS EXACTOS
    # --------------------------------------------------------

    grupos = {}

    for material in materiales:

        clave = clave_auditoria(
            material
        )

        grupos.setdefault(
            clave,
            []
        ).append(
            material
        )

    for clave, grupo in grupos.items():

        if len(grupo) <= 1:
            continue

        cantidad_total = sum(
            float(
                item.get(
                    "cantidad"
                )
                or 0
            )
            for item in grupo
        )

        resultado[
            "exactos"
        ].append({
            "clave": clave,
            "materiales": grupo,
            "cantidad_total":
                cantidad_total,
            "cantidad_registros":
                len(grupo),
        })

    # --------------------------------------------------------
    # MISMO CÓDIGO
    # --------------------------------------------------------

    por_codigo = {}

    for material in materiales:

        codigo = normalizar_codigo(
            material.get("codigo")
        )

        if not codigo:
            continue

        por_codigo.setdefault(
            codigo,
            []
        ).append(
            material
        )

    for codigo, grupo in por_codigo.items():

        if len(grupo) <= 1:
            continue

        for i in range(
            len(grupo)
        ):

            for j in range(
                i + 1,
                len(grupo)
            ):

                a = grupo[i]
                b = grupo[j]

                nombre_a = normalizar_texto(
                    a.get("material")
                )

                nombre_b = normalizar_texto(
                    b.get("material")
                )

                if (
                    nombre_a
                    != nombre_b
                ):

                    resultado[
                        "codigo_mismo_material_diferente"
                    ].append({
                        "codigo": codigo,
                        "a": a,
                        "b": b,
                    })

    # --------------------------------------------------------
    # MISMO MATERIAL, DISTINTA UBICACIÓN
    # --------------------------------------------------------

    por_material = {}

    for material in materiales:

        nombre = normalizar_texto(
            material.get("material")
        )

        if not nombre:
            continue

        por_material.setdefault(
            nombre,
            []
        ).append(
            material
        )

    for nombre, grupo in por_material.items():

        if len(grupo) <= 1:
            continue

        for i in range(
            len(grupo)
        ):

            for j in range(
                i + 1,
                len(grupo)
            ):

                a = grupo[i]
                b = grupo[j]

                ubicacion_a = normalizar_texto(
                    a.get("ubicacion")
                )

                ubicacion_b = normalizar_texto(
                    b.get("ubicacion")
                )

                categoria_a = normalizar_texto(
                    a.get("categoria")
                )

                categoria_b = normalizar_texto(
                    b.get("categoria")
                )

                if (
                    ubicacion_a
                    != ubicacion_b
                ):

                    resultado[
                        "ubicacion_diferente"
                    ].append({
                        "material": nombre,
                        "a": a,
                        "b": b,
                    })

                elif (
                    categoria_a
                    != categoria_b
                ):

                    resultado[
                        "categoria_diferente"
                    ].append({
                        "material": nombre,
                        "a": a,
                        "b": b,
                    })

    # --------------------------------------------------------
    # POSIBLES DIFERENCIAS DE NOMBRE
    # --------------------------------------------------------

    # Comparación conservadora:
    # mismas condiciones salvo pequeñas diferencias
    # de pluralización.

    for i in range(
        len(materiales)
    ):

        for j in range(
            i + 1,
            len(materiales)
        ):

            a = materiales[i]
            b = materiales[j]

            codigo_a = normalizar_codigo(
                a.get("codigo")
            )

            codigo_b = normalizar_codigo(
                b.get("codigo")
            )

            if codigo_a != codigo_b:
                continue

            # Si uno tiene código y otro no,
            # no proponemos coincidencia.
            if not codigo_a:
                continue

            nombre_a = normalizar_texto(
                a.get("material")
            )

            nombre_b = normalizar_texto(
                b.get("material")
            )

            if nombre_a == nombre_b:
                continue

            def singularizar(texto):

                if texto.endswith(
                    "es"
                ):
                    return texto[:-2]

                if texto.endswith(
                    "s"
                ):
                    return texto[:-1]

                return texto

            if (
                singularizar(nombre_a)
                ==
                singularizar(nombre_b)
            ):

                resultado[
                    "posibles_nombres"
                ].append({
                    "a": a,
                    "b": b,
                    "motivo":
                        "Posible diferencia "
                        "singular/plural",
                })

    return resultado


# ============================================================
# RESUMEN DE AUDITORÍA
# ============================================================

def resumen_auditoria():
    auditoria = auditar_materiales()

    return {
        "exactos":
            len(
                auditoria[
                    "exactos"
                ]
            ),

        "ubicacion_diferente":
            len(
                auditoria[
                    "ubicacion_diferente"
                ]
            ),

        "categoria_diferente":
            len(
                auditoria[
                    "categoria_diferente"
                ]
            ),

        "codigo_diferente":
            len(
                auditoria[
                    "codigo_mismo_material_diferente"
                ]
            ),

        "posibles_nombres":
            len(
                auditoria[
                    "posibles_nombres"
                ]
            ),
    }
