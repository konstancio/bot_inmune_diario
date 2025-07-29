import json
from datetime import datetime, date
import pytz
import requests

# Cargar consejos
with open("consejos.json", encoding="utf-8") as f:
    consejos = json.load(f)

# Día actual
hoy = datetime.now(pytz.timezone("Europe/Madrid"))
dias_es = {
    "monday": "lunes",
    "tuesday": "martes",
    "wednesday": "miércoles",
    "thursday": "jueves",
    "friday": "viernes",
    "saturday": "sábado",
    "sunday": "domingo"
}
dia_semana_en = hoy.strftime("%A").lower()
dia_semana = dias_es[dia_semana_en]

dia_semana = hoy.strftime("%A").lower()

# Seleccionar consejo
consejos_dia = consejos.get(dia_semana, [])

if not consejos_dia:
    consejo = f"No hay consejos disponibles para {dia_semana.title()}."
else:
    indice = (hoy.toordinal() - date(2025, 7, 29).toordinal()) % len(consejos_dia)
    consejo = consejos_dia[indice]


# Enviar por Telegram
TOKEN = "AQUÍ_TU_TOKEN"
CHAT_ID = "AQUÍ_TU_CHAT_ID"
mensaje = f"📅 Consejo para hoy ({dia_semana.title()}):\n\n{consejo}"

requests.get(f"https://api.telegram.org/bot{TOKEN}/sendMessage", params={"chat_id": CHAT_ID, "text": mensaje})
