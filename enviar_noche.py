# enviar_noche.py
# Cron cada 5 min: envía recordatorio nocturno cuando should_send_sleep_now(chat) sea True.

from __future__ import annotations

import os
import datetime as dt
import logging
import requests

import usuarios_repo as repo

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("enviar_noche")

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("❌ Falta BOT_TOKEN en variables de entorno")

def tg_send(chat_id: str, text: str) -> None:
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    r = requests.post(
        url,
        json={"chat_id": str(chat_id), "text": text, "disable_web_page_preview": True},
        timeout=20,
    )
    r.raise_for_status()

def main():
    try:
        repo.init_db()
        repo.migrate_fill_defaults()
    except Exception as e:
        logger.warning(f"[WARN] init_db/migrate: {e}")

    chats = repo.list_users()
    if not chats:
        logger.info("No hay usuarios en subscribers.")
        return

    now_utc = dt.datetime.now(dt.timezone.utc)

    for chat_id, chat in chats.items():
        chat_id = str(chat_id)
        try:
            if not repo.should_send_sleep_now(chat, now_utc=now_utc):
                continue

            tzname = (chat.get("tz") or "Europe/Madrid").strip() or "Europe/Madrid"
            try:
                import pytz
                tz = pytz.timezone(tzname)
            except Exception:
                import pytz
                tz = pytz.timezone("Europe/Madrid")
                tzname = "Europe/Madrid"

            local_date = now_utc.astimezone(tz).date()

            msg = (
                "🌙 Modo noche (parasimpático):\n"
                "• Luz baja 60–90 min antes de dormir\n"
                "• Pantallas fuera / filtro cálido\n"
                "• Cena ligera + respiración 4-6\n"
                "• Habitación fresca y oscura\n"
            )

            tg_send(chat_id, msg)
            repo.mark_sleep_sent_today(chat_id, local_date)
            logger.info(f"✅ Nocturno enviado a {chat_id} {local_date.isoformat()}")

        except Exception as e:
            logger.exception(f"❌ Error nocturno a {chat_id}: {e}")

if __name__ == "__main__":
    main()
