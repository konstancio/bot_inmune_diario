# enviar_consejo.py

import os
import datetime
import random
import asyncio
from telegram import Bot
from consejos_diarios import consejos
from ubicacion_y_sol import (
    obtener_ubicacion,
    calcular_intervalos_optimos,
    describir_intervalos,
    obtener_pronostico_meteorologico
)

# Consejo nutricional alternativo
alternativo = """🥦 Consejo nutricional para hoy:\nSi no puedes sintetizar vitamina D por el Sol, aumenta el consumo de pescados azules, yema de huevo, setas shiitake o alimentos enriquecidos como bebidas vegetales. También puedes valorar un suplemento supervisado por un profesional."""

# 1. Obtener ubicación y zona horaria
ubicacion = obtener_ubicacion()
lat = ubicacion["latitud"]
lon = ubicacion["longitud"]
timezone_str = ubicacion["timezone"]
ciudad = ubicacion["ciudad"]

# 2. Obtener fecha actual
hoy = datetime.datetime.now().date()
dia_semana = datetime.datetime.now().weekday()

# 3. Obtener consejo y referencia
consejos_dia = consejos[dia_semana]
indices = list(range(0, len(consejos_dia), 2))
indice = random.choice(indices)
texto_consejo = consejos_dia[indice]
texto_referencia = consejos_dia[indice + 1]

# 4. Calcular intervalos de sol y pronóstico
intervalos = calcular_intervalos_optimos(lat, lon, hoy, timezone_str)
antes, despues = intervalos

# 5. Añadir pronóstico si hay intervalos
if antes or despues:
    pronostico = obtener_pronostico_meteorologico(hoy, lat, lon)
    texto_intervalos = describir_intervalos(intervalos, ciudad, pronostico)
    mensaje = f"{texto_consejo}\n\n{texto_referencia}\n\n{texto_intervalos}"
else:
    mensaje = f"{texto_consejo}\n\n{texto_referencia}\n\n⚠️ Hoy no es posible sintetizar vitamina D por exposición solar.\n\n{alternativo}"

# 6. Enviar mensaje por Telegram
bot_token = os.getenv("BOT_TOKEN")
chat_id = os.getenv("CHAT_ID")

def enviar_mensaje_telegram(texto):
    if not bot_token or not chat_id:
        print("❌ Faltan BOT_TOKEN o CHAT_ID")
        return

    async def enviar():
        bot = Bot(token=bot_token)
        await bot.send_message(chat_id=chat_id, text=texto)

    try:
        asyncio.run(enviar())
        print("✅ Consejo enviado correctamente por Telegram.")
    except Exception as e:
        print(f"❌ Error al enviar mensaje: {e}")

# Ejecutar envío
enviar_mensaje_telegram(mensaje)
