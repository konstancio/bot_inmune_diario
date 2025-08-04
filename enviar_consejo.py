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

# ➕ Función para detectar ubicación con fallback a Málaga
def obtener_ubicacion():
    try:
        ip = requests.get("https://api.ipify.org").text
        response = requests.get(f"https://ipapi.co/{ip}/json/")
        data = response.json()

        ciudad = data.get("city")
        lat = data.get("latitude")
        lon = data.get("longitude")

        if ciudad.lower() != "málaga":
            raise ValueError("Ubicación distinta de Málaga")

        print(f"✅ Ubicación detectada por IP: {ciudad} ({lat}, {lon})")

    except:
        print("⚠️ Error o ubicación no deseada (Ubicación distinta de Málaga). Usando fallback a Málaga.")
        ciudad = "Málaga"
        geolocator = Nominatim(user_agent="bot_inmune_diario")
        location = geolocator.geocode(ciudad)
        lat = location.latitude
        lon = location.longitude

    try:
        tf = TimezoneFinder()
        zona_horaria = tf.timezone_at(lat=lat, lng=lon)
    except:
        zona_horaria = "Europe/Madrid"

    print(f"✅ Ubicación final: {ciudad} ({lat:.4f}, {lon:.4f}) - Zona horaria: {zona_horaria}")

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
dia_semana = datetime.datetime.now().weekday()

# Elegir consejo aleatorio (con texto + referencia)
consejo_dia = random.sample(consejos[dia_semana], 2)
texto_consejo = next(x for x in consejo_dia if not x.startswith("📚"))
referencia = next(x for x in consejo_dia if x.startswith("📚"))

# Calcular intervalos solares seguros
intervalos = calcular_intervalos_optimos(lat, lon, datetime.datetime.now(), timezone_str)
antes, despues = intervalos

# Construir mensaje
mensaje = f"{texto_consejo}\n\n{referencia}\n\n🌞 Intervalos solares seguros para producir vit. D hoy ({ubicacion['ciudad']}):\n"

if antes:
    mensaje += f"🌅 Mañana: {antes[0]} - {antes[-1]}\n"
if despues:
    mensaje += f"🌇 Tarde: {despues[0]} - {despues[-1]}"
if not antes and not despues:
    mensaje += "Hoy no hay intervalos seguros con el Sol entre 30° y 40° de elevación."

# ✉️ Enviar por Telegram
async def enviar_mensaje_telegram(texto):
    bot_token = os.getenv("BOT_TOKEN")
    chat_id = os.getenv("CHAT_ID")
    if not bot_token or not chat_id:
        print("Faltan BOT_TOKEN o CHAT_ID")
        return
    try:
        bot = Bot(token=bot_token)
        await bot.send_message(chat_id=chat_id, text=texto)
        print("✅ Mensaje enviado por Telegram correctamente.")
    except Exception as e:
        print(f"❌ Error al enviar mensaje: {e}")

# Ejecutar
asyncio.run(enviar_mensaje_telegram(mensaje))

