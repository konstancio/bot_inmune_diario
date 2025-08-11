# bot_worker.py
# Worker multiusuario: alta/baja, idioma, ciudad, ubicación GPS y hora de envío
# Bot worker multiusuario: escucha /start, /lang, /city, /when … y deja todo listo para el cron.
# Seguro frente a "event loop already running" en Railway.
# bot_worker.py  (python-telegram-bot v20+)
# Bot Telegram (polling) compatible con PTB 20.x y Railway.
# Gestiona altas y preferencias de cada usuario usando usuarios_repo.py

import os
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
)
from usuarios_repo import (
    init_db,
    subscribe,
    unsubscribe,
    set_lang,
    set_city,
    set_location,
    set_send_hour,
    list_users,
    ensure_user,
)

# Inicializa base de datos
init_db()

TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise ValueError("Falta la variable BOT_TOKEN en Railway.")

# ======================== Comandos ========================

async def cmd_start(update, context):
    chat_id = update.effective_chat.id
    subscribe(chat_id)
    await update.message.reply_text("👋 ¡Bienvenido! Te he suscrito a los consejos diarios.")

    # DEPURACIÓN: Mostrar que se ha suscrito
    print(f"[DEBUG] Usuario suscrito: chat_id={chat_id}")
    print("[DEBUG] Lista actual de usuarios suscritos:", list_users())

async def cmd_stop(update, context):
    chat_id = update.effective_chat.id
    unsubscribe(chat_id)
    await update.message.reply_text("❌ Te has dado de baja de los consejos diarios.")

    # DEPURACIÓN: Mostrar que se ha dado de baja
    print(f"[DEBUG] Usuario dado de baja: chat_id={chat_id}")
    print("[DEBUG] Lista actual de usuarios suscritos:", list_users())

async def cmd_lang(update, context):
    if context.args:
        set_lang(update.effective_chat.id, context.args[0])
        await update.message.reply_text(f"🌐 Idioma cambiado a {context.args[0]}")
    else:
        await update.message.reply_text("Uso: /lang es|en|fr|it|de|pt|nl")

async def cmd_city(update, context):
    if context.args:
        set_city(update.effective_chat.id, " ".join(context.args))
        await update.message.reply_text(f"🏙 Ciudad cambiada a {' '.join(context.args)}")
    else:
        await update.message.reply_text("Uso: /city NombreCiudad")

async def cmd_setloc(update, context):
    if len(context.args) >= 3:
        try:
            lat = float(context.args[0])
            lon = float(context.args[1])
            tz = context.args[2]
            city = " ".join(context.args[3:]) if len(context.args) > 3 else None
            set_location(update.effective_chat.id, lat, lon, tz, city)
            await update.message.reply_text(f"📍 Ubicación fijada: {lat}, {lon}, {tz}, {city or 'Sin ciudad'}")
        except ValueError:
            await update.message.reply_text("Formato inválido. Uso: /setloc lat lon tz [Ciudad]")
    else:
        await update.message.reply_text("Uso: /setloc lat lon tz [Ciudad]")

async def cmd_hour(update, context):
    if context.args:
        try:
            hour = int(context.args[0])
            if 0 <= hour <= 23:
                set_send_hour(update.effective_chat.id, hour)
                await update.message.reply_text(f"⏰ Hora de envío cambiada a las {hour}:00")
            else:
                await update.message.reply_text("Por favor, indica una hora entre 0 y 23.")
        except ValueError:
            await update.message.reply_text("Formato inválido. Uso: /hour número")
    else:
        await update.message.reply_text("Uso: /hour número")

async def cmd_where(update, context):
    user = ensure_user(update.effective_chat.id)
    await update.message.reply_text(str(user))

# ======================== Main ========================

def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("stop", cmd_stop))
    app.add_handler(CommandHandler("lang", cmd_lang))
    app.add_handler(CommandHandler("city", cmd_city))
    app.add_handler(CommandHandler("setloc", cmd_setloc))
    app.add_handler(CommandHandler("hour", cmd_hour))
    app.add_handler(CommandHandler("where", cmd_where))

    app.run_polling()

if __name__ == "__main__":
    print("[DEBUG] Bot Worker iniciado. Esperando comandos...")
    main()
