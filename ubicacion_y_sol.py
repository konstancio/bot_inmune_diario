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

# --- Pronóstico con Open-Meteo (sin API key) ------------------------------
import requests
from datetime import datetime, timedelta

def _safe_tzname(tzname: str) -> str:
    # Open-Meteo entiende "auto" o un nombre tipo "Europe/Madrid".
    # Si el tz falla, usamos "auto".
    try:
        return tzname or "auto"
    except:
        return "auto"

def obtener_pronostico_diario(fecha, lat: float, lon: float, tzname: str):
    """
    Devuelve un dict con datos horarios de nubes (%) y prob. lluvia (%) para la fecha dada.
    Estructura:
      {
        "hora_local_str" -> {"clouds": int, "pop": int}
      }
    Si algo falla, devuelve {}.
    """
    try:
        tzparam = _safe_tzname(tzname)
        # Pedimos 24h alrededor del día para tener margen por zona horaria
        start = datetime(fecha.year, fecha.month, fecha.day, 0, 0)
        end   = start + timedelta(days=1)

        url = (
            "https://api.open-meteo.com/v1/forecast"
            f"?latitude={lat:.5f}&longitude={lon:.5f}"
            "&hourly=cloudcover,precipitation_probability"
            f"&start_date={start.date()}&end_date={end.date()}"
            f"&timezone={tzparam}"
        )
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        data = r.json()

        times   = data.get("hourly", {}).get("time", [])
        clouds  = data.get("hourly", {}).get("cloudcover", [])
        pops    = data.get("hourly", {}).get("precipitation_probability", [])

        out = {}
        for t, c, p in zip(times, clouds, pops):
            # 't' viene como 'YYYY-MM-DDTHH:00'
            out[t] = {"clouds": int(c if c is not None else 0),
                      "pop":    int(p if p is not None else 0)}
        return out
    except Exception:
        return {}

def _media_intervalo(pron_horario: dict, inicio, fin) -> dict | None:
    """
    Calcula medias simples de nubes (%) y prob. lluvia (%) entre [inicio, fin].
    inicio/fin son datetime con tz local.
    """
    if not pron_horario:
        return None

    # Recorremos en pasos de 1 hora redondeando a la hora inferior
    cur = inicio.replace(minute=0, second=0, microsecond=0)
    if cur < inicio:
        cur += timedelta(hours=1)

    vals_c, vals_p = [], []
    while cur <= fin:
        key = cur.strftime("%Y-%m-%dT%H:00")
        if key in pron_horario:
            vals_c.append(pron_horario[key]["clouds"])
            vals_p.append(pron_horario[key]["pop"])
        cur += timedelta(hours=1)

    if not vals_c:
        return None

    nubes = round(sum(vals_c) / len(vals_c))
    pop   = round(sum(vals_p) / len(vals_p))
    # Etiqueta rápida según nubes
    if nubes <= 25:
        estado = "despejado"
    elif nubes <= 60:
        estado = "parcialmente nublado"
    else:
        estado = "nublado"

    return {"estado": estado, "nubes": nubes, "lluvia": pop}

def formatear_intervalos_meteo(intervalos, pron_horario: dict) -> str:
    """
    Añade, si hay datos, una línea con el tiempo en cada tramo.
    intervalos: lista de (inicio_dt_local, fin_dt_local)
    """
    if not intervalos or not pron_horario:
        return ""

    lineas = []
    for idx, (ini, fin) in enumerate(intervalos, start=1):
        m = _media_intervalo(pron_horario, ini, fin)
        if not m:
            continue
        etiqueta = "Mañana" if idx == 1 else "Tarde"
        lineas.append(
            f"   (🌤 {etiqueta}: {m['estado']}, nubes {m['nubes']}%, lluvia {m['lluvia']}%)"
        )
    return ("\n" + "\n".join(lineas)) if lineas else ""
