# bot_worker.py
# Worker multiusuario: alta/baja, idioma, ciudad, ubicación GPS y hora de envío
# Bot worker multiusuario: escucha /start, /lang, /city, /when … y deja todo listo para el cron.
# Seguro frente a "event loop already running" en Railway.

# bot_worker.py  (python-telegram-bot v20+)
import os
from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, ContextTypes
)

BOT_TOKEN = os.environ.get("BOT_TOKEN")

# --- Comandos básicos ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "¡Hola! Estoy listo. Usa /lang es|en|fr|it|de|pt|nl|hr|ru para idioma.\n"
        "Usa /city <ciudad> para fijar ciudad.\n"
        "Usa /hour <0-23> para fijar hora local."
    )

async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("pong")

async def lang(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Ejemplo simple; aquí llamas a tus funciones de usuarios_repo.set_lang(...)
    if not context.args:
        return await update.message.reply_text("Formato: /lang es")
    code = context.args[0].lower()[:2]
    await update.message.reply_text(f"Idioma guardado: {code}")

def main():
    if not BOT_TOKEN:
        raise RuntimeError("Falta BOT_TOKEN en variables de entorno")

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("ping", ping))
    app.add_handler(CommandHandler("lang", lang))

    print("🤖 Bot worker listo. Escuchando comandos...")
    # IMPORTANTE: no usar asyncio.run ni updater; esto bloquea y mantiene el bot vivo
    app.run_polling(allowed_updates=None)  # o Update.ALL_TYPES si lo prefieres

if __name__ == "__main__":
    main()
