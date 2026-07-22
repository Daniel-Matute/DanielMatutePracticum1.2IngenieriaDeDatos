"""
integrar_rpa_macro_empleo.py
==============================
Dos operaciones independientes:

1) fact_macro_anual: REEMPLAZO. RPA ahora trae PIB nominal completo para
   los 60 anios (antes solo 25/60 tenian nominal, el resto quedaba NULL).
   Mismo grano anual, sin conflicto de periodos -> reemplazo directo.

2) fact_empleo_poblacion: TABLA NUEVA. El empleo de RPA (INEC_ENEMDU_POBLACIONES)
   trae CONTEOS DE PERSONAS, no tasas/porcentajes como fact_empleo actual.
   Son unidades distintas (no se puede convertir a tasa sin el dato de PEA,
   que no viene en este JSON), asi que se guardan aparte, sin tocar
   fact_empleo. Decision confirmada: NO mezclar.
"""
import sqlite3

DB_PRINCIPAL = 'pipeline_utpl.db'
DB_RPA = 'macroentorno_silver_RPA.db'


def actualizar_pib_nominal(conn_rpa, conn_ppal):
    print("\n--- Actualizando fact_macro_anual (PIB nominal completo, RPA) ---")
    cur_rpa = conn_rpa.cursor()
    cur_rpa.execute("""
        SELECT anio_fiscal, pib_real_millones, poblacion_total,
               pib_pc_nominal_usd, tasa_variacion_anual
        FROM fact_macro_anual
    """)
    filas_rpa = cur_rpa.fetchall()
    print(f"  Leidas {len(filas_rpa)} filas de fact_macro_anual (RPA)")

    cur_ppal = conn_ppal.cursor()
    cur_ppal.execute("SELECT id_tiempo, anio FROM dim_tiempo")
    mapa_anio = {anio: id_t for id_t, anio in cur_ppal.fetchall()}

    actualizadas = 0
    sin_mapeo = 0
    for anio_fiscal, pib_real_mill, poblacion_total, pib_nominal, variacion in filas_rpa:
        id_tiempo = mapa_anio.get(anio_fiscal)
        if id_tiempo is None:
            sin_mapeo += 1
            continue

        poblacion_miles = poblacion_total / 1000.0 if poblacion_total is not None else None

        cur_ppal.execute("""
            UPDATE fact_macro_anual
            SET pib_real_musd = ?,
                poblacion_miles = ?,
                pib_percapita_nominal_usd = ?,
                variacion_pib_pct = ?
            WHERE id_tiempo = ?
        """, (pib_real_mill, poblacion_miles, pib_nominal, variacion, id_tiempo))
        actualizadas += cur_ppal.rowcount

    conn_ppal.commit()
    print(f"  -> Filas actualizadas: {actualizadas}")
    print(f"  -> Anios sin mapeo en dim_tiempo: {sin_mapeo}")

    cur_ppal.execute("SELECT COUNT(*) FROM fact_macro_anual WHERE pib_percapita_nominal_usd IS NULL")
    nulos = cur_ppal.fetchone()[0]
    print(f"  -> fact_macro_anual: filas con pib_percapita_nominal_usd NULL ahora: {nulos} (antes: 35)")


def crear_tabla_empleo_poblacion(conn_rpa, conn_ppal):
    print("\n--- Creando fact_empleo_poblacion (conteos RPA, tabla nueva) ---")
    cur_ppal = conn_ppal.cursor()

    cur_ppal.execute("""
        CREATE TABLE IF NOT EXISTS fact_empleo_poblacion (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            anio INTEGER NOT NULL,
            periodo TEXT NOT NULL,
            indicador TEXT NOT NULL,
            total_nacional INTEGER,
            total_urbana INTEGER,
            total_rural INTEGER
        )
    """)

    # Idempotencia: si ya se corrio antes, limpiar antes de reinsertar
    cur_ppal.execute("DELETE FROM fact_empleo_poblacion")

    cur_rpa = conn_rpa.cursor()
    cur_rpa.execute("""
        SELECT anio, periodo, indicador, total_nacional, total_urbana, total_rural
        FROM fact_empleo_enemdu
    """)
    filas = cur_rpa.fetchall()
    print(f"  Leidas {len(filas)} filas de fact_empleo_enemdu (RPA)")

    cur_ppal.executemany("""
        INSERT INTO fact_empleo_poblacion
        (anio, periodo, indicador, total_nacional, total_urbana, total_rural)
        VALUES (?, ?, ?, ?, ?, ?)
    """, filas)
    conn_ppal.commit()

    cur_ppal.execute("SELECT COUNT(*) FROM fact_empleo_poblacion")
    total = cur_ppal.fetchone()[0]
    print(f"  -> fact_empleo_poblacion creada con {total} filas")
    print(f"     (nota: NO tiene FK a dim_geografia porque es a nivel nacional,")
    print(f"      igual que fact_empleo actual. Coexiste con fact_empleo sin tocarla.)")


if __name__ == '__main__':
    conn_rpa = sqlite3.connect(DB_RPA)
    conn_ppal = sqlite3.connect(DB_PRINCIPAL)

    try:
        actualizar_pib_nominal(conn_rpa, conn_ppal)
        crear_tabla_empleo_poblacion(conn_rpa, conn_ppal)

        print("\n--- VERIFICACION FINAL ---")
        cur = conn_ppal.cursor()
        cur.execute("PRAGMA foreign_key_check")
        violaciones = cur.fetchall()
        print(f"Violaciones de FK: {len(violaciones)}")

        print("\nIntegracion de Macro y Empleo completada.")
    finally:
        conn_rpa.close()
        conn_ppal.close()
