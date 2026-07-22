"""
migrar_modelo_relacional.py
============================
Semana 4 - Modelo relacional y vistas Gold.

Las Semanas 2 y 3 cargaron cada fuente como una tabla plana
independiente (to_sql con nombres finales, sin llaves foráneas).
Este script:

  1. Renombra esas tablas planas a stg_<nombre> (staging), para no
     perder los datos ya limpios.
  2. Ejecuta create_tables.sql para crear el modelo relacional real
     (dim_geografia, dim_tiempo + tablas de hechos con FK).
  3. Migra los datos desde staging hacia el modelo final, resolviendo
     las llaves foráneas de geografía y tiempo.

Se puede ejecutar varias veces: es idempotente (limpia y reconstruye
las tablas finales en cada corrida).
"""

import sqlite3
import unicodedata
import pandas as pd

RUTA_DB = "pipeline_utpl.db"
RUTA_DDL = "create_tables.sql"

TABLAS_A_ARCHIVAR = [
    "fact_macro_anual", "fact_pib_nominal", "fact_indicadores_diarios",
    "fact_iee", "fact_vab", "dim_geografia", "fact_empleo",
    "fact_ocupacion_censo", "fact_ranking_empresarial", "fact_oferta_academica",
    "dim_empresas", "dim_ciiu",
]


def normalizar_geo(texto):
    """Mayúsculas y sin tildes, para poder cruzar VAB / Supercías / MINEDUC /
    Censo aunque cada fuente entregue provincia/cantón con formato distinto
    (ej. 'Manabí' vs 'MANABI' vs 'Manabi')."""
    if texto is None:
        return None
    texto = str(texto).strip().upper()
    texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("utf-8")
    return texto


VISTAS_GOLD = [
    "gold_pib_tendencia", "gold_empleo_tendencia", "gold_petroleo_30dias",
    "gold_empresas_provincia", "gold_bachilleres_vs_empresas",
]


def eliminar_vistas_gold(conn):
    """Elimina las vistas Gold ANTES de tocar las tablas de las que dependen.
    Necesario porque SQLite valida las vistas dependientes al hacer
    ALTER TABLE ... RENAME, y si una corrida previa de bce.py/inec.py/etc.
    volvió a dejar una tabla en su forma plana (Semana 2/3), las vistas
    Gold (que esperan el esquema final) quedan con columnas inexistentes
    y el RENAME falla. gold_views.sql las vuelve a crear al final del
    pipeline, así que borrarlas aquí es seguro e idempotente."""
    cur = conn.cursor()
    for vista in VISTAS_GOLD:
        cur.execute(f"DROP VIEW IF EXISTS {vista}")
    conn.commit()
    print("[*] Vistas Gold previas eliminadas (se recrean al correr gold_views.sql)")


def archivar_tablas_planas(conn):
    """Mueve las tablas de Semana 2/3 a stg_<nombre> si todavía no se
    archivaron (evita duplicar el prefijo en corridas repetidas)."""
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    existentes = {r[0] for r in cur.fetchall()}
    for tabla in TABLAS_A_ARCHIVAR:
        if tabla in existentes and f"stg_{tabla}" not in existentes:
            cur.execute(f"ALTER TABLE {tabla} RENAME TO stg_{tabla}")
            print(f"  [archivado] {tabla} -> stg_{tabla}")
    conn.commit()


def crear_esquema(conn):
    with open(RUTA_DDL, encoding="utf-8") as f:
        ddl = f.read()
    conn.executescript(ddl)
    conn.commit()
    print("[*] Esquema relacional creado desde create_tables.sql")


def construir_dim_geografia(conn):
    """Reúne provincia/cantón de las 3 fuentes que tienen geografía y
    conserva los códigos DPA cuando MINEDUC los aporta."""
    frames = []

    df_vab = pd.read_sql("SELECT provincia, canton FROM stg_fact_vab", conn)
    frames.append(df_vab)

    df_emp = pd.read_sql("SELECT provincia, canton FROM dim_empresas", conn)
    frames.append(df_emp)

    df_edu = pd.read_sql(
        "SELECT provincia, cod_provincia, canton, cod_canton FROM stg_fact_oferta_academica", conn
    )
    frames.append(df_edu[["provincia", "canton"]])

    todas = pd.concat(frames, ignore_index=True)
    todas["provincia"] = todas["provincia"].apply(normalizar_geo)
    todas["canton"] = todas["canton"].apply(normalizar_geo)
    todas = todas.dropna(subset=["provincia"]).drop_duplicates(subset=["provincia", "canton"])

    # Códigos DPA: solo MINEDUC los trae. Se anexan por coincidencia de
    # provincia+cantón normalizados.
    df_edu["provincia_norm"] = df_edu["provincia"].apply(normalizar_geo)
    df_edu["canton_norm"] = df_edu["canton"].apply(normalizar_geo)
    codigos = df_edu.drop_duplicates(subset=["provincia_norm", "canton_norm"])[
        ["provincia_norm", "canton_norm", "cod_provincia", "cod_canton"]
    ]

    todas = todas.merge(
        codigos, left_on=["provincia", "canton"], right_on=["provincia_norm", "canton_norm"], how="left"
    ).drop(columns=["provincia_norm", "canton_norm"])

    todas = todas.reset_index(drop=True)
    todas.insert(0, "id_geografia", todas.index + 1)
    todas.to_sql("dim_geografia", conn, if_exists="append", index=False)
    print(f"[*] dim_geografia: {len(todas)} combinaciones provincia/cantón")
    return todas


def construir_dim_tiempo(conn):
    """Series anuales de PIB real y PIB nominal per cápita -> fechas 1-ene."""
    anios_real = pd.read_sql("SELECT DISTINCT anio FROM stg_fact_macro_anual", conn)["anio"]
    anios_nominal = pd.read_sql("SELECT DISTINCT periodo AS anio FROM stg_fact_pib_nominal", conn)["anio"]
    anios = sorted(set(anios_real) | set(anios_nominal))

    df = pd.DataFrame({"anio": anios})
    df["fecha"] = df["anio"].apply(lambda a: f"{a}-01-01")
    df["mes"] = 1
    df["trimestre"] = 1
    df = df[["fecha", "anio", "mes", "trimestre"]].reset_index(drop=True)
    df.insert(0, "id_tiempo", df.index + 1)
    df.to_sql("dim_tiempo", conn, if_exists="append", index=False)
    print(f"[*] dim_tiempo: {len(df)} años (1-ene de cada año)")
    return df


def migrar_fact_macro_anual(conn, dim_tiempo):
    real = pd.read_sql("SELECT * FROM stg_fact_macro_anual", conn)
    nominal = pd.read_sql("SELECT periodo AS anio, pib_percapita_nominal_usd FROM stg_fact_pib_nominal", conn)

    df = real.merge(nominal, on="anio", how="left")
    df = df.merge(dim_tiempo[["id_tiempo", "anio"]], on="anio", how="left")

    final = df[["id_tiempo", "pib_real_musd", "poblacion_miles", "pib_percapita_nominal_usd", "variacion_pib_pct"]]
    final.to_sql("fact_macro_anual", conn, if_exists="append", index=False)
    print(f"[*] fact_macro_anual: {len(final)} filas (PIB real + PIB nominal fusionados por año)")


def migrar_fact_indicadores_diarios(conn):
    df = pd.read_sql("SELECT fecha, precio_petroleo_wti, riesgo_pais_pb FROM stg_fact_indicadores_diarios", conn)
    df.to_sql("fact_indicadores_diarios", conn, if_exists="append", index=False)
    print(f"[*] fact_indicadores_diarios: {len(df)} filas")


def migrar_fact_iee(conn):
    df = pd.read_sql("SELECT fecha, iee_global, comercio, construccion, manufactura FROM stg_fact_iee", conn)
    df.to_sql("fact_iee", conn, if_exists="append", index=False)
    print(f"[*] fact_iee: {len(df)} filas")


def migrar_fact_vab(conn, dim_geo):
    df = pd.read_sql("SELECT anio, provincia, canton, ciiu, vab_miles_usd FROM stg_fact_vab", conn)
    df["provincia_norm"] = df["provincia"].apply(normalizar_geo)
    df["canton_norm"] = df["canton"].apply(normalizar_geo)
    df = df.merge(
        dim_geo[["id_geografia", "provincia", "canton"]],
        left_on=["provincia_norm", "canton_norm"], right_on=["provincia", "canton"], how="left",
        suffixes=("", "_geo"),
    )
    sin_match = df["id_geografia"].isna().sum()
    if sin_match:
        print(f" [!] fact_vab: {sin_match} filas sin coincidencia geográfica (quedan con id_geografia NULL)")
    final = df[["id_geografia", "anio", "ciiu", "vab_miles_usd"]]
    final.to_sql("fact_vab", conn, if_exists="append", index=False)
    print(f"[*] fact_vab: {len(final)} filas")


def migrar_fact_empleo(conn):
    """Pivotea el formato largo de la Semana 3 (una fila por área) de
    vuelta al formato ancho que pide el DDL del reto (una fila por
    indicador-período, con nacional/urbana/rural como columnas)."""
    df = pd.read_sql("SELECT periodo, anio, indicador, area, valor FROM stg_fact_empleo", conn)
    ancho = df.pivot_table(
        index=["periodo", "anio", "indicador"], columns="area", values="valor", aggfunc="first"
    ).reset_index()
    ancho = ancho.rename(columns={"nacional": "total_nacional", "urbana": "total_urbana", "rural": "total_rural"})
    for col in ["total_nacional", "total_urbana", "total_rural"]:
        if col not in ancho.columns:
            ancho[col] = None
    final = ancho[["periodo", "anio", "indicador", "total_nacional", "total_urbana", "total_rural"]]
    final.to_sql("fact_empleo", conn, if_exists="append", index=False)
    print(f"[*] fact_empleo: {len(final)} filas (repivotadas a formato ancho)")


def migrar_fact_ocupacion_censo(conn, dim_geo):
    df = pd.read_sql(
        "SELECT provincia, canton, sexo, grupo_edad, rama_actividad, personas_ocupadas FROM stg_fact_ocupacion_censo",
        conn,
    )
    df["provincia_norm"] = df["provincia"].apply(normalizar_geo)
    df["canton_norm"] = df["canton"].apply(normalizar_geo)
    df = df.merge(
        dim_geo[["id_geografia", "provincia", "canton"]],
        left_on=["provincia_norm", "canton_norm"], right_on=["provincia", "canton"], how="left",
    )
    final = df[["id_geografia", "sexo", "grupo_edad", "rama_actividad", "personas_ocupadas"]]
    final.to_sql("fact_ocupacion_censo", conn, if_exists="append", index=False)
    print(f"[*] fact_ocupacion_censo: {len(final)} filas")


def migrar_dim_empresas(conn):
    df = pd.read_sql(
        "SELECT expediente, ruc, nombre, situacion_legal, provincia, canton, ciiu_n1, ciiu_n6, "
        "fecha_constitucion, ultimo_balance FROM stg_dim_empresas",
        conn,
    )
    df = df.dropna(subset=["ruc"]).drop_duplicates(subset=["ruc"])
    df.to_sql("dim_empresas", conn, if_exists="append", index=False)
    print(f"[*] dim_empresas: {len(df)} filas (con RUC como llave primaria)")


def migrar_dim_ciiu(conn):
    df = pd.read_sql("SELECT ciiu, descripcion FROM stg_dim_ciiu", conn)
    df = df.dropna(subset=["ciiu"]).drop_duplicates(subset=["ciiu"])
    df.to_sql("dim_ciiu", conn, if_exists="append", index=False)
    print(f"[*] dim_ciiu: {len(df)} filas")


def migrar_fact_ranking_empresarial(conn, dim_geo):
    df = pd.read_sql(
        "SELECT ruc, provincia, anio, ingresos_totales, activos, patrimonio, utilidad_neta, ciiu_n6 "
        "FROM stg_fact_ranking_empresarial",
        conn,
    )
    df["provincia_norm"] = df["provincia"].apply(normalizar_geo)
    df = df.merge(
        dim_geo[["id_geografia", "provincia"]].drop_duplicates(subset=["provincia"]),
        left_on="provincia_norm", right_on="provincia", how="left",
    )
    final = df[["ruc", "id_geografia", "anio", "ingresos_totales", "activos", "patrimonio", "utilidad_neta", "ciiu_n6"]]
    final.to_sql("fact_ranking_empresarial", conn, if_exists="append", index=False)
    print(f"[*] fact_ranking_empresarial: {len(final)} filas")


def migrar_fact_oferta_academica(conn, dim_geo):
    df = pd.read_sql(
        "SELECT provincia, canton, anio_lectivo, amie, nombre_institucion, sostenimiento, "
        "total_estudiantes, bachillerato, bachilleres_3er_anio FROM stg_fact_oferta_academica",
        conn,
    )
    df["provincia_norm"] = df["provincia"].apply(normalizar_geo)
    df["canton_norm"] = df["canton"].apply(normalizar_geo)
    df = df.merge(
        dim_geo[["id_geografia", "provincia", "canton"]],
        left_on=["provincia_norm", "canton_norm"], right_on=["provincia", "canton"], how="left",
    )
    final = df[[
        "id_geografia", "anio_lectivo", "amie", "nombre_institucion", "sostenimiento",
        "total_estudiantes", "bachillerato", "bachilleres_3er_anio",
    ]]
    final.to_sql("fact_oferta_academica", conn, if_exists="append", index=False)
    print(f"[*] fact_oferta_academica: {len(final)} filas")


def main():
    conn = sqlite3.connect(RUTA_DB)
    try:
        print("Paso 0: eliminar vistas Gold previas (si existen)...")
        eliminar_vistas_gold(conn)

        print("\nPaso 1: archivar tablas planas de Semana 2/3...")
        archivar_tablas_planas(conn)

        print("\nPaso 2: crear modelo relacional (create_tables.sql)...")
        crear_esquema(conn)

        print("\nPaso 3: reconstruir dimensiones...")
        dim_geo = construir_dim_geografia(conn)
        dim_tiempo = construir_dim_tiempo(conn)

        print("\nPaso 4: migrar tablas de hechos...")
        migrar_fact_macro_anual(conn, dim_tiempo)
        migrar_fact_indicadores_diarios(conn)
        migrar_fact_iee(conn)
        migrar_fact_vab(conn, dim_geo)
        migrar_fact_empleo(conn)
        migrar_fact_ocupacion_censo(conn, dim_geo)
        migrar_dim_empresas(conn)
        migrar_dim_ciiu(conn)
        migrar_fact_ranking_empresarial(conn, dim_geo)
        migrar_fact_oferta_academica(conn, dim_geo)

        conn.commit()
        print("\n¡Modelo relacional (Semana 4) construido y poblado correctamente!")
    except Exception as e:
        conn.rollback()
        print(f"Ocurrió un error: {e}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
