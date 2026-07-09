import pandas as pd
import sqlite3
import os

# ==========================================
# 1. FUNCIONES DE LIMPIEZA
# ==========================================

def limpiar_pib_real(ruta_archivo):
    print("Limpiando PIB Real...")
    df_raw = pd.read_excel(ruta_archivo, sheet_name='PIB pc real', engine='openpyxl')
    header_idx = df_raw[df_raw.iloc[:, 0] == 'Años'].index[0]
    df = pd.read_excel(ruta_archivo, sheet_name='PIB pc real', header=header_idx + 1, engine='openpyxl') 
    
    df.rename(columns={
        'Años': 'anio', 
        'PIB \n(Millones de USD encadenado de volumen)': 'pib_real_musd',
        'Población': 'poblacion_miles',
        'PIB Per cápita  \n(USD)': 'pib_percapita_usd',
        'Tasa de variación anual del PIB Per cápita\n(En porcentaje)': 'variacion_pib_pct'
    }, inplace=True)
    
    df.dropna(subset=['pib_real_musd'], inplace=True)
    df['anio'] = df['anio'].astype(str).str.replace(' (p)', '', regex=False).astype(int)
    return df

def limpiar_pib_nominal(ruta_archivo):
    print("Limpiando PIB Nominal...")
    df_raw = pd.read_excel(ruta_archivo, sheet_name=5, engine='openpyxl')
    header_idx = df_raw[df_raw.iloc[:, 0] == 'Años'].index[0]
    
    df = pd.read_excel(ruta_archivo, sheet_name=5, header=header_idx + 1, engine='openpyxl')
    nombres_actuales = df.columns.tolist()
    
    df.rename(columns={
        nombres_actuales[0]: 'periodo',
        nombres_actuales[3]: 'pib_percapita_nominal_usd'
    }, inplace=True)
    
    df.dropna(subset=['pib_percapita_nominal_usd'], inplace=True)
    df['periodo'] = df['periodo'].astype(str).str.replace(' (p)', '', regex=False).astype(int)
    df = df[df['periodo'] >= 2000].copy()
    df['fecha'] = pd.to_datetime(df['periodo'], format='%Y')
    
    return df[['fecha', 'periodo', 'pib_percapita_nominal_usd']]

def limpiar_petroleo_riesgo(ruta_archivo):
    print("Limpiando Petróleo y Riesgo País...")
    df = pd.read_csv(ruta_archivo)
    df.rename(columns={'Período': 'fecha'}, inplace=True)
    df['fecha'] = pd.to_datetime(df['fecha'])
    return df

def limpiar_iee(ruta_archivo):
    print("Limpiando IEE...")
    df = pd.read_csv(ruta_archivo)
    df.columns = [col.lower() for col in df.columns]
    df['fecha'] = pd.to_datetime(df['fecha'], format='%Y-%m-%d')
    return df

def limpiar_vab(ruta_archivo):
    print("Limpiando VAB Provincial...")
    df = pd.read_csv(ruta_archivo)
    df.columns = [col.lower() for col in df.columns]
    df.rename(columns={'año': 'anio'}, inplace=True)
    return df

# ==========================================
# 2. FUNCIÓN DE CARGA A LA BASE DE DATOS
# ==========================================

def cargar_a_silver(df, nombre_tabla, conexion):
    df.to_sql(nombre_tabla, conexion, if_exists='replace', index=False)
    print(f"[*] Tabla '{nombre_tabla}' cargada exitosamente en Silver.")

# ==========================================
# 3. EJECUCIÓN PRINCIPAL (MAIN)
# ==========================================

if __name__ == '__main__':
    ruta_pib = 'datos_macroentorno/retropolacion_1965_2024p.xlsx'
    ruta_petroleo = 'datos_macroentorno/petroleo_riesgo.csv'
    ruta_iee = 'datos_macroentorno/iee.csv'
    ruta_vab = 'datos_macroentorno/vab_provincial.csv'
    
    ruta_db = 'pipeline_utpl.db'
    conn = sqlite3.connect(ruta_db)
    
    try:
        # Ejecutamos todas las limpiezas
        df_pib_real = limpiar_pib_real(ruta_pib)
        df_pib_nom  = limpiar_pib_nominal(ruta_pib)
        df_petroleo = limpiar_petroleo_riesgo(ruta_petroleo)
        df_iee      = limpiar_iee(ruta_iee)
        df_vab      = limpiar_vab(ruta_vab)
        
        # Cargamos las 5 tablas a la BD
        cargar_a_silver(df_pib_real, 'fact_macro_anual', conn)
        cargar_a_silver(df_pib_nom,  'fact_pib_nominal', conn)
        cargar_a_silver(df_petroleo, 'fact_indicadores_diarios', conn)
        cargar_a_silver(df_iee,      'fact_iee', conn)
        cargar_a_silver(df_vab,      'fact_vab', conn)
        
        print("\n¡Semana 2 completada! Las 5 tablas del BCE están en la base de datos.")
        
    except Exception as e:
        print(f"Ocurrió un error: {e}")
    finally:
        conn.close()