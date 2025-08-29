# enviar_consejo.py — dos envíos diarios por usuario:
#   • Mañana (por defecto 09:00): vitamina D (30–40°) + meteo / plan B nutricional
#   • Noche  (por defecto 21:00): consejo parasimpático para dormir
# Traducción multi-idioma, anti-duplicados, y ping manual.

import os
import asyncio
import datetime
from typing import Optional, List, Tuple, Any

from telegram import Bot
from deep_translator import LibreTranslator
from geopy.geocoders import Nominatim
from timezonefinder import TimezoneFinder
import pytz

from consejos_diarios import consejos
from consejos_nutri import CONSEJOS_NUTRI
from consejos_parasimpatico import sugerir_para_noche, formatear_consejo

from usuarios_repo import (
    init_db, list_users,
    should_send_now, should_send_sleep_now,
    mark_sent_today, mark_sleep_sent_today,
    migrate_fill_defaults
)

# === Módulo solar/meteo del repo ===
from ubicacion_y_sol import (
    obtener_ubicacion,
    calcular_intervalos_optimos,   # ventanas 30–40° (mañana/tarde)
    obtener_pronostico_diario,     # pronóstico diario
    formatear_intervalos_meteo,    # meteo “bonita”
)

# ---------- Flags ----------
SHOW_FORMATO_METEO = True

# ---------- Variables de entorno ----------
BOT_TOKEN     = os.getenv("BOT_TOKEN")
FORCE_SEND    = os.getenv("FORCE_SEND", "0") == "1"     # fuerza envíos (guardarraíl 1/día por tipo)
ONLY_CHAT_ID  = os.getenv("ONLY_CHAT_ID")
PING_ON_START = os.getenv("PING_ON_START", "0") == "1"

# ---------- Traducción / idiomas ----------
def _norm_lang(code: Optional[str]) -> str:
    if not code:
        return "es"
    code = code.strip().lower().split("-")[0]
    alias = {"sh":"sr","sc":"sr","srp":"sr","hr":"sr","bs":"sr","pt-br":"pt"}
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

# ---------- Geocodificación ----------
_geolocator = Nominatim(user_agent="bot_inmune_diario_multi")
_tf = TimezoneFinder()

def geocodificar_ciudad(ciudad: str):
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

# ---------- Compatibilidad firmas (por si cambian) ----------
def _calc_tramos_compat(fecha_loc, lat, lon, tzname):
    try:
        return calcular_intervalos_optimos(fecha=fecha_loc, lat=lat, lon=lon, tz=tzname)
    except TypeError:
        pass
    for args in [
        (fecha_loc, lat, lon, tzname),
        (lat, lon, tzname, fecha_loc),
        (tzname, fecha_loc, lat, lon),
        (lat, lon, fecha_loc, tzname),
    ]:
        try:
            return calcular_intervalos_optimos(*args)
        except Exception:
            continue
    print("[ERR] calcular_intervalos_optimos: no se identificó firma. Devolviendo None.")
    return None, None

def _pronostico_compat(lat, lon, fecha_loc, tzname):
    try:
        return obtener_pronostico_diario(lat=lat, lon=lon, fecha=fecha_loc, tz=tzname)
    except TypeError:
        pass
    for args in [(lat, lon, fecha_loc, tzname), (lat, lon, tzname, fecha_loc)]:
        try:
            return obtener_pronostico_diario(*args)
        except Exception:
            continue
    print("[WARN] obtener_pronostico_diario: no se identificó firma. Devolviendo None.")
    return None

# ---------- Estación del año ----------
def estacion_del_anio(fecha: datetime.date, lat: Optional[float]) -> str:
    Y = fecha.year
    prim_i, ver_i, oto_i, inv_i = (datetime.date(Y,3,20), datetime.date(Y,6,21),
                                   datetime.date(Y,9,23), datetime.date(Y,12,21))
    norte = (lat is None) or (lat >= 0.0)
    if norte:
        if prim_i <= fecha < ver_i:  return "Primavera"
        if ver_i  <= fecha < oto_i:  return "Verano"
        if oto_i  <= fecha < inv_i:  return "Otoño"
        return "Invierno"
    else:
        if prim_i <= fecha < ver_i:  return "Otoño"
        if ver_i  <= fecha < oto_i:  return "Invierno"
        if oto_i  <= fecha < inv_i:  return "Primavera"
        return "Verano"

# ---------- Formateo de ventanas y meteo ----------
def _fmt_hhmm(dtobj: datetime.datetime) -> str:
    return dtobj.strftime("%H:%M")

def _normalize_tramos(tramo) -> List[Tuple[datetime.datetime, datetime.datetime]]:
    if not tramo:
        return []
    if isinstance(tramo, tuple) and len(tramo) == 2:
        return [tramo]
    if isinstance(tramo, list):
        return [t for t in tramo if isinstance(t, tuple) and len(t) == 2]
    return []

def _tramos_a_texto_detallado(ciudad: str, tramo_m, tramo_t) -> str:
    m = _normalize_tramos(tramo_m)
    t = _normalize_tramos(tramo_t)
    lineas = [f"🌞 Intervalos solares seguros para producir vit. D hoy en {ciudad}:"]
    if m:
        lineas.append("🌇 Mañana:")
        for a,b in m:
            lineas.append(f"🕒 {_fmt_hhmm(a)} - {_fmt_hhmm(b)}")
    if t:
        lineas.append("🌇 Tarde:")
        for a,b in t:
            lineas.append(f"🕒 {_fmt_hhmm(a)} - {_fmt_hhmm(b)}")
    if not m and not t:
        lineas.append("Hoy no hay ventanas solares seguras (30–40°).")
    return "\n".join(lineas)

def _meteo_impide_sintesis(pron: Any, tramo_m, tramo_t) -> bool:
    if not pron:
        return (not _normalize_tramos(tramo_m) and not _normalize_tramos(tramo_t))
    try:
        cc = None
        for k in ("cloudcover_mean","cloudcover","clouds","nubes"):
            if isinstance(pron, dict) and k in pron:
                cc = pron[k]; break
        if isinstance(cc, (int,float)) and cc >= 80:
            return True
        pr = None
        for k in ("total_precipitation","precipitation","rain","lluvia"):
            if isinstance(pron, dict) and k in pron:
                pr = pron[k]; break
        if isinstance(pr, (int,float)) and pr > 0.1:
            return True
        wc = pron.get("weathercode") if isinstance(pron, dict) else None
        if isinstance(wc, int) and wc >= 51:
            return True
        cond = pron.get("condition") if isinstance(pron, dict) else None
        if isinstance(cond, str) and cond.lower() in ("overcast","cloudy","rain","storm","tormenta","lluvia","muy nuboso"):
            return True
    except Exception:
        pass
    if not _normalize_tramos(tramo_m) and not _normalize_tramos(tramo_t):
        return True
    return False

def _texto_consejo_estacion(estacion: str) -> str:
    data = CONSEJOS_NUTRI.get(estacion)
    if data is None:
        return "Mantén una dieta equilibrada con alimentos ricos en vitamina D y omega-3."
    if isinstance(data, str):
        return data.strip()
    if isinstance(data, (list, tuple)):
        return " ".join([str(x).strip() for x in data if x]).strip()
    return str(data)

# ---------- Envío DIURNO (vitamina D) ----------
async def enviar_diurno(bot: Bot, chat_id: str, prefs: dict, now_utc: datetime.datetime):
    if not FORCE_SEND and not should_send_now(prefs, now_utc=now_utc):
        return

    try:
        tz = pytz.timezone(prefs.get("tz", "Europe/Madrid"))
    except Exception:
        tz = pytz.timezone("Europe/Madrid")
    now_local = now_utc.astimezone(tz)
    hoy_local = now_local.date()
    if prefs.get("last_sent_iso") == hoy_local.isoformat():
        return

    # Ubicación
    lat = prefs.get("lat"); lon = prefs.get("lon")
    tzname = prefs.get("tz"); ciudad = prefs.get("city") or "tu zona"
    if lat is None or lon is None or not tzname:
        if prefs.get("city"):
            geo = geocodificar_ciudad(prefs["city"])
            if geo:
                lat, lon, tzname, ciudad = geo["lat"], geo["lon"], geo["tz"], geo["ciudad"]
            else:
                ub = obtener_ubicacion(); lat, lon, tzname, ciudad = float(ub["latitud"]), float(ub["longitud"]), ub["timezone"], ub["ciudad"]
        else:
            ub = obtener_ubicacion(); lat, lon, tzname, ciudad = float(ub["latitud"]), float(ub["longitud"]), ub["timezone"], ub["ciudad"]

    # Consejo + referencia del día
    dia_semana = now_local.weekday()
    lista_dia = consejos[dia_semana]
    pares = [lista_dia[i:i+2] for i in range(0, len(lista_dia), 2)]
    if not pares:
        return
    consejo_es, referencia_es = pares[now_local.toordinal() % len(pares)]

    # Ventanas + pronóstico
    tramo_m, tramo_t = _calc_tramos_compat(hoy_local, lat, lon, tzname)
    pron = _pronostico_compat(lat, lon, hoy_local, tzname)

    if _meteo_impide_sintesis(pron, tramo_m, tramo_t):
        est = estacion_del_anio(hoy_local, lat)
        bloque_tramos = (
            "⛅ Hoy no se esperan ventanas útiles de sol para sintetizar vitamina D.\n"
            f"🍽️ Consejo de temporada ({est}): {_texto_consejo_estacion(est)}"
        )
    else:
        bloque_tramos = _tramos_a_texto_detallado(ciudad, tramo_m, tramo_t)
        if SHOW_FORMATO_METEO:
            try:
                extra = formatear_intervalos_meteo(tramo_m, tramo_t, ciudad, pron)
            except TypeError:
                try:
                    extra = formatear_intervalos_meteo(tramo_m, tramo_t, ciudad)
                except Exception:
                    extra = None
            if extra and isinstance(extra, str):
                bloque_tramos += f"\n({extra})"

    # Mensaje + traducción
    lang = prefs.get("lang", "es")
    cuerpo = f"{consejo_es}\n\n{referencia_es}\n\n{bloque_tramos}"
    cuerpo = traducir(cuerpo, lang) or cuerpo
    if len(cuerpo) > 4000:
        cuerpo = cuerpo[:3990] + "…"

    await bot.send_message(chat_id=chat_id, text=cuerpo)
    mark_sent_today(chat_id, hoy_local)

# ---------- Envío NOCTURNO (parasimpático 21:00) ----------
async def enviar_nocturno(bot: Bot, chat_id: str, prefs: dict, now_utc: datetime.datetime):
    if not FORCE_SEND and not should_send_sleep_now(prefs, now_utc=now_utc):
        return

    try:
        tz = pytz.timezone(prefs.get("tz", "Europe/Madrid"))
    except Exception:
        tz = pytz.timezone("Europe/Madrid")
    now_local = now_utc.astimezone(tz)
    hoy_local = now_local.date()
    if prefs.get("last_sleep_sent_iso") == hoy_local.isoformat():
        return

    # Sugerencia parasimpática para la noche
    consejo = sugerir_para_noche()
    texto = formatear_consejo(consejo)

    # Traducción al idioma del usuario
    lang = prefs.get("lang", "es")
    mensaje = traducir(texto, lang) or texto

    await bot.send_message(chat_id=chat_id, text=mensaje)
    mark_sleep_sent_today(chat_id, hoy_local)

# ---------- Main ----------
async def main():
    if not BOT_TOKEN:
        raise RuntimeError("❌ Faltan variables de entorno: BOT_TOKEN")

    try: init_db()
    except Exception as e: print(f"[WARN] init_db: {e}")
    try: migrate_fill_defaults()
    except Exception as e: print(f"[WARN] migrate_fill_defaults: {e}")

    bot = Bot(token=BOT_TOKEN)

    if PING_ON_START and ONLY_CHAT_ID:
        try:
            await bot.send_message(chat_id=ONLY_CHAT_ID, text="✅ Ping de diagnóstico (PING_ON_START).")
        except Exception as e:
            print(f"[ERR] PING FAILED: {e}")

    users = list_users()
    if not users:
        print("ℹ️ No hay suscriptores aún.")
        return

    now_utc = datetime.datetime.now(datetime.timezone.utc)
    intentos_diurnos = 0
    intentos_nocturnos = 0

    for uid, prefs in users.items():
        if ONLY_CHAT_ID and uid != ONLY_CHAT_ID:
            continue
        try:
            await enviar_diurno(bot, uid, prefs, now_utc); intentos_diurnos += 1
        except Exception as e:
            print(f"❌ Error diurno {uid}: {e}")
        try:
            await enviar_nocturno(bot, uid, prefs, now_utc); intentos_nocturnos += 1
        except Exception as e:
            print(f"❌ Error nocturno {uid}: {e}")

    print(f"✅ Ciclo cron OK. Usuarios: {len(users)} | Intentos diurnos: {intentos_diurnos} | Nocturnos: {intentos_nocturnos}")

if __name__ == "__main__":
    asyncio.run(main())
