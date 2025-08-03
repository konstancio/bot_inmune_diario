import datetime
import random
import os
import asyncio
import requests
from telegram import Bot
from timezonefinder import TimezoneFinder
from geopy.geocoders import Nominatim

from consejos_diarios import consejos
from calcular_intervalos import calcular_intervalos_optimos

# ─────────────────────────────────────────────────────────────
# 📍 DETECCIÓN DE UBICACIÓN AUTOMÁTICA (CON FALLBACK A MÁLAGA)
# ─────────────────────────────────────────────────────────────

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

# ─────────────────────────────────────────────────────────────
# 🌍 OBTENER UBICACIÓN
# ─────────────────────────────────────────────────────────────

ubicacion = obtener_ubicacion()
if not ubicacion:
    print("Error: No se pudo obtener la ubicación correctamente.")
    exit()

lat = ubicacion["latitud"]
lon = ubicacion["longitud"]
timezone_str = ubicacion["timezone"]

# ─────────────────────────────────────────────────────────────
# 📅 CONSEJO DIARIO Y REFERENCIA
# ─────────────────────────────────────────────────────────────

hoy = datetime.datetime.now()
dia_semana = hoy.weekday()  # lunes = 0, domingo = 6
conjunto_consejo = random.sample(consejos[dia_semana], 2)
texto_consejo, referencia = conjunto_consejo

# ─────────────────────────────────────────────────────────────
# ☀️ CÁLCULO DE INTERVALOS SOLARES ÓPTIMOS
# ─────────────────────────────────────────────────────────────

antes, despues = calcular_intervalos_optimos(lat, lon, hoy, timezone_str)

# ─────────────────────────────────────────────────────────────
# 🧾 CONSTRUCCIÓN DEL MENSAJE
# ─────────────────────────────────────────────────────────────

mensaje = f"{texto_consejo}\n\n{referencia}\n\n☀️ Intervalos solares seguros para producir vit. D hoy ({ubicacion['ciudad']}):\n"

if antes:
    mensaje += f"🌅 Mañana: {antes[0]} – {antes[-1]}\n"
if despues:
    mensaje += f"🌇 Tarde: {despues[0]} – {despues[-1]}\n"
if not antes and not despues:
    mensaje += "Hoy no hay intervalos seguros con el Sol entre 30° y 40° de elevación."

# ─────────────────────────────────────────────────────────────
# 📲 ENVÍO POR TELEGRAM
# ─────────────────────────────────────────────────────────────

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

# ─────────────────────────────────────────────────────────────
# 🚀 EJECUCIÓN
# ─────────────────────────────────────────────────────────────

enviar_mensaje_telegram(mensaje)




