import sqlite3

def revisar(db_path, tabla, columna, filtro=""):
    print(f"\n--- {db_path} : {tabla}.{columna} ---")
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    query = f"SELECT {columna} FROM {tabla} WHERE {columna} LIKE '%├%' OR {columna} LIKE '%Ã%' {filtro} LIMIT 5"
    try:
        cur.execute(query)
        filas = cur.fetchall()
        if filas:
            print(f"  ENCONTRADAS {len(filas)} filas con posible corrupcion visible:")
            for f in filas:
                print(f"    {f}")
        else:
            print("  Sin corrupcion visible (0 filas con ├ o Ã)")
    except Exception as e:
        print(f"  Error: {e}")
    conn.close()

revisar('pipeline_utpl.db', 'dim_empresas', 'nombre')
revisar('pipeline_utpl.db', 'dim_empresas', 'situacion_legal')
revisar('macroentorno_silver_RPA.db', 'fact_directorio_companias', 'nombre')

# Muestra de nombres con ñ/tildes reales, para ver si se ven bien
print("\n--- Muestra de empresas con 'Ñ' o tildes en el nombre (dim_empresas) ---")
conn = sqlite3.connect('pipeline_utpl.db')
cur = conn.cursor()
cur.execute("""
    SELECT nombre FROM dim_empresas
    WHERE nombre LIKE '%Ñ%' OR nombre LIKE '%Ó%' OR nombre LIKE '%Á%' OR nombre LIKE '%É%' OR nombre LIKE '%Í%'
    LIMIT 10
""")
for r in cur.fetchall():
    print(f"   {r[0]}")
conn.close()
