import oracledb
import pandas as pd

dsn_tns = oracledb.makedsn("localhost", 1521, service_name="XEPDB1")
conn = oracledb.connect(user="ADMIN", password="pwdadmin", dsn=dsn_tns)

query = """
    SELECT INDICADOR, COUNT(*) AS total
    FROM TAB_CONSOLIDADO
    GROUP BY INDICADOR
    ORDER BY total DESC
"""
df = pd.read_sql(query, con=conn)
conn.close()

pd.set_option('display.max_rows', None)
pd.set_option('display.max_colwidth', None)
print(df.to_string(index=False))
