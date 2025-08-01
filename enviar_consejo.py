import datetime
import random
from consejos_diarios import consejos
from calcular_intervalos import calcular_intervalos_optimos
from telegram_send import send
from geopy.geocoders import Nominatim
from timezonefinder import TimezoneFinder
import requests

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

# Obtener ubicación al arrancar
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

# Construir mensaje
mensaje = f"{consejo_dia}\n\n☀️ Intervalos solares seguros para hoy ({ubicacion['ciudad']}):\n"

if intervalos:
    for inicio, fin in intervalos:
        mensaje += f"🕒 {inicio.strftime('%H:%M')} - {fin.strftime('%H:%M')}\n"
else:
    mensaje += "Hoy no hay intervalos seguros con el Sol entre 30° y 40° de elevación."

# Enviar mensaje por Telegram
from telegram import Bot
import os

def enviar_mensaje_telegram(texto):
    bot_token = os.getenv("BOT_TOKEN")
    chat_id = os.getenv("CHAT_ID")

    if not bot_token or not chat_id:
        print("Faltan BOT_TOKEN o CHAT_ID")
        return

    bot = Bot(token=bot_token)
    bot.send_message(chat_id=chat_id, text=texto)




