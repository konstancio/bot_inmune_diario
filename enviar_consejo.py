# enviar_consejo.py — cron cada 5': envía a las 09:00 locales (sin duplicados)
# Traducción, meteo y tramos solares 30–40° (mañana/tarde).

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
    init_db,
    list_users,
    should_send_now,
    mark_sent_today,
    migrate_fill_defaults
)

from ubicacion_y_sol import (
    obtener_ubicacion,
    calcular_intervalos_30_40,
    obtener_pronostico_diario,
    formatear_intervalos_meteo,
)

# ---------- Variables de entorno ----------
BOT_TOKEN = os.getenv("BOT_TOKEN")
FORCE_SEND = os.getenv("FORCE_SEND", "0") == "1"
ONLY_CHAT_ID = os.getenv("ONLY_CHAT_ID")

# ---------- Traducción ----------
def _norm_lang(code: Optional[str]) -> str:
    if not code:
        return "es"
    code = code.strip().lower()
    alias = {
        "sh": "sr",
        "sc": "sr",
        "srp": "sr",
        "cro": "hr",
        "ser": "sr",
        "bos": "bs",
        "pt-br": "pt",
    }
    return alias.get(code, code)

def traducir(texto: str, lang: Optional[str]) -> str:
    dest = _norm_lang(lang)
    if dest == "es":
        return texto
    try:
        return LibreTranslator(source="es", target=dest).translate(texto)
    except Exception as e:
        print(f"⚠️ Traducción fallida ({dest}): {e}")
        return texto

# ---------- Geocodificación por ciudad ----------
def geocodificar_ciudad(ciudad: str):
    try:
        geolocator = Nominatim(user_agent="bot_inmune_diario_multi")
        loc = geolocator.geocode(ciudad)
        if not loc:
            return None
        tf = TimezoneFinder()
        tz = tf.timezone_at(lat=loc.latitude, lng=loc.longitude) or "Europe/Madrid"
        nombre = loc.address.split(",")[0] if loc.address else ciudad
        return {
            "lat": float(loc.latitude),
            "lon": float(loc.longitude),
            "tz": tz,
            "ciudad": nombre
        }
    except Exception as e:
        print(f"⚠️ Geocodificación fallida ({ciudad}): {e}")
        return None

# ---------- Envío a un usuario ----------
async def enviar_a_usuario(bot: Bot, chat_id: str, prefs: dict, now_utc: datetime.datetime):
    # Respetar ventana salvo FORCE_SEND
    if not FORCE_SEND and not should_send_now(prefs, now_utc=now_utc):
        return

    # Ubicación
    lat = prefs.get("lat")
    lon = prefs.get("lon")
    tzname = prefs.get("tz")
    ciudad = prefs.get("city")

    if lat is None or lon is None or not tzname:
        if ciudad:
            geo = geocodificar_ciudad(ciudad)
            if geo:
                lat, lon, tzname, ciudad = geo["lat"], geo["lon"], geo["tz"], geo["ciudad"]
            else:
                ub = obtener_ubicacion()
                lat, lon, tzname, ciudad = float(ub["latitud"]), float(ub["longitud"]), ub["timezone"], ub["ciudad"]
        else:
            ub = obtener_ubicacion()
            lat, lon, tzname, ciudad = float(ub["latitud"]), float(ub["longitud"]), ub["timezone"], ub["ciudad"]

    # Fecha/hora local
    try:
        tz = pytz.timezone(tzname)
    except Exception:
        tz = pytz.timezone("Europe/Madrid")
        tzname = "Europe/Madrid"
    now_local = now_utc.astimezone(tz)
    hoy_local = now_local.date()

    # Consejo y referencia
    dia_semana = now_local.weekday()
    pares = [consejos[dia_semana][i:i+2] for i in range(0, len(consejos[dia_semana]), 2)]
    consejo_es, referencia_es = pares[now_local.toordinal() % len(pares)]

    # Intervalos solares + meteo
    tramo_m, tramo_t = calcular_intervalos_30_40(hoy_local, lat, lon, tzname)
    pron = obtener_pronostico_diario(lat, lon, hoy_local, tzname)
    intervalos_es = formatear_intervalos_meteo(tramo_m, tramo_t, ciudad, pron)

    # Mensaje traducido
    lang = prefs.get("lang", "es")
    mensaje = f"{traducir(consejo_es, lang)}\n\n{traducir(referencia_es, lang)}\n\n{traducir(intervalos_es, lang)}"

    # Enviar
    try:
        await bot.send_message(chat_id=chat_id, text=mensaje)
        print(f"[DBG] Mensaje enviado a {chat_id}")
    except Exception as e:
        print(f"[ERR] Error enviando a {chat_id}: {e}")
        return

    # Marcar como enviado
    mark_sent_today(chat_id, hoy_local)

# ---------- Main ----------
async def main():
    if not BOT_TOKEN:
        raise RuntimeError("❌ Faltan variables de entorno: BOT_TOKEN")

    try:
        init_db()
    except Exception as e:
        print(f"[WARN] init_db: {e}")
    try:
        migrate_fill_defaults()
    except Exception as e:
        print(f"[WARN] migrate_fill_defaults: {e}")

    bot = Bot(token=BOT_TOKEN)

    # Ping de diagnóstico si FORCE_SEND activo
    if FORCE_SEND and ONLY_CHAT_ID:
        try:
            await bot.send_message(chat_id=ONLY_CHAT_ID, text="✅ Ping de diagnóstico (FORCE_SEND activo).")
            print(f"[DBG] PING OK to {ONLY_CHAT_ID}")
        except Exception as e:
            print(f"[ERR] PING FAILED to {ONLY_CHAT_ID}: {e}")

    users = list_users()
    if not users:
        print("ℹ️ No hay suscriptores aún.")
        return

    now_utc = datetime.datetime.now(datetime.timezone.utc)
    print(f"[DBG] ONLY_CHAT_ID={ONLY_CHAT_ID} FORCE_SEND={FORCE_SEND}")

    enviados = 0
    for uid, prefs in users.items():
        if ONLY_CHAT_ID and uid != ONLY_CHAT_ID:
            continue
        try:
            await enviar_a_usuario(bot, uid, prefs, now_utc)
            enviados += 1
        except Exception as e:
            print(f"❌ Error enviando a {uid}: {e}")

    print(f"✅ Ciclo cron OK. Usuarios procesados: {len(users)}. Intentos de envío: {enviados}")

if __name__ == "__main__":
    asyncio.run(main())
