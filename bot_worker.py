# bot_worker.py
# Worker multiusuario: alta/baja, idioma, ciudad, ubicación GPS y hora de envío
# Bot worker multiusuario: escucha /start, /lang, /city, /when … y deja todo listo para el cron.
# Seguro frente a "event loop already running" en Railway.
# bot_worker.py  (python-telegram-bot v20+)
# Bot Telegram (polling) compatible con PTB 20.x y Railway.
# Gestiona altas y preferencias de cada usuario usando usuarios_repo.py

import os
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters

from usuarios_repo import (
    init_db, subscribe, unsubscribe, set_lang, set_city,
    set_location, set_send_hour, get_user, VALID_LANG
)

# Inicializamos DB
init_db()

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN no configurado")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Mensajes pretraducidos
MESSAGES = {
    "welcome": {
        "es": "✅ Suscripción confirmada.\nUsa /help para ver comandos.",
        "en": "✅ Subscription confirmed.\nUse /help to see commands.",
        "fr": "✅ Abonnement confirmé.\nUtilisez /help pour voir les commandes.",
        "it": "✅ Iscrizione confermata.\nUsa /help per vedere i comandi.",
        "de": "✅ Anmeldung bestätigt.\nVerwende /help, um Befehle zu sehen.",
        "pt": "✅ Subscrição confirmada.\nUse /help para ver os comandos.",
        "nl": "✅ Abonnement bevestigd.\nGebruik /help om de commando's te zien.",
        "sr": "✅ Pretplata potvrđena.\nKoristite /help da vidite komande.",
        "ru": "✅ Подписка подтверждена.\nИспользуйте /help, чтобы увидеть команды."
    },
    "help": {
        "es": "📋 Comandos disponibles:\n/sethour HH - Cambiar hora de envío local\n/lang XX - Cambiar idioma (es, en, fr, it, de, pt, nl, sr, ru)\n/city Ciudad - Establecer ciudad\n/stop - Cancelar suscripción",
        "en": "📋 Available commands:\n/sethour HH - Change local send hour\n/lang XX - Change language (es, en, fr, it, de, pt, nl, sr, ru)\n/city City - Set city\n/stop - Unsubscribe",
        "fr": "📋 Commandes disponibles:\n/sethour HH - Changer l'heure locale d'envoi\n/lang XX - Changer la langue (es, en, fr, it, de, pt, nl, sr, ru)\n/city Ville - Définir la ville\n/stop - Se désabonner",
        "it": "📋 Comandi disponibili:\n/sethour HH - Cambia ora di invio locale\n/lang XX - Cambia lingua (es, en, fr, it, de, pt, nl, sr, ru)\n/city Città - Imposta città\n/stop - Annulla iscrizione",
        "de": "📋 Verfügbare Befehle:\n/sethour HH - Lokale Sendezeit ändern\n/lang XX - Sprache ändern (es, en, fr, it, de, pt, nl, sr, ru)\n/city Stadt - Stadt festlegen\n/stop - Abmelden",
        "pt": "📋 Comandos disponíveis:\n/sethour HH - Alterar hora de envio local\n/lang XX - Alterar idioma (es, en, fr, it, de, pt, nl, sr, ru)\n/city Cidade - Definir cidade\n/stop - Cancelar subscrição",
        "nl": "📋 Beschikbare commando's:\n/sethour HH - Lokale verzendtijd wijzigen\n/lang XX - Taal wijzigen (es, en, fr, it, de, pt, nl, sr, ru)\n/city Stad - Stad instellen\n/stop - Uitschrijven",
        "sr": "📋 Dostupne komande:\n/sethour HH - Promenite lokalno vreme slanja\n/lang XX - Promenite jezik (es, en, fr, it, de, pt, nl, sr, ru)\n/city Grad - Postavite grad\n/stop - Otkažite pretplatu",
        "ru": "📋 Доступные команды:\n/sethour HH - Изменить локальное время отправки\n/lang XX - Изменить язык (es, en, fr, it, de, pt, nl, sr, ru)\n/city Город - Установить город\n/stop - Отписаться"
    },
    "lang_set": {
        "es": "✅ Idioma cambiado a Español.",
        "en": "✅ Language changed to English.",
        "fr": "✅ Langue changée en Français.",
        "it": "✅ Lingua cambiata in Italiano.",
        "de": "✅ Sprache auf Deutsch geändert.",
        "pt": "✅ Idioma alterado para Português.",
        "nl": "✅ Taal gewijzigd naar Nederlands.",
        "sr": "✅ Jezik promenjen na srpski.",
        "ru": "✅ Язык изменен на русский."
    },
    "invalid_lang": {
        "es": "❌ Idioma no válido. Opciones: es, en, fr, it, de, pt, nl, sr, ru",
        "en": "❌ Invalid language. Options: es, en, fr, it, de, pt, nl, sr, ru",
        "fr": "❌ Langue invalide. Options: es, en, fr, it, de, pt, nl, sr, ru",
        "it": "❌ Lingua non valida. Opzioni: es, en, fr, it, de, pt, nl, sr, ru",
        "de": "❌ Ungültige Sprache. Optionen: es, en, fr, it, de, pt, nl, sr, ru",
        "pt": "❌ Idioma inválido. Opções: es, en, fr, it, de, pt, nl, sr, ru",
        "nl": "❌ Ongeldige taal. Opties: es, en, fr, it, de, pt, nl, sr, ru",
        "sr": "❌ Nevažeći jezik. Opcije: es, en, fr, it, de, pt, nl, sr, ru",
        "ru": "❌ Неверный язык. Варианты: es, en, fr, it, de, pt, nl, sr, ru"
    }
}

def detect_lang_from_user(user) -> str:
    if user.language_code:
        code = user.language_code.lower()
        if "-" in code:
            code = code.split("-")[0]
        if code in VALID_LANG:
            return code
        if code in ("sh", "sc", "srp", "hr", "bs"):
            return "sr"
        if code == "pt-br":
            return "pt"
    return "es"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    lang = detect_lang_from_user(update.effective_user)
    subscribe(chat_id)
    set_lang(chat_id, lang)
    await context.bot.send_message(chat_id=chat_id, text=MESSAGES["welcome"][lang])

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    user = get_user(chat_id)
    lang = user.get("lang", "es")
    await context.bot.send_message(chat_id=chat_id, text=MESSAGES["help"][lang])

async def lang_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    args = context.args
    user = get_user(chat_id)
    current_lang = user.get("lang", "es")
    if not args:
        await context.bot.send_message(chat_id=chat_id, text=MESSAGES["invalid_lang"][current_lang])
        return
    new_lang = args[0].lower()
    if set_lang(chat_id, new_lang):
        await context.bot.send_message(chat_id=chat_id, text=MESSAGES["lang_set"][new_lang])
    else:
        await context.bot.send_message(chat_id=chat_id, text=MESSAGES["invalid_lang"][current_lang])

async def city_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    city_name = " ".join(context.args)
    set_city(chat_id, city_name)
    await context.bot.send_message(chat_id=chat_id, text=f"✅ Ciudad establecida: {city_name}")

async def sethour_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    if not context.args:
        await context.bot.send_message(chat_id=chat_id, text="❌ Debes indicar la hora en formato HH (0-23).")
        return
    try:
        hour = int(context.args[0])
        set_send_hour(chat_id, hour)
        await context.bot.send_message(chat_id=chat_id, text=f"✅ Hora de envío local establecida a las {hour}:00.")
    except ValueError:
        await context.bot.send_message(chat_id=chat_id, text="❌ Formato no válido. Usa un número entre 0 y 23.")

async def stop_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    unsubscribe(chat_id)
    await context.bot.send_message(chat_id=chat_id, text="🛑 Suscripción cancelada.")

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("lang", lang_cmd))
    app.add_handler(CommandHandler("city", city_cmd))
    app.add_handler(CommandHandler("sethour", sethour_cmd))
    app.add_handler(CommandHandler("stop", stop_cmd))
    app.run_polling()

if __name__ == "__main__":
    main()
