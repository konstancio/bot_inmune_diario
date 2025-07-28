
import json
from datetime import datetime, timedelta
from astral import LocationInfo
from astral.sun import elevation, noon
from telegram import Bot

# Configuración
TOKEN = '7254029750:AAG-ukM8YXZ-9Fq7YhcMj2A8ny6Gz92TQvE'
USER_ID = 7678609

# Cargar ubicación
with open("ubicacion.json") as f:
    datos = json.load(f)
ciudad = datos["ciudad"]
lat = datos["latitud"]
lon = datos["longitud"]

# Obtener franja solar entre 30 y 40º antes y después del mediodía
from astral.location import Location
from zoneinfo import ZoneInfo

loc = Location(("", ciudad, lat, lon, "Europe/Madrid", 0))
tz = ZoneInfo("Europe/Madrid")
ahora = datetime.now(tz)
h_ini = ahora.replace(hour=5, minute=0, second=0, microsecond=0)
h_fin = ahora.replace(hour=21, minute=0, second=0)

intervalo = timedelta(minutes=1)
franjas = {"mañana": [], "tarde": []}
mediodia = noon(loc.observer, tzinfo=tz, date=ahora.date())

hora = h_ini
while hora <= h_fin:
    angulo = loc.solar_elevation(hora)
    if 30 <= angulo <= 40:
        if hora < mediodia:
            franjas["mañana"].append(hora)
        elif hora > mediodia:
            franjas["tarde"].append(hora)
    hora += intervalo

def resumen_franja(lista):
    if lista:
        return f"{lista[0].strftime('%H:%M')} a {lista[-1].strftime('%H:%M')}"
    return None

f_manana = resumen_franja(franjas["mañana"])
f_tarde = resumen_franja(franjas["tarde"])

franja_texto = ""
if f_manana:
    franja_texto += f"🔹 Mañana: de {f_manana}\n"
if f_tarde:
    franja_texto += f"🔹 Tarde: de {f_tarde}"

if not franja_texto:
    franja_texto = "Hoy no hay franjas seguras entre 30° y 40°."

# Cargar consejo del día
with open("consejos.json", encoding="utf-8") as f:
    consejos = json.load(f)

# Calcular índice del consejo (1 al 28)
inicio = datetime(2025, 7, 29)
hoy = datetime.now(tz).date()
idx = (hoy - inicio.date()).days + 1
consejo = consejos.get(str(idx), {"tema": "sin tema", "texto": "No hay consejo disponible.", "referencia": ""})

# Mensaje
mensaje = f"""☀️ *Consejo inmunológico diario*

Hoy en *{ciudad}*, el Sol estará entre 30° y 40°:
{franja_texto}

📌 *Tema del día*: {consejo['tema']}
{consejo['texto']}

📖 {consejo['referencia']}
"""

# Enviar mensaje
bot = Bot(token=TOKEN)
bot.send_message(chat_id=USER_ID, text=mensaje, parse_mode="Markdown")
