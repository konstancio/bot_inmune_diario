# bot_worker.py
# Worker multiusuario: alta/baja, idioma, ciudad, ubicación GPS y hora de envío

import os
import logging
import asyncio

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from timezonefinder import TimezoneFinder

# --- almacenamiento de usuarios ---
from usuarios_repo import (
    ensure_user,
    subscribe,
    unsubscribe,
    set_lang,
    set_city,
    set_location,
    set_send_hour,
    list_users,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
log = logging.getLogger("bot_worker")

# ---------- helpers ----------
def _tz_from_latlon(lat: float, lon: float) -> str:
    try:
        tf = TimezoneFinder()
        tz = tf.timezone_at(lat=lat, lng=lon) or "Europe/Madrid"
        return tz
    except Exception:
        return "Europe/Madrid"

# ---------- command handlers ----------
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = str(update.effective_chat.id)
    subscribe(chat_id)
    await update.message.reply_text(
        "👋 ¡Hola! Te has suscrito.\n"
        "Comandos útiles:\n"
        "• /lang es|en|fr|it|de|pt|nl …\n"
        "• /city NombreCiudad\n"
        "• Envía tu 📍 ubicación para fijar lat/lon\n"
        "• /when 9   (hora local de envío 0–23)\n"
        "• /where    (ver configuración)\n"
        "• /stop     (anular suscripción)"
    )

async def cmd_stop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = str(update.effective_chat.id)
    unsubscribe(chat_id)
    await update.message.reply_text("🛑 Suscripción cancelada. ¡Hasta pronto!")

async def cmd_lang(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = str(update.effective_chat.id)
    if not context.args:
        await update.message.reply_text("Uso: /lang es|en|fr|it|de|pt|nl")
        return
    ok = set_lang(chat_id, context.args[0])
    if ok:
        await update.message.reply_text(f"🌐 Idioma actualizado: {context.args[0].lower()}")
    else:
        await update.message.reply_text("❌ Idioma no válido. Usa ISO-2 (p.ej. es, en, fr).")

async def cmd_city(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = str(update.effective_chat.id)
    if not context.args:
        await update.message.reply_text("Uso: /city NombreCiudad")
        return
    city = " ".join(context.args).strip()
    set_city(chat_id, city)
    await update.message.reply_text(f"🏙️ Ciudad guardada: {city}")

async def cmd_when(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = str(update.effective_chat.id)
    if not context.args:
        await update.message.reply_text("Uso: /when 9   (hora local 0–23)")
        return
    try:
        hour = int(context.args[0])
    except Exception:
        await update.message.reply_text("❌ Hora inválida. Usa un entero 0–23.")
        return
    set_send_hour(chat_id, hour)
    await update.message.reply_text(f"⏰ Enviaré cada día a las {hour:02d}:00 (hora local).")

async def cmd_where(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = str(update.effective_chat.id)
    u = ensure_user(chat_id)
    await update.message.reply_text(
        "📄 Configuración actual:\n"
        f"• Idioma: {u.get('lang')}\n"
        f"• Ciudad: {u.get('city')}\n"
        f"• Lat/Lon: {u.get('lat')}, {u.get('lon')}\n"
        f"• TZ: {u.get('tz')}\n"
        f"• Hora envío: {int(u.get('send_hour_local', 9)):02d}:00\n"
        f"• Último envío: {u.get('last_sent_iso')}"
    )

# Mensajes de ubicación
async def on_location(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.location:
        return
    chat_id = str(update.effective_chat.id)
    loc = update.message.location
    lat = float(loc.latitude)
    lon = float(loc.longitude)
    tz = _tz_from_latlon(lat, lon)
    set_location(chat_id, lat, lon, tz)
    await update.message.reply_text(
        f"📍 Ubicación guardada:\n"
        f"• Lat/Lon: {lat:.5f}, {lon:.5f}\n"
        f"• TZ: {tz}"
    )

# ---------- app wiring ----------
def build_app() -> Application:
    token = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("BOT_TOKEN")
    if not token:
        raise RuntimeError("Falta TELEGRAM_BOT_TOKEN (o BOT_TOKEN) en variables de entorno.")

    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("stop", cmd_stop))
    app.add_handler(CommandHandler("lang", cmd_lang))
    app.add_handler(CommandHandler("city", cmd_city))
    app.add_handler(CommandHandler("when", cmd_when))
    app.add_handler(CommandHandler("where", cmd_where))

    app.add_handler(MessageHandler(filters.LOCATION, on_location))

    return app

# ---------- main / run (con fallback para loops ya activos) ----------
app = build_app()

async def main():
    log.info("🤖 Bot worker listo. Escuchando comandos…")
    await app.run_polling(allowed_updates=None)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except RuntimeError as e:
        # Fallback si el loop ya está corriendo (algunos entornos)
        if "event loop is already running" in str(e):
            import nest_asyncio
            nest_asyncio.apply()
            loop = asyncio.get_event_loop()
            loop.run_until_complete(main())
        else:
            raise
