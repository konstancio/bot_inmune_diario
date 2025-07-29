
import json
from datetime import datetime
from pytz import timezone
from astral.sun import noon
from astral import Observer

# Cargar datos
with open("consejos.json", "r", encoding="utf-8") as f:
    consejos = json.load(f)

with open("ubicacion.json", "r", encoding="utf-8") as f:
    ubicacion = json.load(f)

# Obtener fecha y zona horaria
tz = timezone("Europe/Madrid")
ahora = datetime.now(tz)
dia_semana = ahora.strftime("%A").lower()
numero_dia = ahora.day

# Verificar que existen consejos para el día de la semana
if dia_semana not in consejos or not consejos[dia_semana]:
    raise ValueError(f"No hay consejos para el día: {dia_semana}")

# Seleccionar consejo
indice = (numero_dia - 1) % len(consejos[dia_semana])
consejo = consejos[dia_semana][indice]

# Calcular franja segura solar
lat, lon = ubicacion["lat"], ubicacion["lon"]
obs = Observer(latitude=lat, longitude=lon)
mediodia = noon(observer=obs, tzinfo=tz, date=ahora.date())

# Simulación del envío (se reemplaza por bot.send_message en producción)
print(f"Consejo del día ({dia_semana.title()}):\n{consejo}")
print(f"Hora solar local aproximada (mediodía): {mediodia.strftime('%H:%M')}")
