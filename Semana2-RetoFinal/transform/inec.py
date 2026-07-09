import pandas as pd
import sqlite3
import re
import unicodedata

# ==========================================
# 0. UTILIDADES
# ==========================================

MESES = {
    'ene': 1, 'feb': 2, 'mar': 3, 'abr': 4, 'may': 5, 'jun': 6,
    'jul': 7, 'ago': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dic': 12
}

RAMAS_ACTIVIDAD = [
    'agricultura_ganaderia_silvicultura_pesca',
    'explotacion_minas_canteras',
    'industrias_manufactureras',
    'suministro_electricidad_gas_vapor',
    'distribucion_agua_alcantarillado_saneamiento',
    'construccion',
    'comercio_mayor_menor',
    'transporte_almacenamiento',
    'alojamiento_servicios_comida',
    'informacion_comunicacion',
    'actividades_financieras_seguros',
    'actividades_inmobiliarias',
    'actividades_profesionales_cientificas_tecnicas',
    'actividades_servicios_administrativos_apoyo',
    'administracion_publica_defensa',
    'ensenanza',
    'atencion_salud_asistencia_social',
    'arte_entretenimiento_recreacion',
    'otras_actividades_servicios',
    'actividades_hogares_empleadores',
    'organizaciones_organos_extraterritoriales',
    'no_clasificado',
]


def parsear_periodo(valor):
    """Convierte 'dic-07' (texto BCE/INEC) o un datetime ya parseado por Excel
    (años >= 2016 vienen como fecha nativa) a una tupla (fecha, anio)."""
    if isinstance(valor, pd.Timestamp):
        return valor, valor.year
    texto = str(valor).strip().lower()
    m = re.match(r'([a-z]{3})-?(\d{2})', texto)
    if m:
        mes_abv, yy = m.groups()
        mes = MESES.get(mes_abv[:3])
        anio = 2000 + int(yy)
        if mes:
            return pd.Timestamp(year=anio, month=mes, day=1), anio
    return pd.NaT, None


# ==========================================
# 1. FUNCIONES DE LIMPIEZA
# ==========================================

def limpiar_enemdu(ruta_archivo, hoja='2. Tasas'):
    """ENEMDU - Indicadores laborales.
    El archivo real es un Excel de tabulados (no un CSV) con las cabeceras
    partidas en dos filas por celdas combinadas: fila con Encuesta/Periodo/
    Indicadores/Nacional/Área/Sexo y, debajo, Total/Urbana/Rural/Hombre/Mujer.
    Cada indicador viene en una sola fila con las áreas como columnas
    ("ancho"), por lo que se exige pd.melt() para normalizarlo a un área
    por fila ("largo") antes de cargarlo a Silver.
    """
    print(f"Limpiando ENEMDU ({hoja})...")
    try:
        df_raw = pd.read_excel(ruta_archivo, sheet_name=hoja, header=None)
    except FileNotFoundError:
        print(f" [!] No se encontró el archivo: {ruta_archivo}")
        return pd.DataFrame()
    except Exception as e:
        print(f" [!] No se pudo leer la hoja '{hoja}': {e}")
        return pd.DataFrame()

    df = df_raw.iloc[3:].copy()
    df.columns = ['encuesta', 'periodo', 'indicador', 'nacional', 'urbana', 'rural', 'hombre', 'mujer']
    df = df.dropna(subset=['indicador', 'periodo'])
    df['encuesta'] = df['encuesta'].astype(str).str.strip()
    df['indicador'] = df['indicador'].astype(str).str.strip()

    # id_vars: lo que identifica de forma única a cada indicador-periodo.
    # value_vars: las áreas que están como columnas y deben pasar a filas.
    df_largo = df.melt(
        id_vars=['encuesta', 'periodo', 'indicador'],
        value_vars=['nacional', 'urbana', 'rural'],
        var_name='area',
        value_name='valor',
    )
    df_largo['valor'] = pd.to_numeric(df_largo['valor'], errors='coerce')
    df_largo = df_largo.dropna(subset=['valor'])

    fechas = df_largo['periodo'].apply(parsear_periodo)
    df_largo['fecha'] = fechas.apply(lambda t: t[0])
    df_largo['anio'] = fechas.apply(lambda t: t[1])
    df_largo['periodo'] = df_largo['periodo'].astype(str)

    columnas_finales = ['encuesta', 'periodo', 'fecha', 'anio', 'indicador', 'area', 'valor']
    return df_largo[columnas_finales].reset_index(drop=True)


def limpiar_censo_ocupacion(ruta_archivo, hoja='5.1'):
    """Censo 2022 - Población ocupada por rama de actividad.
    La hoja 5.1 trae, por cada combinación provincia/cantón/sexo/grupo de
    edad, un total de ocupados y 22 columnas (una por rama CIIU a un
    dígito). Se aplica el mismo enfoque de melt() para pasar esas 22 ramas
    de columnas a filas.
    """
    print(f"Limpiando Censo 2022 - Rama de actividad (hoja {hoja})...")
    try:
        df_raw = pd.read_excel(ruta_archivo, sheet_name=hoja, header=None)
    except FileNotFoundError:
        print(f" [!] No se encontró el archivo: {ruta_archivo}")
        return pd.DataFrame()
    except Exception as e:
        print(f" [!] No se pudo leer la hoja '{hoja}': {e}")
        return pd.DataFrame()

    columnas = ['indice', 'provincia', 'canton', 'sexo', 'grupo_edad', 'total_ocupados'] + RAMAS_ACTIVIDAD
    df = df_raw.iloc[11:].copy()
    df = df.iloc[:, :len(columnas)]
    df.columns = columnas
    df = df.drop(columns=['indice'])
    df = df.dropna(subset=['provincia'])

    for col in RAMAS_ACTIVIDAD + ['total_ocupados']:
        df[col] = pd.to_numeric(df[col], errors='coerce')

    df['provincia'] = df['provincia'].astype(str).str.strip().str.upper()
    df['canton'] = df['canton'].astype(str).str.strip().str.upper()
    df['sexo'] = df['sexo'].astype(str).str.strip()
    df['grupo_edad'] = df['grupo_edad'].astype(str).str.strip()

    df_largo = df.melt(
        id_vars=['provincia', 'canton', 'sexo', 'grupo_edad', 'total_ocupados'],
        value_vars=RAMAS_ACTIVIDAD,
        var_name='rama_actividad',
        value_name='personas_ocupadas',
    )
    df_largo = df_largo.dropna(subset=['personas_ocupadas'])
    return df_largo.reset_index(drop=True)


# ==========================================
# 2. FUNCIÓN DE CARGA A LA BASE DE DATOS
# ==========================================

def cargar_a_silver(df, nombre_tabla, conexion):
    if df is None or df.empty:
        print(f" [!] Tabla '{nombre_tabla}' no se cargó: DataFrame vacío o con error previo.")
        return
    df.to_sql(nombre_tabla, conexion, if_exists='replace', index=False)
    print(f"[*] Tabla '{nombre_tabla}' cargada exitosamente en Silver ({len(df)} filas).")


# ==========================================
# 3. EJECUCIÓN PRINCIPAL (MAIN)
# ==========================================

if __name__ == '__main__':
    ruta_enemdu = 'datos_macroentorno/Tabulados_Mercado_Laboral.xlsx'
    ruta_censo = 'datos_macroentorno/2022_CPV_Trabajo.xlsx'
    ruta_db = 'pipeline_utpl.db'

    conn = sqlite3.connect(ruta_db)
    try:
        df_empleo = limpiar_enemdu(ruta_enemdu)
        df_ocupacion_censo = limpiar_censo_ocupacion(ruta_censo)

        cargar_a_silver(df_empleo, 'fact_empleo', conn)
        cargar_a_silver(df_ocupacion_censo, 'fact_ocupacion_censo', conn)

        print("\n¡Semana 3 (INEC) completada! fact_empleo y fact_ocupacion_censo están en la base de datos.")

    except Exception as e:
        print(f"Ocurrió un error: {e}")
    finally:
        conn.close()
