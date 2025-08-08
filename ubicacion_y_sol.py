
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

def _declinacion_solar(n):
    # Cooper: δ ≈ 23.44° * sin(2π*(284+n)/365)
    return 23.44 * math.sin(2*math.pi*(284 + n)/365.0)

def _ecuacion_del_tiempo_min(n):
    # Spencer: B = 2π(n-81)/364 ; EoT (min) = 9.87 sin(2B) - 7.53 cos B - 1.5 sin B
    B = 2*math.pi*(n - 81)/364.0
    return 9.87*math.sin(2*B) - 7.53*math.cos(B) - 1.5*math.sin(B)

def _elevacion_solar(phi_deg, delta_deg, hora_solar_decimal):
    # sin(h) = sinφ sinδ + cosφ cosδ cosH , H = 15°*(LST-12)
    H = math.radians(15.0*(hora_solar_decimal - 12.0))
    phi = math.radians(phi_deg)
    delta = math.radians(delta_deg)
    sin_h = math.sin(phi)*math.sin(delta) + math.cos(phi)*math.cos(delta)*math.cos(H)
    # Evitar errores numéricos
    sin_h = max(-1.0, min(1.0, sin_h))
    return math.degrees(math.asin(sin_h))

def calcular_intervalos_30_40(fecha, latitud=36.7213, longitud=-4.4216, zona_horaria="Europe/Madrid"):
    """
    Devuelve (tramo_mañana, tramo_tarde) como pares (inicio_dt, fin_dt) tz-aware en la zona dada,
    para los periodos donde 30° ≤ elevación ≤ 40°.
    """
    tz = pytz.timezone(zona_horaria)
    n = fecha.timetuple().tm_yday
    delta = _declinacion_solar(n)                   # declinación en grados
    eot_min = _ecuacion_del_tiempo_min(n)           # Ecuación del tiempo en minutos

    # Offset del huso en horas (incluye DST si aplica ese día)
    # Usamos mediodía local para coger el offset del día
    noon_local = tz.localize(datetime.datetime(fecha.year, fecha.month, fecha.day, 12, 0))
    offset_horas = noon_local.utcoffset().total_seconds() / 3600.0
    # Meridiano estándar del huso
    L_st = 15.0 * offset_horas  # grados

    # Corrección total en minutos para pasar de hora local a hora solar
    # TC = 4*(longitud - L_st) + EoT   (min)
    TC_min = 4.0 * (longitud - L_st) + eot_min

    # Hora local del mediodía solar (LST=12 ⇒ LT = 12 - TC/60)
    mediodia_local_decimal = 12.0 - (TC_min / 60.0)
    mediodia_local_dt = tz.localize(datetime.datetime(
        fecha.year, fecha.month, fecha.day, int(mediodia_local_decimal),
        int((mediodia_local_decimal % 1)*60)
    ))

    # Escaneamos el día con paso fino
    paso_min = 5
    inicio_busqueda = tz.localize(datetime.datetime(fecha.year, fecha.month, fecha.day, 6, 0))
    fin_busqueda     = tz.localize(datetime.datetime(fecha.year, fecha.month, fecha.day, 21, 0))

    puntos = []
    t = inicio_busqueda
    while t <= fin_busqueda:
        # Hora local decimal
        h_local = t.hour + t.minute/60.0
        # Hora solar verdadera
        h_solar = h_local + (TC_min / 60.0)
        elev = _elevacion_solar(latitud, delta, h_solar)
        puntos.append((t, elev))
        t += datetime.timedelta(minutes=paso_min)

    # Detectar tramos 30–40
    tramos = []
    en_tramo = False
    t_inicio = None
    for i, (ti, elev) in enumerate(puntos):
        if 30.0 <= elev <= 40.0:
            if not en_tramo:
                en_tramo = True
                t_inicio = ti
        else:
            if en_tramo:
                tramos.append((t_inicio, puntos[i-1][0]))
                en_tramo = False
    if en_tramo:
        tramos.append((t_inicio, puntos[-1][0]))

    # Separar en mañana/tarde usando el mediodía solar calculado
    tramo_manana = None
    tramo_tarde  = None
    for ini, fin in tramos:
        if fin <= mediodia_local_dt and tramo_manana is None:
            tramo_manana = (ini, fin)
        elif ini >= mediodia_local_dt and tramo_tarde is None:
            tramo_tarde = (ini, fin)

    return tramo_manana, tramo_tarde

def formatear_intervalos(tramo_manana, tramo_tarde, ciudad):
    texto = f"\n☀️ Intervalos solares seguros para producir vit. D hoy en {ciudad}:"
    if tramo_manana:
        a, b = tramo_manana
        texto += f"\n🌅 Mañana:\n🕒 {a.strftime('%H:%M')} - {b.strftime('%H:%M')}"
    if tramo_tarde:
        a, b = tramo_tarde
        texto += f"\n🌇 Tarde:\n🕒 {a.strftime('%H:%M')} - {b.strftime('%H:%M')}"
    if not tramo_manana and not tramo_tarde:
        texto += "\n(No hay elevación solar suficiente hoy para producir vitamina D)"
    return texto

    return texto.strip()
