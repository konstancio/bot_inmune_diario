# enviar_noche.py — mensaje parasimpático nocturno (multiusuario)

import os
import asyncio
import datetime as dt
import pytz
from telegram import Bot

from usuarios_repo import (
    init_db,
    list_users,
    should_send_sleep_now,   # wrapper -> should_send_sleep_now
    mark_sleep_sent_today,     # wrapper -> mark_sleep_sent_today
)

from consejos_parasimpatico import CONSEJOS_PARASIMPATICO

BOT_TOKEN = os.getenv("BOT_TOKEN")
ONLY_CHAT_ID = os.getenv("ONLY_CHAT_ID")
FORCE_SEND = os.getenv("FORCE_SEND", "0").strip() == "1"


def elegir_consejo(chat_id: str, fecha: dt.date) -> str:
    idx = (hash(str(chat_id)) + fecha.toordinal()) % len(CONSEJOS_PARASIMPATICO)
    return CONSEJOS_PARASIMPATICO[idx]


async def enviar_a_usuario(bot: Bot, chat_id: str, prefs: dict, now_utc: dt.datetime):
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

    # Lógica de envío:
    # - normal: solo si entra en ventana (21:00 y 0-10 min por defecto) y no enviado hoy
    # - FORCE_SEND=1: permite probar, pero sin duplicar ese día
    if not FORCE_SEND:
        if not should_send_sleep_now(prefs, now_utc):
            return
    else:
        # Si ya se envió hoy, no reenviar
        if prefs.get("last_sleep_sent_iso") == hoy_local.isoformat():
            return

    consejo = elegir_consejo(chat_id, hoy_local)

    mensaje = (
        "🌙 Consejo para activar tu sistema parasimpático antes de dormir:\n\n"
        f"{consejo}\n\n"
        "😴 Respira despacio, baja las luces y deja que el cuerpo haga su trabajo."
    )

    await bot.send_message(chat_id=str(chat_id), text=mensaje)

    # Marcar enviado hoy (clave nocturna)
    mark_sleep_sent_today(str(chat_id), hoy_local)


async def main():
    if not BOT_TOKEN:
        raise RuntimeError("Falta BOT_TOKEN")

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
            print(f"❌ Error nocturno {uid}: {e}")


if __name__ == "__main__":
    asyncio.run(main())
