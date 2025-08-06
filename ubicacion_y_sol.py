
# ubicacion_y_sol.py

import requests
from geopy.geocoders import Nominatim
from timezonefinder import TimezoneFinder
from astral import LocationInfo
from astral.sun import sun
from astral import sun as astral_sun
from datetime import datetime, timedelta
import pytz
import os

# 1. Función para obtener ubicación por IP con fallback a Málaga
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

        print(f"✅ Ubicación detectada: {ciudad} ({lat}, {lon})")
    except Exception as e:
        print(f"⚠️ Error al obtener ubicación por IP: {e}")
        print("🔁 Usando ubicación por defecto: Málaga")
        ciudad = "Málaga"
        geolocator = Nominatim(user_agent="bot_inmune_diario")
        location = geolocator.geocode(ciudad)
        if not location:
            print("❌ No se pudo geolocalizar Málaga.")
            return None
        lat = location.latitude
        lon = location.longitude

    try:
        tf = TimezoneFinder()
        zona_horaria = tf.timezone_at(lat=lat, lng=lon)
    except:
        zona_horaria = "Europe/Madrid"

    return {
        "latitud": lat,
        "longitud": lon,
        "ciudad": ciudad,
        "timezone": zona_horaria
    }

# 2. Función para calcular intervalos solares óptimos (30°–40°)
def calcular_intervalos_optimos(lat, lon, fecha, zona_horaria):
    from astral import Observer
    from astral.sun import elevation
    import math

    tz = pytz.timezone(zona_horaria)
    observer = Observer(latitude=lat, longitude=lon)
    hora = datetime(fecha.year, fecha.month, fecha.day, 6, 0, tzinfo=tz)
    fin = datetime(fecha.year, fecha.month, fecha.day, 21, 0, tzinfo=tz)

    intervalo_m = []
    intervalo_t = []

    while hora <= fin:
        elev = elevation(observer, hora)
        if 30 <= elev <= 40:
            if hora < datetime(fecha.year, fecha.month, fecha.day, 12, 0, tzinfo=tz):
                intervalo_m.append(hora)
            else:
                intervalo_t.append(hora)
        hora += timedelta(minutes=10)

    def agrupar_intervalos(intervalos):
        if not intervalos:
            return []
        bloques = []
        inicio = intervalos[0]
        for i in range(1, len(intervalos)):
            if (intervalos[i] - intervalos[i - 1]) > timedelta(minutes=20):
                fin = intervalos[i - 1]
                bloques.append((inicio, fin))
                inicio = intervalos[i]
        bloques.append((inicio, intervalos[-1]))
        return bloques

    return agrupar_intervalos(intervalo_m), agrupar_intervalos(intervalo_t)

# 3. Función para obtener pronóstico del tiempo
def obtener_pronostico_meteorologico(fecha, lat, lon):
    clave = os.getenv("OPENWEATHER_API_KEY")
    if not clave:
        return {}

    url = f"https://api.openweathermap.org/data/2.5/forecast?lat={lat}&lon={lon}&appid={clave}&units=metric&lang=es"
    try:
        respuesta = requests.get(url)
        datos = respuesta.json()
    except:
        return {}

    pronostico = {}
    for entrada in datos["list"]:
        hora_texto = entrada["dt_txt"]
        hora_dt = datetime.strptime(hora_texto, "%Y-%m-%d %H:%M:%S")
        if hora_dt.date() == fecha:
            descripcion = entrada["weather"][0]["description"]
            nubes = entrada["clouds"]["all"]
            pronostico[hora_dt.replace(tzinfo=pytz.utc)] = {
                "descripcion": descripcion,
                "nubes": nubes
            }
    return pronostico

# 4. Función para describir los intervalos en texto
def describir_intervalos(intervalos, ciudad, pronostico=None):
    antes, despues = intervalos
    texto = f"☀️ Intervalos solares seguros para producir vit. D hoy en {ciudad}:\n"
    
    def formatear_intervalo(inicio, fin, label):
        texto = f"🕒 {inicio.strftime('%H:%M')} - {fin.strftime('%H:%M')}"
        if pronostico:
            hora_clave = inicio.replace(minute=0, second=0, microsecond=0)
            datos = pronostico.get(hora_clave.astimezone(pytz.utc))
            if datos:
                if datos["nubes"] > 75:
                    texto += f" (☁️ {datos['descripcion']})"
                else:
                    texto += f" (🌤️ {datos['descripcion']})"
        return f"{label}\n{texto}\n"

    if antes:
        for inicio, fin in antes:
            texto += formatear_intervalo(inicio, fin, "🌅 Mañana:")
    if despues:
        for inicio, fin in despues:
            texto += formatear_intervalo(inicio, fin, "🌇 Tarde:")
    if not antes and not despues:
        texto += "⚠️ Hoy no hay intervalos solares seguros (30°–40° de elevación)."

    # 5. Función para calcular grados solares cada día del año.
import math
import datetime
import pytz

def calcular_intervalos_30_40(fecha, latitud=36.7213, longitud=-4.4214, zona_horaria="Europe/Madrid"):
    # Declinación solar aproximada
    def declinacion(dia_del_ano):
        return 23.44 * math.sin(math.radians((360 / 365) * (dia_del_ano - 81)))

    # Elevación solar
    def elevacion_solar(hora_decimal, declinacion, lat):
        h = (hora_decimal - 12) * 15  # ángulo horario
        return math.degrees(math.asin(
            math.sin(math.radians(lat)) * math.sin(math.radians(declinacion)) +
            math.cos(math.radians(lat)) * math.cos(math.radians(declinacion)) * math.cos(math.radians(h))
        ))

    # Obtener zona horaria
    tz = pytz.timezone(zona_horaria)
    hoy = datetime.datetime.combine(fecha, datetime.time(0, 0)).astimezone(tz)
    dia_del_ano = fecha.timetuple().tm_yday
    decl = declinacion(dia_del_ano)

    paso_min = 5
    elevaciones = []
    for minuto in range(0, 24 * 60, paso_min):
        hora = hoy + datetime.timedelta(minutes=minuto)
        hora_local = hora.astimezone(tz)
        hora_decimal = hora_local.hour + hora_local.minute / 60
        elev = elevacion_solar(hora_decimal, decl, latitud)
        elevaciones.append((hora_local, elev))

    # Buscar tramos donde la elevación esté entre 30 y 40 grados
    tramos = []
    en_tramo = False
    inicio = None

    for i, (hora, elev) in enumerate(elevaciones):
        if 30 <= elev <= 40:
            if not en_tramo:
                inicio = hora
                en_tramo = True
        else:
            if en_tramo:
                fin = elevaciones[i - 1][0]
                tramos.append((inicio, fin))
                en_tramo = False

    if en_tramo:
        tramos.append((inicio, elevaciones[-1][0]))

    # Separar en dos tramos: uno antes del mediodía y otro después
    mediodia = hoy.replace(hour=12, minute=0)
    tramo_manana = next(((i, f) for i, f in tramos if f <= mediodia), None)
    tramo_tarde = next(((i, f) for i, f in tramos if i > mediodia), None)

    return tramo_manana, tramo_tarde

def formatear_intervalos(tramo_manana, tramo_tarde, ciudad):
    texto = f"\n☀️ Intervalos solares seguros para producir vit. D hoy en {ciudad}:"

    if tramo_manana:
        inicio_m, fin_m = tramo_manana
        texto += f"\n🌅 Mañana:\n🕒 {inicio_m.strftime('%H:%M')} - {fin_m.strftime('%H:%M')}"
    if tramo_tarde:
        inicio_t, fin_t = tramo_tarde
        texto += f"\n🌇 Tarde:\n🕒 {inicio_t.strftime('%H:%M')} - {fin_t.strftime('%H:%M')}"

    if not tramo_manana and not tramo_tarde:
        texto += "\n(No hay elevación solar suficiente hoy para producir vitamina D)"

    return texto

    return texto.strip()
