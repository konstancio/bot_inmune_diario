import datetime
import random
from consejos_diarios import consejos
from calcular_intervalos import calcular_intervalos_optimos
from geopy.geocoders import Nominatim
from timezonefinder import TimezoneFinder
import requests
from telegram import Bot
import asyncio
import os

# Obtener ciudad desde variable de entorno (forzamos Málaga)
ciudad = os.environ.get("CIUDAD", "Málaga")
geolocalizador = Nominatim(user_agent="obtener_ubicacion")
ubicacion_geo = geolocalizador.geocode(ciudad)

if ubicacion_geo:
    lat = ubicacion_geo.latitude
    lon = ubicacion_geo.longitude
    tf = TimezoneFinder()
    timezone_str = tf.timezone_at(lat=lat, lng=lon)
    print(f"✅ Ubicación guardada: {ciudad} ({lat}, {lon}) - Zona horaria: {timezone_str}")
else:
    print("❌ No se pudo encontrar la ciudad. Abortando.")
    exit()

# Día actual
hoy = datetime.datetime.now()
dia_semana = hoy.weekday()  # lunes = 0, domingo = 6

# Consejo del día
consejo_dia = random.choice(consejos[dia_semana])

# Calcular intervalos solares óptimos
antes, despues = calcular_intervalos_optimos(lat, lon, hoy, timezone_str)

# Construcción del mensaje
mensaje = f"{consejo_dia}\n\n☀️ Intervalos solares seguros para producir vit. D hoy ({ciudad}):\n"

if antes:
    mensaje += f"🌅 Mañana: {antes[0].strftime('%H:%M')} – {antes[-1].strftime('%H:%M')}\n"
if despues:
    mensaje += f"🌇 Tarde: {despues[0].strftime('%H:%M')} – {despues[-1].strftime('%H:%M')}\n"

if not antes and not despues:
    mensaje += "Hoy no hay intervalos seguros con el Sol entre 30° y 40° de elevación."

# Envío a Telegram
bot_token = os.getenv("BOT_TOKEN")
chat_id = os.getenv("CHAT_ID")

def enviar_mensaje_telegram(texto):
    if not bot_token or not chat_id:
        print("Faltan BOT_TOKEN o CHAT_ID")
        return

    async def enviar():
        bot = Bot(token=bot_token)
        await bot.send_message(chat_id=chat_id, text=texto)

    try:
        asyncio.run(enviar())
        print("✅ Mensaje enviado por Telegram correctamente.")
    except Exception as e:
        print(f"❌ Error al enviar el mensaje por Telegram: {e}")

# Ejecutar envío
enviar_mensaje_telegram(mensaje)



