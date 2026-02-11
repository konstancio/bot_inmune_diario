# bot_worker.py
# Worker multiusuario: alta/baja, idioma, ciudad, ubicación GPS (persistente o temporal) y hora de envío
# python-telegram-bot v20+

import os
import logging
import datetime as dt

from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler, ContextTypes, filters
)

import usuarios_repo as repo

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("❌ Falta BOT_TOKEN en variables de entorno")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

HELP_TEXT = (
    "🤖 *Consejos Inmunes* — comandos disponibles:\n\n"
    "🧾 Suscripción:\n"
    "• /start — suscribirte\n"
    "• /stop — darte de baja\n\n"
    "🌍 Ubicación:\n"
    "• /loc — te pido que envíes tu ubicación (persistente)\n"
    "• /loctemp 24 — la próxima ubicación será *temporal* (ej. 24h)\n"
    "• /locreset — borra ubicación temporal y vuelve a la persistente\n"
    "• /city NombreCiudad — ciudad preferida si no usas GPS\n"
    "• /setloc lat lon tz [Ciudad] — fija ubicación manual\n\n"
    "🕘 Horarios:\n"
    "• /sethour HH — hora local de envío (0–23) (alias: /when)\n\n"
    "ℹ️ Estado:\n"
    "• /where — ver tus ajustes\n"
)

# ----------------- helpers -----------------

def _guess_tz_from_coords(lat: float, lon: float) -> str:
    # Si ya lo guardas por setloc, ok. Si no, dejamos por defecto.
    return "Europe/Madrid"

# ----------------- comandos -----------------

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    repo.subscribe(chat_id)
    await update.message.reply_text(HELP_TEXT, parse_mode="Markdown")

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(HELP_TEXT, parse_mode="Markdown")

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
    await update.message.reply_text("✅ Idioma actualizado." if ok else "❌ Idioma no válido.")

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
    # si existiera modo temporal, lo apagamos al fijar manualmente:
    if hasattr(repo, "clear_temp_location"):
        repo.clear_temp_location(chat_id)
    await update.message.reply_text(f"✅ Ubicación persistente actualizada: {lat}, {lon}, {tz} {('- ' + city) if city else ''}")

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

async def cmd_when(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await cmd_sethour(update, context)

async def cmd_where(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    user = repo.get_user(chat_id)
    if not user:
        await update.message.reply_text("❌ No estás suscrito.")
        return

    # si existe ubicación temporal en tu repo (cuando la implementemos)
    temp = None
    if "temp_lat" in user and user.get("temp_lat") is not None:
        until = user.get("temp_until_iso")
        temp = f"{user.get('temp_lat')}, {user.get('temp_lon')} (hasta {until})"

    txt = (
        f"👤 *Tus ajustes:*\n"
        f"• Idioma: `{user.get('lang')}`\n"
        f"• Ciudad: `{user.get('city')}`\n"
        f"• GPS persistente: `{user.get('lat')}, {user.get('lon')}`\n"
        f"• GPS temporal: `{temp or '—'}`\n"
        f"• Zona horaria: `{user.get('tz')}`\n"
        f"• Hora envío: `{user.get('send_hour_local')}:00`\n"
        f"• Hora nocturna: `{user.get('sleep_hour_local', 21)}:00`\n"
    )
    await update.message.reply_text(txt, parse_mode="Markdown")

# --- UX: pedir ubicación ---

async def cmd_loc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📍 Envíame tu ubicación desde Telegram:\n"
        "Adjuntar (📎) → Ubicación → *Enviar mi ubicación actual*.\n\n"
        "La guardaré como *persistente*."
    )

async def cmd_loctemp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Marca que la PRÓXIMA ubicación que envíe el usuario se guardará como temporal X horas.
    """
    hours = 24
    if context.args:
        try:
            hours = max(1, min(168, int(context.args[0])))  # 1h..7 días
        except Exception:
            hours = 24

    context.user_data["loctemp_hours"] = hours
    await update.message.reply_text(
        f"🧭 Vale. La *próxima* ubicación que envíes será *temporal* durante {hours}h.\n"
        "Ahora envíamela: Adjuntar (📎) → Ubicación → Enviar ubicación actual."
    )

async def cmd_locreset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    if hasattr(repo, "clear_temp_location"):
        repo.clear_temp_location(chat_id)
    context.user_data.pop("loctemp_hours", None)
    await update.message.reply_text("✅ Ubicación temporal borrada. Volvemos a la ubicación persistente.")

# --- handler de ubicación (lo importante) ---

async def on_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    repo.ensure_user(chat_id)

    loc = update.message.location
    lat, lon = float(loc.latitude), float(loc.longitude)

    # Si el usuario venía de /loctemp, guardamos temporal
    hours = context.user_data.pop("loctemp_hours", None)

    if hours and hasattr(repo, "set_temp_location"):
        tz = _guess_tz_from_coords(lat, lon)
        until = dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=int(hours))
        repo.set_temp_location(chat_id, lat, lon, tz, until)
        await update.message.reply_text(f"✅ Ubicación temporal guardada {hours}h: {lat:.5f}, {lon:.5f}")
        return

    # Persistente
    tz = _guess_tz_from_coords(lat, lon)
    repo.set_location(chat_id, lat, lon, tz, None)
    # si existiera modo temporal, lo apagamos al actualizar persistente
    if hasattr(repo, "clear_temp_location"):
        repo.clear_temp_location(chat_id)

    await update.message.reply_text(f"✅ Ubicación persistente guardada: {lat:.5f}, {lon:.5f}")

# ----------------- main -----------------

def main():
    repo.init_db()
    if hasattr(repo, "migrate_fill_defaults"):
        repo.migrate_fill_defaults()

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("stop", cmd_stop))
    app.add_handler(CommandHandler("lang", cmd_lang))
    app.add_handler(CommandHandler("city", cmd_city))
    app.add_handler(CommandHandler("setloc", cmd_setloc))
    app.add_handler(CommandHandler("sethour", cmd_sethour))
    app.add_handler(CommandHandler("when", cmd_when))
    app.add_handler(CommandHandler("where", cmd_where))

    app.add_handler(CommandHandler("loc", cmd_loc))
    app.add_handler(CommandHandler("loctemp", cmd_loctemp))
    app.add_handler(CommandHandler("locreset", cmd_locreset))

    # 👇 clave: capturar ubicación enviada desde Telegram
    app.add_handler(MessageHandler(filters.LOCATION, on_location))

    logger.info("🤖 Bot worker en marcha (polling)…")
    app.run_polling()

if __name__ == "__main__":
    main()
