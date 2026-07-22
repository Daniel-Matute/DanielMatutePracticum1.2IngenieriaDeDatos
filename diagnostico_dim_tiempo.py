import sqlite3
conn = sqlite3.connect('pipeline_utpl.db')
cur = conn.cursor()
cur.execute("SELECT id_tiempo, anio, mes, trimestre FROM dim_tiempo ORDER BY anio LIMIT 5")
for r in cur.fetchall():
    print(r)
cur.execute("SELECT COUNT(*), COUNT(DISTINCT anio) FROM dim_tiempo")
print("Total filas, anios distintos:", cur.fetchone())
conn.close()
