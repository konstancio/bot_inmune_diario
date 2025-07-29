import json
from datetime import datetime, timedelta
import math
import os
from telegram import Bot
from astral.sun import sun
from astral.location import LocationInfo
from astral import sun as astral_sun

# Token y Chat ID desde variables de entorno por seguridad
import os
TOKEN = os.getenv("TELEGRAM_TOKEN")
USER_ID = os.getenv("TELEGRAM_USER_ID")

# Comprobar si ya se ha enviado hoy
FECHA_HOY = datetime.now().date().isoformat()
RUTA_FECHA = "ultimo_envio.txt"

if os.path.exists(RUTA_FECHA):
    with open(RUTA_FECHA, "r") as f:
        ultima_fecha = f.read().strip()
    if ultima_fecha == FECHA_HOY:
        print("Ya se envió el consejo hoy. Abortando envío.")
        exit()

# Cargar ubicación
with open("ubicacion.json") as f:
    datos = json.load(f)

lat = datos["latitud"]
lon = datos["longitud"]
ciudad = datos["ciudad"]

# Determinar hora solar entre 30° y 40° (dividido en mañana y tarde)
location = LocationInfo(name=ciudad, region="España", timezone="Europe/Madrid", latitude=lat, longitude=lon)
ahora = datetime.now(location.tzinfo)
intervalo = timedelta(minutes=1)

def obtener_franjas_30_40():
    inicio = ahora.replace(hour=5, minute=0, second=0, microsecond=0)
    fin = ahora.replace(hour=21, minute=0)
    elevaciones = []
    hora = inicio
    while hora <= fin:
        elev = location.solar_elevation(hora)
        if 30 <= elev <= 40:
            elevaciones.append(hora)
        hora += intervalo
    if not elevaciones:
        return "hoy no hay una franja solar entre 30° y 40°"
    mediodia = astral_sun.noon(location.observer, date=ahora.date(), tzinfo=location.timezone)
    mañana = [h for h in elevaciones if h < mediodia]
    tarde = [h for h in elevaciones if h > mediodia]
    partes = []
    if mañana:
        partes.append(f"por la mañana entre las {mañana[0].strftime('%H:%M')} y las {mañana[-1].strftime('%H:%M')}")
    if tarde:
        partes.append(f"por la tarde entre las {tarde[0].strftime('%H:%M')} y las {tarde[-1].strftime('%H:%M')}")
    return " y ".join(partes)

# Cargar consejos
with open("consejos.json") as f:
    consejos = json.load(f)

dia_semana = datetime.now().weekday()  # 0=lunes, 6=domingo
indice = datetime.now().toordinal() % len(consejos[str(dia_semana)])
consejo = consejos[str(dia_semana)][indice]

franja = obtener_franjas_30_40()

mensaje = f"""
☀️ *Consejo inmunológico diario ({FECHA_HOY})*

Hoy en *{ciudad}*, el Sol estará entre 30° y 40° de elevación {franja}.

{consejo}

🕘 Recuerda que una exposición breve, controlada y sin filtros activa tu sistema inmune de forma natural.
"""

# Enviar mensaje
bot = Bot(token=TOKEN)
bot.send_message(chat_id=USER_ID, text=mensaje, parse_mode="Markdown")

# Guardar la fecha del último envío
with open(RUTA_FECHA, "w") as f:
    f.write(FECHA_HOY)

print(f"Archivo de control creado: {RUTA_FECHA}")

print("Archivo guardado correctamente")

