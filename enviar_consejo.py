import json
import pytz
import requests
import os
from datetime import datetime, date

# Diccionario de traducción de días
dias_es = {
    "monday": "lunes",
    "tuesday": "martes",
    "wednesday": "miércoles",
    "thursday": "jueves",
    "friday": "viernes",
    "saturday": "sábado",
    "sunday": "domingo"
}

# Obtener fecha y día de la semana
zona = pytz.timezone("Europe/Madrid")
hoy = datetime.now(zona)
dia_semana_en = hoy.strftime("%A").lower()
dia_semana = dias_es[dia_semana_en]

# Cargar consejos
with open("consejos.json", encoding="utf-8") as f:
    consejos = json.load(f)

# Seleccionar los consejos del día correspondiente
consejos_dia = consejos.get(dia_semana, [])

# Si no hay consejos para ese día, mensaje por defecto
if not consejos_dia:
    consejo = f"No hay consejos disponibles para {dia_semana.title()}."
else:
    # Seleccionar un consejo rotatorio según el día juliano
    indice = (hoy.toordinal() - date(2025, 7, 29).toordinal()) % len(consejos_dia)
    consejo = consejos_dia[indice]

# Comprobar si ya se ha enviado hoy
ruta_ultimo_envio = "ultimo_envio.txt"
fecha_hoy_str = hoy.strftime("%Y-%m-%d")

enviar = True
if os.path.exists(ruta_ultimo_envio):
    with open(ruta_ultimo_envio, "r") as f:
        ultima_fecha = f.read().strip()
        if ultima_fecha == fecha_hoy_str:
            enviar = False

# Enviar por Telegram si no se ha enviado hoy
if enviar:
    TOKEN = os.getenv("TOKEN")
    CHAT_ID = os.getenv("CHAT_ID")
    mensaje = f"🛡 Consejo para hoy ({dia_semana.title()}):\n\n{consejo}"

    requests.get(
        f"https://api.telegram.org/bot{TOKEN}/sendMessage",
        params={"chat_id": CHAT_ID, "text": mensaje}
    )

    with open(ruta_ultimo_envio, "w") as f:
        f.write(fecha_hoy_str)
else:
    print(f"Ya se envió el consejo el {fecha_hoy_str}, no se vuelve a enviar.")
