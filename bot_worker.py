# bot_worker.py
# Worker multiusuario: alta/baja, idioma, ciudad, ubicación GPS y hora de envío

import os
import asyncio
from typing import Optional

from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    Application, CommandHandler, MessageHandler, ContextTypes, filters
)

from usuarios_repo import (
    subscribe, unsubscribe, set_lang, set_city, set_location, set_send_hour,
    list_users, migrate_fill_defaults
)
from timezonefinder import TimezoneFinder

BOT_TOKEN = os.getenv("BOT_TOKEN")

# ----------------- Utilidades -----------------

def _ok_lang(code: str) -> bool:
    return isinstance(code, str) and len(code) == 2 and code.isalpha()

def _norm_city(args) -> Optional[str]:
    if not args:
        return None
    name = " ".join(args).strip()
    return name or None

# ----------------- Handlers -----------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_chat.id)
    subscribe(uid)
    await update.message.reply_text(
        "✅ Suscripción activada.\n\n"
        "Comandos útiles:\n"
        "• /idioma en|es|fr|it|de|pt – Fijar idioma\n"
        "• /ciudad Nombre – Fijar ciudad por texto (ej: /ciudad Málaga)\n"
        "• /ubicacion – Compartir ubicación GPS\n"
        "• /hora 9 – Fijar hora local de envío (0–23)\n"
        "• /miinfo – Ver tus datos\n"
        "• /stop – Darse de baja"
    )

async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_chat.id)
    unsubscribe(uid)
    await update.message.reply_text("🛑 Suscripción desactivada. ¡Hasta pronto!")

async def idioma(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_chat.id)
    if not context.args:
        return await update.message.reply_text("Uso: /idioma en | es | fr | it | de | pt")
    lang = context.args[0].lower()
    if not _ok_lang(lang):
        return await update.message.reply_text("Idioma inválido. Usa un código ISO-2 (ej: en, es, fr, it, de, pt).")
    ok = set_lang(uid, lang)
    if ok:
        await update.message.reply_text(f"🌍 Idioma guardado: {lang}")
    else:
        await update.message.reply_text("No se pudo guardar el idioma. Inténtalo de nuevo.")

async def ciudad(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_chat.id)
    name = _norm_city(context.args)
    if not name:
        return await update.message.reply_text("Uso: /ciudad NombreDeCiudad (ej: /ciudad Málaga)")
    # Guardamos solo el nombre; lat/lon/tz se calcularán al enviar o cuando el cron lo necesite
    set_city(uid, name)
    await update.message.reply_text(f"📍 Ciudad guardada: {name}\n\n"
                                    "Consejo: si puedes, usa /ubicacion para guardar coordenadas GPS y zona horaria exactas.")

async def ubicacion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = ReplyKeyboardMarkup(
        [[KeyboardButton("📍 Enviar mi ubicación", request_location=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
        input_field_placeholder="Pulsa el botón para compartir tu ubicación"
    )
    await update.message.reply_text("Toca el botón para compartir tu ubicación:", reply_markup=kb)

async def on_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_chat.id)
    if not update.message or not update.message.location:
        return
    lat = float(update.message.location.latitude)
    lon = float(update.message.location.longitude)

    # Resolver zona horaria desde lat/lon
    tf = TimezoneFinder()
    tz = tf.timezone_at(lat=lat, lng=lon) or "Europe/Madrid"

    set_location(uid, lat, lon, tz)
    await update.message.reply_text(
        f"✅ Ubicación guardada.\nLat: {lat:.4f}, Lon: {lon:.4f}\nZona horaria: {tz}"
    )

async def hora(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_chat.id)
    if not context.args:
        return await update.message.reply_text("Uso: /hora 9  (valor entre 0 y 23)")
    try:
        h = int(context.args[0])
    except Exception:
        return await update.message.reply_text("Introduce una hora válida entre 0 y 23 (ej: /hora 9)")
    if not (0 <= h <= 23):
        return await update.message.reply_text("La hora debe estar entre 0 y 23.")
    set_send_hour(uid, h)
    await update.message.reply_text(f"⏰ Hora local de envío guardada: {h:02d}:00")

async def miinfo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_chat.id)
    users = list_users()
    prefs = users.get(uid)
    if not prefs:
        return await update.message.reply_text("No hay datos. Usa /start para suscribirte.")
    # Formato bonito
    txt = (
        "🧾 *Tus datos guardados:*\n"
        f"• Idioma: `{prefs.get('lang', 'es')}`\n"
        f"• Ciudad: `{prefs.get('city')}`\n"
        f"• Lat/Lon: `{prefs.get('lat')}`, `{prefs.get('lon')}`\n"
        f"• Zona horaria: `{prefs.get('tz')}`\n"
        f"• Último envío (fecha local): `{prefs.get('last_sent_iso')}`\n"
        f"• Hora local preferida: `{prefs.get('send_hour_local', 9)}`"
    )
    await update.message.reply_text(txt, parse_mode="Markdown")

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Comandos:\n"
        "/start – suscribirse\n"
        "/stop – darse de baja\n"
        "/idioma en|es|fr|it|de|pt – fijar idioma\n"
        "/ciudad Nombre – fijar ciudad por texto\n"
        "/ubicacion – compartir ubicación GPS\n"
        "/hora 9 – fijar hora local de envío (0–23)\n"
        "/miinfo – ver preferencias guardadas"
    )

# ----------------- Main -----------------

async def main():
    if not BOT_TOKEN:
        raise RuntimeError("Falta BOT_TOKEN en variables de entorno.")
    # Migrar/asegurar estructura de usuarios
    migrate_fill_defaults()

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stop", stop))
    app.add_handler(CommandHandler("idioma", idioma))
    app.add_handler(CommandHandler("ciudad", ciudad))
    app.add_handler(CommandHandler("ubicacion", ubicacion))
    app.add_handler(CommandHandler("hora", hora))
    app.add_handler(CommandHandler("miinfo", miinfo))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(MessageHandler(filters.LOCATION, on_location))

    print("🤖 Bot worker iniciado. Escuchando comandos...")
    await app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    asyncio.run(main())