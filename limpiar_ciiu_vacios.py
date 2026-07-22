import sqlite3

conn = sqlite3.connect('pipeline_utpl.db')
cur = conn.cursor()

print("--- Convirtiendo ciiu vacio ('') a NULL en las 3 tablas ---")

cur.execute("UPDATE dim_empresas SET ciiu_n1 = NULL WHERE TRIM(ciiu_n1) = ''")
print(f"  dim_empresas.ciiu_n1: {cur.rowcount} filas limpiadas")

cur.execute("UPDATE dim_empresas SET ciiu_n6 = NULL WHERE TRIM(ciiu_n6) = ''")
print(f"  dim_empresas.ciiu_n6: {cur.rowcount} filas limpiadas")

cur.execute("UPDATE fact_ranking_empresarial SET ciiu_n6 = NULL WHERE TRIM(ciiu_n6) = ''")
print(f"  fact_ranking_empresarial.ciiu_n6: {cur.rowcount} filas limpiadas")

cur.execute("UPDATE fact_vab SET ciiu = NULL WHERE TRIM(ciiu) = ''")
print(f"  fact_vab.ciiu: {cur.rowcount} filas limpiadas")

conn.commit()

print("\n--- VERIFICACION FINAL ---")
cur.execute("PRAGMA foreign_key_check")
violaciones = cur.fetchall()
print(f"Violaciones de FK: {len(violaciones)}")
if violaciones:
    for v in violaciones[:20]:
        print("  ", v)

conn.close()
