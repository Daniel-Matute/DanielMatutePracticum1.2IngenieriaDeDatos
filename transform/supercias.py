import pandas as pd
import sqlite3
import re
import unicodedata

# ==========================================
# 0. UTILIDADES
# ==========================================

def normalizar_snake_case(texto):
    texto = str(texto).strip().lower()
    texto = unicodedata.normalize('NFKD', texto).encode('ascii', 'ignore').decode('utf-8')
    texto = re.sub(r'[^a-z0-9]+', '_', texto).strip('_')
    return texto


# ==========================================
# 1. FUNCIONES DE LIMPIEZA
# ==========================================

def limpiar_directorio(ruta_archivo):
    """Directorio de Compañías (Supercias).
    El archivo trae 4 filas de metadata (título del reporte, número de filas,
    fecha de corte) antes del encabezado real, por lo que se usa skiprows=4.
    """
    print("Limpiando Directorio de Compañías...")
    try:
        df = pd.read_excel(ruta_archivo, skiprows=4)
    except FileNotFoundError:
        print(f" [!] No se encontró el archivo: {ruta_archivo}")
        return pd.DataFrame()
    except Exception as e:
        print(f" [!] Error leyendo el directorio: {e}")
        return pd.DataFrame()

    df.columns = [normalizar_snake_case(c) for c in df.columns]
    df = df.rename(columns={'ciiu_nivel_1': 'ciiu_n1', 'ciiu_nivel_6': 'ciiu_n6'})

    columnas_esperadas = ['expediente', 'ruc', 'nombre', 'situacion_legal', 'provincia', 'canton']
    faltantes = [c for c in columnas_esperadas if c not in df.columns]
    if faltantes:
        print(f" [!] Columnas esperadas no encontradas en el directorio: {faltantes}")

    df['ruc'] = df['ruc'].astype(str).str.strip()
    df['expediente'] = pd.to_numeric(df['expediente'], errors='coerce')
    df['nombre'] = df['nombre'].astype(str).str.strip().str.upper()
    df['situacion_legal'] = df['situacion_legal'].astype(str).str.strip().str.upper()
    df['provincia'] = df['provincia'].astype(str).str.strip().str.upper()
    df['canton'] = df['canton'].astype(str).str.strip().str.upper()

    df = df.dropna(subset=['ruc', 'expediente'])
    df = df.drop_duplicates(subset=['ruc'])

    columnas_utiles = ['expediente', 'ruc', 'nombre', 'situacion_legal', 'provincia', 'canton',
                        'ciiu_n1', 'ciiu_n6', 'fecha_constitucion', 'ultimo_balance']
    columnas_utiles = [c for c in columnas_utiles if c in df.columns]
    return df[columnas_utiles].reset_index(drop=True)


def limpiar_ciiu_catalogo(ruta_archivo):
    """Catálogo CIIU (código -> descripción). Sirve como dimensión de apoyo
    para cruzar VAB, Censo y Supercias por rama de actividad."""
    print("Limpiando catálogo CIIU...")
    try:
        df = pd.read_csv(ruta_archivo, encoding='utf-8')
    except FileNotFoundError:
        print(f" [!] No se encontró el archivo: {ruta_archivo}")
        return pd.DataFrame()
    except UnicodeDecodeError:
        print(" [!] utf-8 falló, reintentando con latin1...")
        df = pd.read_csv(ruta_archivo, encoding='latin1')
    except Exception as e:
        print(f" [!] Error leyendo el catálogo CIIU: {e}")
        return pd.DataFrame()

    df.columns = [normalizar_snake_case(c) for c in df.columns]
    df['ciiu'] = df['ciiu'].astype(str).str.strip()
    df['descripcion'] = df['descripcion'].astype(str).str.strip()
    df = df.dropna(subset=['ciiu'])
    df = df.drop_duplicates(subset=['ciiu'])
    return df.reset_index(drop=True)


def limpiar_ranking(ruta_archivo, df_directorio):
    """Ranking de Empresas (Supercias).
    OJO: el CSV real (bi_ranking.csv) NO trae RUC, Nombre, Situación Legal
    ni Provincia -tal como se asumió inicialmente-, solo 'expediente' y
    ratios financieros. Esos campos se obtienen cruzando por 'expediente'
    con el Directorio de Compañías (mismo identificador en ambas fuentes).
    Se usa usecols para no cargar en memoria las ~54 columnas del archivo
    (más de 300 MB) cuando solo se necesitan las relevantes para el modelo.
    """
    print("Limpiando Ranking de Empresas...")
    columnas_necesarias = [
        'anio', 'expediente', 'posicion_general', 'ingresos_ventas', 'ingresos_totales',
        'activos', 'patrimonio', 'utilidad_neta', 'n_empleados', 'ciiu_n1', 'ciiu_n6',
    ]
    # dtype explícito: con >1.5 millones de filas y usecols, el parser C de
    # pandas infiere tipos por chunk y puede lanzar un IndexError interno
    # ("list index out of range") si un chunk detecta un tipo distinto al
    # de otro. Fijar dtype evita esa inferencia inconsistente.
    dtypes_ranking = {
        'anio': 'float64', 'expediente': 'float64', 'posicion_general': 'float64',
        'ingresos_ventas': 'float64', 'ingresos_totales': 'float64', 'activos': 'float64',
        'patrimonio': 'float64', 'utilidad_neta': 'float64', 'n_empleados': 'float64',
        'ciiu_n1': 'object', 'ciiu_n6': 'object',
    }
    try:
        df = pd.read_csv(
            ruta_archivo,
            usecols=lambda c: c in columnas_necesarias,
            dtype=dtypes_ranking,
            low_memory=False,
        )
    except FileNotFoundError:
        print(f" [!] No se encontró el archivo: {ruta_archivo}")
        return pd.DataFrame()
    except Exception as e:
        print(f" [!] Error leyendo el ranking: {e}")
        return pd.DataFrame()

    df.columns = [normalizar_snake_case(c) for c in df.columns]

    for col in ['anio', 'expediente', 'n_empleados']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').astype('Int64')
    for col in ['ingresos_ventas', 'ingresos_totales', 'activos', 'patrimonio', 'utilidad_neta']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')

    df = df.dropna(subset=['expediente'])

    if df_directorio is not None and not df_directorio.empty:
        df = df.merge(
            df_directorio[['expediente', 'ruc', 'nombre', 'situacion_legal', 'provincia']],
            on='expediente', how='left',
        )
    else:
        print(" [!] Directorio vacío: fact_ranking_empresarial quedará sin RUC/Nombre/Provincia.")

    return df.reset_index(drop=True)


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
    ruta_directorio = 'datos_macroentorno/directorio_companias.xlsx'
    ruta_ciiu = 'datos_macroentorno/bi_ciiu.csv'
    ruta_ranking = 'datos_macroentorno/bi_ranking.csv'
    ruta_db = 'pipeline_utpl.db'

    conn = sqlite3.connect(ruta_db)
    try:
        df_directorio = limpiar_directorio(ruta_directorio)
        df_ciiu = limpiar_ciiu_catalogo(ruta_ciiu)
        df_ranking = limpiar_ranking(ruta_ranking, df_directorio)

        cargar_a_silver(df_directorio, 'dim_empresas', conn)
        cargar_a_silver(df_ciiu, 'dim_ciiu', conn)
        cargar_a_silver(df_ranking, 'fact_ranking_empresarial', conn)

        print("\n¡Semana 3 (Supercias) completada! dim_empresas, dim_ciiu y fact_ranking_empresarial están en la base de datos.")

    except Exception as e:
        print(f"Ocurrió un error: {e}")
    finally:
        conn.close()
