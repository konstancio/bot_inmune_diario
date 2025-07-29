import json
from datetime import datetime
import pytz
import requests

# Cargar consejos
with open("consejos.json", encoding="utf-8") as f:
    consejos = json.load(f)

# Día actual
hoy = datetime.now(pytz.timezone("Europe/Madrid"))
dia_semana = hoy.strftime("%A").lower()

# Seleccionar consejo
indice = (hoy.toordinal() - date(2025, 7, 29).toordinal()) % len(consejos.get(dia_semana, []))
consejo = consejos.get(dia_semana, ["No hay consejo para hoy."])[indice]

# Enviar por Telegram
TOKEN = "AQUÍ_TU_TOKEN"
CHAT_ID = "AQUÍ_TU_CHAT_ID"
mensaje = f"📅 Consejo para hoy ({dia_semana.title()}):\n\n{consejo}"

requests.get(f"https://api.telegram.org/bot{TOKEN}/sendMessage", params={"chat_id": CHAT_ID, "text": mensaje})
