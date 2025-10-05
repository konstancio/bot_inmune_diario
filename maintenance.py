# maintenance.py — collation OK + reindex robusto

from usuarios_repo import _get_conn

SQL_INFO = """
SELECT datname AS db, datcollate, datctype, datcollversion
FROM pg_database WHERE datname = current_database();
"""

def main():
    try:
        with _get_conn() as conn, conn.cursor() as cur:
            print("🔧 Iniciando mantenimiento…")
            cur.execute("SELECT current_database();")
            dbname = cur.fetchone()[0]
            print(f"ℹ️  Base de datos detectada: {dbname}")

            print("ℹ️  Estado ANTES:")
            cur.execute(SQL_INFO); print(cur.fetchone())

            # Ya lo hiciste antes, pero por si vuelves a lanzar el script:
            try:
                cur.execute(f'ALTER DATABASE "{dbname}" REFRESH COLLATION VERSION;')
                print("✅ REFRESH COLLATION VERSION ejecutado.")
            except Exception as e:
                print(f"⚠️ REFRESH COLLATION VERSION no se pudo (ok ignorar si ya está): {e}")

            print("ℹ️  Estado DESPUÉS:")
            cur.execute(SQL_INFO); print(cur.fetchone())

            # --- REINDEX TABLE subscribers (si existe) ---
            try:
                cur.execute("SELECT to_regclass('public.subscribers');")
                exists = cur.fetchone()[0] is not None
                if exists:
                    cur.execute("REINDEX TABLE public.subscribers;")
                    print("✅ REINDEX TABLE public.subscribers ok.")
                else:
                    print("ℹ️  Tabla public.subscribers no existe; se omite.")
            except Exception as e:
                print(f"⚠️ REINDEX TABLE public.subscribers falló: {e}")
                try:
                    conn.rollback()
                    print("ℹ️  rollback ok (continuamos).")
                except Exception:
                    pass

            # --- REINDEX DATABASE completo (opcional) ---
            try:
                cur.execute(f'REINDEX DATABASE "{dbname}";')
                print("✅ REINDEX DATABASE completo ok.")
            except Exception as e:
                print(f"⚠️ REINDEX DATABASE falló (puede omitirse): {e}")
                try:
                    conn.rollback()
                except Exception:
                    pass

        print("🎉 Mantenimiento terminado.")
    except Exception as e:
        print(f"❌ Error general de mantenimiento: {e}")

if __name__ == "__main__":
    main()
