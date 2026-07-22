import sqlite3

conn = sqlite3.connect('macroentorno_silver_RPA.db')
cur = conn.cursor()

print("="*70)
print("  fact_macro_anual - verificar pib_pc_nominal_usd")
print("="*70)
cur.execute("SELECT anio_fiscal, pib_pc_real_usd, pib_pc_nominal_usd FROM fact_macro_anual ORDER BY anio_fiscal LIMIT 5")
for row in cur.fetchall():
    print(f"   {row}")

cur.execute("SELECT COUNT(*) FROM fact_macro_anual WHERE pib_pc_nominal_usd IS NULL")
nulos = cur.fetchone()[0]
cur.execute("SELECT COUNT(*) FROM fact_macro_anual")
total = cur.fetchone()[0]
print(f"\n   Filas con pib_pc_nominal_usd NULL: {nulos} de {total}")

print("\n" + "="*70)
print("  fact_empleo_enemdu - verificar total_urbana / total_rural")
print("="*70)
cur.execute("SELECT periodo, anio, indicador, total_nacional, total_urbana, total_rural FROM fact_empleo_enemdu LIMIT 5")
for row in cur.fetchall():
    print(f"   {row}")

cur.execute("SELECT COUNT(*) FROM fact_empleo_enemdu WHERE total_urbana IS NULL OR total_rural IS NULL")
nulos2 = cur.fetchone()[0]
cur.execute("SELECT COUNT(*) FROM fact_empleo_enemdu")
total2 = cur.fetchone()[0]
print(f"\n   Filas con total_urbana o total_rural NULL: {nulos2} de {total2}")

print("\n" + "="*70)
print("  Periodos que cubre fact_empleo_enemdu (RPA) vs fact_empleo (actual)")
print("="*70)
cur.execute("SELECT MIN(anio), MAX(anio), COUNT(DISTINCT anio) FROM fact_empleo_enemdu")
print(f"   RPA: {cur.fetchone()}")

conn.close()

conn2 = sqlite3.connect('pipeline_utpl.db')
cur2 = conn2.cursor()
cur2.execute("SELECT MIN(anio), MAX(anio), COUNT(DISTINCT anio) FROM fact_empleo")
print(f"   Actual (pipeline_utpl.db): {cur2.fetchone()}")
conn2.close()
