# maintenance.py — refresca la versión de collation en la base de datos Railway
# y reindexa la tabla "subscribers" si es necesario.

from usuarios_repo import _get_conn

def main():
    try:
        with _get_conn() as conn, conn.cursor() as cur:
            print("🔧 Ejecutando mantenimiento de base de datos...")
            cur.execute('ALTER DATABASE "railway" REFRESH COLLATION VERSION;')
            print("✅ Collation version actualizada correctamente.")
            
            # Reindexar solo la tabla principal
            cur.execute('REINDEX TABLE subscribers;')
            print("✅ Tabla 'subscribers' reindexada correctamente.")
            
        print("🎉 Mantenimiento completado sin errores.")
    except Exception as e:
        print(f"⚠️ Error durante el mantenimiento: {e}")

if __name__ == "__main__":
    main()