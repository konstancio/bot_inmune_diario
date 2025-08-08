# enviar_consejo.py

import os
import datetime
import random
import asyncio
from telegram import Bot
from consejos_diarios import consejos
from ubicacion_y_sol import (
    obtener_ubicacion,
    calcular_intervalos_30_40,
    formatear_intervalos,
)

# 1) Ubicación y zona horaria
ubicacion = obtener_ubicacion()
lat = float(ubicacion["latitud"])
lon = float(ubicacion["longitud"])
timezone_str = ubicacion["timezone"]
ciudad = ubicacion["ciudad"]

# 2) Fecha y día de la semana
hoy = datetime.date.today()
dia_semana = datetime.datetime.now().weekday()  # lunes=0 ... domingo=6

# 3) Consejo y referencia del día (pares consecutivos)
conj = consejos[dia_semana]
pares = [conj[i:i+2] for i in range(0, len(conj), 2)]
consejo, referencia = random.choice(pares)

# 4) Intervalos solares precisos 30–40°
tramo_manana, tramo_tarde = calcular_intervalos_30_40(hoy, lat, lon, timezone_str)
texto_intervalos = formatear_intervalos(tramo_manana, tramo_tarde, ciudad)

# 5) Mensaje final
mensaje = f"{consejo}\n\n{referencia}\n\n{texto_intervalos}"

# 6) Envío por Telegram
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

def enviar_mensaje_telegram(texto: str):
    if not BOT_TOKEN or not CHAT_ID:
        print("❌ Faltan BOT_TOKEN o CHAT_ID")
        return

    async def _send():
        bot = Bot(token=BOT_TOKEN)
        await bot.send_message(chat_id=CHAT_ID, text=texto)

    try:
        asyncio.run(_send())
        print("✅ Consejo enviado correctamente por Telegram.")
    except Exception as e:
        print(f"❌ Error al enviar mensaje: {e}")

# Ejecutar
enviar_mensaje_telegram(mensaje)
