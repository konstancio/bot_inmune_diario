import json
from datetime import datetime, timedelta
from telegram import Bot
from astral import LocationInfo
from astral.sun import sun
from astral.location import Location
from zoneinfo import ZoneInfo
import asyncio

# === CONFIGURACIÓN ===
TOKEN = '7254029750:AAG-ukM8YXZ-9Fq7YhcMj2A8ny6Gz92TQvE'
USER_ID = 7678609

async def enviar_consejo():
    # Leer ubicación
    with open("ubicacion.json") as f:
        datos = json.load(f)

    lat = datos["latitud"]
    lon = datos["longitud"]
    ciudad = datos["ciudad"]
    tz = ZoneInfo("Europe/Madrid")

    # Crear objeto de localización
    loc_info = LocationInfo(ciudad, "España", "Europe/Madrid", lat, lon)
    loc = Location(loc_info)
    ahora = datetime.now(tz=tz)
    hoy = ahora.date()

    # Obtener el mediodía solar exacto
    eventos = sun(loc.observer, date=hoy, tzinfo=tz)
    mediodia = eventos['noon']

    # Barrido horario para detectar elevaciones entre 30° y 40°
    inicio_dia = datetime.combine(hoy, datetime.min.time(), tz)
    fin_dia = datetime.combine(hoy, datetime.max.time(), tz)
    hora = inicio_dia.replace(hour=5, minute=0, second=0)
    paso = timedelta(minutes=1)

    mañana = []
    tarde = []

    while hora <= fin_dia:
        elev = loc.solar_elevation(hora)
        if 30 <= elev <= 40:
            if hora < mediodia:
                mañana.append(hora)
            elif hora > mediodia:
                tarde.append(hora)
        hora += paso

    # Formatear resultado
    def formatear_intervalo(lista):
        if not lista:
            return "—"
        return f"{lista[0].strftime('%H:%M')} a {lista[-1].strftime('%H:%M')}"

    bloque_mañana = formatear_intervalo(mañana)
    bloque_tarde = formatear_intervalo(tarde)

    mensaje = f"""
☀️ *Consejo inmunológico diario*

Hoy en *{ciudad}*, el Sol estará entre 30° y 40° de elevación en los siguientes intervalos *seguros para sintetizar vitamina D*:

• 🌅 Mañana: {bloque_mañana}
• 🌇 Tarde: {bloque_tarde}

✅ Aprovecha 10–20 minutos de exposición directa en uno de estos bloques:
- Sin gafas de sol ni protector solar (en ese breve tiempo)
- Con brazos y cara descubiertos si es posible

🎯 Exposición regular, breve y bien cronometrada = máxima inmunidad sin daño solar.
"""

    bot = Bot(token=TOKEN)
    await bot.send_message(chat_id=USER_ID, text=mensaje, parse_mode="Markdown")

# Ejecutar
asyncio.run(enviar_consejo())

