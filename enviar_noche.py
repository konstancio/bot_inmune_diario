# enviar_noche.py — mensaje parasimpático nocturno

import os
import asyncio
import datetime as dt
import pytz
from telegram import Bot

from usuarios_repo import (
    init_db,
    list_users,
    should_send_night,
    mark_sent_night,
)

from consejos_parasimpaticos import CONSEJOS_PARASIMPATICOS

BOT_TOKEN = os.getenv("BOT_TOKEN")
ONLY_CHAT_ID = os.getenv("ONLY_CHAT_ID")


def elegir_consejo(chat_id: str, fecha: dt.date) -> str:
    idx = (hash(chat_id) + fecha.toordinal()) % len(CONSEJOS_PARASIMPATICOS)
    return CONSEJOS_PARASIMPATICOS[idx]


async def enviar_a_usuario(bot: Bot, chat_id: str, prefs: dict, now_utc: dt.datetime):
    if ONLY_CHAT_ID and str(chat_id) != str(ONLY_CHAT_ID):
        return

    if not should_send_night(prefs, now_utc):
        return

    tzname = prefs.get("tz") or "Europe/Madrid"
    tz = pytz.timezone(tzname)
    hoy = now_utc.astimezone(tz).date()

    consejo = elegir_consejo(chat_id, hoy)

    mensaje = (
        "🌙 Consejo para activar tu sistema parasimpático antes de dormir:\n\n"
        f"{consejo}\n\n"
        "😴 Respira despacio, baja las luces y deja que el cuerpo haga su trabajo."
    )

    await bot.send_message(chat_id=chat_id, text=mensaje)
    mark_sent_night(chat_id, hoy)


async def main():
    if not BOT_TOKEN:
        raise RuntimeError("Falta BOT_TOKEN")

    init_db()
    users = list_users()
    bot = Bot(BOT_TOKEN)
    now_utc = dt.datetime.now(dt.timezone.utc)

    for uid, prefs in users.items():
        try:
            await enviar_a_usuario(bot, uid, prefs, now_utc)
        except Exception as e:
            print(f"❌ Error nocturno {uid}: {e}")


if __name__ == "__main__":
    asyncio.run(main())