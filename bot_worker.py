# bot_worker.py
# Worker multiusuario: alta/baja, idioma, ciudad, ubicación GPS y hora de envío
# Bot worker multiusuario: escucha /start, /lang, /city, /when … y deja todo listo para el cron.
# Seguro frente a "event loop already running" en Railway.

import os
import logging
import asyncio

from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters, ContextTypes
)

from usuarios_repo import (
    ensure_user, set_lang, set_city, set_location, set_send_hour,
    subscribe, unsubscribe, list_users, migrate_fill_defaults
)

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
log = logging.getLogger("worker")

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("BOT_TOKEN")


# ------------------- Handlers sencillos -------------------

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    ensure_user(chat_id)
    await update.message.reply_text(
        "¡Hola! Te he suscrito al bot de consejos diarios.\n\n"
        "Comandos útiles:\n"
        "• /lang es|en|fr|it|de|pt|nl|ru|hr\n"
        "• /city NombreDeCiudad (o envíame tu ubicación)\n"
        "• /when 9  (hora local preferida)\n"
        "• /stop para dejar de recibir mensajes"
    )


async def cmd_stop(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    unsubscribe(chat_id)
    await update.message.reply_text("He eliminado tu suscripción. ¡Hasta otra!")


async def cmd_lang(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    if not ctx.args:
        return await update.message.reply_text("Uso: /lang es|en|fr|it|de|pt|nl|ru|hr")

    lang = ctx.args[0].lower()
    ok = set_lang(chat_id, lang)
    if ok:
        await update.message.reply_text(f"Idioma guardado: {lang}")
    else:
        await update.message.reply_text("Formato no válido. Usa dos letras, ej. es/en.")


async def cmd_when(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    if not ctx.args:
        return await update.message.reply_text("Uso: /when 9   (hora local, 0–23)")

    try:
        hour = int(ctx.args[0])
    except Exception:
        return await update.message.reply_text("Hora inválida. Usa un número 0–23.")
    set_send_hour(chat_id, hour)
    await update.message.reply_text(f"Perfecto, te escribiré cada día a las {hour:02d}:00 (hora local).")


async def cmd_city(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    if not ctx.args:
        return await update.message.reply_text("Uso: /city NombreDeCiudad")
    name = " ".join(ctx.args).strip()
    set_city(chat_id, name)
    await update.message.reply_text(f"Ciudad preferida guardada: {name}")


async def handle_location(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    loc = update.message.location
    if not loc:
        return
    # Si quieres, aquí podrías resolver zona horaria real con timezonefinder
    set_location(chat_id, loc.latitude, loc.longitude, tz="Europe/Madrid", city_hint="(GPS)")
    await update.message.reply_text("¡Ubicación guardada! (lat/lon).")


async def cmd_debug(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    # pequeño helper para ver cómo estamos guardando
    users = list_users()
    me = users.get(str(update.effective_chat.id), {})
    await update.message.reply_text(f"Tus datos:\n{me}")


# ------------------- wiring de la app -------------------

def build_application() -> Application:
    if not BOT_TOKEN:
        raise RuntimeError("Falta TELEGRAM_BOT_TOKEN (o BOT_TOKEN) en variables de entorno.")

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("stop", cmd_stop))
    app.add_handler(CommandHandler("lang", cmd_lang))
    app.add_handler(CommandHandler("when", cmd_when))
    app.add_handler(CommandHandler("city", cmd_city))
    app.add_handler(CommandHandler("debug", cmd_debug))
    app.add_handler(MessageHandler(filters.LOCATION, handle_location))

    return app


async def main_async():
    migrate_fill_defaults()
    app = build_application()

    # Arranque “manual” compatible con bucles ya activos:
    await app.initialize()
    await app.start()
    log.info("🤖 Bot worker listo. Escuchando comandos…")

    # PTB 21.x: usar updater para polling manual
    await app.updater.start_polling()
    await app.updater.wait_until_idle()

    await app.stop()
    await app.shutdown()


if __name__ == "__main__":
    try:
        # Si YA hay un loop corriendo (Railway a veces), aplicamos nest_asyncio
        asyncio.get_running_loop()
        import nest_asyncio
        nest_asyncio.apply()
        loop = asyncio.get_event_loop()
        loop.run_until_complete(main_async())
    except RuntimeError:
        # No hay loop: run normal
        asyncio.run(main_async())

