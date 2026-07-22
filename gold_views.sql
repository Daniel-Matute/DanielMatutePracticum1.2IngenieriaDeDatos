-- ============================================================
-- gold_views.sql — Capa Gold (Semana 4)
-- Implementa los 4 TODO del reto sobre el modelo relacional
-- creado en create_tables.sql.
-- ============================================================

-- Ya existía en el reto (referencia, no se modifica):
-- gold_pib_tendencia -> evolución del PIB con clasificación de ciclo.

-- ------------------------------------------------------------
-- gold_pib_tendencia
-- Evolución del PIB con clasificación de ciclo económico.
-- Provista por el reto como referencia ("ya existía, no se
-- modifica"), pero nunca quedó creada en este proyecto: la
-- adapto aquí al esquema real (fact_macro_anual ya trae
-- pib_percapita_nominal_usd fusionado desde la Semana 4, en vez
-- de vivir en una tabla separada como en el DDL original).
-- Fuente de P1 (evolución de la economía ecuatoriana).
-- ------------------------------------------------------------
CREATE VIEW IF NOT EXISTS gold_pib_tendencia AS
SELECT
    t.anio,
    m.pib_real_musd,
    m.pib_percapita_nominal_usd,
    m.variacion_pib_pct,
    CASE
        WHEN m.variacion_pib_pct > 2 THEN 'Crecimiento fuerte'
        WHEN m.variacion_pib_pct > 0 THEN 'Crecimiento moderado'
        WHEN m.variacion_pib_pct = 0 THEN 'Estancamiento'
        ELSE 'Contracción'
    END AS clasificacion
FROM fact_macro_anual m
JOIN dim_tiempo t ON t.id_tiempo = m.id_tiempo
ORDER BY t.anio;

-- ------------------------------------------------------------
-- TODO 1: gold_empleo_tendencia
-- Tasa de desempleo trimestral histórica (ENEMDU).
-- Se agrupa por trimestre porque ENEMDU reporta rondas mensuales,
-- no trimestrales; el trimestre se deriva del mes en 'periodo'
-- (formato 'mmm-aa', ej. 'dic-24').
-- ------------------------------------------------------------
CREATE VIEW IF NOT EXISTS gold_empleo_tendencia AS
SELECT
    anio,
    CASE
        WHEN substr(periodo, 1, 3) IN ('ene', 'feb', 'mar') THEN 1
        WHEN substr(periodo, 1, 3) IN ('abr', 'may', 'jun') THEN 2
        WHEN substr(periodo, 1, 3) IN ('jul', 'ago', 'sep') THEN 3
        ELSE 4
    END AS trimestre,
    'Desempleo (%)' AS indicador,
    ROUND(AVG(total_nacional), 2) AS tasa_nacional,
    ROUND(AVG(total_urbana), 2)  AS tasa_urbana,
    ROUND(AVG(total_rural), 2)   AS tasa_rural
FROM fact_empleo
WHERE indicador = 'Desempleo (%)'
GROUP BY anio, trimestre
ORDER BY anio, trimestre;

-- ------------------------------------------------------------
-- TODO 2: gold_petroleo_30dias
-- Promedio móvil de 30 días del precio WTI (ventana de filas,
-- no de fechas de calendario: asume una fila por día hábil).
-- ------------------------------------------------------------
CREATE VIEW IF NOT EXISTS gold_petroleo_30dias AS
SELECT
    fecha,
    precio_petroleo_wti,
    riesgo_pais_pb,
    ROUND(
        AVG(precio_petroleo_wti) OVER (
            ORDER BY fecha ROWS BETWEEN 29 PRECEDING AND CURRENT ROW
        ), 2
    ) AS promedio_movil_30d
FROM fact_indicadores_diarios
ORDER BY fecha;

-- ------------------------------------------------------------
-- TODO 3: gold_empresas_provincia
-- Empresas activas e ingresos por provincia (Supercías).
-- ------------------------------------------------------------
CREATE VIEW IF NOT EXISTS gold_empresas_provincia AS
SELECT
    g.provincia,
    COUNT(DISTINCT CASE WHEN e.situacion_legal = 'ACTIVA' THEN e.ruc END) AS empresas_activas,
    ROUND(SUM(r.ingresos_totales), 2) AS ingresos_totales,
    ROUND(SUM(r.activos), 2)          AS activos_totales
FROM fact_ranking_empresarial r
JOIN dim_empresas e   ON e.ruc = r.ruc
JOIN dim_geografia g  ON g.id_geografia = r.id_geografia
GROUP BY g.provincia
ORDER BY empresas_activas DESC;

-- ------------------------------------------------------------
-- TODO 4: gold_bachilleres_vs_empresas  (pregunta P3 del dashboard)
-- Cruce MINEDUC + Supercías por provincia: bachilleres de 3er año
-- (año lectivo más reciente) vs. empresas activas.
-- ------------------------------------------------------------
CREATE VIEW IF NOT EXISTS gold_bachilleres_vs_empresas AS
WITH bachilleres AS (
    SELECT
        g.provincia,
        SUM(f.bachilleres_3er_anio) AS bachilleres_3er_anio
    FROM fact_oferta_academica f
    JOIN dim_geografia g ON g.id_geografia = f.id_geografia
    WHERE f.anio_lectivo = (SELECT MAX(anio_lectivo) FROM fact_oferta_academica)
    GROUP BY g.provincia
)
SELECT
    b.provincia,
    b.bachilleres_3er_anio,
    COALESCE(e.empresas_activas, 0) AS empresas_activas,
    ROUND(
        CAST(b.bachilleres_3er_anio AS REAL) / NULLIF(e.empresas_activas, 0), 2
    ) AS bachilleres_por_empresa
FROM bachilleres b
LEFT JOIN gold_empresas_provincia e ON e.provincia = b.provincia
ORDER BY bachilleres_por_empresa DESC;
