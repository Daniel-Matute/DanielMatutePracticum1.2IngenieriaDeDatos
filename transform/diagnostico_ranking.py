import oracledb
import json
import pandas as pd

dsn_tns = oracledb.makedsn("localhost", 1521, service_name="XEPDB1")
conn = oracledb.connect(user="ADMIN", password="pwdadmin", dsn=dsn_tns)

query = "SELECT DATOS_JSON FROM TAB_CONSOLIDADO WHERE INDICADOR = 'SUPERCIAS_RANKING' AND ROWNUM <= 5"
df_crudo = pd.read_sql(query, con=conn)
conn.close()

print("=== Tipo de dato crudo (antes de tocar nada) ===")
print(type(df_crudo['DATOS_JSON'].iloc[0]))
print()

print("=== Valor crudo, primeros 500 caracteres ===")
print(str(df_crudo['DATOS_JSON'].iloc[0])[:500])
print()

# Replicamos exactamente lo que hace el pipeline
df_crudo['DATOS_JSON'] = df_crudo['DATOS_JSON'].apply(lambda x: json.loads(x) if isinstance(x, str) else x)

print("=== Tipo de dato DESPUES del json.loads condicional ===")
print(type(df_crudo['DATOS_JSON'].iloc[0]))
print()

print("=== Contenido ya parseado (primer registro) ===")
print(df_crudo['DATOS_JSON'].iloc[0])
print()

# Intentamos el normalize tal cual lo hace el pipeline
try:
    df = pd.json_normalize(df_crudo['DATOS_JSON'])
    print("=== Resultado de pd.json_normalize ===")
    print("Shape:", df.shape)
    print("Columnas:", df.columns.tolist())
except Exception as e:
    print("=== FALLO pd.json_normalize ===")
    print(f"Tipo de error: {type(e).__name__}")
    print(f"Mensaje: {e}")
