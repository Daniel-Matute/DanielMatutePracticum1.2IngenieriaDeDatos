"""
formalizar_fk_ciiu.py
=======================
SQLite no permite ALTER TABLE ADD FOREIGN KEY. Para formalizar la FK de
ciiu -> dim_ciiu(ciiu) en dim_empresas, fact_ranking_empresarial y fact_vab,
hay que reconstruir cada tabla: renombrar la vieja, crear la nueva con la
FK, copiar los datos, borrar la vieja.

Precondicion ya verificada: 0.000% de desajuste en las 4 columnas afectadas
(dim_empresas.ciiu_n1/ciiu_n6, fact_ranking_empresarial.ciiu_n6, fact_vab.ciiu)
contra dim_ciiu, incluso despues de la integracion RPA.
"""
import sqlite3

DB_PRINCIPAL = 'pipeline_utpl.db'


def reconstruir_dim_empresas(cur):
    print("\n--- Reconstruyendo dim_empresas con FK a dim_ciiu ---")
    cur.execute("ALTER TABLE dim_empresas RENAME TO dim_empresas_old")
    cur.execute("""
        CREATE TABLE dim_empresas (
            ruc              TEXT PRIMARY KEY,
            expediente       INTEGER,
            nombre           TEXT,
            situacion_legal  TEXT,
            provincia        TEXT,
            canton           TEXT,
            ciiu_n1          TEXT REFERENCES dim_ciiu(ciiu),
            ciiu_n6          TEXT REFERENCES dim_ciiu(ciiu),
            fecha_constitucion TEXT,
            ultimo_balance     TEXT
        )
    """)
    cur.execute("""
        INSERT INTO dim_empresas
        SELECT ruc, expediente, nombre, situacion_legal, provincia, canton,
               ciiu_n1, ciiu_n6, fecha_constitucion, ultimo_balance
        FROM dim_empresas_old
    """)
    cur.execute("DROP TABLE dim_empresas_old")
    cur.execute("SELECT COUNT(*) FROM dim_empresas")
    print(f"  -> dim_empresas reconstruida: {cur.fetchone()[0]} filas")


def reconstruir_fact_ranking(cur):
    print("\n--- Reconstruyendo fact_ranking_empresarial con FK a dim_ciiu ---")
    cur.execute("ALTER TABLE fact_ranking_empresarial RENAME TO fact_ranking_empresarial_old")
    cur.execute("""
        CREATE TABLE fact_ranking_empresarial (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            ruc               TEXT REFERENCES dim_empresas(ruc),
            id_geografia      INTEGER REFERENCES dim_geografia(id_geografia),
            anio              INTEGER,
            ingresos_totales  REAL,
            activos           REAL,
            patrimonio        REAL,
            utilidad_neta     REAL,
            ciiu_n6           TEXT REFERENCES dim_ciiu(ciiu)
        )
    """)
    cur.execute("""
        INSERT INTO fact_ranking_empresarial
        (id, ruc, id_geografia, anio, ingresos_totales, activos, patrimonio, utilidad_neta, ciiu_n6)
        SELECT id, ruc, id_geografia, anio, ingresos_totales, activos, patrimonio, utilidad_neta, ciiu_n6
        FROM fact_ranking_empresarial_old
    """)
    cur.execute("DROP TABLE fact_ranking_empresarial_old")
    cur.execute("SELECT COUNT(*) FROM fact_ranking_empresarial")
    print(f"  -> fact_ranking_empresarial reconstruida: {cur.fetchone()[0]} filas")
    # Se pierden los indices al recrear la tabla, los volvemos a crear
    cur.execute("CREATE INDEX IF NOT EXISTS ix_fact_ranking_geo ON fact_ranking_empresarial(id_geografia)")


def reconstruir_fact_vab(cur):
    print("\n--- Reconstruyendo fact_vab con FK a dim_ciiu ---")
    cur.execute("ALTER TABLE fact_vab RENAME TO fact_vab_old")
    cur.execute("""
        CREATE TABLE fact_vab (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            id_geografia   INTEGER REFERENCES dim_geografia(id_geografia),
            anio           INTEGER NOT NULL,
            ciiu           TEXT REFERENCES dim_ciiu(ciiu),
            vab_miles_usd  REAL
        )
    """)
    cur.execute("""
        INSERT INTO fact_vab (id, id_geografia, anio, ciiu, vab_miles_usd)
        SELECT id, id_geografia, anio, ciiu, vab_miles_usd
        FROM fact_vab_old
    """)
    cur.execute("DROP TABLE fact_vab_old")
    cur.execute("SELECT COUNT(*) FROM fact_vab")
    print(f"  -> fact_vab reconstruida: {cur.fetchone()[0]} filas")


if __name__ == '__main__':
    conn = sqlite3.connect(DB_PRINCIPAL)
    conn.execute("PRAGMA foreign_keys = OFF")
    cur = conn.cursor()

    try:
        # IMPORTANTE: ALTER TABLE ... RENAME reescribe automaticamente las
        # vistas que dependen de esa tabla para apuntar al nuevo nombre
        # temporal (ej. dim_empresas_old). Si no borramos las vistas antes,
        # quedan rotas cuando esa tabla _old se elimina. Las borramos aqui
        # y el usuario las vuelve a crear al final con verificar_vistas_gold.py
        cur.execute("SELECT name FROM sqlite_master WHERE type='view'")
        vistas_existentes = [r[0] for r in cur.fetchall()]
        print(f"Borrando {len(vistas_existentes)} vistas antes de reconstruir tablas: {vistas_existentes}")
        for v in vistas_existentes:
            cur.execute(f"DROP VIEW IF EXISTS {v}")

        reconstruir_dim_empresas(cur)
        reconstruir_fact_ranking(cur)
        reconstruir_fact_vab(cur)
        conn.commit()

        print("\n--- VERIFICACION FINAL ---")
        conn.execute("PRAGMA foreign_keys = ON")
        cur.execute("PRAGMA foreign_key_check")
        violaciones = cur.fetchall()
        print(f"Violaciones de FK: {len(violaciones)}")
        if violaciones:
            for v in violaciones[:10]:
                print("  ", v)

        print("\nFK de dim_ciiu formalizada en las 3 tablas.")
        print("IMPORTANTE: las vistas Gold se borraron y hay que recrearlas.")
        print("Corre ahora: python transform\\verificar_vistas_gold.py")
    except Exception as e:
        conn.rollback()
        print(f"\nERROR, se hizo rollback: {e}")
        raise
    finally:
        conn.close()
