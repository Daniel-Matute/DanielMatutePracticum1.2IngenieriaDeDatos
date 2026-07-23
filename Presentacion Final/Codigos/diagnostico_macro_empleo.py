import oracledb
import json
import pandas as pd

dsn_tns = oracledb.makedsn("localhost", 1521, service_name="XEPDB1")
conn = oracledb.connect(user="ADMIN", password="pwdadmin", dsn=dsn_tns)

print("="*70)
print("  INEC_ENEMDU_POBLACIONES - estructura real del JSON")
print("="*70)
query = "SELECT DATOS_JSON FROM TAB_CONSOLIDADO WHERE INDICADOR = 'INEC_ENEMDU_POBLACIONES' AND ROWNUM <= 3"
df = pd.read_sql(query, con=conn)
for i, val in enumerate(df['DATOS_JSON']):
    parsed = json.loads(val) if isinstance(val, str) else val
    print(f"\n--- registro {i} ---")
    print(json.dumps(parsed, indent=2, ensure_ascii=False))

print("\n" + "="*70)
print("  PIB_NOMINAL_PER_CAPITA - estructura real del JSON")
print("="*70)
query2 = "SELECT DATOS_JSON FROM TAB_CONSOLIDADO WHERE INDICADOR = 'PIB_NOMINAL_PER_CAPITA' AND ROWNUM <= 3"
df2 = pd.read_sql(query2, con=conn)
for i, val in enumerate(df2['DATOS_JSON']):
    parsed = json.loads(val) if isinstance(val, str) else val
    print(f"\n--- registro {i} ---")
    print(json.dumps(parsed, indent=2, ensure_ascii=False))

# Rango de anios que cubre el indicador nominal, para comparar contra
# el histórico actual (que solo tiene nominal en 25 de 60 anios)
print("\n" + "="*70)
print("  Cuantos anios distintos trae PIB_NOMINAL_PER_CAPITA en total")
print("="*70)
query3 = "SELECT COUNT(*) FROM TAB_CONSOLIDADO WHERE INDICADOR = 'PIB_NOMINAL_PER_CAPITA'"
df3 = pd.read_sql(query3, con=conn)
print(f"Total filas del indicador: {df3.iloc[0,0]}")

conn.close()
