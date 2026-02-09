# enviar_consejo.py — CRON diario multiusuario (PRO)
# Vitamina D (30–40°) + mediodía solar + meteo + nutrición por estación + traducción
#
# - Envía a cada usuario a su hora local (por defecto 9) sin duplicar por día
# - Calcula tramos seguros 30–40° (mañana/tarde), INCLUSIVO (30 cuenta)
# - Añade 🧭 mediodía solar (cuando el Sol está más alto, no “las 12 del reloj”)
# - Si NO hay tramos (Sol <30°) -> mensaje “astronómico” (no llega por latitud/estación)
# - Si SÍ hay tramos pero la meteo lo impide -> muestra igualmente los tramos “teóricos” + nutri
# - Si SÍ hay tramos y la meteo es OK -> muestra tramos “reales” (según astron.) + sin nutri extra
#
# Variables de entorno (Railway):
#   BOT_TOKEN        (obligatoria)
#   DATABASE_DSN     (obligatoria, la usa usuarios_repo.py)  o  DATABASE_URL
#   FORCE_SEND=1     (opcional: envía aunque no sea la hora; NO duplica en el día)
#   ONLY_CHAT_ID=... (opcional: procesa solo ese chat_id)
#   PING_ON_START=1  (opcional: manda ping de diagnóstico al usuario)
#   CANAL_CHAT_ID=.. (opcional: publica también en un canal)
#
# Requiere: python-telegram-bot==21.4, deep-translator, pytz

import os
import asyncio
import datetime as dt
from typing import Optional, Tuple

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
    calcular_mediodia_solar,
)

# ================= ENV =================

BOT_TOKEN = os.getenv("BOT_TOKEN")
FORCE_SEND = os.getenv("FORCE_SEND", "0").strip() == "1"
ONLY_CHAT_ID = os.getenv("ONLY_CHAT_ID")
PING_ON_START = os.getenv("PING_ON_START", "0").strip() == "1"
CANAL_CHAT_ID = os.getenv("CANAL_CHAT_ID")  # opcional

# Nota: DATABASE_DSN/DATABASE_URL se usan dentro de usuarios_repo.py. Aquí no se leen.

# ================= Idiomas =================

VALID_LANG = {"es", "en", "fr", "it", "de", "pt", "nl", "sr", "ru"}

_LANG_ALIAS = {
    # serbio como proxy para croata/bosnio (+ códigos antiguos)
    "sh": "sr", "sc": "sr", "srp": "sr", "hr": "sr", "bs": "sr",
    # variantes comunes
    "pt-br": "pt",
    "es-es": "es",
    "en-us": "en",
    "en-gb": "en",
}

def _norm_lang(code: Optional[str]) -> str:
    if not code:
        return "es"
    code = code.strip().lower()
    code = _LANG_ALIAS.get(code, code)
    return code if code in VALID_LANG else "es"

def traducir(texto: str, lang: Optional[str]) -> str:
    dest = _norm_lang(lang)
    if dest == "es":
        return texto
    try:
        return LibreTranslator(source="es", target=dest).translate(texto)
    except Exception as e:
        print(f"⚠️ Traducción fallida ({dest}): {e}")
        return texto

# ================= Estación (simple y robusta) =================

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
    ops = list(ops)
    if not ops:
        return "Prioriza alimentos reales y, si procede, alimentos fortificados en vitamina D."
    idx = (hash(str(chat_id)) + fecha.toordinal()) % len(ops)
    return ops[idx]

# ================= Consejo diario =================

def consejo_del_dia(now_local: dt.datetime) -> Tuple[str, str]:
    """
    consejos[dia_semana] = [texto, ref, texto, ref, ...]
    Elegimos 1 par estable por fecha local.
    """
    lista = consejos[now_local.weekday()]
    pares = [lista[i:i+2] for i in range(0, len(lista), 2)]
    idx = now_local.date().toordinal() % len(pares)
    consejo, ref = pares[idx]
    return consejo, ref

# ================= Meteo: regla “simple pero útil” =================
# (mantengo tu criterio actual: si cloudcover horaria alcanza >=85% lo consideramos “mala”)

def meteo_mala_por_nubes(pron: Optional[dict]) -> bool:
    if not pron:
        return False
    clouds = pron.get("cloudcover")
    if not clouds:
        return False
    try:
        return max(clouds) >= 85
    except Exception:
        return False

# ================= Formato solar “pro” =================

Tramo = Optional[Tuple[dt.datetime, dt.datetime]]

def _fmt_hhmm(x: dt.datetime) -> str:
    return x.strftime("%H:%M")

def _bloque_ventanas(ciudad: str, tramo_m: Tramo, tramo_t: Tramo) -> str:
    """
    Devuelve líneas con ventanas mañana/tarde si existen.
    """
    lineas = [f"🌤️ Ventanas 30–40° en {ciudad}:"]
    if tramo_m:
        lineas.append(f"🌅 Mañana: {_fmt_hhmm(tramo_m[0])}–{_fmt_hhmm(tramo_m[1])}")
    if tramo_t:
        lineas.append(f"🌇 Tarde: {_fmt_hhmm(tramo_t[0])}–{_fmt_hhmm(tramo_t[1])}")
    return "\n".join(lineas)

def _linea_mediodia_solar(fecha: dt.date, lon: float, tzname: str) -> str:
    """
    Línea divulgativa: mediodía solar (máxima altura del Sol).
    """
    try:
        ms = calcular_mediodia_solar(fecha, lon, tzname)
        return f"🧭 Mediodía solar: {ms.strftime('%H:%M')} (máxima altura del Sol)"
    except Exception:
        return ""

# ================= Envío =================

async def enviar_a_usuario(bot: Bot, chat_id: str, prefs: dict, now_utc: dt.datetime):

    # Filtrado opcional
    if ONLY_CHAT_ID and str(chat_id) != str(ONLY_CHAT_ID):
        return

    # TZ
    tzname = (prefs.get("tz") or "Europe/Madrid").strip()
    try:
        tz = pytz.timezone(tzname)
    except Exception:
        tz = pytz.timezone("Europe/Madrid")
        tzname = "Europe/Madrid"

    now_local = now_utc.astimezone(tz)
    hoy = now_local.date()

    # Ventana de envío:
    if not FORCE_SEND:
        if not should_send_now(prefs, now_utc):
            return
    else:
        # FORCE_SEND sin spam: respeta “no duplicado por día”
        if prefs.get("last_sent_iso") == hoy.isoformat():
            return

    # Ubicación: preferimos coords guardadas. Si faltan -> obtener_ubicacion (fallback Málaga)
    lat = prefs.get("lat")
    lon = prefs.get("lon")
    ciudad = prefs.get("city") or "tu zona"

    if lat is None or lon is None:
        ub = obtener_ubicacion()
        lat = ub["latitud"]
        lon = ub["longitud"]
        ciudad = ub.get("ciudad") or ciudad

    lat = float(lat)
    lon = float(lon)

    # Mediodía solar (línea)
    linea_mediodia = _linea_mediodia_solar(hoy, lon, tzname)

    # 1) Ventanas 30–40° (astronómicas)
    try:
        tramo_m, tramo_t = calcular_intervalos_optimos(
            lat=lat,
            lon=lon,
            fecha=hoy,
            tzname=tzname,
        )
    except Exception as e:
        print(f"[WARN] calcular_intervalos_optimos falló: {e}")
        tramo_m, tramo_t = None, None

    hay_ventana = bool(tramo_m or tramo_t)

    # 2) Meteo
    try:
        pron = obtener_pronostico_diario(hoy, lat, lon, tzname)
    except Exception as e:
        print(f"[WARN] obtener_pronostico_diario falló: {e}")
        pron = None

    meteo_mala = meteo_mala_por_nubes(pron)

    # 3) Construir bloque solar según casos
    # A) No hay ventana: por latitud/estación no llega a 30°
    # B) Hay ventana pero meteo mala: mostrar tramos “teóricos” + nutri
    # C) Hay ventana y meteo OK: mostrar tramos “reales” (astronómicos)

    if not hay_ventana:
        texto_solar_es = (
            f"☁️ Hoy, en tu latitud, el Sol no subirá por encima de 30° sobre el horizonte en {ciudad}.\n"
            f"➡️ Por tanto, no hay ventana 30–40° para sintetizar vitamina D."
        )
        if linea_mediodia:
            texto_solar_es += f"\n{linea_mediodia}"

        est = estacion_del_anio(hoy, lat)
        nutri = pick_nutri(est, str(chat_id), hoy)
        extra_es = f"\n\n🍽️ Consejo nutricional de {est}:\n{nutri}"

    elif meteo_mala:
        texto_solar_es = (
            "☁️ Hoy no se espera una ventana útil de sol para sintetizar vitamina D por nubosidad alta.\n"
            "📌 Aun así, estas son las horas *teóricas* en las que el Sol estaría entre 30° y 40°:"
            f"\n\n{_bloque_ventanas(ciudad, tramo_m, tramo_t)}"
        )
        if linea_mediodia:
            texto_solar_es += f"\n{linea_mediodia}"

        est = estacion_del_anio(hoy, lat)
        nutri = pick_nutri(est, str(chat_id), hoy)
        extra_es = f"\n\n🍽️ Consejo nutricional de {est}:\n{nutri}"

    else:
        texto_solar_es = (
            "🌞 Ventanas saludables para vitamina D (30–40°):"
            f"\n\n{_bloque_ventanas(ciudad, tramo_m, tramo_t)}"
        )
        if linea_mediodia:
            texto_solar_es += f"\n{linea_mediodia}"
        extra_es = ""

    # 4) Consejo del día
    consejo_es, ref_es = consejo_del_dia(now_local)
    dia = ["Lunes","Martes","Miércoles","Jueves","Viernes","Sábado","Domingo"][now_local.weekday()]

    mensaje_es = (
        f"🧠 Consejo para hoy ({dia}):\n{consejo_es}\n\n"
        f"📚 Referencia: {ref_es}\n\n"
        f"{texto_solar_es}{extra_es}"
    )

    # 5) Traducción
    lang = prefs.get("lang")
    mensaje = traducir(mensaje_es, lang)

    # 6) Ping opcional
    if PING_ON_START:
        try:
            await bot.send_message(chat_id=chat_id, text="✅ Ping de diagnóstico (PING_ON_START activo).")
        except Exception as e:
            print(f"[WARN] Ping falló: {e}")

    # 7) Enviar
    await bot.send_message(chat_id=chat_id, text=mensaje)

    # 8) Marcar como enviado hoy (no duplicar)
    mark_sent_today(chat_id, hoy)

    # 9) Publicar en canal (opcional)
    if CANAL_CHAT_ID:
        try:
            pub = f"🔔 Consejo público:\n{mensaje}"
            if len(pub) > 3800:
                pub = pub[:3790] + "…"
            await bot.send_message(chat_id=CANAL_CHAT_ID, text=pub)
        except Exception as e:
            print(f"[WARN] No pude publicar en canal: {e}")

# ================= Main =================

async def main():
    if not BOT_TOKEN:
        raise RuntimeError("❌ Falta BOT_TOKEN")

    init_db()
    users = list_users()
    if not users:
        print("ℹ️ No hay suscriptores aún.")
        return

    bot = Bot(BOT_TOKEN)
    now_utc = dt.datetime.now(dt.timezone.utc)

    procesados = 0
    enviados = 0

    for uid, prefs in users.items():
        procesados += 1
        try:
            before = prefs.get("last_sent_iso")
            await enviar_a_usuario(bot, uid, prefs, now_utc)
            # No re-leemos DB; “enviados” real lo verás por logs de Telegram.
            # Aun así, contamos como intento.
            enviados += 1
        except Exception as e:
            print(f"❌ Error en {uid}: {e}")

    print(f"✅ Cron OK. Procesados: {procesados}. Intentos: {enviados}. FORCE_SEND={FORCE_SEND}")

if __name__ == "__main__":
    asyncio.run(main())
