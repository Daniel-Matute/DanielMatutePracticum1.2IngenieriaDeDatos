import pandas as pd

print("Iniciando Fase 2: Limpieza de Datos...")
# Cargamos el archivo igual que en la Fase 1
df = pd.read_csv('2_MINEDUC_RegistrosAdministrativos_2023-2024Inicio.csv', sep=';', encoding='latin-1')

# --- TRANSFORMACIÓN 1: Renombrar ---
# Quitamos tildes y espacios para facilitar el trabajo en SQL y Power BI
RENAME = {
    'Año lectivo': 'anio_lectivo', 
    'AMIE': 'cod_amie',
    'Nombre_Institución': 'nombre_institucion', # <- ¡Aquí está la corrección (con tilde)!
    'Provincia': 'provincia',
    'Nivel Educación': 'nivel_educacion', 
    'Sostenimiento': 'sostenimiento',
    'Área': 'area', 
    'Total Docentes': 'total_docentes', 
    'Total Estudiantes': 'total_estudiantes',
    'Estudiantes Femenino': 'estudiantes_f', 
    'Estudiantes Masculino': 'estudiantes_m'
}
df = df.rename(columns=RENAME)
print("1. Columnas renombradas correctamente.")

# --- TRANSFORMACIÓN 2: Llenar Nulos ---
# Llenamos con 0 los nulos en métricas clave y los convertimos a números enteros
nums = ['total_docentes', 'total_estudiantes', 'estudiantes_f', 'estudiantes_m']
df[nums] = df[nums].fillna(0).astype(int)
print("2. Valores nulos convertidos a cero.")

# --- TRANSFORMACIÓN 3: Eliminar Duplicados ---
# Eliminamos registros duplicados usando el código AMIE y el año lectivo
filas_antes = len(df)
df = df.drop_duplicates(subset=['cod_amie', 'anio_lectivo'])
filas_despues = len(df)
print(f"3. Duplicados eliminados. Pasamos de {filas_antes} a {filas_despues} filas.")

# --- TRANSFORMACIÓN 4: Consistencia Matemática ---
# Verificamos que el total de estudiantes sea igual a la suma de mujeres + hombres
inconsistentes = df[df['total_estudiantes'] != (df['estudiantes_f'] + df['estudiantes_m'])]
print(f"4. Se encontraron {len(inconsistentes)} registros inconsistentes matemáticamente.")

# Guardamos el resultado en un nuevo CSV temporal (opcional pero muy útil)
df.to_csv('mineduc_limpio.csv', index=False, sep=';', encoding='utf-8')
print("¡Limpieza finalizada! Archivo 'mineduc_limpio.csv' guardado.")