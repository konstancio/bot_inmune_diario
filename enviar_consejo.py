import json
from datetime import datetime
import os
import requests
from configuracion_ubicacion import obtener_ubicacion
from calcular_intervalos import calcular_intervalos_optimos

TOKEN = os.environ.get("TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")

# Día actual
hoy = datetime.now()
dia_semana = hoy.strftime("%A").lower()

# Cargar consejos
with open("consejos.json", encoding="utf-8") as f:
    todos_los_consejos = json.load(f)

consejo = todos_los_consejos.get(dia_semana, {}).get("1", "No hay consejo disponible.")

# Cargar ubicación
ubicacion = obtener_ubicacion()
mañana, tarde = calcular_intervalos_optimos(
    ubicacion["latitud"], ubicacion["longitud"], hoy
)

texto_intervalos = ""
if mañana:
    texto_intervalos += f"🌤️ Por la mañana: {mañana[0]}–{mañana[1]}\n"
if tarde:
    texto_intervalos += f"🌇 Por la tarde: {tarde[0]}–{tarde[1]}\n"
if not texto_intervalos:
    texto_intervalos = "☁️ Hoy no hay una franja solar entre 30° y 40° antes o después del mediodía.\n"

mensaje = f"""🦠 Consejo inmunológico para hoy (*{dia_semana.title()}*):

{consejo}

☀️ Horarios óptimos de exposición solar en {ubicacion["ciudad"]}:
{texto_intervalos}

Ten un gran día 🌱
"""

url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
params = {
    "chat_id": CHAT_ID,
    "text": mensaje,
    "parse_mode": "Markdown"
}

response = requests.get(url, params=params)
print("✅ Enviado:", response.status_code, response.text)
