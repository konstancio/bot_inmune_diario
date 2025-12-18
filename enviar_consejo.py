# enviar_consejo.py — CRON diario multiusuario
# Vitamina D (30–40°), meteo, nutrición por estación y traducción
#
# ✅ Corrección clave: NUNCA usar IP del servidor (Railway) para ubicar al usuario.
#    Si el usuario no tiene lat/lon guardados:
#      1) intentamos geocodificar su /city (Open-Meteo Geocoding)
#      2) si no hay city o falla -> fallback explícito a Málaga
#
# 🆕 Primera vez (primer envío) -> manda un mensaje con comandos útiles.

import os
import asyncio
import datetime as dt
from typing import Optional, Tuple, Dict, Any

import pytz
import requests
from telegram import Bot
from deep_translator import LibreTranslator

from consejos_diarios import consejos
from consejos_nutri import CONSEJOS_NUTRI
from usuarios_repo import init_db, list_users, should_send_now, mark_sent_today

from ubicacion_y_sol import (
    calcular_intervalos_optimos,
    obtener_pronostico_diario,
)

# ================= ENV =================

BOT_TOKEN = os.getenv("BOT_TOKEN")
DATABASE_DSN = os.getenv("DATABASE_DSN") or os.getenv("DATABASE_URL")  # según cómo lo tengas en Railway
FORCE_SEND = os.getenv("FORCE_SEND", "0").strip() == "1"
ONLY_CHAT_ID = os.getenv("ONLY_CHAT_ID")
PING_ON_START = os.getenv("PING_ON_START", "0").strip() == "1"
CANAL_CHAT_ID = os.getenv("CANAL_CHAT_ID")  # opcional (canal)

# ================= Idiomas =================

VALID_LANG = {"es", "en", "fr", "it", "de", "pt", "nl", "sr", "ru"}

_LANG_ALIAS = {
    # serbio proxy croata/bosnio
    "sh": "sr", "sc": "sr", "srp": "sr", "hr": "sr", "bs": "sr",
    # variantes
    "pt-br": "pt",
    "es-es": "es", "en-us": "en", "en-gb": "en",
}

def _norm_lang(code: Optional[str]) -> str:
    if not code:
        return "es"
    code = (code or "").strip().lower()
    code = _LANG_ALIAS.get(code, code)
    return code if code in VALID_LANG else "es"

def traducir(texto: str, lang: Optional[str]) -> str:
    dest = _norm_lang(lang)
    if dest == "es":
        return texto
    try:
        return LibreTranslator(source="es", target=dest).translate(texto)
    except Exception:
        return texto

# ================= Estación =================

def estacion_del_anio(fecha: dt.date, lat: float) -> str:
    m = fecha.month
    norte = lat >= 0
    if norte:
        return ("Invierno","Invierno","Invierno",
                "Primavera","Primavera","Primavera",
                "Verano","Verano","Verano",
                "Otoño","Otoño","Otoño")[m-1]
    else:
        return ("Verano","Verano","Verano",
                "Otoño","Otoño","Otoño",
                "Invierno","Invierno","Invierno",
                "Primavera","Primavera","Primavera")[m-1]

def pick_nutri(est: str, chat_id: str, fecha: dt.date) -> str:
    ops = CONSEJOS_NUTRI.get(est)
    if not ops:
        return "Prioriza alimentos reales y, si procede, alimentos fortificados en vitamina D."
    if isinstance(ops, str):
        return ops
    idx = (hash(chat_id) + fecha.toordinal()) % len(ops)
    return ops[idx]

# ================= Consejo diario =================

def consejo_del_dia(now_local: dt.datetime) -> Tuple[str, str]:
    lista = consejos[now_local.weekday()]
    pares = [lista[i:i+2] for i in range(0, len(lista), 2)]
    idx = now_local.date().toordinal() % len(pares)
    consejo, ref = pares[idx]
    return consejo, ref

# ================= Geocoding (si el usuario usa /city) =================

def geocode_city_open_meteo(city: str) -> Optional[Dict[str, Any]]:
    """
    Devuelve {"lat": float, "lon": float, "name": str, "timezone": str?}
    o None si falla.
    """
    city = (city or "").strip()
    if not city:
        return None
    try:
        url = "https://geocoding-api.open-meteo.com/v1/search"
        params = {"name": city, "count": 1, "language": "en", "format": "json"}
        r = requests.get(url, params=params, timeout=8)
        r.raise_for_status()
        data = r.json()
        results = data.get("results") or []
        if not results:
            return None
        top = results[0]
        lat = top.get("latitude")
        lon = top.get("longitude")
        name = top.get("name") or city
        tz = top.get("timezone")  # a veces viene
        if lat is None or lon is None:
            return None
        return {"lat": float(lat), "lon": float(lon), "name": str(name), "timezone": tz}
    except Exception:
        return None

# ================= Mensaje de bienvenida (una sola vez) =================

def welcome_help_es() -> str:
    return (
        "👋 ¡Bienvenido! Te he suscrito a los consejos diarios.\n\n"
        "🧩 Comandos útiles:\n"
        "• /help — ver ayuda\n"
        "• /where — ver tus ajustes actuales\n"
        "• /lang es|en|fr|it|de|pt|nl|sr|ru — idioma\n"
        "• /city NombreCiudad — fijar ciudad (si no usas GPS)\n"
        "• /setloc lat lon tz [Ciudad] — fijar ubicación precisa\n"
        "• /sethour 0–23 — hora local del envío (por defecto 9)\n"
        "• /stop — darte de baja\n\n"
        "📌 Nota: si no configuras ciudad/ubicación, usaré Málaga como valor por defecto."
    )

# ================= Envío =================

Tramo = Optional[Tuple[dt.datetime, dt.datetime]]

async def enviar_a_usuario(bot: Bot, chat_id: str, prefs: dict, now_utc: dt.datetime):

    if ONLY_CHAT_ID and str(chat_id) != str(ONLY_CHAT_ID):
        return

    tzname = (prefs.get("tz") or "Europe/Madrid").strip()
    try:
        tz = pytz.timezone(tzname)
    except Exception:
        tz = pytz.timezone("Europe/Madrid")
        tzname = "Europe/Madrid"

    now_local = now_utc.astimezone(tz)
    hoy = now_local.date()

    # Ventana de envío / anti-duplicados
    if not FORCE_SEND and not should_send_now(prefs, now_utc):
        return
    if FORCE_SEND and prefs.get("last_sent_iso") == hoy.isoformat():
        return

    # ================= Ubicación (FIX) =================
    # ❌ NO usar IP (Railway) para ubicar al usuario.
    # ✅ Usar lat/lon guardados; si no, intentar geocodificar /city; si no, fallback Málaga explícito.
    lat = prefs.get("lat")
    lon = prefs.get("lon")
    ciudad = prefs.get("city")  # puede venir None

    if lat is None or lon is None:
        geo = geocode_city_open_meteo(ciudad or "")
        if geo:
            lat = geo["lat"]
            lon = geo["lon"]
            ciudad = ciudad or geo["name"]
            # Si viene timezone y el usuario no tenía tz, no lo tocamos aquí (lo ideal es guardarlo en /city o /setloc)
        else:
            # fallback explícito: Málaga
            lat = 36.7213
            lon = -4.4214
            ciudad = ciudad or "Málaga"

    # Idioma
    lang = prefs.get("lang", "es")

    # 🆕 Bienvenida/ayuda SOLO si es la primera vez que le mandamos algo
    # (lo más robusto sin cambiar el esquema es: last_sent_iso == None)
    if not prefs.get("last_sent_iso"):
        try:
            await bot.send_message(chat_id, traducir(welcome_help_es(), lang))
        except Exception:
            pass

    # 🔭 Cálculo solar (30–40°)
    tramo_m: Tramo = None
    tramo_t: Tramo = None
    try:
        tramo_m, tramo_t = calcular_intervalos_optimos(
            lat=float(lat),
            lon=float(lon),
            fecha=hoy,
            tzname=tzname,
        )
    except Exception as e:
        print(f"[WARN] calcular_intervalos_optimos falló: {e}")
        tramo_m, tramo_t = None, None

    hay_30_40 = bool(tramo_m or tramo_t)

    # 🌦️ Meteo (simple: nubes muy altas)
    pron = None
    try:
        pron = obtener_pronostico_diario(hoy, float(lat), float(lon), tzname)
    except Exception as e:
        print(f"[WARN] obtener_pronostico_diario falló: {e}")
        pron = None

    meteo_mala = False
    try:
        # tu hourly de Open-Meteo trae "cloudcover" (0-100) por hora
        if isinstance(pron, dict) and pron.get("cloudcover"):
            meteo_mala = max(pron["cloudcover"]) >= 85
    except Exception:
        meteo_mala = False

    # 🌞 Texto solar por casos
    if not hay_30_40:
        texto_solar = (
            f"☁️ En tu latitud hoy no podrás producir vitamina D: "
            f"el Sol no subirá por encima de 30° sobre el horizonte en {ciudad}."
        )
        est = estacion_del_anio(hoy, float(lat))
        extra = f"\n\n🍽️ Consejo nutricional de {est}:\n{pick_nutri(est, str(chat_id), hoy)}"

    elif meteo_mala:
        texto_solar = (
            "☁️ Hoy no se espera una ventana útil para sintetizar vitamina D por las condiciones meteorológicas.\n"
            "📌 Aun así, estas son las horas en las que el Sol estaría entre 30° y 40°:"
        )
        if tramo_m:
            texto_solar += f"\n🌅 Mañana: {tramo_m[0].strftime('%H:%M')}–{tramo_m[1].strftime('%H:%M')}"
        if tramo_t:
            texto_solar += f"\n🌇 Tarde: {tramo_t[0].strftime('%H:%M')}–{tramo_t[1].strftime('%H:%M')}"
        est = estacion_del_anio(hoy, float(lat))
        extra = f"\n\n🍽️ Consejo nutricional de {est}:\n{pick_nutri(est, str(chat_id), hoy)}"

    else:
        texto_solar = f"🌞 Intervalos solares seguros (30–40°) en {ciudad}:"
        if tramo_m:
            texto_solar += f"\n🌅 Mañana: {tramo_m[0].strftime('%H:%M')}–{tramo_m[1].strftime('%H:%M')}"
        if tramo_t:
            texto_solar += f"\n🌇 Tarde: {tramo_t[0].strftime('%H:%M')}–{tramo_t[1].strftime('%H:%M')}"
        extra = ""

    consejo, ref = consejo_del_dia(now_local)
    dia = ["Lunes","Martes","Miércoles","Jueves","Viernes","Sábado","Domingo"][now_local.weekday()]

    mensaje_es = (
        f"🧠 Consejo para hoy ({dia}):\n{consejo}\n\n"
        f"📚 *Referencia:* {ref}\n\n"
        f"{texto_solar}{extra}"
    )

    mensaje = traducir(mensaje_es, lang)

    if PING_ON_START:
        try:
            await bot.send_message(chat_id, "✅ Ping de diagnóstico (PING_ON_START activo).")
        except Exception:
            pass

    await bot.send_message(chat_id, mensaje)

    # ✅ anti-duplicados diario
    mark_sent_today(chat_id, hoy)

    # Canal opcional
    if CANAL_CHAT_ID:
        try:
            await bot.send_message(CANAL_CHAT_ID, mensaje)
        except Exception as e:
            print(f"[WARN] Canal: {e}")

# ================= Main =================

async def main():
    if not BOT_TOKEN:
        raise RuntimeError("❌ Falta BOT_TOKEN (Railway Variables).")
    if not DATABASE_DSN:
        # usuarios_repo normalmente usa DATABASE_DSN/DATABASE_URL para conectarse
        print("⚠️ Aviso: no veo DATABASE_DSN/DATABASE_URL en Variables. Si usuarios_repo usa Postgres, esto fallará.")

    init_db()
    users = list_users()
    if not users:
        print("ℹ️ No hay suscriptores aún.")
        return

    bot = Bot(BOT_TOKEN)
    now_utc = dt.datetime.now(dt.timezone.utc)

    for uid, prefs in users.items():
        try:
            await enviar_a_usuario(bot, uid, prefs, now_utc)
        except Exception as e:
            print(f"❌ Error en {uid}: {e}")

if __name__ == "__main__":
    asyncio.run(main())
