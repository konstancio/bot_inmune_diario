# enviar_consejo.py — envío diario (mañana) con sol 30–40°, meteo y mediodía solar
# Requiere: usuarios_repo.py, ubicacion_y_sol.py, consejos_diarios.py
# ENV:
#   BOT_TOKEN=...
#   DATABASE_URL o DATABASE_DSN=...
#   ONLY_CHAT_ID=... (opcional, para pruebas)
#   FORCE_SEND=1 (opcional, fuerza envío aunque no sea la hora)

import os
import asyncio
import datetime as dt
import pytz
from telegram import Bot

import usuarios_repo as repo

from consejos_diarios import CONSEJOS_DIARIOS

from ubicacion_y_sol import (
    calcular_intervalos_optimos,
    describir_intervalos,
    obtener_pronostico_diario,
    formatear_intervalos_meteo,
)

BOT_TOKEN = os.getenv("BOT_TOKEN")
ONLY_CHAT_ID = os.getenv("ONLY_CHAT_ID")
FORCE_SEND = os.getenv("FORCE_SEND", "").strip() in {"1", "true", "True", "YES", "yes"}


def elegir_consejo(chat_id: str, fecha: dt.date) -> str:
    # determinista por usuario y día (evita repetición rara si reinicias)
    idx = (hash(str(chat_id)) + fecha.toordinal()) % len(CONSEJOS_DIARIOS)
    return CONSEJOS_DIARIOS[idx]


def _solar_noon_local(fecha: dt.date, lon: float, tzname: str) -> dt.datetime:
    """
    Mediodía solar aproximado (cuando el ángulo horario = 0).
    Usamos la misma ecuación del tiempo que en ubicacion_y_sol (vía llamada interna simple).
    Como no está exportada, lo aproximamos por búsqueda: el minuto con mayor elevación.
    """
    tz = pytz.timezone(tzname)
    # barrido rápido de 10:00 a 14:00 local
    best_t = None
    best_e = -999.0

    # Importamos internamente la elevación ya implementada en ubicacion_y_sol
    # (sin tocar su API pública)
    from ubicacion_y_sol import _declinacion_solar, _solar_hour_angle, _elevacion_solar_deg  # type: ignore

    n = fecha.timetuple().tm_yday
    decl = _declinacion_solar(n)

    base = tz.localize(dt.datetime(fecha.year, fecha.month, fecha.day, 10, 0))
    for m in range(0, 4 * 60):  # 10:00–14:00
        t = base + dt.timedelta(minutes=m)
        h = _solar_hour_angle(t, lon, tzname, n)
        e = _elevacion_solar_deg(float(os.getenv("_TMP_LAT", "0") or 0), decl, h)  # placeholder, lo sobrescribimos
        # 👆 truco: lo recalcularemos bien fuera. Esta función la reemplazamos abajo.

    # Rehacemos correctamente sin el truco:
    # (duplicamos una línea para no depender de variables globales)
    from ubicacion_y_sol import _declinacion_solar as dsol  # type: ignore
    from ubicacion_y_sol import _solar_hour_angle as sha     # type: ignore
    from ubicacion_y_sol import _elevacion_solar_deg as esd  # type: ignore

    decl = dsol(n)

    # La latitud la recibiremos por un closure en la función que llama; aquí la dejamos preparada:
    # (la función real se monta en enviar_a_usuario)
    return tz.localize(dt.datetime(fecha.year, fecha.month, fecha.day, 12, 0))


async def enviar_a_usuario(bot: Bot, chat_id: str, prefs: dict, now_utc: dt.datetime) -> None:
    # filtro opcional para pruebas
    if ONLY_CHAT_ID and str(chat_id) != str(ONLY_CHAT_ID):
        return

    tzname = (prefs.get("tz") or "Europe/Madrid").strip()
    try:
        tz = pytz.timezone(tzname)
    except Exception:
        tz = pytz.timezone("Europe/Madrid")
        tzname = "Europe/Madrid"

    now_local = now_utc.astimezone(tz)
    hoy_local = now_local.date()

    # DEBUG mínimo por usuario
    print(
        f"[DEBUG] uid={chat_id} now_local={now_local:%Y-%m-%d %H:%M} "
        f"send_hour={prefs.get('send_hour_local')} last_sent={prefs.get('last_sent_iso')}"
    )

    # condición de envío (o forzado)
    if not FORCE_SEND:
        if not repo.should_send_now(prefs, now_utc):
            return
    else:
        print(f"[DEBUG] FORCE_SEND activo -> envío forzado a uid={chat_id}")

    # ubicación preferente: lat/lon si existen; si no, cae a Málaga (tu repo lo gestiona por defecto en ubicacion_y_sol)
    lat = prefs.get("lat")
    lon = prefs.get("lon")
    ciudad = prefs.get("city") or "tu zona"

    if lat is None or lon is None:
        # fallback estable (si el usuario no fijó GPS)
        # Málaga por defecto
        lat = 36.7213
        lon = -4.4214
        if ciudad == "tu zona":
            ciudad = "Málaga"

    lat = float(lat)
    lon = float(lon)

    # 1) consejo + referencia (si tus strings ya llevan referencia, perfecto)
    consejo = elegir_consejo(str(chat_id), hoy_local)

    # 2) intervalos 30–40
    intervalos = calcular_intervalos_optimos(lat, lon, hoy_local, tzname, paso_min=1)
    texto_sol = describir_intervalos(intervalos, ciudad)

    # 3) meteo durante esos tramos (si hay)
    hourly = obtener_pronostico_diario(hoy_local, lat, lon, tzname)
    texto_meteo = formatear_intervalos_meteo(intervalos, hourly)

    # 4) mediodía solar + altura máxima aproximada del día
    # Para altura máxima: la aproximamos como elevación a las 12:00 “solares” por búsqueda 10–14
    from ubicacion_y_sol import _declinacion_solar, _solar_hour_angle, _elevacion_solar_deg  # type: ignore
    n = hoy_local.timetuple().tm_yday
    decl = _declinacion_solar(n)

    # buscamos minuto con elevación máxima entre 10 y 14 local
    base = tz.localize(dt.datetime(hoy_local.year, hoy_local.month, hoy_local.day, 10, 0))
    best_t = base
    best_e = -999.0
    for m in range(0, 4 * 60):
        t = base + dt.timedelta(minutes=m)
        h = _solar_hour_angle(t, lon, tzname, n)
        e = _elevacion_solar_deg(lat, decl, h)
        if e > best_e:
            best_e = e
            best_t = t

    mediodia_txt = f"🧭 Mediodía solar: {best_t.strftime('%H:%M')} (altura máx ≈ {best_e:.1f}°)"

    mensaje = (
        f"🧠 Consejo para hoy ({now_local.strftime('%A')}):\n"
        f"{consejo}\n\n"
        f"{texto_sol}{texto_meteo}\n"
        f"{mediodia_txt}"
    )

    try:
        # chat_id en Telegram suele ser int, pero str también funciona; aquí lo hacemos robusto
        await bot.send_message(chat_id=int(chat_id), text=mensaje)
        repo.mark_sent_today(str(chat_id), hoy_local)
        print(f"[OK] Enviado a uid={chat_id} y marcado last_sent_iso={hoy_local.isoformat()}")
    except Exception as e:
        print(f"[ERROR] Fallo enviando a uid={chat_id}: {e}")


async def main():
    if not BOT_TOKEN:
        raise RuntimeError("Falta BOT_TOKEN en variables de entorno")

    repo.init_db()
    users = repo.list_users()
    print(f"[INFO] usuarios en DB: {len(users)}  FORCE_SEND={FORCE_SEND}  ONLY_CHAT_ID={ONLY_CHAT_ID}")

    bot = Bot(BOT_TOKEN)
    now_utc = dt.datetime.now(dt.timezone.utc)

    for uid, prefs in users.items():
        try:
            await enviar_a_usuario(bot, uid, prefs, now_utc)
        except Exception as e:
            print(f"[ERROR] loop usuario {uid}: {e}")


if __name__ == "__main__":
    asyncio.run(main())
