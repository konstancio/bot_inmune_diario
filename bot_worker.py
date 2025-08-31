# bot_worker.py
# Worker multiusuario: alta/baja, idioma, ciudad, ubicación GPS y hora de envío
# Bot worker multiusuario: escucha /start, /lang, /city, /sethour (/when), /setloc, /where … y deja todo listo para el cron.
# Seguro frente a "event loop already running" en Railway.
# bot_worker.py  (python-telegram-bot v20+)
# Bot Telegram (polling) compatible con PTB 20.x y Railway.
# Gestiona altas y preferencias de cada usuario usando usuarios_repo.py

import os
import logging
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, ContextTypes
)

import usuarios_repo as repo

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("❌ Falta BOT_TOKEN en variables de entorno")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --------- comandos ---------

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    repo.subscribe(chat_id)
    await update.message.reply_text(
        "👋 ¡Bienvenido! Te he suscrito a los consejos diarios.\n\n"
        "Comandos útiles:\n"
        "• /lang es|en|fr|it|de|pt|nl|sr|ru — idioma de los consejos\n"
        "• /city NombreCiudad — ciudad preferida (si no usas lat/lon)\n"
        "• /setloc lat lon tz [Ciudad] — fija ubicación precisa\n"
        "• /sethour HH — hora local de envío (0–23) (alias: /when)\n"
        "• /where — ver tus ajustes\n"
        "• /stop — darte de baja"
    )

async def cmd_stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    repo.unsubscribe(chat_id)
    await update.message.reply_text("✅ Has sido dado de baja.")

async def cmd_lang(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    if not context.args:
        await update.message.reply_text("Uso: /lang es|en|fr|it|de|pt|nl|sr|ru")
        return
    ok = repo.set_lang(chat_id, context.args[0])
    if ok:
        await update.message.reply_text(f"✅ Idioma actualizado a {context.args[0]}")
    else:
        await update.message.reply_text("❌ Idioma no válido.")

async def cmd_city(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    if not context.args:
        await update.message.reply_text("Uso: /city NombreCiudad")
        return
    city = " ".join(context.args)
    repo.set_city(chat_id, city)
    await update.message.reply_text(f"✅ Ciudad actualizada a {city}")

async def cmd_setloc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    if len(context.args) < 3:
        await update.message.reply_text("Uso: /setloc lat lon tz [Ciudad]")
        return
    lat = float(context.args[0])
    lon = float(context.args[1])
    tz = context.args[2]
    city = " ".join(context.args[3:]) if len(context.args) > 3 else None
    repo.set_location(chat_id, lat, lon, tz, city)
    await update.message.reply_text(f"✅ Ubicación actualizada: {lat}, {lon}, {tz}, {city or ''}")

async def cmd_sethour(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    if not context.args:
        await update.message.reply_text("Uso: /sethour HH")
        return
    try:
        hh = int(context.args[0])
    except Exception:
        await update.message.reply_text("❌ Hora inválida.")
        return
    repo.set_send_hour(chat_id, hh)
    await update.message.reply_text(f"✅ Hora local de envío ajustada a las {hh:02d}:00")

# alias: /when → /sethour
async def cmd_when(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await cmd_sethour(update, context)

async def cmd_where(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    user = repo.get_user(chat_id)
    if not user:
        await update.message.reply_text("❌ No estás suscrito.")
        return
    txt = (
        f"👤 Tus ajustes:\n"
        f"• Idioma: {user.get('lang')}\n"
        f"• Ciudad: {user.get('city')}\n"
        f"• Lat/Lon: {user.get('lat')}, {user.get('lon')}\n"
        f"• Zona horaria: {user.get('tz')}\n"
        f"• Hora envío: {user.get('send_hour_local')}:00\n"
    )
    await update.message.reply_text(txt)

# --------- main ---------

def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("stop", cmd_stop))
    app.add_handler(CommandHandler("lang", cmd_lang))
    app.add_handler(CommandHandler("city", cmd_city))
    app.add_handler(CommandHandler("setloc", cmd_setloc))
    app.add_handler(CommandHandler("sethour", cmd_sethour))
    app.add_handler(CommandHandler("when", cmd_when))   # alias de /sethour
    app.add_handler(CommandHandler("where", cmd_where))

    logger.info("🤖 Bot worker en marcha (polling)…")
    app.run_polling()

if __name__ == "__main__":
    main()
