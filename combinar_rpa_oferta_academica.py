"""
combinar_rpa_oferta_academica.py
==================================
Agrega el periodo 2025-2026 (RPA, fact_mineduc_amie) a fact_oferta_academica,
SIN tocar el historico 2009-2024 que ya tienes. Es un INSERT adicional, no
un reemplazo (a diferencia de empresas/ranking).

Confirmado por diagnostico previo:
- Historico actual cubre 2009-2010 .. 2024-2025 (16 periodos, 322,602 filas)
- RPA trae exactamente 2025-2026 (periodo_lectivo='2025-2026 Inicio',
  anio_base=2025), sin solape -> combinacion segura.

Mapeo de columnas RPA -> modelo dimensional:
  institucion_amie                          -> amie
  institucion_nombre                        -> nombre_institucion
  institucion_sostenimiento                 -> sostenimiento
  estudiantes_resumen_total_estudiantes     -> total_estudiantes
  suma bachillerato 1er+2do+3er (m+h)       -> bachillerato
  suma bachillerato 3er_ano (m+h)           -> bachilleres_3er_anio
     (mismo fix de sumar M+H que ya se aplico en pipeline_rpa_fixed.py
      para el bug de bachilleres que solo contaba mujeres)
  institucion_provincia + institucion_canton -> id_geografia (via dim_geografia,
     normalizando texto: mayusculas sin tildes, igual que en empresas)
"""
import sqlite3
import unicodedata

DB_PRINCIPAL = 'pipeline_utpl.db'
DB_RPA = 'macroentorno_silver_RPA.db'
ANIO_LECTIVO_NUEVO = '2025-2026'


def normalizar_texto(valor):
    if valor is None:
        return None
    texto = str(valor).strip().upper()
    texto = unicodedata.normalize('NFKD', texto).encode('ascii', 'ignore').decode('ascii')
    return texto


def a_entero(valor):
    if valor is None:
        return 0
    try:
        return int(valor)
    except (ValueError, TypeError):
        return 0


def main():
    conn_ppal = sqlite3.connect(DB_PRINCIPAL)
    conn_rpa = sqlite3.connect(DB_RPA)

    cur_ppal = conn_ppal.cursor()

    # Guarda de idempotencia: si ya se corrio antes, no duplicar
    cur_ppal.execute(
        "SELECT COUNT(*) FROM fact_oferta_academica WHERE anio_lectivo = ?",
        (ANIO_LECTIVO_NUEVO,)
    )
    ya_existe = cur_ppal.fetchone()[0]
    if ya_existe > 0:
        print(f"El periodo {ANIO_LECTIVO_NUEVO} ya existe ({ya_existe} filas). "
              f"No se inserta de nuevo. Si quieres forzar, borra esas filas primero:")
        print(f"  DELETE FROM fact_oferta_academica WHERE anio_lectivo = '{ANIO_LECTIVO_NUEVO}';")
        conn_ppal.close()
        conn_rpa.close()
        return

    # Mapa provincia+canton -> id_geografia
    cur_ppal.execute("SELECT id_geografia, provincia, canton FROM dim_geografia")
    mapa_geo = {}
    for id_geo, provincia, canton in cur_ppal.fetchall():
        clave = (normalizar_texto(provincia), normalizar_texto(canton))
        mapa_geo[clave] = id_geo
    print(f"Mapa provincia+canton -> id_geografia construido ({len(mapa_geo)} combinaciones)")

    # Leer instituciones de RPA
    cur_rpa = conn_rpa.cursor()
    cur_rpa.execute("""
        SELECT institucion_amie, institucion_nombre, institucion_sostenimiento,
               institucion_provincia, institucion_canton,
               estudiantes_resumen_total_estudiantes,
               estudiantes_detallado_bachillerato_1er_ano_m,
               estudiantes_detallado_bachillerato_1er_ano_h,
               estudiantes_detallado_bachillerato_2do_ano_m,
               estudiantes_detallado_bachillerato_2do_ano_h,
               estudiantes_detallado_bachillerato_3er_ano_m,
               estudiantes_detallado_bachillerato_3er_ano_h
        FROM fact_mineduc_amie
    """)
    filas_rpa = cur_rpa.fetchall()
    print(f"Leidas {len(filas_rpa)} instituciones de RPA (periodo {ANIO_LECTIVO_NUEVO})")

    filas_finales = []
    sin_geografia = 0
    for (amie, nombre, sostenimiento, provincia, canton, total_est,
         b1m, b1h, b2m, b2h, b3m, b3h) in filas_rpa:

        clave = (normalizar_texto(provincia), normalizar_texto(canton))
        id_geo = mapa_geo.get(clave)
        if id_geo is None:
            sin_geografia += 1

        bachillerato_total = (a_entero(b1m) + a_entero(b1h) +
                               a_entero(b2m) + a_entero(b2h) +
                               a_entero(b3m) + a_entero(b3h))
        bachilleres_3ro = a_entero(b3m) + a_entero(b3h)

        filas_finales.append((
            id_geo, ANIO_LECTIVO_NUEVO, amie, nombre, sostenimiento,
            a_entero(total_est), bachillerato_total, bachilleres_3ro
        ))

    print(f"-> Sin match de provincia+canton en dim_geografia: {sin_geografia} "
          f"({sin_geografia/len(filas_rpa)*100:.2f}%)")
    print(f"-> Filas listas para insertar: {len(filas_finales)}")

    cur_ppal.executemany("""
        INSERT INTO fact_oferta_academica
        (id_geografia, anio_lectivo, amie, nombre_institucion, sostenimiento,
         total_estudiantes, bachillerato, bachilleres_3er_anio)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, filas_finales)
    conn_ppal.commit()

    cur_ppal.execute("SELECT COUNT(*) FROM fact_oferta_academica")
    total = cur_ppal.fetchone()[0]
    print(f"\n-> fact_oferta_academica ahora tiene {total} filas (antes: 322602, "
          f"+{total - 322602} del periodo nuevo)")

    cur_ppal.execute("PRAGMA foreign_key_check")
    violaciones = cur_ppal.fetchall()
    print(f"Violaciones de FK: {len(violaciones)}")

    conn_ppal.close()
    conn_rpa.close()


if __name__ == '__main__':
    main()
