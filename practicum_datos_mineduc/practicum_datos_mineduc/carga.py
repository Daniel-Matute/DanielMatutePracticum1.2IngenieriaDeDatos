import pandas as pd
from sqlalchemy import create_engine, text

print("Iniciando Fase 3: Carga en SQLite...")

# 1. Leer el dataset limpio que guardamos en la Fase 2
# Como lo guardamos con sep=';', lo leemos con ese mismo separador
df = pd.read_csv('mineduc_limpio.csv', sep=';')

# 2. Filtrar solo el año lectivo más reciente (2023-2024)
# Esto es un requisito obligatorio antes de realizar la carga
print("Filtrando datos para el año lectivo 2023-2024...")
df_reciente = df[df['anio_lectivo'] == '2023-2024'].copy()

# 3. Crear el motor de conexión con SQLite
engine = create_engine('sqlite:///amie_mineduc.db')

# 4. Cargar el DataFrame completo a la base de datos
print("Insertando datos en la tabla 'instituciones'...")
df.to_sql('instituciones', engine, if_exists='replace', index=False)

print("¡Carga finalizada con éxito!")

# 5. Verificación rápida mediante una consulta SQL directo en Python
print("\n--- Ejecutando consulta de verificación ---")
with engine.connect() as con:
    # Envolvemos el string SQL con la función text()
    total_filas = con.execute(text("SELECT COUNT(*) FROM instituciones")).fetchone()[0]
    print(f"Total de registros cargados en la tabla 'instituciones': {total_filas}")
    
    # Mostramos las primeras 3 filas para asegurar que los campos se lean bien
    print("\nPrimeras 3 filas de la tabla:")
    resultado = con.execute(text("SELECT cod_amie, nombre_institucion, sostenimiento FROM instituciones LIMIT 3")).fetchall()
    for fila in resultado:
        print(fila)