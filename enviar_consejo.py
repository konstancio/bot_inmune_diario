import datetime
from configuracion_ubicacion import obtener_ubicacion
from calcular_intervalos import calcular_intervalos_optimos
from consejos_diarios import consejos
import random

# Obtener ubicación actual y zona horaria
ubicacion = obtener_ubicacion()

if not ubicacion:
    print("Error: No se pudo obtener la ubicación correctamente.")
    exit()

lat = ubicacion["latitud"]
lon = ubicacion["longitud"]
timezone_str = ubicacion["timezone"]

# Obtener fecha de hoy (solo fecha, no datetime completo)
hoy = datetime.date.today()

# Calcular los intervalos óptimos
intervalos_antes, intervalos_despues = calcular_intervalos_optimos(lat, lon, hoy, timezone_str)

# Día de la semana actual (0 = lunes, 6 = domingo)
dia_semana = hoy.weekday()

# Seleccionar consejo para el día actual
consejos_del_dia = consejos.get(dia_semana, [])
if consejos_del_dia:
    consejo = random.choice(consejos_del_dia)
else:
    consejo = "Hoy no hay consejo disponible."

# Mostrar salida
print(f"📍 Ubicación detectada: {ubicacion['ciudad']} ({lat}, {lon}) - Zona horaria: {timezone_str}")
print(f"📅 Fecha: {hoy.strftime('%Y-%m-%d')} - Día de la semana: {['Lun','Mar','Mié','Jue','Vie','Sáb','Dom'][dia_semana]}")
print(f"\n🌞 Intervalos óptimos de exposición solar:\n - Antes del mediodía: {intervalos_antes}\n - Después del mediodía: {intervalos_despues}")
print(f"\n🧬 Consejo del día:\n{consejo}")


