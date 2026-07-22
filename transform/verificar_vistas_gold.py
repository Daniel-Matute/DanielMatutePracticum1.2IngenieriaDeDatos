"""
verificar_vistas_gold.py
========================
Ejecuta gold_views.sql y muestra una muestra de cada vista, para
confirmar que producen resultados correctos ANTES de conectar Power BI
(tal como pide el entregable de la Semana 4).
"""

import sqlite3
import pandas as pd

RUTA_DB = "pipeline_utpl.db"
RUTA_VIEWS = "gold_views.sql"

VISTAS = [
    "gold_pib_tendencia",
    "gold_empleo_tendencia",
    "gold_petroleo_30dias",
    "gold_empresas_provincia",
    "gold_bachilleres_vs_empresas",
]


def main():
    conn = sqlite3.connect(RUTA_DB)
    try:
        with open(RUTA_VIEWS, encoding="utf-8") as f:
            conn.executescript(f.read())
        conn.commit()
        print("[*] Vistas Gold creadas/actualizadas desde gold_views.sql\n")

        for vista in VISTAS:
            print(f"===== {vista} =====")
            df = pd.read_sql(f"SELECT * FROM {vista}", conn)
            print(f"Filas: {len(df)}")
            print(df.head(8).to_string(index=False))
            print()
    except Exception as e:
        print(f"Ocurrió un error verificando las vistas: {e}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
