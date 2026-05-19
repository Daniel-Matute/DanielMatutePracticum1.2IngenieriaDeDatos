import pandas as pd

# CSV anual 2023-2024 — separador ; y encoding latin-1
# OJO: Asegúrate de que el nombre del archivo coincida exactamente con el que descargaste
df = pd.read_csv('2_MINEDUC_RegistrosAdministrativos_2023-2024Inicio.csv', sep=';', encoding='latin-1')

print("--- Dimensiones del Dataset ---")
print(df.shape)

print("\n--- Top 15 columnas con más valores nulos ---")
print(df.isnull().sum().sort_values(ascending=False).head(15))

print("\n--- Distribución por Sostenimiento ---")
print(df['Sostenimiento'].value_counts())

print("\n--- Distribución por Nivel de Educación ---")
print(df['Nivel Educación'].value_counts())