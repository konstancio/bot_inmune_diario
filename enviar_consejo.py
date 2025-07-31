import os
from datetime import datetime, date
from configuracion_ubicacion import obtener_ubicacion
from calcular_intervalos import calcular_intervalos_optimos
import requests

# Diccionario con los consejos diarios
from consejos_diarios import consejos

# Día de la semana en español
dias_es = {
    "monday": "lunes",
    "tuesday": "martes",
    "wednesday": "miércoles",
    "thursday": "jueves",
    "friday": "viernes",
    "saturday": "sábado",
    "sunday": "domingo"
}

# Comprobar si ya se ha enviado hoy
archivo_envio = "ultimo_envio.txt"
hoy = date.today()

if os.path.exists(archivo_envio):
    with open(archivo_envio, "r") as f:
        ultima_fecha = f.read().strip()
    if ultima_fecha == hoy.isoformat():
        print(f"Ya se envió el consejo el {ultima_fecha}, no se vuelve a enviar.")
        exit()

# Obtener ubicación actual
ubicacion = obtener_ubicacion()

if not ubicacion or "latitud" not in ubicacion or "longitud" not in ubicacion:
    print("Error: No se pudo obtener la ubicación correctamente.")
    exit(1)

lat = ubicacion["latitud"]
lon = ubicacion["longitud"]

timezone_str = ubicacion["zona_horaria"]

# Día de la semana
dia_semana_en = hoy.strftime("%A").lower()
dia_semana = dias_es[dia_semana_en]

# Seleccionar consejo
consejos_dia = consejos.get(dia_semana, [])

if not consejos_dia:
    consejo = f"No hay consejos disponibles para {dia_semana.title()}."
else:
    indice = (hoy.toordinal() - date(2025, 7, 29).toordinal()) % len(consejos_dia)
    consejo = consejos_dia[indice]

# Calcular intervalos solares óptimos
intervalos = calcular_intervalos_optimos(lat, lon, hoy, timezone_str)

texto_intervalos = "\n".join([f"• {inicio} – {fin}" for inicio, fin in intervalos]) or "No se encontraron intervalos óptimos."

# Enviar por Telegram
TOKEN = os.getenv("TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

mensaje = (
    f"🌞 Consejo para hoy ({dia_semana.title()}):\n\n"
    f"{consejo}\n\n"
    f"🕒 Intervalos solares recomendados:\n{texto_intervalos}"
)

try:
    response = requests.get(
        f"https://api.telegram.org/bot{TOKEN}/sendMessage",
        params={"chat_id": CHAT_ID, "text": mensaje}
    )
    if response.status_code == 200:
        print("✅ Consejo enviado con éxito.")
        with open(archivo_envio, "w") as f:
            f.write(hoy.isoformat())
    else:
        print(f"❌ Error al enviar mensaje: {response.text}")
except Exception as e:
    print(f"❌ Excepción al enviar mensaje: {e}")

