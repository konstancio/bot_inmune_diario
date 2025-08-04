import os
import asyncio
import random
import datetime
import requests
from telegram import Bot
from timezonefinder import TimezoneFinder
from geopy.geocoders import Nominatim

from consejos_diarios import consejos
from calcular_intervalos import calcular_intervalos_optimos

# ─────────────────────────────────────────────
# 1) Ubicación robusta (forzar Málaga si es necesario)
# ─────────────────────────────────────────────
def obtener_ubicacion():
    # Fallback fijo a Málaga
    fallback_ciudad = "Málaga"
    fallback_lat = 36.7213
    fallback_lon = -4.4214
    fallback_tz = "Europe/Madrid"

    try:
        ip = requests.get("https://api.ipify.org", timeout=5).text
        resp = requests.get(f"https://ipapi.co/{ip}/json/", timeout=8)
        data = resp.json()
        ciudad = data.get("city")
        lat = data.get("latitude")
        lon = data.get("longitude")

        if not ciudad or not lat or not lon:
            raise ValueError("Datos IP incompletos")

        print(f"✅ Ubicación por IP: {ciudad} ({lat}, {lon})")

        # Si la ciudad no es Málaga, forzamos fallback
        if ciudad.lower() != "málaga":
            raise ValueError("Ciudad distinta de Málaga")

    except Exception as e:
        print(f"⚠️ Error/ubicación no deseada ({e}). Usando fallback a Málaga.")
        ciudad = fallback_ciudad
        lat = fallback_lat
        lon = fallback_lon

    try:
        tf = TimezoneFinder()
        tz = tf.timezone_at(lat=lat, lng=lon) or fallback_tz
    except Exception:
        tz = fallback_tz

    print(f"✅ Ubicación final: {ciudad} ({lat:.4f}, {lon:.4f}) - TZ: {tz}")

    return {
        "latitud": float(lat),
        "longitud": float(lon),
        "ciudad": ciudad,
        "timezone": tz
    }

# ─────────────────────────────────────────────
# 2) Meteo: nubosidad/lluvia (Open‑Meteo, sin API key)
# ─────────────────────────────────────────────
def obtener_nubosidad_horaria(lat, lon, timezone_str, fecha):
    """
    Devuelve lista de (dt, cloudcover%, precip_prob%) para la fecha dada.
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
    times = [datetime.datetime.fromisoformat(t) for t in data["hourly"]["time"]]
    covers = data["hourly"]["cloudcover"]
    precps = data["hourly"]["precipitation_probability"]
    return list(zip(times, covers, precps))

def hora_hhmm_a_dt(hhmm, fecha):
    """Convierte 'HH:MM' a datetime naive en la fecha dada."""
    h, m = map(int, hhmm.split(":"))
    return datetime.datetime(fecha.year, fecha.month, fecha.day, h, m)

def resumen_nubes(nubosidad_horaria, inicio_dt, fin_dt):
    """
    Media de nubosidad y precip máx en [inicio_dt, fin_dt].
    Devuelve (etiqueta, media_nubes, max_precip) o None si no hay datos.
    """
    trozos = [(c, p) for (t, c, p) in nubosidad_horaria if inicio_dt <= t <= fin_dt]
    if not trozos:
        return None
    media = sum(c for c, _ in trozos) / len(trozos)
    pmax = max(p for _, p in trozos)
    if media <= 30:
        estado = "☀️ despejado"
    elif media <= 70:
        estado = "⛅ variable"
    else:
        estado = "☁️ nuboso"
    return estado, round(media), pmax

# ─────────────────────────────────────────────
# 3) Consejos nutricionales por estación
# ─────────────────────────────────────────────
consejos_estacionales = {
    "invierno": "🌰 Consejo nutricional: Incluye pescados grasos (sardinas, caballa) y lácteos/enriquecidos.",
    "primavera": "🥚 Consejo nutricional: Huevos, setas expuestas al sol y alimentos fortificados.",
    "verano": "🐟 Consejo nutricional: Atún, yema de huevo; si no hay sol, valora alimentos enriquecidos.",
    "otoño": "🧀 Consejo nutricional: Quesos curados, hígado de bacalao; consulta suplementos si procede."
}

def estacion_del_anio(fecha):
    mes = fecha.month
    if mes in [12, 1, 2]:
        return "invierno"
    if mes in [3, 4, 5]:
        return "primavera"
    if mes in [6, 7, 8]:
        return "verano"
    return "otoño"

# ─────────────────────────────────────────────
# 4) Flujo principal
# ─────────────────────────────────────────────
ubicacion = obtener_ubicacion()
if not ubicacion:
    print("❌ Sin ubicación. Abortando.")
    raise SystemExit(1)

lat = ubicacion["latitud"]
lon = ubicacion["longitud"]
tz = ubicacion["timezone"]
ciudad = ubicacion["ciudad"]

hoy = datetime.datetime.now()
dia_semana = hoy.weekday()  # 0=lun ... 6=dom

# Elegir pareja (consejo + referencia) de forma robusta
pares = [consejos[dia_semana][i:i+2] for i in range(0, len(consejos[dia_semana]), 2)]
par = random.choice(pares)
# Identificar cuál es consejo y cuál referencia
texto_consejo = next(x for x in par if not x.startswith("📚"))
referencia = next(x for x in par if x.startswith("📚"))

# Intervalos solares (listas de 'HH:MM')
antes, despues = calcular_intervalos_optimos(lat, lon, hoy, tz)

# Meteo para hoy
try:
    nubosidad_hoy = obtener_nubosidad_horaria(lat, lon, tz, hoy.date())
except Exception as e:
    print(f"⚠️ No se pudo obtener meteo: {e}")
    nubosidad_hoy = []

# Estación y consejo estacional
estacion = estacion_del_anio(hoy)
consejo_estacion = consejos_estacionales[estacion]

# Construir mensaje
mensaje = f"{texto_consejo}\n\n{referencia}\n\n"
mensaje += f"🌞 Intervalos solares seguros para producir vit. D hoy ({ciudad}):\n"

aviso_nubes_alta = False

# Mañana
if antes:
    ini_m = hora_hhmm_a_dt(antes[0], hoy.date())
    fin_m = hora_hhmm_a_dt(antes[-1], hoy.date())
    tag = f"🌅 Mañana: {antes[0]} – {antes[-1]}"
    if nubosidad_hoy:
        n_m = resumen_nubes(nubosidad_horaria=nubosidad_hoy, inicio_dt=ini_m, fin_dt=fin_m)
        if n_m:
            estado_m, media_m, pmax_m = n_m
            mensaje += f"{tag} ({estado_m}, nubes {media_m}%, lluvia {pmax_m}%)\n"
            if media_m >= 90:
                aviso_nubes_alta = True
        else:
            mensaje += f"{tag}\n"
    else:
        mensaje += f"{tag}\n"

# Tarde
if despues:
    ini_t = hora_hhmm_a_dt(despues[0], hoy.date())
    fin_t = hora_hhmm_a_dt(despues[-1], hoy.date())
    tag = f"🌇 Tarde: {despues[0]} – {despues[-1]}"
    if nubosidad_hoy:
        n_t = resumen_nubes(nubosidad_horaria=nubosidad_hoy, inicio_dt=ini_t, fin_dt=fin_t)
        if n_t:
            estado_t, media_t, pmax_t = n_t
            mensaje += f"{tag} ({estado_t}, nubes {media_t}%, lluvia {pmax_t}%)\n"
            if media_t >= 90:
                aviso_nubes_alta = True
        else:
            mensaje += f"{tag}\n"
    else:
        mensaje += f"{tag}\n"

# Sin tramos o nubosidad muy alta
if (not antes and not despues) or aviso_nubes_alta:
    if not antes and not despues:
        mensaje += "⚠️ Hoy el Sol no alcanza 30° de elevación.\n"
    else:
        mensaje += "⚠️ Nubosidad muy alta: la síntesis cutánea de vit. D puede ser baja.\n"
    mensaje += f"{consejo_estacion}\n"

# ─────────────────────────────────────────────
# 5) Envío por Telegram (python-telegram-bot v20+)
# ─────────────────────────────────────────────
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

async def enviar_mensaje_telegram(texto):
    if not BOT_TOKEN or not CHAT_ID:
        print("❌ Faltan BOT_TOKEN o CHAT_ID")
        return
    try:
        bot = Bot(token=BOT_TOKEN)
        await bot.send_message(chat_id=CHAT_ID, text=texto)
        print("✅ Mensaje enviado por Telegram.")
    except Exception as e:
        print(f"❌ Error al enviar mensaje: {e}")

# Ejecutar envío
asyncio.run(enviar_mensaje_telegram(mensaje))

