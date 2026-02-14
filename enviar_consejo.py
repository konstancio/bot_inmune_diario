
# enviar_consejo.py — envío diario (mañana)
# Multiusuario (DB) + ventanas solares 30–40° + meteo + mediodía solar
#
# ENV:
#   BOT_TOKEN=...
#   DATABASE_URL o DATABASE_DSN=...
#   ONLY_CHAT_ID=... (opcional: para pruebas, envía solo a ese chat)
#   FORCE_SEND=1 (opcional: fuerza envío sin depender de la hora)
#
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
    mediodia_solar_y_altura_max,
)

BOT_TOKEN = os.getenv("BOT_TOKEN")
ONLY_CHAT_ID = os.getenv("ONLY_CHAT_ID")
FORCE_SEND = os.getenv("FORCE_SEND", "").strip() in {"1", "true", "True", "YES", "yes"}


def elegir_consejo(chat_id: str, fecha: dt.date) -> str:
    idx = (hash(str(chat_id)) + fecha.toordinal()) % len(CONSEJOS_DIARIOS)
    return CONSEJOS_DIARIOS[idx]


async def enviar_a_usuario(bot: Bot, chat_id: str, prefs: dict, now_utc: dt.datetime) -> None:
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

    # logs útiles (para Railway)
    print(
        f"[DEBUG] uid={chat_id} now_local={now_local:%Y-%m-%d %H:%M} "
        f"send_hour={prefs.get('send_hour_local')} last_sent={prefs.get('last_sent_iso')} tz={tzname}"
    )

    if not FORCE_SEND and not repo.should_send_now(prefs, now_utc):
        return

    # ubicación por usuario (SIEMPRE). Si falta, fallback Málaga.
    lat = prefs.get("lat")
    lon = prefs.get("lon")
    ciudad = prefs.get("city") or "Málaga"
    if lat is None or lon is None:
        lat = 36.7213
        lon = -4.4214
        if not prefs.get("city"):
            ciudad = "Málaga"

    lat = float(lat)
    lon = float(lon)

    consejo = elegir_consejo(str(chat_id), hoy_local)

    intervalos = calcular_intervalos_optimos(lat, lon, hoy_local, tzname, paso_min=1)
    texto_sol = describir_intervalos(intervalos, ciudad)

    hourly = obtener_pronostico_diario(hoy_local, lat, lon, tzname)
    texto_meteo = formatear_intervalos_meteo(intervalos, hourly)

    t_noon, elev_max = mediodia_solar_y_altura_max(lat, lon, hoy_local, tzname)
    texto_noon = f"🧭 Mediodía solar: {t_noon.strftime('%H:%M')} (altura máx ≈ {elev_max:.1f}°)"

    mensaje = (
        f"🧠 Consejo para hoy ({now_local.strftime('%A')}):\n"
        f"{consejo}\n\n"
        f"{texto_sol}{texto_meteo}\n"
        f"{texto_noon}"
    )

    try:
        await bot.send_message(chat_id=int(chat_id), text=mensaje)
        repo.mark_sent_today(str(chat_id), hoy_local)
        print(f"[OK] Enviado a uid={chat_id} y marcado last_sent_iso={hoy_local.isoformat()}")
    except Exception as e:
        print(f"[ERROR] Fallo enviando a uid={chat_id}: {e}")


async def main():
    if not BOT_TOKEN:
        raise RuntimeError("Falta BOT_TOKEN")

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
