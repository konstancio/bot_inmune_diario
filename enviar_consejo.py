import json
from astral import LocationInfo
from astral.sun import sun, noon
from astral.location import Observer
from datetime import datetime, timedelta
import pytz
from telegram import Bot
import random

# Cargar ubicación
with open("ubicacion.json") as f:
    datos = json.load(f)

lat = datos["latitud"]
lon = datos["longitud"]
ciudad = datos["ciudad"]

# Configurar zona horaria
tz = pytz.timezone("Europe/Madrid")

# Crear objeto LocationInfo y observer
loc = LocationInfo(name=ciudad, region="España", timezone="Europe/Madrid", latitude=lat, longitude=lon)
ahora = datetime.now(tz)
intervalo = timedelta(minutes=1)
obs = Observer(latitude=lat, longitude=lon)
mediodia = noon(observer=obs, tzinfo=tz, date=ahora.date())

# Cargar consejos desde JSON
with open("consejos_diarios.json") as f:
    consejos = json.load(f)

dia_semana = ahora.strftime("%A").lower()
numero_dia = ahora.day
indice = (numero_dia - 1) % len(consejos.get(dia_semana, []))
consejo_dia = consejos.get(dia_semana, ["No hay consejo disponible."])[indice]

# Calcular horas de sol entre 30° y 40° antes y después del mediodía
franjas = {"mañana": [], "tarde": []}

hora = ahora.replace(hour=5, minute=0, second=0, microsecond=0)
fin = ahora.replace(hour=21, minute=0)

while hora <= fin:
    elev = loc.solar_elevation(hora)
    if 30 <= elev <= 40:
        if hora < mediodia:
            franjas["mañana"].append(hora)
        elif hora > mediodia:
            franjas["tarde"].append(hora)
    hora += intervalo

def formatear_franja(franja):
    if not franja:
        return "no hay franja solar entre 30° y 40°"
    return f"entre las {franja[0].strftime('%H:%M')} y las {franja[-1].strftime('%H:%M')}"

franja_manana = formatear_franja(franjas["mañana"])
franja_tarde = formatear_franja(franjas["tarde"])

# Construir mensaje
mensaje = f"""
☀️ *Consejo inmunológico diario*

Hoy en *{ciudad}*, el Sol estará entre 30° y 40° de elevación:

🌅 Por la mañana: {franja_manana}
🌇 Por la tarde: {franja_tarde}

📌 Consejo del día:
{consejo_dia}

🕘 Repite esto a diario y tu sistema inmune se sincronizará con el Sol 🌿
"""

# Enviar mensaje
TOKEN = 'TU_TOKEN'
USER_ID = TU_ID

bot = Bot(token=TOKEN)
bot.send_message(chat_id=USER_ID, text=mensaje, parse_mode="Markdown")