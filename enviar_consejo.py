# enviar_consejo.py — multiusuario (cron) + vit D 30–40° + meteo + consejo nutricional por estación + traducción
# - Envía a cada usuario a su hora local (por defecto 9) sin duplicar por día
# - Calcula tramos seguros 30–40° (mañana/tarde)
# - Si NO hay tramos (Sol <30°) -> mensaje astronómico (no se puede por latitud)
# - Si SÍ hay tramos pero la meteo lo impide -> muestra igualmente las horas 30–40° como "teóricas"
# - Si SÍ hay tramos y la meteo es OK -> muestra las horas 30–40° y consejo normal
#
# Variables de entorno:
#   BOT_TOKEN        (obligatoria)
#   DATABASE_DSN     (obligatoria para Postgres)
#   FORCE_SEND=1     (opcional: envía aunque no sea la hora; respeta "no duplicados" del día)
#   ONLY_CHAT_ID=... (opcional: procesa solo ese chat_id)
#   PING_ON_START=1  (opcional: manda un ping de diagnóstico al usuario)
#   CANAL_CHAT_ID=.. (opcional: publica también en un canal)
#
# Requiere: python-telegram-bot (Bot), deep-translator, pytz

import os
import asyncio
import datetime
from typing import Optional, Tuple, Any, Dict

import pytz
from telegram import Bot
from deep_translator import LibreTranslator

from consejos_diarios import consejos
from consejos_nutri import CONSEJOS_NUTRI
from usuarios_repo import (
    init_db,
    list_users,
    should_send_now,
    mark_sent_today,
)

from ubicacion_y_sol import (
    obtener_ubicacion,          # fallback general
    calcular_intervalos_optimos, # tu cálculo "preciso" (ya lo tienes funcionando)
    obtener_pronostico_diario,   # Open-Meteo (ya lo tienes)
)

# -------------------- ENV --------------------

BOT_TOKEN = os.getenv("BOT_TOKEN")
FORCE_SEND = os.getenv("FORCE_SEND", "0").strip() == "1"
PING_ON_START = os.getenv("PING_ON_START", "0").strip() == "1"
ONLY_CHAT_ID = os.getenv("ONLY_CHAT_ID")
CANAL_CHAT_ID = os.getenv("CANAL_CHAT_ID")  # opcional

# -------------------- Traducción --------------------

# Idiomas soportados por tu bot (canónicos)
VALID_LANG = {"es", "en", "fr", "it", "de", "pt", "nl", "sr", "ru"}

# Alias -> canónico
_LANG_ALIAS = {
    # serbio como proxy para croata/bosnio (+ códigos antiguos)
    "sh": "sr", "sc": "sr", "srp": "sr", "hr": "sr", "bs": "sr",
    # variantes comunes
    "pt-br": "pt",
    # a veces llegan así:
    "es-es": "es", "en-us": "en", "en-gb": "en",
}

def _norm_lang(code: Optional[str]) -> str:
    if not code:
        return "es"
    code = code.strip().lower()
    code = _LANG_ALIAS.get(code, code)
    if code not in VALID_LANG:
        return "es"
    return code

def traducir(texto: str, lang: Optional[str]) -> str:
    dest = _norm_lang(lang)
    if dest == "es":
        return texto
    try:
        return LibreTranslator(source="es", target=dest).translate(texto)
    except Exception as e:
        print(f"⚠️ Traducción fallida ({dest}): {e}")
        return texto

# -------------------- Estación del año --------------------

def estacion_del_anio(fecha: datetime.date, lat: float) -> str:
    """
    Devuelve: 'Primavera'|'Verano'|'Otoño'|'Invierno'
    Ajusta por hemisferio según latitud.
    """
    # Rangos meteorológicos aproximados por meses (simple y robusto)
    m = fecha.month
    hemisferio_norte = (lat is None) or (lat >= 0)

    if hemisferio_norte:
        if m in (12, 1, 2):
            return "Invierno"
        if m in (3, 4, 5):
            return "Primavera"
        if m in (6, 7, 8):
            return "Verano"
        return "Otoño"
    else:
        # invertido
        if m in (12, 1, 2):
            return "Verano"
        if m in (3, 4, 5):
            return "Otoño"
        if m in (6, 7, 8):
            return "Invierno"
        return "Primavera"

def _pick_nutri_tip(estacion: str, chat_id: str, fecha: datetime.date) -> str:
    """
    CONSEJOS_NUTRI[estacion] puede ser tupla/lista de strings o un string.
    Elegimos 1 de forma estable por fecha+usuario.
    """
    opciones = CONSEJOS_NUTRI.get(estacion) or CONSEJOS_NUTRI.get("Invierno")
    if opciones is None:
        return "Prioriza alimentos reales ricos en nutrientes y, si procede, alimentos fortificados en vitamina D."
    if isinstance(opciones, str):
        return opciones
    try:
        opciones = list(opciones)
        if not opciones:
            return "Prioriza alimentos reales ricos en nutrientes y, si procede, alimentos fortificados en vitamina D."
        idx = (hash(str(chat_id)) + fecha.toordinal()) % len(opciones)
        return opciones[idx]
    except Exception:
        return "Prioriza alimentos reales ricos en nutrientes y, si procede, alimentos fortificados en vitamina D."

# -------------------- Meteo: decidir si “impide” vit D --------------------

# Códigos Open-Meteo típicos (WMO):
# 0: despejado, 1/2/3: principalmente despejado/ parcialmente/ nublado
# 45/48: niebla, 51-67: llovizna, 61-65: lluvia, 71-77: nieve, 80-82: chubascos, 95-99 tormenta
_BAD_WEATHER_CODES = set([45, 48, 51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 71, 73, 75, 77, 80, 81, 82, 85, 86, 95, 96, 99])

def _extract_weathercode(pron: Any) -> Optional[int]:
    """
    Intenta sacar un weathercode “diario” de distintas formas.
    """
    if pron is None:
        return None
    try:
        # Si es dict estilo Open-Meteo:
        if isinstance(pron, dict):
            # daily.weathercode[0]
            daily = pron.get("daily")
            if isinstance(daily, dict):
                wc = daily.get("weathercode")
                if isinstance(wc, list) and wc:
                    return int(wc[0])
                if wc is not None:
                    return int(wc)
            # a veces viene directo
            wc = pron.get("weathercode")
            if isinstance(wc, list) and wc:
                return int(wc[0])
            if wc is not None:
                return int(wc)
        return None
    except Exception:
        return None

def _extract_cloud_or_precip(pron: Any) -> Tuple[Optional[float], Optional[float]]:
    """
    Devuelve (cloudcover, precip_prob) si aparecen.
    """
    cloud = None
    pprob = None
    try:
        if isinstance(pron, dict):
            daily = pron.get("daily")
            if isinstance(daily, dict):
                # Open-Meteo puede dar cloudcover_mean, precipitation_probability_max
                cc = daily.get("cloudcover_mean") or daily.get("cloudcover")
                if isinstance(cc, list) and cc:
                    cloud = float(cc[0])
                elif cc is not None:
                    cloud = float(cc)

                pp = daily.get("precipitation_probability_max") or daily.get("precipitation_probability")
                if isinstance(pp, list) and pp:
                    pprob = float(pp[0])
                elif pp is not None:
                    pprob = float(pp)
        return cloud, pprob
    except Exception:
        return cloud, pprob

def meteo_impide_vitd(pron: Any) -> bool:
    """
    Regla robusta:
    - Si weathercode es “malo” -> True
    - Si prob. precip alta -> True
    - Si nubosidad media muy alta -> True (umbral conservador)
    """
    wc = _extract_weathercode(pron)
    if wc is not None and wc in _BAD_WEATHER_CODES:
        return True

    cloud, pprob = _extract_cloud_or_precip(pron)
    if pprob is not None and pprob >= 50:
        return True
    if cloud is not None and cloud >= 85:
        return True

    return False

# -------------------- Formateo de tramos --------------------

# tramo: (inicio_dt, fin_dt) o None
Tramo = Optional[Tuple[datetime.datetime, datetime.datetime]]

def _fmt_hhmm(dt: datetime.datetime) -> str:
    return dt.strftime("%H:%M")

def _tramo_to_str(label: str, tramo: Tramo) -> Optional[str]:
    if not tramo:
        return None
    a, b = tramo
    return f"{label}: {_fmt_hhmm(a)}–{_fmt_hhmm(b)}"

def _tramos_a_texto_detallado(ciudad: str, tramo_m: Tramo, tramo_t: Tramo) -> str:
    partes = [f"🌤️ Intervalos 30–40° en {ciudad}:"]
    m = _tramo_to_str("🌅 Mañana", tramo_m)
    t = _tramo_to_str("🌇 Tarde", tramo_t)
    if m:
        partes.append(m)
    if t:
        partes.append(t)
    # si solo hay 1 tramo (a veces pasa), no inventamos el otro
    return "\n".join(partes)

def _hay_alguna_ventana(tramo_m: Tramo, tramo_t: Tramo) -> bool:
    return bool(tramo_m) or bool(tramo_t)

# -------------------- Consejo diario (inmune) --------------------

def _consejo_del_dia(now_local: datetime.datetime) -> Tuple[str, str]:
    """
    Usa tu estructura consejos[dia_semana] = [texto, ref, texto, ref, ...]
    Elige par estable por fecha (no se repite en el mismo día).
    """
    dia_semana = now_local.weekday()  # lunes=0
    lista = consejos[dia_semana]
    pares = [lista[i:i+2] for i in range(0, len(lista), 2)]
    idx = now_local.date().toordinal() % len(pares)
    consejo_es, ref_es = pares[idx]
    return consejo_es, ref_es

# -------------------- Envío a un usuario --------------------

async def enviar_a_usuario(bot: Bot, chat_id: str, prefs: dict, now_utc: datetime.datetime):
    # Filtrado opcional por chat_id
    if ONLY_CHAT_ID and str(chat_id) != str(ONLY_CHAT_ID):
        return

    # Hora local del usuario
    tzname = (prefs.get("tz") or "Europe/Madrid").strip()
    try:
        tz = pytz.timezone(tzname)
    except Exception:
        tz = pytz.timezone("Europe/Madrid")
        tzname = "Europe/Madrid"

    now_local = now_utc.astimezone(tz)
    hoy_local = now_local.date()

    # Ventana de envío:
    # - si FORCE_SEND: se permite enviar ahora, pero igual NO duplicamos por día (mark_sent_today lo bloquea)
    # - si no FORCE_SEND: usamos should_send_now (ventana 10 min y no enviado hoy)
    if not FORCE_SEND:
        if not should_send_now(prefs, now_utc=now_utc):
            return
    else:
        # si ya se envió hoy, no forzamos de nuevo (evita spam cada 5 min)
        if prefs.get("last_sent_iso") == hoy_local.isoformat():
            return

    # Ubicación: GPS > ciudad > fallback
    lat = prefs.get("lat")
    lon = prefs.get("lon")
    ciudad = prefs.get("city")
    if lat is None or lon is None:
        ub = obtener_ubicacion()  # tu fallback
        lat = float(ub["latitud"])
        lon = float(ub["longitud"])
        ciudad = ciudad or ub.get("ciudad") or "tu zona"

    # Idioma
    lang = prefs.get("lang", "es")

    # 1) Calcular intervalos 30–40°
    #    (Se asume que tu calcular_intervalos_optimos ya devuelve (tramo_m, tramo_t) en hora local)
    tramo_m: Tramo = None
    tramo_t: Tramo = None
    try:
        tramo_m, tramo_t = calcular_intervalos_optimos(hoy_local, float(lat), float(lon), tzname)
    except Exception as e:
        print(f"[WARN] calcular_intervalos_optimos falló: {e}")
        tramo_m, tramo_t = None, None

    hay_tramos = _hay_alguna_ventana(tramo_m, tramo_t)

    # 2) Meteo (para decidir si “impide” vit D)
    pron = None
    try:
        pron = obtener_pronostico_diario(float(lat), float(lon), hoy_local, tzname)
    except Exception as e:
        print(f"[WARN] obtener_pronostico_diario falló: {e}")
        pron = None

    meteo_mala = meteo_impide_vitd(pron)

    # 3) Construir bloque solar según casos
    # Caso A: NO hay tramos -> el Sol no llega a 30° (latitud/estación)
    # Caso B: hay tramos, pero meteo mala -> mostrar horas 30–40 como teóricas
    # Caso C: hay tramos y meteo OK -> mostrar horas 30–40 normales
    if not hay_tramos:
        texto_solar_es = (
            f"☁️ En tu latitud hoy no podrás producir vitamina D: "
            f"el Sol no subirá por encima de 30° sobre el horizonte en {ciudad}."
        )
        # Como no hay 30–40°, no podemos listarlos.
        est = estacion_del_anio(hoy_local, float(lat))
        nutri_es = _pick_nutri_tip(est, str(chat_id), hoy_local)
        bloque_extra_es = f"🍽️ Consejo nutricional de {est}:\n{nutri_es}"

    elif meteo_mala:
        # ✅ Tu petición: aunque hoy no sea aprovechable por meteo, damos las horas 30–40°
        tramos_txt = _tramos_a_texto_detallado(ciudad, tramo_m, tramo_t)
        texto_solar_es = (
            "☁️ Hoy no se espera una ventana útil de sol para sintetizar vitamina D por las condiciones meteorológicas.\n"
            "📌 Aun así, estas son las horas en las que el Sol estará entre 30° y 40° sobre el horizonte (si el cielo estuviera despejado):\n\n"
            f"{tramos_txt}"
        )
        est = estacion_del_anio(hoy_local, float(lat))
        nutri_es = _pick_nutri_tip(est, str(chat_id), hoy_local)
        bloque_extra_es = f"🍽️ Consejo nutricional de {est}:\n{nutri_es}"

    else:
        # Caso C: hay tramos y meteo OK
        tramos_txt = _tramos_a_texto_detallado(ciudad, tramo_m, tramo_t)
        texto_solar_es = (
            "🌞 Intervalos solares seguros para producir vit. D (30–40°):\n\n"
            f"{tramos_txt}"
        )
        bloque_extra_es = ""  # no metemos nutricional salvo que quieras (ahora lo dejamos limpio)

    # 4) Consejo inmune del día + referencia
    consejo_es, ref_es = _consejo_del_dia(now_local)
    dia_nombre_es = ["Lunes","Martes","Miércoles","Jueves","Viernes","Sábado","Domingo"][now_local.weekday()]

    cuerpo_es = (
        f"🧠 Consejo para hoy ({dia_nombre_es}):\n{consejo_es}\n\n"
        f"📚 *Referencia:* {ref_es}\n\n"
        f"{texto_solar_es}"
    )
    if bloque_extra_es:
        cuerpo_es += "\n\n" + bloque_extra_es

    cuerpo = traducir(cuerpo_es, lang) or cuerpo_es
    if len(cuerpo) > 4000:
        cuerpo = cuerpo[:3990] + "…"

    # Ping opcional (solo si lo activas)
    if PING_ON_START:
        try:
            await bot.send_message(chat_id=chat_id, text="✅ Ping de diagnóstico (PING_ON_START activo).")
        except Exception as e:
            print(f"[WARN] Ping falló: {e}")

    # 5) Enviar a usuario
    await bot.send_message(chat_id=chat_id, text=cuerpo)

    # 6) Marcar enviado hoy (para no repetir)
    mark_sent_today(chat_id, hoy_local)

    # 7) Opcional: publicar también en canal
    if CANAL_CHAT_ID:
        try:
            pub = f"🔔 Consejo público:\n{cuerpo}"
            if len(pub) > 3800:
                pub = pub[:3790] + "…"
            await bot.send_message(chat_id=CANAL_CHAT_ID, text=pub)
        except Exception as e:
            print(f"[WARN] No pude publicar en canal: {e}")

# -------------------- Main (cron) --------------------

async def main():
    if not BOT_TOKEN:
        raise RuntimeError("❌ Falta BOT_TOKEN en Variables de Railway.")
    init_db()

    users = list_users()
    if not users:
        print("ℹ️ No hay suscriptores aún.")
        return

    bot = Bot(token=BOT_TOKEN)
    now_utc = datetime.datetime.now(datetime.timezone.utc)

    procesados = 0
    intentos = 0
    errores = 0

    for uid, prefs in users.items():
        procesados += 1
        try:
            before_last = prefs.get("last_sent_iso")
            await enviar_a_usuario(bot, uid, prefs, now_utc)
            # si cambió last_sent_iso en DB, cuenta como intento real
            # (no lo leemos aquí otra vez para no recargar; lo dejamos como “intento potencial”)
            intentos += 1
        except Exception as e:
            errores += 1
            print(f"❌ Error enviando a {uid}: {e}")

    print(f"✅ Ciclo cron OK. Usuarios procesados: {procesados}. Intentos: {intentos}. Errores: {errores}. FORCE_SEND={FORCE_SEND}")

if __name__ == "__main__":
    asyncio.run(main())
