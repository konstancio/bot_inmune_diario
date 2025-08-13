# enviar_consejo.py — multiusuario: 9:00 locales + no duplicados + traducción + meteo + 30–40°

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
    migrate_fill_defaults,
)

# Usamos tus utilidades existentes (¡sin Astral!):
from ubicacion_y_sol import (
    obtener_ubicacion,              # fallback general si no hay datos del usuario
    calcular_intervalos_optimos,    # devuelve los tramos 30–40° (mañana y tarde)
    obtener_pronostico_diario,      # Open-Meteo, sin API key
    formatear_intervalos_meteo,     # añade icono + estado + temp a los tramos
)

BOT_TOKEN = os.getenv("BOT_TOKEN")
ONLY_CHAT_ID = os.getenv("ONLY_CHAT_ID")
FORCE_SEND   = os.getenv("FORCE_SEND", "0") == "1"

# ---------- Traducción ----------

def _norm_lang(code: Optional[str]) -> str:
    if not code:
        return "es"
    code = code.strip().lower()
    alias = {
        "sh": "sr",   # serbocroata → serbio como proxy
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
    if dest == "es" or not texto:
        return texto
    try:
        return LibreTranslator(source="es", target=dest).translate(texto)
    except Exception as e:
        print(f"⚠️ Traducción fallida ({dest}): {e}")
        return texto

# ---------- Geocodificación por ciudad ----------

_geolocator = Nominatim(user_agent="bot_inmune_diario_multi")
_tf = TimezoneFinder()

def geocodificar_ciudad(ciudad: str):
    """Devuelve dict con lat, lon, tz y nombre de ciudad legible. None si falla."""
    try:
        loc = _geolocator.geocode(ciudad)
        if not loc:
            return None
        tz = _tf.timezone_at(lat=loc.latitude, lng=loc.longitude) or "Europe/Madrid"
        nombre = loc.address.split(",")[0] if loc.address else ciudad
        return {"lat": float(loc.latitude), "lon": float(loc.longitude), "tz": tz, "ciudad": nombre}
    except Exception as e:
        print(f"⚠️ Geocodificación fallida ({ciudad}): {e}")
        return None

# ---------- Envío a un usuario ----------

async def enviar_a_usuario(bot: Bot, chat_id: str, prefs: dict, now_utc: datetime.datetime):
    # ¿Toca enviar ahora para este usuario?
    if not should_send_now(prefs, now_utc=now_utc):
        return

    # Determinar ubicación priorizando GPS > ciudad > fallback
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

    # Fecha/hora local del usuario
    try:
        tz = pytz.timezone(tzname)
    except Exception:
        tz = pytz.timezone("Europe/Madrid")
        tzname = "Europe/Madrid"
    now_local = now_utc.astimezone(tz)
    hoy_local = now_local.date()

    # Consejo + referencia del día (pares) según día local; rotación estable por fecha
    dia_semana = now_local.weekday()  # lunes=0
    lista_dia = consejos[dia_semana]
    pares = [lista_dia[i:i+2] for i in range(0, len(lista_dia), 2)]
    if not pares:
        print("⚠️ 'consejos' para este día está vacío.")
        return
    idx = now_local.toordinal() % len(pares)
    consejo_es, referencia_es = pares[idx]

    # Intervalos 30–40° (mañana y tarde) + meteo
    # ⬇️ Antes llamabas a 'calcular_intervalos_30_40', que no existe; usamos tu función real:
    tramo_m, tramo_t = calcular_intervalos_optimos(hoy_local, lat, lon, tzname)
    pron = obtener_pronostico_diario(lat, lon, hoy_local, tzname)
    intervalos_es = formatear_intervalos_meteo(tramo_m, tramo_t, ciudad, pron)

    # Traducción al idioma del usuario (consejo + referencia + intervalos)
    lang = prefs.get("lang", "es")
    cuerpo = f"{consejo_es}\n\n{referencia_es}\n\n{intervalos_es}"
    cuerpo = traducir(cuerpo, lang)

    # Telegram: límite 4096 chars
    if len(cuerpo) > 4000:
        cuerpo = cuerpo[:3990] + "…"

    # Enviar
    await bot.send_message(chat_id=chat_id, text=cuerpo)

    # Marcar como enviado hoy (fecha local)
    mark_sent_today(chat_id, hoy_local)

# ---------- Main (cron cada 5 min) ----------

async def main():
    if not BOT_TOKEN:
        raise RuntimeError("❌ Faltan variables de entorno: BOT_TOKEN")

    # Asegura esquema y columnas nuevas
    try:
        init_db()
    except Exception as e:
        print(f"[WARN] init_db: {e}")
    try:
        migrate_fill_defaults()
    except Exception as e:
        print(f"[WARN] migrate_fill_defaults: {e}")

    users = list_users()
    if not users:
        print("ℹ️ No hay suscriptores aún.")
        return

    bot = Bot(token=BOT_TOKEN)
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    intentos = 0

    for uid, prefs in users.items():
        if ONLY_CHAT_ID and uid != ONLY_CHAT_ID: 
        continue
        try:
            await enviar_a_usuario(bot, uid, prefs, now_utc)
            intentos += 1
        except Exception as e:
            print(f"❌ Error enviando a {uid}: {e}")

    print(f"✅ Ciclo cron OK. Usuarios procesados: {len(users)}. Intentos de envío: {intentos}")

if __name__ == "__main__":
    asyncio.run(main())
