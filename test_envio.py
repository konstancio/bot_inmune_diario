import os
import json
from datetime import datetime
import pytz
import requests

# Cargar consejos
with open("consejos.json", encoding="utf-8") as f:
    consejos = json.load(f)

# Traducir días al español
dias_es = {
    "monday": "lunes",
    "tuesday": "martes",
    "wednesday": "miércoles",
    "thursday": "jueves",
    "friday": "viernes",
    "saturday": "sábado",
    "sunday": "domingo"
}

# Día actual
hoy = datetime.now(pytz.timezone("Europe/Madrid"))
dia_semana_en = hoy.strftime("%A").lower()
dia_semana = dias_es[dia_semana_en]

# Elegir consejo
consejos_dia = consejos.get(dia_semana, [])
if not consejos_dia:
    consejo = f"No hay consejos disponibles para {dia_semana.title()}."
else:
    indice = hoy.toordinal() % len(consejos_dia)
    consejo = consejos_dia[indice]

# Enviar por Telegram
TOKEN = os.getenv("7254029750:AAG-ukM8YXZ-9Fq7YhcMj2A8ny6Gz92TQvE")
CHAT_ID = os.getenv("7678609")

mensaje = f"📅 Consejo para hoy ({dia_semana.title()}):\n\n{consejo}"

respuesta = requests.get(
    f"https://api.telegram.org/bot{TOKEN}/sendMessage",
    params={"chat_id": CHAT_ID, "text": mensaje}
)

print("Código de respuesta:", respuesta.status_code)
print("Mensaje enviado:", mensaje)
print("Respuesta Telegram:", respuesta.text)
