# ubicacion_y_sol.py
import math
import datetime as dt
import pytz
import requests
from timezonefinder import TimezoneFinder
from geopy.geocoders import Nominatim

# ---------- Ubicación con fallback a Málaga ----------
def obtener_ubicacion():
    ciudad = None
    lat = None
    lon = None
    try:
        ip = requests.get("https://api.ipify.org", timeout=5).text
        data = requests.get(f"https://ipapi.co/{ip}/json/", timeout=5).json()
        ciudad = data.get("city")
        lat = data.get("latitude")
        lon = data.get("longitude")
    except Exception:
        pass

    if not ciudad or not lat or not lon:
        ciudad = "Málaga"
        geolocator = Nominatim(user_agent="bot_inmune_diario")
        location = geolocator.geocode(ciudad)
        if not location:
            raise RuntimeError("No se pudo obtener ubicación")
        lat, lon = location.latitude, location.longitude

    try:
        tzname = TimezoneFinder().timezone_at(lat=float(lat), lng=float(lon)) or "Europe/Madrid"
    except Exception:
        tzname = "Europe/Madrid"

    return {
        "latitud": float(lat),
        "longitud": float(lon),
        "ciudad": ciudad,
        "timezone": tzname,
    }

# ---------- Astronomía: intervalos 30°–40° ----------
def _declinacion_solar(doy: int) -> float:
    # aproximación suficiente para nuestra franja
    return 23.44 * math.sin(math.radians((360 / 365) * (doy - 81)))

def _elevacion(lat, dec, hora_decimal):
    H = (hora_decimal - 12) * 15.0  # ángulo horario
    latr = math.radians(lat)
    decr = math.radians(dec)
    Hr   = math.radians(H)
    s = math.sin(latr)*math.sin(decr) + math.cos(latr)*math.cos(decr)*math.cos(Hr)
    s = max(-1.0, min(1.0, s))
    return math.degrees(math.asin(s))

def calcular_intervalos_optimos(lat, lon, fecha: dt.date, zona_horaria: str):
    tz = pytz.timezone(zona_horaria)
    base = dt.datetime.combine(fecha, dt.time(0,0,0, tzinfo=tz))
    doy = fecha.timetuple().tm_yday
    dec = _declinacion_solar(doy)

    paso = 5  # minutos
    puntos = []
    for m in range(0, 24*60, paso):
        t = base + dt.timedelta(minutes=m)
        hd = t.hour + t.minute/60.0
        elev = _elevacion(lat, dec, hd)
        puntos.append((t, elev))

    # agrupar en tramos donde 30 <= elev <= 40
    tramos = []
    en = False; ini = None
    for i,(t,e) in enumerate(puntos):
        dentro = (30 <= e <= 40)
        if dentro and not en:
            en = True; ini = t
        elif not dentro and en:
            fin = puntos[i-1][0]
            tramos.append((ini, fin)); en = False
    if en:
        tramos.append((ini, puntos[-1][0]))

    # separar mañana / tarde respecto a las 12:00 locales
    mediodia = base.replace(hour=12, minute=0)
    maniana = next(((i,f) for i,f in tramos if f <= mediodia), None)
    tarde   = next(((i,f) for i,f in tramos if i >  mediodia), None)
    return maniana, tarde

def describir_intervalos(intervalos, ciudad: str) -> str:
    maniana, tarde = intervalos
    parts = [f"☀️ Intervalos solares seguros para producir vit. D hoy en {ciudad}:"]
    if maniana:
        i,f = maniana
        parts += [ "🌅 Mañana:", f"🕒 {i.strftime('%H:%M')} - {f.strftime('%H:%M')}" ]
    if tarde:
        i,f = tarde
        parts += [ "🌇 Tarde:", f"🕒 {i.strftime('%H:%M')} - {f.strftime('%H:%M')}" ]
    if not maniana and not tarde:
        parts.append("🙁 Hoy el Sol no alcanza 30° de elevación.")
    return "\n".join(parts)
