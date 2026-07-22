import oracledb
import pandas as pd

dsn_tns = oracledb.makedsn("localhost", 1521, service_name="XEPDB1")
conn = oracledb.connect(user="ADMIN", password="pwdadmin", dsn=dsn_tns)

query = """
    SELECT DATOS_JSON FROM TAB_CONSOLIDADO
    WHERE INDICADOR = 'SUPERCIAS_DIRECTORIO' AND ROWNUM <= 1
"""
df = pd.read_sql(query, con=conn)
conn.close()

valor = df['DATOS_JSON'].iloc[0]
print("=== Texto crudo (tal como llega de Oracle) ===")
print(valor[:300])

print("\n=== Intento de reversion: encode('cp437').decode('utf-8') ===")
try:
    corregido = valor.encode('cp437').decode('utf-8')
    print(corregido[:300])
except Exception as e:
    print(f"FALLO: {e}")

print("\n=== Intento alternativo: encode('cp1252').decode('utf-8') (el que usa el fix actual) ===")
try:
    corregido2 = valor.encode('cp1252').decode('utf-8')
    print(corregido2[:300])
except Exception as e:
    print(f"FALLO: {e}")
