import sqlite3

conn = sqlite3.connect('macroentorno_silver_RPA.db')
cur = conn.cursor()

cur.execute("SELECT COUNT(*) FROM fact_directorio_companias")
total = cur.fetchone()[0]
print(f"Total filas: {total}")

cur.execute("SELECT COUNT(*) FROM fact_directorio_companias WHERE ruc IS NULL OR TRIM(ruc) = ''")
vacios = cur.fetchone()[0]
print(f"Filas con ruc vacio/NULL: {vacios} ({vacios/total*100:.2f}%)")

cur.execute("""
    SELECT ruc, COUNT(*) as n
    FROM fact_directorio_companias
    WHERE ruc IS NOT NULL AND TRIM(ruc) != ''
    GROUP BY ruc
    HAVING n > 1
    ORDER BY n DESC
    LIMIT 15
""")
dups = cur.fetchall()
print(f"\nRUCs no vacios que se repiten (top 15):")
for ruc, n in dups:
    print(f"   {ruc}: {n} veces")

cur.execute("""
    SELECT COUNT(*) FROM (
        SELECT ruc FROM fact_directorio_companias
        WHERE ruc IS NOT NULL AND TRIM(ruc) != ''
        GROUP BY ruc HAVING COUNT(*) > 1
    )
""")
n_rucs_duplicados = cur.fetchone()[0]
print(f"\nTotal de RUCs distintos (no vacios) que aparecen mas de una vez: {n_rucs_duplicados}")

conn.close()
