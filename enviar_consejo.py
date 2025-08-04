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

import datetime
import requests

def obtener_nubosidad_horaria(lat, lon, timezone_str, fecha):
    """
    Devuelve lista de tuplas (hora: datetime, cloudcover: int, precip_prob: int)
    para el día 'fecha' en la zona horaria 'timezone_str'. Usa Open-Meteo (sin API key).
    """
    base = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": "cloudcover,precipitation_probability",
        "start_date": fecha.strftime("%Y-%m-%d"),
        "end_date": fecha.strftime("%Y-%m-%d"),
        "timezone": timezone_str,
    }
    r = requests.get(base, params=params, timeout=10)
    r.raise_for_status()
    data = r.json()
    tiempos = [datetime.datetime.fromisoformat(t) for t in data["hourly"]["time"]]
    covers = data["hourly"]["cloudcover"]
    precps = data["hourly"]["precipitation_probability"]
    return list(zip(tiempos, covers, precps))

def hora_hhmm_a_dt(hhmm, fecha):
    """Convierte 'HH:MM' a datetime (naive) en la fecha dada (misma tz local que Open-Meteo)."""
    h, m = map(int, hhmm.split(":"))
    return datetime.datetime(fecha.year, fecha.month, fecha.day, h, m)

def resumen_nubes(nubosidad_horaria, inicio_dt, fin_dt):
    """
    Calcula nubosidad media (%) y precip prob máx. (%) entre inicio_dt y fin_dt.
    Devuelve (etiqueta, media_nubes, max_precip) o None si no hay datos.
    """
    trozos = [(c, p) for (t, c, p) in nubosidad_horaria if inicio_dt <= t <= fin_dt]
    if not trozos:
        return None
    medias = sum(c for c, _ in trozos) / len(trozos)
    pmax = max(p for _, p in trozos)
    if medias <= 30:
        estado = "☀️ despejado"
    elif medias <= 70:
        estado = "⛅ variable"
    else:
        estado = "☁️ nuboso"
    return estado, round(medias), pmax


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
# Obtener nubosidad horaria para hoy
nubosidad_hoy = obtener_nubosidad_horaria(lat, lon, timezone_str, hoy.date())

# Construcción del mensaje
mensaje = f"{texto_consejo}\n\n{referencia}\n\n"
mensaje += f"🌞 Intervalos solares seguros para producir vit. D hoy ({ubicacion['ciudad']}):\n"

# Mañana
if antes:
    ini_m = hora_hhmm_a_dt(antes[0], hoy.date())
    fin_m = hora_hhmm_a_dt(antes[-1], hoy.date())
    nubes_m = resumen_nubes(nubosidad_horaria=nubosidad_hoy, inicio_dt=ini_m, fin_dt=fin_m)

    if nubes_m:
        estado_m, media_m, pmax_m = nubes_m
        mensaje += f"🌅 Mañana: {antes[0]} – {antes[-1]} ({estado_m}, nubes {media_m}%, lluvia {pmax_m}%)\n"
    else:
        mensaje += f"🌅 Mañana: {antes[0]} – {antes[-1]}\n"

# Tarde
if despues:
    ini_t = hora_hhmm_a_dt(despues[0], hoy.date())
    fin_t = hora_hhmm_a_dt(despues[-1], hoy.date())
    nubes_t = resumen_nubes(nubosidad_horaria=nubosidad_hoy, inicio_dt=ini_t, fin_dt=fin_t)

    if nubes_t:
        estado_t, media_t, pmax_t = nubes_t
        mensaje += f"🌇 Tarde: {despues[0]} – {despues[-1]} ({estado_t}, nubes {media_t}%, lluvia {pmax_t}%)\n"
    else:
        mensaje += f"🌇 Tarde: {despues[0]} – {despues[-1]}\n"

if not antes and not despues:
    mensaje += "Hoy el Sol no alcanza 30° de elevación. Aprovecha para descansar, hidratarte y cuidar tu alimentación ☕🍊.\n"


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

