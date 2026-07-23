import sqlite3

print("=== Periodos en el HISTORICO actual (fact_oferta_academica, modelo dimensional) ===")
conn_ppal = sqlite3.connect('pipeline_utpl.db')
cur = conn_ppal.cursor()
cur.execute("""
    SELECT anio_lectivo, COUNT(*) 
    FROM fact_oferta_academica 
    GROUP BY anio_lectivo 
    ORDER BY anio_lectivo
""")
for anio, n in cur.fetchall():
    print(f"   {anio}: {n} filas")
conn_ppal.close()

print("\n=== Periodos en RPA (fact_mineduc_amie) ===")
conn_rpa = sqlite3.connect('macroentorno_silver_RPA.db')
cur = conn_rpa.cursor()
cur.execute("""
    SELECT periodo_lectivo, anio_base, COUNT(*) 
    FROM fact_mineduc_amie 
    GROUP BY periodo_lectivo, anio_base 
    ORDER BY anio_base
""")
for periodo, anio_base, n in cur.fetchall():
    print(f"   periodo_lectivo={periodo}  anio_base={anio_base}: {n} filas")

print("\n=== Muestra de provincia/canton en RPA (para chequear formato vs dim_geografia) ===")
cur.execute("""
    SELECT DISTINCT institucion_provincia, institucion_canton 
    FROM fact_mineduc_amie 
    LIMIT 10
""")
for prov, cant in cur.fetchall():
    print(f"   provincia='{prov}'  canton='{cant}'")
conn_rpa.close()

print("\n=== Muestra de provincia/canton en dim_geografia (para comparar formato) ===")
conn_ppal = sqlite3.connect('pipeline_utpl.db')
cur = conn_ppal.cursor()
cur.execute("SELECT DISTINCT provincia, canton FROM dim_geografia LIMIT 10")
for prov, cant in cur.fetchall():
    print(f"   provincia='{prov}'  canton='{cant}'")
conn_ppal.close()
