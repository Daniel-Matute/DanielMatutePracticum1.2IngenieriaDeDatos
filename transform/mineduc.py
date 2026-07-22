import pandas as pd
import sqlite3
import re
import unicodedata
import openpyxl

# ==========================================
# 0. UTILIDADES (misma lógica de snake_case usada en la Semana 1 - AMIE)
# ==========================================

def normalizar_snake_case(texto):
    texto = str(texto).strip().lower()
    texto = unicodedata.normalize('NFKD', texto).encode('ascii', 'ignore').decode('utf-8')
    texto = re.sub(r'[^a-z0-9]+', '_', texto).strip('_')
    return texto


# El archivo real tiene 109 columnas (desagregaciones por etnia, discapacidad,
# tipo de contrato docente, etc.) que no forman parte del modelo Silver de
# este reto. Igual que se hizo con el AMIE en la Semana 1, nos quedamos solo
# con las columnas identificadoras/geográficas y los indicadores de matrícula
# que alimentan dim_geografia y la pregunta P3 del dashboard.
COLUMNAS_AMIE = [
    'Año_lectivo', 'Provincia', 'Cod_Provincia', 'Canton', 'Cod_Canton',
    'Nombre_Institucion', 'Codigo_Institucion', 'Sostenimiento',
    'Total_Estudiantes', 'Bachillerato', 'Estudiante_Bachillerato_edad_15_17',
    '3er Año Bachillerato',
]


# ==========================================
# 1. FUNCIÓN DE LIMPIEZA
# ==========================================

def limpiar_mineduc(ruta_archivo, hoja='Historico_Inicio'):
    """MINEDUC - Registro Administrativo Histórico.
    OJO: la fuente real NO es el AMIE 2023-2024 de una sola cohorte que se
    describió al inicio, sino una serie histórica 2009-2024 con 322 mil
    filas y 109 columnas. Tampoco existe una columna 'Nivel_Educacion' con
    un único valor por institución: 'Nivel_educativo' viene combinado
    (ej. 'Inicial/EGB/Bachillerato'), así que en vez de filtrar por ese
    campo se usa directamente la columna '3er Año Bachillerato', que es el
    indicador que necesita la pregunta P3 (bachilleres a punto de graduarse).

    Se usa openpyxl en modo read_only + streaming fila por fila (en vez de
    pd.read_excel) porque el archivo pesa ~313 MB y cargar las 109 columnas
    completas para 322 mil filas con pandas es muy costoso en memoria; aquí
    solo se materializan las ~12 columnas que realmente se necesitan.
    """
    print(f"Limpiando MINEDUC - Registro Administrativo (hoja {hoja})...")
    try:
        wb = openpyxl.load_workbook(ruta_archivo, read_only=True, data_only=True)
        ws = wb[hoja]
    except FileNotFoundError:
        print(f" [!] No se encontró el archivo: {ruta_archivo}")
        return pd.DataFrame()
    except KeyError:
        print(f" [!] La hoja '{hoja}' no existe en el archivo.")
        return pd.DataFrame()
    except Exception as e:
        print(f" [!] Error abriendo el archivo: {e}")
        return pd.DataFrame()

    filas = ws.iter_rows(values_only=True)
    encabezado = next(filas)
    indices = {nombre: pos for pos, nombre in enumerate(encabezado)}

    faltantes = [c for c in COLUMNAS_AMIE if c not in indices]
    if faltantes:
        print(f" [!] Columnas esperadas no encontradas: {faltantes}")

    columnas_disponibles = [c for c in COLUMNAS_AMIE if c in indices]
    registros = [tuple(fila[indices[c]] for c in columnas_disponibles) for fila in filas]
    wb.close()

    if not registros:
        print(" [!] La hoja no devolvió filas de datos.")
        return pd.DataFrame()

    df = pd.DataFrame(registros, columns=columnas_disponibles)
    df.columns = [normalizar_snake_case(c) for c in df.columns]
    df.rename(columns={'ano_lectivo': 'anio_lectivo'}, inplace=True)

    # 'Año_lectivo' llega como '2009-2010 Inicio'; se conserva solo el ciclo.
    df['anio_lectivo'] = df['anio_lectivo'].astype(str).str.replace(' Inicio', '', regex=False).str.strip()

    df.rename(columns={
        'codigo_institucion': 'amie',
        '3er_ano_bachillerato': 'bachilleres_3er_anio',
        'estudiante_bachillerato_edad_15_17': 'estudiantes_bachillerato_15_17',
    }, inplace=True)

    for col in ['total_estudiantes', 'bachillerato', 'estudiantes_bachillerato_15_17', 'bachilleres_3er_anio']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0).astype(int)

    df['provincia'] = df['provincia'].astype(str).str.strip().str.upper()
    df['canton'] = df['canton'].astype(str).str.strip().str.upper()
    df['nombre_institucion'] = df['nombre_institucion'].astype(str).str.strip()
    df['sostenimiento'] = df['sostenimiento'].astype(str).str.strip()
    df['amie'] = df['amie'].astype(str).str.strip()

    df = df.dropna(subset=['amie'])
    df = df[df['amie'] != 'None']
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
    ruta_mineduc = 'datos_macroentorno/Registro-Administrativo-Historico_2009-202X-Inicio.xlsx'
    ruta_db = 'pipeline_utpl.db'

    conn = sqlite3.connect(ruta_db)
    try:
        df_mineduc = limpiar_mineduc(ruta_mineduc)
        cargar_a_silver(df_mineduc, 'fact_oferta_academica', conn)

        print("\n¡Semana 3 (MINEDUC) completada! fact_oferta_academica está en la base de datos.")

    except Exception as e:
        print(f"Ocurrió un error: {e}")
    finally:
        conn.close()
