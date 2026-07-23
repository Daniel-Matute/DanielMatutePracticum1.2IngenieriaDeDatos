import sqlite3

def inspeccionar(db_path, etiqueta):
    print(f"\n{'='*70}")
    print(f"  {etiqueta}: {db_path}")
    print('='*70)
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tablas = [r[0] for r in cur.fetchall()]

    for t in tablas:
        cur.execute(f"SELECT COUNT(*) FROM {t}")
        n = cur.fetchone()[0]
        cur.execute(f"PRAGMA table_info({t})")
        cols = cur.fetchall()
        print(f"\n-- {t} ({n} filas) --")
        for c in cols:
            # c = (cid, name, type, notnull, dflt_value, pk)
            print(f"   {c[1]:35s} {c[2]}")
    conn.close()

# AJUSTA LAS RUTAS SI ES NECESARIO (corre este script desde la raíz del proyecto,
# donde tienes ambos archivos .db)
inspeccionar('macroentorno_silver_RPA.db', 'BASE SILVER RPA (plana, sin FK)')
inspeccionar('pipeline_utpl.db', 'BASE PRINCIPAL (modelo dimensional con FK)')
