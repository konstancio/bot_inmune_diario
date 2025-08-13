# enviar_consejo.py — cron cada 5': 09:00 locales, ventanas 30–40° (mañana/tarde) + Plan B nutricional por estación
# Traducción, meteo, DB Postgres y guardarraíl anti-duplicados (incluso con FORCE_SEND=1).
# Incluye PING manual controlado por PING_ON_START=1.

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
from consejos_nutri import CONSEJOS_NUTRI  # ← archivo separado
from usuarios_repo import (
    init_db, list_users, should_send_now, mark_sent_today, migrate_fill_defaults
)

# === Módulo solar/meteo del repo ===
from ubicacion_y_sol import (
    obtener_ubicacion,             # fallback si falta info
    calcular_intervalos_optimos,   # ventanas 30–40°
    obtener_pronostico_diario,     # Open-Meteo (o similar)
    formatear_intervalos_meteo,    # meteo “bonita” (opcional)
)

# ---------- Flags fáciles de ajustar ----------
SHOW_FORMATO_METEO = True  # pon False si no quieres la línea extra de meteo formateada

# ---------- Variables de entorno ----------
BOT_TOKEN     = os.getenv("BOT_TOKEN")
FORCE_SEND    = os.getenv("FORCE_SEND", "0") == "1"   # fuerza envío (una vez al día gracias al guardarraíl)
ONLY_CHAT_ID  = os.getenv("ONLY_CHAT_ID")             # limita a un chat concreto (tests)
PING_ON_START = os.getenv("PING_ON_START", "0") == "1" # ping manual al arrancar (siempre y solo si tú lo activas)

# ---------- Traducción ----------
def _norm_lang(code: Optional[str]) -> str:
    if not code:
        return "es"
    code = code.strip().lower()
    alias = {"sh":"sr","sc":"sr","srp":"sr","cro":"hr","ser":"sr","bos":"bs","pt-br":"pt"}
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

# ---------- Compatibilidad firmas (por si tu módulo cambia) ----------
def _calc_tramos_compat(fecha_loc, lat, lon, tzname):
    try:  # kwargs
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

# ---------- Estación del año (considera hemisferio) ----------
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
    else:  # Sur: invertidas
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

def _tramos_a_texto(tramo_m, tramo_t) -> str:
    m = _normalize_tramos(tramo_m)
    t = _normalize_tramos(tramo_t)
    partes = []
    if m:
        rangos = ", ".join(f"{_fmt_hhmm(a)}–{_fmt_hhmm(b)}" for a,b in m)
        partes.append(f"☀️ Mañana: {rangos}")
    if t:
        rangos = ", ".join(f"{_fmt_hhmm(a)}–{_fmt_hhmm(b)}" for a,b in t)
        partes.append(f"🌇 Tarde: {rangos}")
    if not partes:
        return "Hoy no hay ventanas solares seguras (30–40°)."
    return "\n".join(partes)

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

# ---------- Envío a un usuario ----------
async def enviar_a_usuario(bot: Bot, chat_id: str, prefs: dict, now_utc: datetime.datetime):
    # Respetar ventana salvo FORCE_SEND
    if not FORCE_SEND and not should_send_now(prefs, now_utc=now_utc):
        return

    # Evitar duplicados incluso forzando (máx 1/día por usuario)
    try:
        tz = pytz.timezone(prefs.get("tz", "Europe/Madrid"))
    except Exception:
        tz = pytz.timezone("Europe/Madrid")
    now_local = now_utc.astimezone(tz)
    hoy_local = now_local.date()
    if prefs.get("last_sent_iso") == hoy_local.isoformat():
        print(f"[DBG] skip {chat_id}: ya enviado hoy")
        return

    # Ubicación priorizando GPS > city > fallback
    lat = prefs.get("lat"); lon = prefs.get("lon")
    tzname = prefs.get("tz"); ciudad = prefs.get("city")
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

    # Consejo + referencia del día
    dia_semana = now_local.weekday()
    lista_dia = consejos[dia_semana]
    pares = [lista_dia[i:i+2] for i in range(0, len(lista_dia), 2)]
    if not pares:
        print("⚠️ 'consejos' vacío para este día.")
        return
    consejo_es, referencia_es = pares[now_local.toordinal() % len(pares)]

    # Ventanas solares + pronóstico
    tramo_m, tramo_t = _calc_tramos_compat(hoy_local, lat, lon, tzname)
    pron = _pronostico_compat(lat, lon, hoy_local, tzname)
    print(f"[DBG] {chat_id} tz={tzname} tramos_m={tramo_m} tramos_t={tramo_t} pron={pron}")

    # Texto de tramos o Plan B por estación
    if _meteo_impide_sintesis(pron, tramo_m, tramo_t):
        est = estacion_del_anio(hoy_local, lat)
        texto_tramos = (
            "⛅ Hoy no se esperan ventanas útiles de sol para sintetizar vitamina D.\n"
            f"🍽️ Consejo de temporada ({est}): {CONSEJOS_NUTRI[est]}"
        )
    else:
        texto_tramos = _tramos_a_texto(tramo_m, tramo_t)
        # (opcional) añade meteo “bonita” de tu módulo:
        if SHOW_FORMATO_METEO:
            try:
                extra = formatear_intervalos_meteo(tramo_m, tramo_t, ciudad, pron)
                if extra and isinstance(extra, str):
                    texto_tramos += f"\n({extra})"
            except TypeError:
                try:
                    extra = formatear_intervalos_meteo(tramo_m, tramo_t, ciudad)
                    if extra and isinstance(extra, str):
                        texto_tramos += f"\n({extra})"
                except Exception:
                    pass

    # Mensaje final + traducción
    lang = prefs.get("lang", "es")
    cuerpo = f"{consejo_es}\n\n{referencia_es}\n\n{texto_tramos}"
    cuerpo = traducir(cuerpo, lang)
    if len(cuerpo) > 4000:
        cuerpo = cuerpo[:3990] + "…"

    # Enviar y marcar
    try:
        await bot.send_message(chat_id=chat_id, text=cuerpo)
        print(f"[DBG] OK sent to {chat_id}")
    except Exception as e:
        print(f"[ERR] Telegram send_message {chat_id}: {e}")
        return
    mark_sent_today(chat_id, hoy_local)

# ---------- Main ----------
async def main():
    if not BOT_TOKEN:
        raise RuntimeError("❌ Faltan variables de entorno: BOT_TOKEN")

    try: init_db()
    except Exception as e: print(f"[WARN] init_db: {e}")
    try: migrate_fill_defaults()
    except Exception as e: print(f"[WARN] migrate_fill_defaults: {e}")

    bot = Bot(token=BOT_TOKEN)

    # Ping manual: solo si PING_ON_START=1 y hay ONLY_CHAT_ID
    if PING_ON_START and ONLY_CHAT_ID:
        try:
            await bot.send_message(chat_id=ONLY_CHAT_ID, text="✅ Ping de diagnóstico (PING_ON_START).")
            print(f"[DBG] PING OK to {ONLY_CHAT_ID}")
        except Exception as e:
            print(f"[ERR] PING FAILED to {ONLY_CHAT_ID}: {e}")

    users = list_users()
    if not users:
        print("ℹ️ No hay suscriptores aún.")
        return

    now_utc = datetime.datetime.now(datetime.timezone.utc)
    print(f"[DBG] ONLY_CHAT_ID={ONLY_CHAT_ID} FORCE_SEND={FORCE_SEND} PING_ON_START={PING_ON_START}")

    procesados = 0
    for uid, prefs in users.items():
        if ONLY_CHAT_ID and uid != ONLY_CHAT_ID:
            continue
        try:
            await enviar_a_usuario(bot, uid, prefs, now_utc)
            procesados += 1
        except Exception as e:
            print(f"❌ Error enviando a {uid}: {e}")

    print(f"✅ Ciclo cron OK. Usuarios procesados: {procesados} / {len(users)}")

if __name__ == "__main__":
    asyncio.run(main())
