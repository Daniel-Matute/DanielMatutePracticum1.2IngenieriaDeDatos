"""
integrar_rpa_empresas_ranking.py
==================================
Reemplaza dim_empresas y fact_ranking_empresarial en pipeline_utpl.db
con los datos actualizados de macroentorno_silver_RPA.db.

Por que estos dos primero: son los datasets donde RPA es estrictamente
mejor (mas filas, datos mas recientes '2026-07') sin perdida de
informacion frente a lo que ya tenias. Macro/Empleo/Oferta academica/VAB
quedan para un segundo script porque tienen gaps o necesitan combinarse
con el historico en vez de reemplazar.

Detalle clave: el ranking de RPA (fact_ranking_empresarial en la base
silver) NO trae ruc ni provincia directamente, solo 'expediente'. Hay
que cruzarlo con el directorio de empresas de RPA para recuperarlos,
igual que hiciste en Semana 2-3 con bi_ranking.csv + directorio_companias.
"""
import sqlite3
import unicodedata

DB_PRINCIPAL = 'pipeline_utpl.db'
DB_RPA = 'macroentorno_silver_RPA.db'


def normalizar_texto(valor):
    """Mayusculas, sin tildes. Misma convencion usada en migrar_modelo_relacional.py
    de Semana 4, para que provincia/canton calcen con dim_geografia."""
    if valor is None:
        return None
    texto = str(valor).strip().upper()
    texto = unicodedata.normalize('NFKD', texto).encode('ascii', 'ignore').decode('ascii')
    return texto


def a_numero(valor):
    """Convierte TEXT de Oracle/RPA a float, tolerando None, '', 'None', comas."""
    if valor is None:
        return None
    s = str(valor).strip()
    if s == '' or s.lower() == 'none':
        return None
    try:
        return float(s.replace(',', ''))
    except ValueError:
        return None


def migrar_empresas(conn_rpa, conn_ppal):
    print("\n--- Migrando dim_empresas (RPA -> pipeline_utpl.db) ---")
    cur_rpa = conn_rpa.cursor()
    cur_rpa.execute("""
        SELECT ruc, expediente, nombre, situacion_legal, provincia, canton,
               ciiu_nivel1, ciiu_nivel6, fecha_constitucion, ultimo_balance_anio
        FROM fact_directorio_companias
    """)
    filas = cur_rpa.fetchall()
    print(f"  Leidas {len(filas)} filas de fact_directorio_companias (RPA)")

    filas_norm = []
    sin_ruc = 0
    for ruc, expediente, nombre, situacion, provincia, canton, ciiu_n1, ciiu_n6, fecha, balance in filas:
        # dim_empresas.ruc es UNIQUE. Empresas disueltas/liquidadas a veces
        # no tienen RUC asignado (confirmado: 4675 filas, 2.08% del total,
        # 0 rucs reales duplicados). Sin RUC no hay forma confiable de
        # identificarlas en este modelo, asi que se excluyen (igual criterio
        # que el ~21% de id_geografia NULL ya documentado en Semana 4).
        if ruc is None or str(ruc).strip() == '':
            sin_ruc += 1
            continue
        filas_norm.append((
            ruc, expediente, nombre, situacion,
            normalizar_texto(provincia), normalizar_texto(canton),
            ciiu_n1, ciiu_n6, fecha, balance
        ))

    print(f"  -> Excluidas por RUC vacio/NULL: {sin_ruc} ({sin_ruc/len(filas)*100:.2f}%)")
    print(f"  -> Filas listas para insertar: {len(filas_norm)}")

    cur_ppal = conn_ppal.cursor()
    cur_ppal.execute("DELETE FROM dim_empresas")
    cur_ppal.executemany("""
        INSERT INTO dim_empresas
        (ruc, expediente, nombre, situacion_legal, provincia, canton,
         ciiu_n1, ciiu_n6, fecha_constitucion, ultimo_balance)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, filas_norm)
    conn_ppal.commit()

    cur_ppal.execute("SELECT COUNT(*) FROM dim_empresas")
    total = cur_ppal.fetchone()[0]
    print(f"  -> dim_empresas ahora tiene {total} filas (antes: 212106)")
    return total


def migrar_ranking(conn_rpa, conn_ppal):
    print("\n--- Migrando fact_ranking_empresarial (RPA -> pipeline_utpl.db) ---")

    # 1) Traer el mapa expediente -> (ruc, provincia) desde el directorio RPA
    #    OJO: excluyo aqui tambien las empresas sin ruc (mismo criterio que
    #    en migrar_empresas), porque esas ya no existen en dim_empresas y
    #    dejarian el ranking con un ruc huerfano.
    cur_rpa = conn_rpa.cursor()
    cur_rpa.execute("SELECT expediente, ruc, provincia FROM fact_directorio_companias")
    mapa_expediente = {}
    for expediente, ruc, provincia in cur_rpa.fetchall():
        if ruc is None or str(ruc).strip() == '':
            continue
        mapa_expediente[expediente] = (ruc, normalizar_texto(provincia))
    print(f"  Mapa expediente->ruc/provincia construido ({len(mapa_expediente)} empresas con ruc valido)")

    # 2) Traer el mapa provincia -> id_geografia desde dim_geografia
    #    (uso el primer canton de cada provincia como aproximacion nacional;
    #    fact_ranking_empresarial en el modelo actual ya funciona asi, a nivel provincia)
    cur_ppal = conn_ppal.cursor()
    cur_ppal.execute("SELECT id_geografia, provincia FROM dim_geografia")
    mapa_geografia = {}
    for id_geo, provincia in cur_ppal.fetchall():
        prov_norm = normalizar_texto(provincia)
        if prov_norm not in mapa_geografia:
            mapa_geografia[prov_norm] = id_geo
    print(f"  Mapa provincia->id_geografia construido ({len(mapa_geografia)} provincias)")

    # 3) Leer el ranking de RPA y armar las filas finales
    cur_rpa.execute("""
        SELECT expediente, anio, ingresos_totales, activos, patrimonio,
               utilidad_neta, ciiu_n6
        FROM fact_ranking_empresarial
    """)

    filas_finales = []
    sin_expediente = 0
    sin_geografia = 0
    total_leidas = 0

    for expediente, anio, ingresos_totales, activos, patrimonio, utilidad_neta, ciiu_n6 in cur_rpa:
        total_leidas += 1
        info_empresa = mapa_expediente.get(expediente)
        if info_empresa is None:
            sin_expediente += 1
            continue
        ruc, provincia = info_empresa
        id_geo = mapa_geografia.get(provincia)
        if id_geo is None:
            sin_geografia += 1

        filas_finales.append((
            ruc, id_geo, a_numero(anio),
            a_numero(ingresos_totales), a_numero(activos),
            a_numero(patrimonio), a_numero(utilidad_neta), ciiu_n6
        ))

    print(f"  Leidas {total_leidas} filas de fact_ranking_empresarial (RPA)")
    print(f"  -> Sin match de expediente en directorio: {sin_expediente} ({sin_expediente/total_leidas*100:.2f}%)")
    print(f"  -> Con expediente pero sin match de provincia->id_geografia: {sin_geografia} ({sin_geografia/total_leidas*100:.2f}%)")
    print(f"  -> Filas listas para insertar: {len(filas_finales)}")

    cur_ppal.execute("DELETE FROM fact_ranking_empresarial")
    cur_ppal.executemany("""
        INSERT INTO fact_ranking_empresarial
        (ruc, id_geografia, anio, ingresos_totales, activos, patrimonio, utilidad_neta, ciiu_n6)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, filas_finales)
    conn_ppal.commit()

    cur_ppal.execute("SELECT COUNT(*) FROM fact_ranking_empresarial")
    total = cur_ppal.fetchone()[0]
    print(f"  -> fact_ranking_empresarial ahora tiene {total} filas (antes: 1521018)")
    return total


if __name__ == '__main__':
    conn_rpa = sqlite3.connect(DB_RPA)
    conn_ppal = sqlite3.connect(DB_PRINCIPAL)

    try:
        # IMPORTANTE: dejamos la conexion sin autocommit por defecto de sqlite3
        # esta bien, cada migrar_* hace su propio commit al final.
        migrar_empresas(conn_rpa, conn_ppal)
        migrar_ranking(conn_rpa, conn_ppal)

        print("\n--- VERIFICACION FINAL ---")
        cur = conn_ppal.cursor()
        cur.execute("PRAGMA foreign_key_check")
        violaciones = cur.fetchall()
        print(f"Violaciones de FK (PRAGMA foreign_key_check): {len(violaciones)}")
        if violaciones:
            print("  ATENCION: hay violaciones de integridad referencial, revisar antes de usar en Power BI.")
            for v in violaciones[:10]:
                print("   ", v)

        print("\nMigracion de Empresas y Ranking completada.")
    finally:
        conn_rpa.close()
        conn_ppal.close()
