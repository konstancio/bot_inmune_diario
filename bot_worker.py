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
    subscribe,
    unsubscribe,
    set_lang,
    set_city,
    set_location,
    set_send_hour,
    list_users,
    ensure_user,
)

TOKEN = os.getenv("BOT_TOKEN")


# ----------------------------- Comandos -----------------------------

async def cmd_start(update, context):
    chat_id = str(update.effective_chat.id)
    u = subscribe(chat_id)
    await update.message.reply_text(
        "👋 ¡Bienvenido! Te he suscrito a los consejos diarios.\n\n"
        "Comandos útiles:\n"
        "• /lang es|en|fr|it|de|pt|nl — idioma de los consejos\n"
        "• /city NombreCiudad — ciudad preferida (si no usas lat/lon)\n"
        "• /setloc lat lon tz [Ciudad] — fija ubicación precisa (ej. 36.72 -4.42 Europe/Madrid Málaga)\n"
        "• /hour 9 — hora local de envío (0–23)\n"
        "• /where — ver tus ajustes\n"
        "• /stop — darte de baja"
    )

async def cmd_stop(update, context):
    chat_id = str(update.effective_chat.id)
    unsubscribe(chat_id)
    await update.message.reply_text("📴 Te he dado de baja. ¡Vuelve cuando quieras con /start!")

async def cmd_lang(update, context):
    chat_id = str(update.effective_chat.id)
    if not context.args:
        await update.message.reply_text("Uso: /lang es|en|fr|it|de|pt|nl")
        return
    code = context.args[0].lower()
    ok = set_lang(chat_id, code)
    if ok:
        await update.message.reply_text(f"🌐 Idioma actualizado a: {code}")
    else:
        await update.message.reply_text("❌ Código de idioma no válido. Usa: es, en, fr, it, de, pt, nl.")

async def cmd_city(update, context):
    chat_id = str(update.effective_chat.id)
    if not context.args:
        await update.message.reply_text("Uso: /city NombreCiudad (ej. /city Málaga)")
        return
    city = " ".join(context.args).strip()
    set_city(chat_id, city)
    await update.message.reply_text(f"🏙️ Ciudad preferida guardada: {city}")

async def cmd_setloc(update, context):
    """
    /setloc lat lon tz [Ciudad]
    ej: /setloc 36.7213 -4.4214 Europe/Madrid Málaga
    """
    chat_id = str(update.effective_chat.id)
    if len(context.args) < 3:
        await update.message.reply_text(
            "Uso: /setloc lat lon tz [Ciudad]\n"
            "Ej: /setloc 36.7213 -4.4214 Europe/Madrid Málaga"
        )
        return
    try:
        lat = float(context.args[0])
        lon = float(context.args[1])
        tz = context.args[2]
        city_hint = " ".join(context.args[3:]).strip() if len(context.args) > 3 else None
        set_location(chat_id, lat, lon, tz, city_hint)
        msg_city = f" — {city_hint}" if city_hint else ""
        await update.message.reply_text(f"📍 Ubicación guardada: {lat}, {lon} — {tz}{msg_city}")
    except Exception as e:
        await update.message.reply_text(f"❌ Parámetros inválidos. Error: {e}")

async def cmd_hour(update, context):
    chat_id = str(update.effective_chat.id)
    if not context.args:
        await update.message.reply_text("Uso: /hour 9  (hora local 0–23)")
        return
    try:
        hour = int(context.args[0])
        set_send_hour(chat_id, hour)
        await update.message.reply_text(f"⏰ Hora local de envío actualizada a: {hour:02d}:00")
    except Exception:
        await update.message.reply_text("❌ Introduce una hora válida (0–23).")

async def cmd_where(update, context):
    chat_id = str(update.effective_chat.id)
    u = ensure_user(chat_id)
    await update.message.reply_text(
        "🔎 Tus ajustes actuales:\n"
        f"• Idioma: {u.get('lang')}\n"
        f"• Ciudad: {u.get('city')}\n"
        f"• Lat/Lon: {u.get('lat')}, {u.get('lon')}\n"
        f"• Zona horaria: {u.get('tz')}\n"
        f"• Envío diario a las: {int(u.get('send_hour_local', 9)):02d}:00"
    )

async def cmd_users(update, context):
    # Opcional: listado rápido para verificar que persiste el fichero
    sus = list_users()
    await update.message.reply_text(f"👥 Suscriptores almacenados: {len(sus)}")

async def fallback_text(update, context):
    await update.message.reply_text(
        "No te he entendido 😅\n"
        "Prueba /help o /start para ver los comandos disponibles."
    )

async def cmd_help(update, context):
    await cmd_start(update, context)


# ----------------------------- Arranque -----------------------------

def main():
    if not TOKEN:
        raise RuntimeError("Falta BOT_TOKEN en variables de entorno.")
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help",  cmd_help))
    app.add_handler(CommandHandler("stop",  cmd_stop))
    app.add_handler(CommandHandler("lang",  cmd_lang))
    app.add_handler(CommandHandler("city",  cmd_city))
    app.add_handler(CommandHandler("setloc", cmd_setloc))
    app.add_handler(CommandHandler("hour",  cmd_hour))
    app.add_handler(CommandHandler("where", cmd_where))
    app.add_handler(CommandHandler("users", cmd_users))   # opcional

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, fallback_text))

    print("🤖 Bot worker listo. Escuchando comandos…")
    # Gestiona internamente el event loop (evita el error de asyncio)
    app.run_polling(allowed_updates=None)

if __name__ == "__main__":
    main()
