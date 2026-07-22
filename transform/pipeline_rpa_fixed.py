import sqlite3
import json
import oracledb
import pandas as pd
import warnings
from prefect import task, flow

warnings.filterwarnings('ignore', 'pandas only supports SQLAlchemy connectable')

# AQUÍ ESTÁ EL CAMBIO: Nuevo nombre de la base de datos
DB_SQLITE = 'macroentorno_silver_RPA.db'


def obtener_conexion_oracle():
    # Oracle local (tu propia instalacion XE 21c), no la IP de un tercero.
    # Usuario ADMIN: es el esquema donde se cargo TAB_CONSOLIDADO
    # (tab_consolidado_export.sql + tab_consolidado_supercias.sql).
    dsn_tns = oracledb.makedsn("localhost", 1521, service_name="XEPDB1")
    return oracledb.connect(user="ADMIN", password="pwdadmin", dsn=dsn_tns)


def cargar_a_silver(df, nombre_tabla, modo='replace'):
    conexion = sqlite3.connect(DB_SQLITE)
    try:
        df.to_sql(nombre_tabla, conexion, if_exists=modo, index=False, chunksize=2000)
        print(f"  -> '{nombre_tabla}' guardada en SQLite ({len(df)} filas).")
    except Exception as e:
        print(f"  -> Error al cargar {nombre_tabla}: {e}")
    finally:
        conexion.close()


def arreglar_codificacion(texto):
    if not isinstance(texto, str):
        return texto
    try:
        return texto.encode('cp1252').decode('utf-8')
    except:
        reemplazos = {'Ã“': 'Ó', 'Ã³': 'ó', 'Ã‘': 'Ñ', 'Ã±': 'ñ', 'Ã\xad': 'í', 'Ã': 'Í', 'Ã¡': 'á', 'Ã': 'Á',
                      'Ã©': 'é', 'Ã‰': 'É', 'Ãº': 'ú', 'Ãš': 'Ú', 'Â': ''}
        for mal, bien in reemplazos.items():
            texto = texto.replace(mal, bien)
        return texto.strip()


# ===========================================================================
# BLOQUE 1: MACROECONOMÍA
# ===========================================================================
@task(name="Procesar PIB (Anual)")
def procesar_pib():
    print("Extrayendo PIB Real per cápita...")
    conn = obtener_conexion_oracle()
    query = "SELECT DATOS_JSON FROM TAB_CONSOLIDADO WHERE INDICADOR = 'PIB_REAL_PER_CAPITA'"
    df_crudo = pd.read_sql(query, con=conn)

    # FIX: antes solo se consultaba PIB_REAL_PER_CAPITA y el nominal quedaba
    # fuera del pipeline (dejaba pib_percapita_nominal_usd en NULL para todos
    # los anios que no venian del historico viejo de 25 filas). El indicador
    # PIB_NOMINAL_PER_CAPITA si existe en Oracle con cobertura completa
    # (60 anios, 1965 en adelante), asi que ahora se trae y se fusiona por
    # anio_fiscal, igual criterio que la fusion real+nominal de Semana 4.
    print("Extrayendo PIB Nominal per cápita...")
    query_nominal = "SELECT DATOS_JSON FROM TAB_CONSOLIDADO WHERE INDICADOR = 'PIB_NOMINAL_PER_CAPITA'"
    df_crudo_nominal = pd.read_sql(query_nominal, con=conn)
    conn.close()

    if not df_crudo.empty:
        df_crudo['DATOS_JSON'] = df_crudo['DATOS_JSON'].apply(lambda x: json.loads(x) if isinstance(x, str) else x)
        df_pib = pd.json_normalize(df_crudo['DATOS_JSON'])

        if not df_crudo_nominal.empty:
            df_crudo_nominal['DATOS_JSON'] = df_crudo_nominal['DATOS_JSON'].apply(
                lambda x: json.loads(x) if isinstance(x, str) else x)
            df_nominal = pd.json_normalize(df_crudo_nominal['DATOS_JSON'])
            # Solo nos interesa el pib per capita nominal, cruzado por anio_fiscal
            df_nominal = df_nominal[['anio_fiscal', 'pib_pc_nominal_usd']]
            df_pib = df_pib.merge(df_nominal, on='anio_fiscal', how='left')
        else:
            print("  -> Aviso: no se encontraron datos de PIB_NOMINAL_PER_CAPITA.")
            df_pib['pib_pc_nominal_usd'] = None

        cargar_a_silver(df_pib, 'fact_macro_anual')


@task(name="Procesar VAB (Provincias)")
def procesar_vab():
    print("Extrayendo VAB Provincial para el mapa...")
    conn = obtener_conexion_oracle()
    query = "SELECT DATOS_JSON FROM TAB_CONSOLIDADO WHERE INDICADOR = 'VAB_CANTONAL_CIIU'"
    df_crudo = pd.read_sql(query, con=conn)
    conn.close()

    if not df_crudo.empty:
        df_crudo['DATOS_JSON'] = df_crudo['DATOS_JSON'].apply(lambda x: json.loads(x) if isinstance(x, str) else x)
        df_vab = pd.json_normalize(df_crudo['DATOS_JSON'])

        df_vab.columns = (df_vab.columns.astype(str).str.replace('.', '_')
                          .str.lower().str.replace(' ', '_').str.replace('ó', 'o')
                          .str.replace('í', 'i').str.replace('á', 'a').str.replace('ñ', 'n'))

        for col in df_vab.select_dtypes(include=['object']).columns:
            df_vab[col] = df_vab[col].apply(arreglar_codificacion).astype(str)

        col_vab = next((c for c in df_vab.columns if 'vab' in c or 'valor' in c or 'usd' in c or 'miles' in c),
                       df_vab.columns[-1])
        df_vab = df_vab.rename(columns={col_vab: 'valor'})

        # AVISO: el campo "anio" de este indicador llega nulo desde el
        # origen (RPA todavia no lo esta poblando en TAB_CONSOLIDADO).
        # No es un bug de este script - repórtaselo al equipo de RPA.
        if df_vab['anio'].isna().all():
            print("  -> [AVISO] 'anio' llega vacío en VAB_CANTONAL_CIIU (falta en el dato de origen de RPA).")

        cargar_a_silver(df_vab, 'fact_vab_geografico')


# ===========================================================================
# BLOQUE 2: SUPERCIAS
# ===========================================================================
def procesar_supercias(query_sql, tabla_destino):
    conn = obtener_conexion_oracle()
    primer_chunk = True
    columnas_maestras = []

    for chunk in pd.read_sql(query_sql, con=conn, chunksize=50000):
        chunk['DATOS_JSON'] = chunk['DATOS_JSON'].apply(lambda x: json.loads(x) if isinstance(x, str) else x)
        df = pd.json_normalize(chunk['DATOS_JSON'])
        df.columns = df.columns.astype(str).str.split('.').str[-1]
        df.columns = df.columns.str.lower().str.replace(' ', '_').str.replace('ó', 'o').str.replace('í',
                                                                                                    'i').str.replace(
            'ñ', 'n')
        df = df.loc[:, (df.columns != '') & (df.columns != 'nan') & ~df.columns.duplicated()]

        for col in df.select_dtypes(include=['object']).columns:
            df[col] = df[col].apply(arreglar_codificacion).astype(str)

        if primer_chunk:
            columnas_maestras = df.columns.tolist()
        else:
            df = df.reindex(columns=columnas_maestras)

        modo = 'replace' if primer_chunk else 'append'
        cargar_a_silver(df, tabla_destino, modo=modo)
        primer_chunk = False
    conn.close()


@task(name="Procesar Supercías")
def procesar_empresas():
    print("Procesando Directorio Supercías (224k filas)...")
    procesar_supercias("SELECT DATOS_JSON FROM TAB_CONSOLIDADO WHERE INDICADOR = 'SUPERCIAS_DIRECTORIO'",
                       'fact_directorio_companias')
    print("Procesando Ranking Supercías (1.6M filas)...")
    procesar_supercias("SELECT DATOS_JSON FROM TAB_CONSOLIDADO WHERE INDICADOR = 'SUPERCIAS_RANKING'",
                       'fact_ranking_empresarial')


# ===========================================================================
# BLOQUE 3: MINEDUC
# ===========================================================================
@task(name="Procesar Educación (MINEDUC)")
def procesar_mineduc():
    print("Extrayendo datos del Ministerio de Educación (AMIE)...")
    conn = obtener_conexion_oracle()
    query = "SELECT DATOS_JSON FROM TAB_CONSOLIDADO WHERE INDICADOR LIKE 'MINEDUC_AMIE%'"
    df_crudo = pd.read_sql(query, con=conn)
    conn.close()

    if not df_crudo.empty:
        df_crudo['DATOS_JSON'] = df_crudo['DATOS_JSON'].apply(lambda x: json.loads(x) if isinstance(x, str) else x)
        df_amie = pd.json_normalize(df_crudo['DATOS_JSON'])

        df_amie.columns = df_amie.columns.astype(str).str.replace('.', '_')
        df_amie.columns = df_amie.columns.str.lower().str.replace(' ', '_').str.replace('ó', 'o').str.replace('í',
                                                                                                              'i').str.replace(
            'ñ', 'n')
        df_amie = df_amie.loc[:, ~df_amie.columns.duplicated()]

        for col in df_amie.select_dtypes(include=['object']).columns:
            df_amie[col] = df_amie[col].apply(arreglar_codificacion).astype(str)

        cargar_a_silver(df_amie, 'fact_mineduc_amie')

        col_prov = next((c for c in df_amie.columns if 'provincia' in c and 'cod' not in c), 'provincia')
        col_anio = next((c for c in df_amie.columns if 'anio' in c or 'base' in c), 'anio_base')

        # --- ARREGLADO ---
        # Antes: next((c for c in df_amie.columns if '3' in c and 'bach' in c), None)
        # Esa busqueda matchea TANTO "...bachillerato_3er_ano_m" (mujeres)
        # como "...bachillerato_3er_ano_h" (hombres), y next() se quedaba
        # solo con la primera (mujeres) -> se perdia ~49% de los bachilleres
        # (confirmado con datos reales: Azuay 2025 reportaba 6375 en vez
        # de 12450 reales). Ahora se toman ambas columnas y se suman.
        col_b3_m = next((c for c in df_amie.columns if '3er_ano_m' in c and 'bach' in c), None)
        col_b3_h = next((c for c in df_amie.columns if '3er_ano_h' in c and 'bach' in c), None)

        if col_prov and col_anio and col_b3_m and col_b3_h:
            df_amie[col_b3_m] = pd.to_numeric(df_amie[col_b3_m], errors='coerce').fillna(0)
            df_amie[col_b3_h] = pd.to_numeric(df_amie[col_b3_h], errors='coerce').fillna(0)
            df_amie['bachilleres_3ro_total'] = df_amie[col_b3_m] + df_amie[col_b3_h]

            df_bach = df_amie.groupby([col_anio, col_prov], as_index=False).agg(
                bachilleres_3ro=('bachilleres_3ro_total', 'sum')
            )
            df_bach = df_bach.rename(columns={col_anio: 'anio', col_prov: 'provincia'})
            cargar_a_silver(df_bach, 'fact_mineduc_bachilleres')
        else:
            print("  -> Aviso: no se encontraron ambas columnas (mujeres/hombres) de 3er año de bachillerato.")


# ===========================================================================
# BLOQUE 4: EMPLEO (ENEMDU)
# ===========================================================================
@task(name="Procesar Empleo (ENEMDU)")
def procesar_enemdu():
    print("Extrayendo datos de Empleo (ENEMDU)...")
    conn = obtener_conexion_oracle()
    query = "SELECT DATOS_JSON FROM TAB_CONSOLIDADO WHERE INDICADOR = 'INEC_ENEMDU_POBLACIONES'"
    df_crudo = pd.read_sql(query, con=conn)
    conn.close()

    if not df_crudo.empty:
        df_crudo['DATOS_JSON'] = df_crudo['DATOS_JSON'].apply(lambda x: json.loads(x) if isinstance(x, str) else x)
        df_enemdu = pd.json_normalize(df_crudo['DATOS_JSON'])

        # FIX: el JSON trae un objeto anidado "metricas" con nacional_total,
        # area_urbana y area_rural. Antes solo se buscaba la columna con
        # 'nacional' en el nombre y se descartaban urbana/rural, dejando
        # area='nacional' fijo para todo (mismo patron de bug que el de
        # bachilleres: agarrar solo una variante quando existian varias).
        # pd.json_normalize aplana "metricas.area_urbana" -> despues del
        # replace('.', '_') queda "metricas_area_urbana".
        df_enemdu.columns = (df_enemdu.columns.astype(str).str.replace('.', '_')
                             .str.lower().str.replace(' ', '_').str.replace('ó', 'o')
                             .str.replace('í', 'i').str.replace('é', 'e'))

        for col in df_enemdu.select_dtypes(include=['object']).columns:
            df_enemdu[col] = df_enemdu[col].apply(arreglar_codificacion).astype(str)

        col_nacional = next((c for c in df_enemdu.columns if 'nacional_total' in c), None)
        col_urbana = next((c for c in df_enemdu.columns if 'area_urbana' in c), None)
        col_rural = next((c for c in df_enemdu.columns if 'area_rural' in c), None)
        col_anio = next((c for c in df_enemdu.columns if 'anio_fiscal' in c), None)
        col_periodo = next((c for c in df_enemdu.columns if 'periodo_original' in c), None)
        col_ind = next((c for c in df_enemdu.columns if 'nombre_indicador' in c), None)

        if all([col_nacional, col_urbana, col_rural, col_anio, col_periodo, col_ind]):
            df_enemdu = df_enemdu.rename(columns={
                col_nacional: 'total_nacional',
                col_urbana: 'total_urbana',
                col_rural: 'total_rural',
                col_anio: 'anio',
                col_periodo: 'periodo',
                col_ind: 'indicador'
            })
            for c in ['total_nacional', 'total_urbana', 'total_rural']:
                df_enemdu[c] = pd.to_numeric(df_enemdu[c], errors='coerce')

            cols_vitales = ['periodo', 'anio', 'indicador', 'total_nacional', 'total_urbana', 'total_rural']
            df_enemdu = df_enemdu[cols_vitales]

            cargar_a_silver(df_enemdu, 'fact_empleo_enemdu')
        else:
            print("  -> Aviso: Faltan columnas clave en ENEMDU (nacional_total, area_urbana, area_rural, anio_fiscal, periodo_original o nombre_indicador).")


# ===========================================================================
# CREACIÓN DE VISTAS GOLD
# ===========================================================================
@task(name="Construir Vistas Gold")
def generar_vistas_gold():
    print("Generando Vistas Gold analíticas...")
    conexion = sqlite3.connect(DB_SQLITE)
    cur = conexion.cursor()

    try:
        cur.execute("DROP VIEW IF EXISTS gold_pib_tendencia")
        cur.execute("""
            CREATE VIEW gold_pib_tendencia AS
            SELECT CAST(anio_fiscal AS INTEGER) AS anio, pib_real_millones AS pib_real_musd, tasa_variacion_anual AS variacion_pib_pct,
                CASE WHEN tasa_variacion_anual > 2 THEN 'Crecimiento fuerte' WHEN tasa_variacion_anual > 0 THEN 'Crecimiento moderado'
                     WHEN tasa_variacion_anual = 0 THEN 'Estancamiento' ELSE 'Contracción' END AS clasificacion
            FROM fact_macro_anual ORDER BY anio
        """)
    except Exception as e:
        print(f"Aviso PIB: {e}")

    try:
        cur.execute("DROP VIEW IF EXISTS gold_empleo_ciiu")
        cur.execute("""
            CREATE VIEW gold_empleo_ciiu AS
            SELECT 
                CASE ciiu_nivel1 WHEN 'A' THEN 'Agricultura, Ganadería y Pesca' WHEN 'B' THEN 'Minas y Canteras' WHEN 'C' THEN 'Manufactura'
                WHEN 'D' THEN 'Suministro de Energía y Gas' WHEN 'E' THEN 'Distribución de Agua y Saneamiento' WHEN 'F' THEN 'Construcción'
                WHEN 'G' THEN 'Comercio al por Mayor y Menor' WHEN 'H' THEN 'Transporte y Almacenamiento' WHEN 'I' THEN 'Alojamiento y Comida'
                WHEN 'J' THEN 'Información y Comunicación' WHEN 'K' THEN 'Actividades Financieras y Seguros' WHEN 'L' THEN 'Actividades Inmobiliarias'
                WHEN 'M' THEN 'Actividades Profesionales y Científicas' WHEN 'N' THEN 'Servicios Administrativos' WHEN 'P' THEN 'Enseñanza'
                WHEN 'Q' THEN 'Salud Humana y Asistencia Social' ELSE 'Otras Actividades' END AS sector_economico, COUNT(*) AS total_empresas
            FROM fact_directorio_companias WHERE ciiu_nivel1 IS NOT NULL AND ciiu_nivel1 != 'None' AND ciiu_nivel1 != ''
            GROUP BY ciiu_nivel1 ORDER BY total_empresas DESC LIMIT 10
        """)
    except Exception as e:
        print(f"Aviso CIIU: {e}")

    try:
        cur.execute("DROP VIEW IF EXISTS gold_empleo_tendencia")
        cur.execute("""
            CREATE VIEW gold_empleo_tendencia AS
            SELECT periodo, indicador, area, CAST(valor_tasa AS FLOAT) AS valor_tasa
            FROM fact_empleo_enemdu 
            WHERE valor_tasa IS NOT NULL 
            ORDER BY periodo
        """)
    except Exception as e:
        print(f"Aviso Empleo Tendencia: {e}")

    try:
        cur.execute("DROP VIEW IF EXISTS gold_vab_provincia")
        cur.execute("""
            CREATE VIEW gold_vab_provincia AS
            SELECT anio, UPPER(provincia) AS provincia, SUM(CAST(valor AS FLOAT)) AS vab_total
            FROM fact_vab_geografico
            GROUP BY anio, UPPER(provincia)
            ORDER BY anio, vab_total DESC
        """)
    except Exception as e:
        print(f"Aviso VAB Provincia: {e}")

    try:
        cur.execute("DROP VIEW IF EXISTS gold_empresas_provincia")
        cur.execute("""
            CREATE VIEW gold_empresas_provincia AS
            SELECT provincia, COUNT(*) AS empresas_activas
            FROM fact_directorio_companias WHERE UPPER(situacion_legal) LIKE '%ACTIV%' AND provincia != 'None'
            GROUP BY provincia ORDER BY empresas_activas DESC
        """)
    except Exception as e:
        print(f"Aviso Provincias: {e}")

    try:
        cur.execute("DROP VIEW IF EXISTS gold_bachilleres_vs_empresas")
        cur.execute("""
            CREATE VIEW gold_bachilleres_vs_empresas AS
            WITH ult AS (SELECT MAX(anio) AS anio FROM fact_mineduc_bachilleres),
            bach AS (SELECT UPPER(b.provincia) AS provincia_norm, b.provincia, b.bachilleres_3ro FROM fact_mineduc_bachilleres b, ult WHERE b.anio = ult.anio),
            emp AS (SELECT UPPER(provincia) AS provincia_norm, COUNT(*) AS empresas_activas FROM fact_directorio_companias WHERE UPPER(situacion_legal) LIKE '%ACTIV%' AND provincia != 'None' GROUP BY UPPER(provincia))
            SELECT bach.provincia, bach.bachilleres_3ro, COALESCE(emp.empresas_activas, 0) AS empresas_activas,
                CASE WHEN COALESCE(emp.empresas_activas, 0) = 0 THEN NULL ELSE ROUND(CAST(bach.bachilleres_3ro AS FLOAT) / emp.empresas_activas, 3) END AS ratio_bachilleres_por_empresa
            FROM bach LEFT JOIN emp ON bach.provincia_norm = emp.provincia_norm ORDER BY ratio_bachilleres_por_empresa DESC
        """)
    except Exception as e:
        print(f"Aviso Ratio: {e}")

    conexion.commit()
    conexion.close()
    print("  -> ¡Vistas Gold creadas y listas para Power BI!")


# ===========================================================================
# ORQUESTADOR (FLOW)
# ===========================================================================
@flow(name="Pipeline Integrado Macroentorno")
def pipeline_principal():
    print("\n--- INICIANDO PIPELINE ETL (ORACLE -> SQLITE) ---")
    procesar_pib()
    procesar_vab()
    procesar_empresas()
    procesar_mineduc()
    procesar_enemdu()
    generar_vistas_gold()
    print("--- PIPELINE FINALIZADO CON ÉXITO ---\n")


if __name__ == '__main__':
    pipeline_principal()
