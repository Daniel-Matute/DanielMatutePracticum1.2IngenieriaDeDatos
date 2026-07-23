import sqlite3

conn = sqlite3.connect('pipeline_utpl.db')
cur = conn.cursor()

def reporte(tabla, columna):
    cur.execute(f"SELECT COUNT(*) FROM {tabla} WHERE {columna} IS NOT NULL AND TRIM({columna}) != ''")
    total = cur.fetchone()[0]
    cur.execute(f"""
        SELECT COUNT(*) FROM {tabla}
        WHERE {columna} IS NOT NULL AND TRIM({columna}) != ''
        AND {columna} NOT IN (SELECT ciiu FROM dim_ciiu)
    """)
    sin_match = cur.fetchone()[0]
    pct = (sin_match / total * 100) if total > 0 else 0
    print(f"{tabla}.{columna}: {sin_match} de {total} sin match en dim_ciiu ({pct:.3f}%)")
    return sin_match

print("="*70)
print("  Desajuste CIIU real, DESPUES de la integracion RPA")
print("="*70)
reporte('dim_empresas', 'ciiu_n1')
reporte('dim_empresas', 'ciiu_n6')
reporte('fact_ranking_empresarial', 'ciiu_n6')
reporte('fact_vab', 'ciiu')

cur.execute("SELECT COUNT(*) FROM dim_ciiu")
print(f"\nTotal de codigos en dim_ciiu (catalogo): {cur.fetchone()[0]}")

# Muestra de codigos que no calzan, para ver si es un patron reconocible
print("\n--- Muestra de ciiu_n6 en dim_empresas que NO estan en dim_ciiu ---")
cur.execute("""
    SELECT DISTINCT ciiu_n6 FROM dim_empresas
    WHERE ciiu_n6 IS NOT NULL AND TRIM(ciiu_n6) != ''
    AND ciiu_n6 NOT IN (SELECT ciiu FROM dim_ciiu)
    LIMIT 10
""")
for r in cur.fetchall():
    print(f"   {r[0]}")

conn.close()
