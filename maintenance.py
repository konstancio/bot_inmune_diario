# maintenance.py — refresca collation y reindexa (con logs claros y tolerante a permisos)

from usuarios_repo import _get_conn

SQL_INFO = """
SELECT datname       AS db,
       datcollate,
       datctype,
       datcollversion
FROM pg_database
WHERE datname = current_database();
"""

def main():
    try:
        with _get_conn() as conn, conn.cursor() as cur:
            print("🔧 Iniciando mantenimiento…")

            # Nombre real de la BD actual
            cur.execute("SELECT current_database();")
            dbname = cur.fetchone()[0]
            print(f"ℹ️  Base de datos detectada: {dbname}")

            print("ℹ️  Estado ANTES:")
            cur.execute(SQL_INFO)
            print(cur.fetchone())

            # 1) REFRESH COLLATION VERSION
            try:
                cur.execute(f'ALTER DATABASE "{dbname}" REFRESH COLLATION VERSION;')
                print("✅ REFRESH COLLATION VERSION ejecutado.")
            except Exception as e:
                print(f"⚠️ No se pudo REFRESH COLLATION VERSION (permiso u otra razón): {e}")

            # 2) Mostrar estado DESPUÉS
            print("ℹ️  Estado DESPUÉS:")
            cur.execute(SQL_INFO)
            print(cur.fetchone())

            # 3) Reindexar la tabla principal (rápido)
            try:
                cur.execute("REINDEX TABLE IF EXISTS subscribers;")
                print("✅ REINDEX TABLE subscribers ok.")
            except Exception as e:
                print(f"⚠️ No se pudo REINDEX TABLE subscribers: {e}")

            # 4) Reindexar toda la BD (opcional; puede bloquear brevemente)
            try:
                cur.execute(f'REINDEX DATABASE "{dbname}";')
                print("✅ REINDEX DATABASE completo ok.")
            except Exception as e:
                print(f"⚠️ No se pudo REINDEX DATABASE completo: {e}")

        print("🎉 Mantenimiento terminado.")
    except Exception as e:
        print(f"❌ Error general de mantenimiento: {e}")

if __name__ == "__main__":
    main()
