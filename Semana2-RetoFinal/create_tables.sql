-- ============================================================
-- create_tables.sql — Modelo relacional Silver (Semana 4)
-- Adaptado a SQLite (el DDL original del reto usa sintaxis
-- PostgreSQL: SERIAL -> INTEGER PRIMARY KEY AUTOINCREMENT).
-- ============================================================

PRAGMA foreign_keys = ON;

-- ------------------------------------------------------------
-- DIMENSIONES
-- ------------------------------------------------------------

-- Compartida entre VAB, Censo, Supercías y MINEDUC.
-- provincia/canton van normalizados (mayúsculas, sin tildes) porque
-- cada fuente los entregaba con formato distinto (ver notas de migración).
CREATE TABLE IF NOT EXISTS dim_geografia (
    id_geografia   INTEGER PRIMARY KEY AUTOINCREMENT,
    provincia      TEXT NOT NULL,
    cod_provincia  TEXT,
    canton         TEXT,
    cod_canton     TEXT,
    UNIQUE (provincia, canton)
);

-- Cubre las series anuales (PIB, VAB, empleo agregado por año).
CREATE TABLE IF NOT EXISTS dim_tiempo (
    id_tiempo   INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha       TEXT NOT NULL,
    anio        INTEGER NOT NULL,
    mes         INTEGER,
    trimestre   INTEGER,
    UNIQUE (fecha)
);

-- Catálogo CIIU (Supercías), ya limpio desde la Semana 3.
CREATE TABLE IF NOT EXISTS dim_ciiu (
    ciiu         TEXT PRIMARY KEY,
    descripcion  TEXT
);

-- Directorio de compañías (Supercías), ya limpio desde la Semana 3.
CREATE TABLE IF NOT EXISTS dim_empresas (
    ruc              TEXT PRIMARY KEY,
    expediente       INTEGER,
    nombre           TEXT,
    situacion_legal  TEXT,
    provincia        TEXT,
    canton           TEXT,
    ciiu_n1          TEXT,
    ciiu_n6          TEXT,
    fecha_constitucion TEXT,
    ultimo_balance     TEXT
);

-- ------------------------------------------------------------
-- HECHOS
-- ------------------------------------------------------------

-- Fusiona lo que en Semana 2 quedó como dos tablas sueltas
-- (fact_macro_anual + fact_pib_nominal): ambas son anuales y se
-- cruzan por año, tal como lo define el DDL original del reto.
CREATE TABLE IF NOT EXISTS fact_macro_anual (
    id                     INTEGER PRIMARY KEY AUTOINCREMENT,
    id_tiempo              INTEGER REFERENCES dim_tiempo(id_tiempo),
    pib_real_musd          REAL,
    poblacion_miles        REAL,
    pib_percapita_nominal_usd REAL,
    variacion_pib_pct      REAL
);

-- Serie diaria BCE (petróleo y riesgo país). No necesita FK a
-- dim_tiempo: el propio DDL del reto la deja con fecha directa.
CREATE TABLE IF NOT EXISTS fact_indicadores_diarios (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha                TEXT NOT NULL,
    precio_petroleo_wti  REAL,
    riesgo_pais_pb       INTEGER
);

-- Serie mensual BCE (expectativas empresariales). Indicador nacional,
-- sin dimensión geográfica.
CREATE TABLE IF NOT EXISTS fact_iee (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha         TEXT NOT NULL,
    iee_global    REAL,
    comercio      REAL,
    construccion  REAL,
    manufactura   REAL
);

-- VAB por provincia/cantón e industria (BCE).
CREATE TABLE IF NOT EXISTS fact_vab (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    id_geografia   INTEGER REFERENCES dim_geografia(id_geografia),
    anio           INTEGER NOT NULL,
    ciiu           TEXT,
    vab_miles_usd  REAL
);

-- ENEMDU (INEC). Se conserva el formato ANCHO que pide el DDL del
-- reto (total_nacional/urbana/rural como columnas): el melt() de la
-- Semana 3 sigue siendo necesario para llegar aquí, solo que el
-- resultado se vuelve a pivotar antes de la carga final.
CREATE TABLE IF NOT EXISTS fact_empleo (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    periodo         TEXT NOT NULL,
    anio            INTEGER,
    indicador       TEXT NOT NULL,
    total_nacional  REAL,
    total_urbana    REAL,
    total_rural     REAL
);

-- Censo 2022 - ocupación por rama de actividad (INEC). No estaba en
-- el DDL original (que solo pedía ENEMDU); se añade porque ya se
-- construyó en la Semana 3 y alimenta cruces por CIIU.
CREATE TABLE IF NOT EXISTS fact_ocupacion_censo (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    id_geografia       INTEGER REFERENCES dim_geografia(id_geografia),
    sexo               TEXT,
    grupo_edad         TEXT,
    rama_actividad     TEXT,
    personas_ocupadas  REAL
);

-- Ranking financiero de Supercías, ya cruzado con el directorio.
CREATE TABLE IF NOT EXISTS fact_ranking_empresarial (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    ruc               TEXT REFERENCES dim_empresas(ruc),
    id_geografia      INTEGER REFERENCES dim_geografia(id_geografia),
    anio              INTEGER,
    ingresos_totales  REAL,
    activos           REAL,
    patrimonio        REAL,
    utilidad_neta     REAL,
    ciiu_n6           TEXT
);

-- Registro administrativo MINEDUC (histórico 2009-2024).
CREATE TABLE IF NOT EXISTS fact_oferta_academica (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    id_geografia             INTEGER REFERENCES dim_geografia(id_geografia),
    anio_lectivo             TEXT NOT NULL,
    amie                     TEXT NOT NULL,
    nombre_institucion       TEXT,
    sostenimiento            TEXT,
    total_estudiantes        INTEGER,
    bachillerato             INTEGER,
    bachilleres_3er_anio     INTEGER
);

-- ------------------------------------------------------------
-- ÍNDICES de apoyo para las vistas Gold
-- ------------------------------------------------------------
CREATE INDEX IF NOT EXISTS ix_fact_empleo_indicador ON fact_empleo(indicador);
CREATE INDEX IF NOT EXISTS ix_fact_ranking_geo ON fact_ranking_empresarial(id_geografia);
CREATE INDEX IF NOT EXISTS ix_fact_oferta_geo ON fact_oferta_academica(id_geografia);
CREATE INDEX IF NOT EXISTS ix_fact_oferta_anio ON fact_oferta_academica(anio_lectivo);
CREATE INDEX IF NOT EXISTS ix_fact_indicadores_fecha ON fact_indicadores_diarios(fecha);
