# enviar_consejo.py — envíos diurno/nocturno + plan B nutricional + canal
# - Diurno (09:00 por defecto): consejo inmune + ventanas 30–40° con meteo.
#   Si no hay ventanas o llueve fuerte / muy nublado ⇒ consejo nutricional por estación (varía a diario).
# - Nocturno (21:00 por defecto): consejo parasimpático.
# - Traducción automática, publicación opcional en canal y guardarraíles anti-doble envío.

import os
import asyncio
import datetime
import hashlib
from typing import Optional, List, Tuple, Any

from telegram import Bot
from deep_translator import LibreTranslator
from geopy.geocoders import Nominatim
from timezonefinder import TimezoneFinder
import pytz

# ---- Contenido y repos ----
from consejos_diarios import consejos
from consejos_nutri import CONSEJOS_NUTRI
from consejos_parasimpatico import sugerir_para_noche, formatear_consejo

from usuarios_repo import (
    init_db, list_users,
    should_send_now, should_send_sleep_now,
    mark_sent_today, mark_sleep_sent_today,
    migrate_fill_defaults
)

# --- módulo solar/meteo de tu repo ---
from ubicacion_y_sol import (
    obtener_ubicacion,
    calcular_intervalos_optimos,     # ventanas 30–40° (mañana/tarde)
    obtener_pronostico_diario,       # pronóstico (sin API key)
    formatear_intervalos_meteo,      # string opcional con emojis/meteo
)

# ========== Flags / Entorno ==========
BOT_TOKEN       = os.getenv("BOT_TOKEN")
FORCE_SEND      = os.getenv("FORCE_SEND", "0") == "1"     # fuerza 1 envío por tipo hoy
ONLY_CHAT_ID    = os.getenv("ONLY_CHAT_ID")               # limita a un chat para pruebas
PING_ON_START   = os.getenv("PING_ON_START", "0") == "1"  # ping al iniciar si ONLY_CHAT_ID
SHOW_FORMATO_METEO = True

# Canal (público o privado). Ejemplos: @MiCanal  o  -1001234567890
CANAL_CHAT_ID   = os.getenv("CANAL_CHAT_ID")  # si está vacío, no publica al canal

# ========== Traducción ==========
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

# ========== Geocodificación ==========
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

# ========== Compat firmas (por si cambian) ==========
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
    print("[ERR] calcular_intervalos_optimos: firma desconocida.")
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
    print("[WARN] obtener_pronostico_diario: firma desconocida.")
    return None

# ========== Estación del año ==========
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

# ========== Formateo ==========
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

# ========= NUEVO: detección meteo suavizada =========
def _meteo_impide_sintesis(pron: Any, tramo_m, tramo_t) -> bool:
    """
    Devuelve True si el pronóstico o los tramos solares impiden la síntesis de vitamina D.
    Dia 'aprovechable' si hay al menos una ventana 30–40°, aunque haya nubosidad.
    Marca malo si NO hay tramos y además hay nubes muy altas (>90%) o lluvia significativa.
    """
    # Si hay al menos un tramo válido de 30–40°, consideramos el día válido.
    tramos_validos = _normalize_tramos(tramo_m) or _normalize_tramos(tramo_t)
    if tramos_validos:
        return False

    # Si no hay tramos, evaluamos la meteorología
    if not pron:
        return True

    try:
        # Cobertura nubosa media: muy nublado solo si >= 90 %
        cc = None
        for k in ("cloudcover_mean", "cloudcover", "clouds", "nubes"):
            if isinstance(pron, dict) and k in pron:
                cc = pron[k]; break
        if isinstance(cc, (int, float)) and cc >= 90:
            return True

        # Lluvia: significativo si > 1 mm
        pr = None
        for k in ("total_precipitation", "precipitation", "rain", "lluvia"):
            if isinstance(pron, dict) and k in pron:
                pr = pron[k]; break
        if isinstance(pr, (int, float)) and pr > 1.0:
            return True

        # Condición textual severa
        cond = str(pron.get("condition", "")).lower() if isinstance(pron, dict) else ""
        if any(x in cond for x in ["tormenta", "fuerte lluvia", "rain heavy", "storm"]):
            return True

    except Exception as e:
        print(f"[WARN] Evaluando meteo: {e}")

    # Si no hay tramos y tampoco evidencia clara de meteo severa ⇒ probablemente no útil
    return True

# ========== Variedad en días nublados ==========
def _pick_nutri_tip(estacion: str, chat_id: str, fecha: datetime.date) -> str:
    """
    Devuelve un consejo nutricional de CONSEJOS_NUTRI[estacion] sin repetirse:
    índice estable por usuario y por fecha (rota a diario y por usuario).
    """
    lista = CONSEJOS_NUTRI.get(estacion, [])
    if not lista:
        return "Mantén una dieta equilibrada con alimentos ricos en vitamina D y omega-3."
    seed = f"{chat_id}-{fecha.toordinal()}"
    h = int(hashlib.sha256(seed.encode()).hexdigest(), 16)
    return str(lista[h % len(lista)])

# ========== Envío DIURNO ==========
async def enviar_diurno(bot: Bot, chat_id: str, prefs: dict, now_utc: datetime.datetime, context_flags: dict):
    if not FORCE_SEND and not should_send_now(prefs, now_utc=now_utc):
        return

    # Zona horaria y fecha local
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

    # Consejo inmune del día (según día semana, pares [texto, ref])
    dia_semana = now_local.weekday()
    lista_dia = consejos[dia_semana]
    pares = [lista_dia[i:i+2] for i in range(0, len(lista_dia), 2)]
    if not pares:
        return
    consejo_es, referencia_es = pares[now_local.toordinal() % len(pares)]

    # Ventanas + pronóstico
    tramo_m, tramo_t = _calc_tramos_compat(hoy_local, lat, lon, tzname)
    pron = _pronostico_compat(lat, lon, hoy_local, tzname)

    # ¿Hay impedimento para síntesis (nublado fuerte/lluvia) o no hay ventanas?
    if _meteo_impide_sintesis(pron, tramo_m, tramo_t):
        est = estacion_del_anio(hoy_local, lat)
        consejo_nutri_es = _pick_nutri_tip(est, str(chat_id), hoy_local)
        lang = prefs.get("lang", "es")
        cuerpo = traducir(
            f"☁️ Hoy no hay ventanas seguras de 30–40° para sintetizar vitamina D en {ciudad}.\n"
            f"🍽️ Consejo nutricional de {est}:\n{consejo_nutri_es}",
            lang
        )
        if len(cuerpo) > 4000:
            cuerpo = cuerpo[:3990] + "…"

        # Enviar al usuario
        await bot.send_message(chat_id=chat_id, text=cuerpo)
        mark_sent_today(chat_id, hoy_local)

        # Publicar UNA VEZ por ciclo en el canal (si está definido)
        if CANAL_CHAT_ID and not context_flags.get("posted_channel_diurno", False):
            try:
                pub = f"🔔 Consejo público:\n{cuerpo}"
                if len(pub) > 3800:
                    pub = pub[:3790] + "…"
                await bot.send_message(chat_id=CANAL_CHAT_ID, text=pub)
                context_flags["posted_channel_diurno"] = True
            except Exception as e:
                print(f"[WARN] No pude publicar en canal (diurno, nublado): {e}")
        return  # importante: no seguir con bloque solar

    # Si hay Sol: mensaje inmune normal con tramos (y meteo opcional)
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

    lang = prefs.get("lang", "es")
    cuerpo = f"{consejo_es}\n\n{referencia_es}\n\n{bloque_tramos}"
    cuerpo = traducir(cuerpo, lang) or cuerpo
    if len(cuerpo) > 4000:
        cuerpo = cuerpo[:3990] + "…"

    # Enviar al usuario
    await bot.send_message(chat_id=chat_id, text=cuerpo)
    mark_sent_today(chat_id, hoy_local)

    # Publicar UNA VEZ por ciclo en el canal (si está definido)
    if CANAL_CHAT_ID and not context_flags.get("posted_channel_diurno", False):
        try:
            pub = f"🔔 Consejo público:\n{cuerpo}"
            if len(pub) > 3800:
                pub = pub[:3790] + "…"
            await bot.send_message(chat_id=CANAL_CHAT_ID, text=pub)
            context_flags["posted_channel_diurno"] = True
        except Exception as e:
            print(f"[WARN] No pude publicar en canal (diurno, soleado): {e}")

# ========== Envío NOCTURNO ==========
async def enviar_nocturno(bot: Bot, chat_id: str, prefs: dict, now_utc: datetime.datetime, context_flags: dict):
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

    lang = prefs.get("lang", "es")
    consejo_txt = sugerir_para_noche(lang=lang)             # ya sale traducido si pasamos lang
    mensaje = formatear_consejo(consejo_txt, lang=lang)     # encabezado traducido

    if len(mensaje) > 4000:
        mensaje = mensaje[:3990] + "…"

    # Enviar al usuario
    await bot.send_message(chat_id=chat_id, text=mensaje)
    mark_sleep_sent_today(chat_id, hoy_local)

    # Publicar UNA VEZ por ciclo en el canal (si está definido)
    if CANAL_CHAT_ID and not context_flags.get("posted_channel_nocturno", False):
        try:
            pub = f"🌙 Consejo para dormir (público):\n{mensaje}"
            if len(pub) > 3800:
                pub = pub[:3790] + "…"
            await bot.send_message(chat_id=CANAL_CHAT_ID, text=pub)
            context_flags["posted_channel_nocturno"] = True
        except Exception as e:
            print(f"[WARN] No pude publicar en canal (nocturno): {e}")

# ========== Main ==========
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

    # Flags compartidos del ciclo para publicar en canal solo una vez por tipo
    context_flags = {"posted_channel_diurno": False, "posted_channel_nocturno": False}

    for uid, prefs in users.items():
        if ONLY_CHAT_ID and uid != ONLY_CHAT_ID:
            continue
        try:
            await enviar_diurno(bot, uid, prefs, now_utc, context_flags=context_flags); intentos_diurnos += 1
        except Exception as e:
            print(f"❌ Error diurno {uid}: {e}")
        try:
            await enviar_nocturno(bot, uid, prefs, now_utc, context_flags=context_flags); intentos_nocturnos += 1
        except Exception as e:
            print(f"❌ Error nocturno {uid}: {e}")

    print(f"✅ Ciclo cron OK. Usuarios: {len(users)} | Intentos diurnos: {intentos_diurnos} | Nocturnos: {intentos_nocturnos}")

if __name__ == "__main__":
    asyncio.run(main())
