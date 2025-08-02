
import datetime
import random
from consejos_diarios import consejos
from calcular_intervalos import calcular_intervalos_optimos
from geopy.geocoders import Nominatim
from timezonefinder import TimezoneFinder
import requests
from telegram import Bot
from telegram.request import HTTPXRequest
import asyncio
from telegram import Bot

import os

# Función para detectar ubicación con fallback a Málaga
def obtener_ubicacion():
    try:
        ip = requests.get("https://api.ipify.org").text
        response = requests.get(f"https://ipapi.co/{ip}/json/")
        data = response.json()

        ciudad = data.get("city")
        lat = data.get("latitude")
        lon = data.get("longitude")

        if not ciudad or not lat or not lon:
            raise ValueError("Datos incompletos desde IP. Se usará fallback.")

        print(f"✅ Ubicación detectada: {ciudad} ({lat}, {lon})")

    except Exception as e:
        print(f"⚠️ Error al obtener ubicación por IP: {e}")
        print("🔁 Usando ubicación por defecto: Málaga")
        ciudad = "Málaga"
        geolocator = Nominatim(user_agent="bot_inmune_diario")
        location = geolocator.geocode(ciudad)

        if not location:
            print("❌ No se pudo geolocalizar Málaga. Abortando.")
            return None

        lat = location.latitude
        lon = location.longitude
        print(f"✅ Ubicación por defecto: {ciudad} ({lat}, {lon})")

    try:
        tf = TimezoneFinder()
        zona_horaria = tf.timezone_at(lat=lat, lng=lon)
    except Exception as e:
        print(f"❌ Error al obtener la zona horaria: {e}")
        zona_horaria = "Europe/Madrid"

    print(f"✅ Ubicación guardada: {ciudad} ({lat}, {lon}) - Zona horaria: {zona_horaria}")

    return {
        "latitud": lat,
        "longitud": lon,
        "ciudad": ciudad,
        "timezone": zona_horaria
    }

# Obtener ubicación
ubicacion = obtener_ubicacion()

if not ubicacion:
    print("Error: No se pudo obtener la ubicación correctamente.")
    exit()

lat = ubicacion["latitud"]
lon = ubicacion["longitud"]
timezone_str = ubicacion["timezone"]

# Día de la semana actual
hoy = datetime.datetime.now()
dia_semana = hoy.weekday()  # lunes = 0, domingo = 6

# Elegir consejo aleatorio según el día
consejo_dia = random.choice(consejos[dia_semana])

# Calcular intervalos óptimos de exposición solar
intervalos = calcular_intervalos_optimos(lat, lon, hoy, timezone_str)
antes, despues = intervalos

# Construir mensaje
mensaje = f"{consejo_dia}\n\n☀️ Intervalos solares seguros para hoy ({ubicacion['ciudad']}):\n"

if antes:
    mensaje += "🌅 Mañana:\n"
    for hora in antes:
        mensaje += f"🕒 {hora}\n"

if despues:
    mensaje += "🌇 Tarde:\n"
    for hora in despues:
        mensaje += f"🕒 {hora}\n"

if not antes and not despues:
    mensaje += "Hoy no hay intervalos seguros con el Sol entre 30° y 40° de elevación."

from telegram import Bot
import os

# Obtener variables de entorno globalmente
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

# Llamada final para enviar el mensaje
enviar_mensaje_telegram(mensaje)


