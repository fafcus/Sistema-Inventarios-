import sqlite3
from pathlib import Path


DB_PATH = Path(__file__).parent / "inventario.db"


def conectar():
    conexion = sqlite3.connect(DB_PATH)
    conexion.execute("PRAGMA foreign_keys = ON")
    return conexion


def columna_existe(cursor, tabla, columna):
    cursor.execute(f"PRAGMA table_info({tabla})")
    columnas = cursor.fetchall()

    return any(fila[1] == columna for fila in columnas)


def crear_base():

    conexion = conectar()
    cursor = conexion.cursor()

    # ========================================================
    # DOCUMENTOS WORD
    # ========================================================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS documentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            ruta TEXT NOT NULL,
            fecha_importacion TEXT NOT NULL,
            fecha_modificacion_archivo TEXT,
            UNIQUE(nombre, ruta)
        )
    """)

    # ========================================================
    # MATERIALES
    # ========================================================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS materiales (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo TEXT UNIQUE,
            material TEXT NOT NULL,
            cantidad REAL DEFAULT 0,
            unidad TEXT,
            categoria TEXT,
            ubicacion TEXT,
            observaciones TEXT,
            archivo_origen TEXT,
            fecha_importacion TEXT
        )
    """)

    # ========================================================
    # MOVIMIENTOS
    # ========================================================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS movimientos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            material_id INTEGER NOT NULL,
            tipo TEXT NOT NULL,
            cantidad REAL NOT NULL,
            stock_anterior REAL NOT NULL,
            stock_nuevo REAL NOT NULL,
            archivo_origen TEXT,
            usuario TEXT,
            fecha TEXT NOT NULL,
            observaciones TEXT,
            FOREIGN KEY(material_id)
                REFERENCES materiales(id)
        )
    """)

    # ========================================================
    # RELACIÓN WORD -> MATERIAL
    #
    # Guarda cuánto aporta cada Word a cada material.
    #
    # Esto evita que si modificás un Word:
    #
    # 10 -> 12
    #
    # el programa haga:
    #
    # 10 + 12 = 22
    #
    # En cambio reemplaza el aporte anterior:
    #
    # 10 -> 12
    # ========================================================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS documento_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            documento_id INTEGER NOT NULL,
            material_id INTEGER NOT NULL,
            cantidad REAL NOT NULL DEFAULT 0,
            unidad TEXT,
            codigo TEXT,
            material TEXT,
            categoria TEXT,
            ubicacion TEXT,
            observaciones TEXT,

            UNIQUE(documento_id, material_id),

            FOREIGN KEY(documento_id)
                REFERENCES documentos(id)
                ON DELETE CASCADE,

            FOREIGN KEY(material_id)
                REFERENCES materiales(id)
        )
    """)

    # ========================================================
    # MIGRACIONES
    # ========================================================

    if not columna_existe(
        cursor,
        "documentos",
        "fecha_modificacion_archivo"
    ):
        cursor.execute("""
            ALTER TABLE documentos
            ADD COLUMN fecha_modificacion_archivo TEXT
        """)

    if not columna_existe(
        cursor,
        "materiales",
        "observaciones"
    ):
        cursor.execute("""
            ALTER TABLE materiales
            ADD COLUMN observaciones TEXT
        """)

    # ========================================================
    # ÍNDICES
    # ========================================================

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS
        idx_movimientos_material
        ON movimientos(material_id)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS
        idx_documento_items_documento
        ON documento_items(documento_id)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS
        idx_documento_items_material
        ON documento_items(material_id)
    """)

    conexion.commit()
    conexion.close()


if __name__ == "__main__":

    crear_base()

    print(
        "Base de datos creada/actualizada correctamente."
    )