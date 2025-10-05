# maintenance.py — refrescar collation y reindexar con logs claros

from usuarios_repo import _get_conn

SQL_INFO = """
SELECT current_database() AS db,
       datcollate,
       datctype,
       collversion
FROM pg_database
WHERE datname = current_database();
"""

def main():
    try:
        with _get_conn() as conn, conn.cursor() as cur:
            print("🔧 Iniciando mantenimiento…")
            print("ℹ️  Estado ANTES:")
            cur.execute(SQL_INFO)
            print(cur.fetchone())

            # 1) REFRESH COLLATION VERSION
            try:
                cur.execute('ALTER DATABASE CURRENT DATABASE REFRESH COLLATION VERSION;')
                print("✅ REFRESH COLLATION VERSION ejecutado.")
            except Exception as e:
                print(f"⚠️ No se pudo REFRESH COLLATION VERSION (permiso u otra razón): {e}")

            # 2) Mostrar estado DESPUÉS
            print("ℹ️  Estado DESPUÉS:")
            cur.execute(SQL_INFO)
            print(cur.fetchone())

            # 3) Reindexar lo importante
            try:
                cur.execute('REINDEX TABLE subscribers;')
                print("✅ REINDEX TABLE subscribers ok.")
            except Exception as e:
                print(f"⚠️ No se pudo REINDEX TABLE subscribers: {e}")

            # 4) (Opcional) Reindexar todo — comenta si no lo quieres
            try:
                cur.execute('REINDEX DATABASE CURRENT DATABASE;')
                print("✅ REINDEX DATABASE completo ok.")
            except Exception as e:
                print(f"⚠️ No se pudo REINDEX DATABASE completo: {e}")

        print("🎉 Mantenimiento terminado.")
    except Exception as e:
        print(f"❌ Error general de mantenimiento: {e}")

if __name__ == "__main__":
    main()
