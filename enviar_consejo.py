# enviar_consejo.py
# Multiusuario + 9:00 locales + no duplicados + traducción + meteo + intervalos 30–40°

import os
import asyncio
import datetime
from typing import Optional

from telegram import Bot
from deep_translator import LibreTranslator
from geopy.geocoders import Nominatim
from timezonefinder import TimezoneFinder
import pytz

from consejos_diarios import consejos
from usuarios_repo import (
    list_users, should_send_now, mark_sent_today, migrate_fill_defaults
)
from ubicacion_y_sol import (
    obtener_ubicacion,              # fallback general
    calcular_intervalos_30_40,      # fórmula precisa con EoT y longitud
    obtener_pronostico_diario,      # Open-Meteo, sin API key
    formatear_intervalos_meteo,     # añade icono + estado + temp
)

BOT_TOKEN = os.getenv("BOT_TOKEN")

# ---------- Utilidades ----------

def traducir(texto: str, lang: Optional[str]) -> str:
    """Traduce usando LibreTranslator si lang != 'es'."""
    if not lang or lang.lower() == "es":
        return texto
    try:
        return LibreTranslator(source="auto", target=lang.lower()).translate(texto)
    except Exception as e:
        print(f"⚠️ Traducción fallida ({lang}): {e}")
        return texto

def geocodificar(ciudad: str):
    """Devuelve dict con lat, lon, tz y nombre de ciudad. None si falla."""
    try:
        geolocator = Nominatim(user_agent="bot_inmune_diario")
        loc = geolocator.geocode(ciudad)
        if not loc:
            return None
        tf = TimezoneFinder()
        tz = tf.timezone_at(lat=loc.latitude, lng=loc.longitude) or "Europe/Madrid"
        return {
            "lat": float(loc.latitude),
            "lon": float(loc.longitude),
            "tz": tz,
            "ciudad": ciudad
        }
    except Exception as e:
        print(f"⚠️ Geocodificación fallida ({ciudad}): {e}")
        return None

async def enviar_a_usuario(bot: Bot, chat_id: str, prefs: dict, now_utc: datetime.datetime):
    """
    Decide si debe enviar ahora (9:00 locales). Si sí, genera y envía el mensaje
    (consejo + referencia + intervalos 30–40° + meteo) y marca como enviado hoy.
    """
    # ¿Toca enviar ahora?
    if not should_send_now(prefs, now_utc=now_utc):
        return

    # ---- Determinar ubicación del usuario (prioridad: GPS > ciudad > fallback) ----
    lat = prefs.get("lat")
    lon = prefs.get("lon")
    tzname = prefs.get("tz")
    ciudad = prefs.get("city")

    if lat is None or lon is None or not tzname:
        if ciudad:
            g = geocodificar(ciudad)
            if g:
                lat, lon, tzname, ciudad = g["lat"], g["lon"], g["tz"], g["ciudad"]
            else:
                ub = obtener_ubicacion()
                lat = float(ub["latitud"]); lon = float(ub["longitud"])
                tzname = ub["timezone"]; ciudad = ub["ciudad"]
        else:
            ub = obtener_ubicacion()
            lat = float(ub["latitud"]); lon = float(ub["longitud"])
            tzname = ub["timezone"]; ciudad = ub["ciudad"]

    # ---- Fecha y hora local para este usuario ----
    try:
        tz = pytz.timezone(tzname)
    except Exception:
        tz = pytz.timezone("Europe/Madrid")
        tzname = "Europe/Madrid"

    now_local = now_utc.astimezone(tz)
    hoy_local = now_local.date()

    # ---- Consejo y referencia del día (pares) ----
    dia_semana = now_local.weekday()  # lunes=0
    conj = consejos[dia_semana]
    pares = [conj[i:i+2] for i in range(0, len(conj), 2)]
    consejo, referencia = pares[now_local.toordinal() % len(pares)]  # rotación estable por fecha local

    # ---- Intervalos 30–40° y pronóstico ----
    tramo_m, tramo_t = calcular_intervalos_30_40(hoy_local, lat, lon, tzname)
    pron = obtener_pronostico_diario(lat, lon, hoy_local, tzname)
    texto_intervalos = formatear_intervalos_meteo(tramo_m, tramo_t, ciudad, pron)

    mensaje = f"{consejo}\n\n{referencia}\n\n{texto_intervalos}"
    mensaje = traducir(mensaje, prefs.get("lang", "es"))

    # ---- Enviar ----
    await bot.send_message(chat_id=chat_id, text=mensaje)

    # ---- Marcar como enviado hoy (por fecha local) ----
    mark_sent_today(chat_id, hoy_local)

# ---------- Main ----------

async def main():
    if not BOT_TOKEN:
        raise RuntimeError("❌ Faltan variables de entorno: BOT_TOKEN")
    bot = Bot(token=BOT_TOKEN)

    # Asegurar que usuarios.json tiene todos los campos nuevos
    migrate_fill_defaults()

    users = list_users()
    if not users:
        print("ℹ️ No hay suscriptores aún.")
        return

    now_utc = datetime.datetime.now(datetime.timezone.utc)
    enviados = 0
    for uid, prefs in users.items():
        try:
            await enviar_a_usuario(bot, uid, prefs, now_utc)
            enviados += 1
        except Exception as e:
            print(f"❌ Error enviando a {uid}: {e}")

    print(f"✅ Ciclo cron OK. Procesados {len(users)} usuarios. Intentos de envío: {enviados}")

if __name__ == "__main__":
    asyncio.run(main())
