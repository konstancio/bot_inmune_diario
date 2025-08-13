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
    # si no tienes migrate_fill_defaults, comenta la import y la llamada más abajo
    migrate_fill_defaults,
)

# Utilidades existentes en tu repo (¡sin Astral!):
from ubicacion_y_sol import (
    obtener_ubicacion,            # fallback general si falta info de usuario
    calcular_intervalos_optimos,  # devuelve tramos 30–40° (mañana y tarde)
    obtener_pronostico_diario,    # Open-Meteo
    formatear_intervalos_meteo,   # texto bonito con meteo + tramos
)

BOT_TOKEN = os.getenv("BOT_TOKEN")
ONLY_CHAT_ID = os.getenv("ONLY_CHAT_ID")           # si se define, solo envía a ese chat
FORCE_SEND   = os.getenv("FORCE_SEND", "0") == "1" # ignora hora/duplicados

# ---------- Traducción ----------

def _norm_lang(code: Optional[str]) -> str:
    if not code:
        return "es"
    code = code.strip().lower()
    alias = {
        "sh": "sr", "sc": "sr", "srp": "sr",
        "cro": "hr", "ser": "sr", "bos": "bs",
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
        
# --- Compatibilidad con ubicacion_y_sol.py (acepte kwargs o no) ---

def _calc_tramos_compat(hoy_local, lat, lon, tzname):
    # 1) intento con nombres (fecha, lat, lon, tz)
    try:
        return calcular_intervalos_optimos(fecha=hoy_local, lat=lat, lon=lon, tz=tzname)
    except TypeError:
        pass
    # 2) intento con orden alternativo (lat, lon, tz, fecha)
    try:
        return calcular_intervalos_optimos(lat, lon, tzname, hoy_local)
    except Exception as e:
        print(f"[ERR] calcular_intervalos_optimos compat: {e}")
        return None, None

def _pronostico_compat(lat, lon, hoy_local, tzname):
    # 1) intento con nombres
    try:
        return obtener_pronostico_diario(lat=lat, lon=lon, fecha=hoy_local, tz=tzname)
    except TypeError:
        pass
    # 2) intento con orden alternativo
    try:
        return obtener_pronostico_diario(lat, lon, hoy_local, tzname)
    except Exception as e:
        print(f"[ERR] obtener_pronostico_diario compat: {e}")
        return None

# ===== Wrappers de compatibilidad para ubicacion_y_sol.py =====
from datetime import datetime, date

def _as_date(x):
    return isinstance(x, (datetime, date))

def _calc_tramos_compat(hoy_local, lat, lon, tzname):
    """
    Intenta varias firmas habituales:
    - (fecha, lat, lon, tz)
    - (lat, lon, tz, fecha)
    - (tz, fecha, lat, lon)
    - (lat, lon, fecha, tz)
    """
    try:
        # 1) con kwargs típicos
        return calcular_intervalos_optimos(fecha=hoy_local, lat=lat, lon=lon, tz=tzname)
    except TypeError:
        pass
    # 2) probar permutaciones más frecuentes
    for args in [
        (hoy_local, lat, lon, tzname),
        (lat, lon, tzname, hoy_local),
        (tzname, hoy_local, lat, lon),
        (lat, lon, hoy_local, tzname),
    ]:
        try:
            return calcular_intervalos_optimos(*args)
        except Exception as e:
            # si el error es claramente por tipos, seguimos intentando
            continue
    print("[ERR] No se pudo llamar a calcular_intervalos_optimos con ninguna firma conocida.")
    return None, None

def _pronostico_compat(lat, lon, hoy_local, tzname):
    """
    Intenta varias firmas habituales para el pronóstico:
    - (lat, lon, fecha, tz)
    - (lat, lon, tz, fecha)
    - kwargs
    """
    try:
        return obtener_pronostico_diario(lat=lat, lon=lon, fecha=hoy_local, tz=tzname)
    except TypeError:
        pass
    for args in [
        (lat, lon, hoy_local, tzname),
        (lat, lon, tzname, hoy_local),
    ]:
        try:
            return obtener_pronostico_diario(*args)
        except Exception:
            continue
    print("[WARN] obtener_pronostico_diario devolvió None (no se identificó firma).")
    return None

def _formatear_compat(tramo_m, tramo_t, ciudad, pron):
    """
    La función de tu repo puede aceptar:
    - (tramo_m, tramo_t)    -> 2 args
    - (tramo_m, tramo_t, ciudad) -> 3 args
    - (tramo_m, tramo_t, ciudad, pron) -> 4 args
    Elegimos la más completa que soporte.
    """
    import inspect
    try:
        n = len(inspect.signature(formatear_intervalos_meteo).parameters)
    except Exception:
        n = 2  # fallback

    try:
        if n >= 4:
            return formatear_intervalos_meteo(tramo_m, tramo_t, ciudad, pron)
        elif n == 3:
            return formatear_intervalos_meteo(tramo_m, tramo_t, ciudad)
        else:
            return formatear_intervalos_meteo(tramo_m, tramo_t)
    except TypeError:
        # si falló por número de args, degradamos
        try:
            return formatear_intervalos_meteo(tramo_m, tramo_t, ciudad)
        except Exception:
            return formatear_intervalos_meteo(tramo_m, tramo_t)
        
# ---------- Envío a un usuario ----------

async def enviar_a_usuario(bot: Bot, chat_id: str, prefs: dict, now_utc: datetime.datetime):
    # Respetar ventana horaria salvo FORCE_SEND
    if not FORCE_SEND and not should_send_now(prefs, now_utc=now_utc):
        return

    # Ubicación priorizando GPS > ciudad > fallback genérico
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

    # Log de depuración
    print(f"[DBG] chat={chat_id} tz={tzname} now_local={now_local.isoformat()} "
          f"send_hour={prefs.get('send_hour_local')} last_sent={prefs.get('last_sent_iso')} "
          f"force={FORCE_SEND}")

    # Consejo + referencia del día (pares) según día local; rotación estable por fecha
    dia_semana = now_local.weekday()  # lunes=0
    lista_dia = consejos[dia_semana]
    pares = [lista_dia[i:i+2] for i in range(0, len(lista_dia), 2)]
    if not pares:
        print("⚠️ 'consejos' para este día está vacío.")
        return
    idx = now_local.toordinal() % len(pares)
    consejo_es, referencia_es = pares[idx]

    # Tramos 30–40° + meteo
    tramo_m, tramo_t = _calc_tramos_compat(hoy_local, lat, lon, tzname)
print(f"[DBG] tramos: mañana={tramo_m} tarde={tramo_t}")

pron = _pronostico_compat(lat, lon, hoy_local, tzname)
print(f"[DBG] meteo: {pron}")

try:
    intervalos_es = _formatear_compat(tramo_m, tramo_t, ciudad, pron)
except Exception as e:
    print(f"[WARN] formatear_intervalos_meteo compat: {e}")
    if not tramo_m and not tramo_t:
        intervalos_es = f"Hoy no hay ventanas solares 30–40° útiles en {ciudad}."
    else:
        intervalos_es = "Ventanas solares calculadas correctamente."
        
    # Construcción + traducción
    lang = prefs.get("lang", "es")
    cuerpo = f"{consejo_es}\n\n{referencia_es}\n\n{intervalos_es}"
    cuerpo = traducir(cuerpo, lang)

    # Límite Telegram
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

    # Asegura esquema / migración suave
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

    print(f"[DBG] ONLY_CHAT_ID={ONLY_CHAT_ID} FORCE_SEND={FORCE_SEND}")

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
