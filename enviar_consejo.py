# enviar_consejo.py — CRON diario multiusuario
# Vitamina D (30–40°), meteo, nutrición por estación y traducción

import os
import asyncio
import datetime as dt
from typing import Optional

import pytz
from telegram import Bot
from deep_translator import LibreTranslator

from consejos_diarios import consejos
from consejos_nutri import CONSEJOS_NUTRI
from usuarios_repo import init_db, list_users, should_send_now, mark_sent_today

from ubicacion_y_sol import (
    obtener_ubicacion,
    calcular_intervalos_optimos,
    obtener_pronostico_diario,
    obtener_mediodia_solar_y_altura_max,
    describir_intervalos_con_mediodia,
    formatear_intervalos_meteo,
)

# ================= ENV =================

BOT_TOKEN = os.getenv("BOT_TOKEN")
FORCE_SEND = os.getenv("FORCE_SEND", "0") == "1"
ONLY_CHAT_ID = os.getenv("ONLY_CHAT_ID")
PING_ON_START = os.getenv("PING_ON_START", "0") == "1"
CANAL_CHAT_ID = os.getenv("CANAL_CHAT_ID")

# ================= Idiomas =================

VALID_LANG = {"es", "en", "fr", "it", "de", "pt", "nl", "sr", "ru"}

_LANG_ALIAS = {
    "sh": "sr", "sc": "sr", "srp": "sr", "hr": "sr", "bs": "sr",
    "pt-br": "pt",
    "es-es": "es", "en-us": "en", "en-gb": "en",
}

def _norm_lang(code: Optional[str]) -> str:
    if not code:
        return "es"
    code = _LANG_ALIAS.get(code.lower(), code.lower())
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

def consejo_del_dia(now_local: dt.datetime):
    lista = consejos[now_local.weekday()]
    pares = [lista[i:i+2] for i in range(0, len(lista), 2)]
    idx = now_local.date().toordinal() % len(pares)
    return pares[idx]

# ================= Envío =================

async def enviar_a_usuario(bot: Bot, chat_id: str, prefs: dict, now_utc: dt.datetime):

    if ONLY_CHAT_ID and str(chat_id) != str(ONLY_CHAT_ID):
        return

    tzname = prefs.get("tz") or "Europe/Madrid"
    tz = pytz.timezone(tzname)
    now_local = now_utc.astimezone(tz)
    hoy = now_local.date()

    if not FORCE_SEND and not should_send_now(prefs, now_utc):
        return
    if FORCE_SEND and prefs.get("last_sent_iso") == hoy.isoformat():
        return

    lat = prefs.get("lat")
    lon = prefs.get("lon")
    ciudad = prefs.get("city") or "tu ciudad"

    # Si el usuario NO tiene lat/lon guardadas, usamos IP (pero solo como último recurso)
    if lat is None or lon is None:
        ub = obtener_ubicacion()
        lat, lon, ciudad = ub["latitud"], ub["longitud"], ub["ciudad"]

    lat = float(lat)
    lon = float(lon)

    # 🔭 Cálculo solar (30–40) + mediodía solar y altura máxima
    tramo_m, tramo_t = calcular_intervalos_optimos(
        lat=lat,
        lon=lon,
        fecha=hoy,
        tzname=tzname,
    )
    mediodia_solar_dt, alt_max = obtener_mediodia_solar_y_altura_max(lat, lon, hoy, tzname)

    hay_30 = bool(tramo_m or tramo_t)

    # 🌦️ Meteo
    pron = obtener_pronostico_diario(hoy, lat, lon, tzname)

    # Evaluación simple: nubosidad alta en el día (si hay datos)
    meteo_mala = False
    if pron and pron.get("cloudcover"):
        try:
            meteo_mala = max(pron["cloudcover"]) >= 85
        except Exception:
            meteo_mala = False

    # 🧾 Texto solar base (sin “teóricas”)
    if not hay_30:
        texto_solar = (
            f"☁️ En tu latitud hoy no podrás producir vitamina D: "
            f"el Sol no subirá por encima de 30° sobre el horizonte en {ciudad}.\n"
            f"🧭 Mediodía solar: {mediodia_solar_dt.strftime('%H:%M')} (altura máxima ≈ {alt_max:.1f}°)"
        )
        est = estacion_del_anio(hoy, lat)
        extra = f"\n\n🍽️ Consejo nutricional de {est}:\n{pick_nutri(est, chat_id, hoy)}"

    else:
        # Siempre mostramos las ventanas reales 30–40°
        base_ventanas = describir_intervalos_con_mediodia(
            (tramo_m, tramo_t),
            ciudad=ciudad,
            mediodia_solar=mediodia_solar_dt,
            alt_max=alt_max,
        )

        if meteo_mala:
            # Aclaración correcta: el Sol estará ahí, pero la síntesis puede verse limitada por nubes
            texto_solar = (
                "☁️ Hoy hay nubosidad alta: eso puede reducir mucho la radiación UVB y, por tanto, la síntesis real de vitamina D.\n"
                "📌 Aun así, estas son las ventanas en las que el Sol estará entre 30° y 40°:"
                f"\n\n{base_ventanas}"
            )

            # Añadimos resumen meteo dentro de los tramos, si podemos
            meteo_txt = formatear_intervalos_meteo((tramo_m, tramo_t), pron)
            if meteo_txt:
                texto_solar += f"\n\n🌦️ Meteo durante las ventanas:{meteo_txt}"

            est = estacion_del_anio(hoy, lat)
            extra = f"\n\n🍽️ Consejo nutricional de {est}:\n{pick_nutri(est, chat_id, hoy)}"
        else:
            texto_solar = f"{base_ventanas}"
            meteo_txt = formatear_intervalos_meteo((tramo_m, tramo_t), pron)
            if meteo_txt:
                texto_solar += f"\n\n🌦️ Meteo durante las ventanas:{meteo_txt}"
            extra = ""

    consejo, ref = consejo_del_dia(now_local)
    dia = ["Lunes","Martes","Miércoles","Jueves","Viernes","Sábado","Domingo"][now_local.weekday()]

    mensaje_es = (
        f"🧠 Consejo para hoy ({dia}):\n{consejo}\n\n"
        f"📚 *Referencia:* {ref}\n\n"
        f"{texto_solar}{extra}"
    )

    mensaje = traducir(mensaje_es, prefs.get("lang"))

    if PING_ON_START:
        await bot.send_message(chat_id, "✅ Ping de diagnóstico")

    await bot.send_message(chat_id, mensaje)
    mark_sent_today(chat_id, hoy)

    if CANAL_CHAT_ID:
        await bot.send_message(CANAL_CHAT_ID, mensaje)

# ================= Main =================

async def main():
    if not BOT_TOKEN:
        raise RuntimeError("Falta BOT_TOKEN")

    init_db()
    users = list_users()
    if not users:
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
