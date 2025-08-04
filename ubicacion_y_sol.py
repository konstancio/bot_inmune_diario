# ubicacion_y_sol.py

import requests
from geopy.geocoders import Nominatim
from timezonefinder import TimezoneFinder
from astral import LocationInfo
from astral.sun import sun
from astral.location import Observer
from datetime import datetime, timedelta
import pytz


def obtener_ubicacion():
    try:
        ip = requests.get("https://api.ipify.org").text
        response = requests.get(f"https://ipapi.co/{ip}/json/")
        data = response.json()

        ciudad = data.get("city")
        lat = data.get("latitude")
        lon = data.get("longitude")

        if not ciudad or not lat or not lon:
            raise ValueError("Datos incompletos desde IP")

        print(f"✅ Ubicación detectada por IP: {ciudad} ({lat}, {lon})")

    except Exception as e:
        print(f"⚠️ Error al obtener ubicación por IP: {e}")
        ciudad = "Málaga"
        geolocator = Nominatim(user_agent="bot_inmune_diario")
        location = geolocator.geocode(ciudad)
        lat = location.latitude
        lon = location.longitude
        print(f"🔁 Usando ubicación por defecto: Málaga ({lat}, {lon})")

    try:
        tf = TimezoneFinder()
        zona_horaria = tf.timezone_at(lat=lat, lng=lon)
    except Exception as e:
        print(f"❌ Error al obtener la zona horaria: {e}")
        zona_horaria = "Europe/Madrid"

    return {
        "latitud": lat,
        "longitud": lon,
        "ciudad": ciudad,
        "timezone": zona_horaria
    }


def calcular_intervalos_optimos(lat, lon, fecha, zona_horaria):
    location = LocationInfo("Ubicación", "España", zona_horaria, lat, lon)
    observer = Observer(latitude=lat, longitude=lon)
    s = sun(observer, date=fecha, tzinfo=pytz.timezone(zona_horaria))

    elevaciones_validas = []
    hora_actual = s["sunrise"]
    fin = s["sunset"]

    while hora_actual <= fin:
        altitud = location.solar_elevation(hora_actual)
        if 30 <= altitud <= 40:
            elevaciones_validas.append(hora_actual)
        hora_actual += timedelta(minutes=10)

    # Dividir entre mañana y tarde según mediodía solar
    mediodia = s["noon"]
    antes = [h for h in elevaciones_validas if h < mediodia]
    despues = [h for h in elevaciones_validas if h > mediodia]

    # Compactar los intervalos en bloques
    def agrupar_intervalos(lista):
        if not lista:
            return []

        grupos = []
        inicio = lista[0]
        anterior = lista[0]

        for actual in lista[1:]:
            if (actual - anterior) > timedelta(minutes=10):
                grupos.append((inicio, anterior))
                inicio = actual
            anterior = actual

        grupos.append((inicio, anterior))
        return grupos

    return agrupar_intervalos(antes), agrupar_intervalos(despues)


def describir_intervalos(intervalos, ciudad):
    if not intervalos[0] and not intervalos[1]:
        return f"⚠️ Hoy no se puede producir vitamina D en {ciudad} (el Sol no supera los 30° de elevación)."

    mensaje = f"☀️ Intervalos solares seguros para producir vit. D hoy en {ciudad}:\n"

    if intervalos[0]:
        mensaje += "🌅 Mañana:\n"
        for inicio, fin in intervalos[0]:
            mensaje += f"🕒 {inicio.strftime('%H:%M')} - {fin.strftime('%H:%M')}\n"

    if intervalos[1]:
        mensaje += "🌇 Tarde:\n"
        for inicio, fin in intervalos[1]:
            mensaje += f"🕒 {inicio.strftime('%H:%M')} - {fin.strftime('%H:%M')}\n"

    return mensaje