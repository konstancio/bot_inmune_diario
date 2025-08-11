# ubicacion_y_sol.py
# Cálculo de intervalos 30–40° sin Astral + detección de ubicación

import os
import math
import datetime
import requests
import pytz
from geopy.geocoders import Nominatim
from timezonefinder import TimezoneFinder

# ---------------- Ubicación ----------------

def obtener_ubicacion():
    """
    Intenta IP -> ipapi; si falla, fallback a ciudad de entorno CIUDAD o 'Málaga'.
    Devuelve dict: {latitud, longitud, ciudad, timezone}
    """
    ciudad_env = (os.getenv("CIUDAD") or "").strip()
    ciudad = ciudad_env if ciudad_env else "Málaga"

    lat = lon = tz_name = None

    # 1) Por IP
    try:
        ip = requests.get("https://api.ipify.org", timeout=5).text
        data = requests.get(f"https://ipapi.co/{ip}/json/", timeout=7).json()
        lat = data.get("latitude")
        lon = data.get("longitude")
        ciudad_ip = data.get("city")
        if ciudad_ip:
            ciudad = ciudad_ip
        print(f"✅ Ubicación detectada por IP: {ciudad} ({lat}, {lon})")
    except Exception as e:
        print(f"⚠️ Error al obtener ubicación por IP: {e}")

    # 2) Fallback geocodificando ciudad
    if lat is None or lon is None:
        try:
            geolocator = Nominatim(user_agent="bot_inmune_diario")
            loc = geolocator.geocode(ciudad, timeout=10)
            if not loc:
                raise RuntimeError(f"No se geocodificó {ciudad}")
            lat = loc.latitude
            lon = loc.longitude
            print(f"✅ Fallback geocodificado: {ciudad} ({lat}, {lon})")
        except Exception as e:
            print(f"❌ No se pudo geocodificar: {e}")
            # Último recurso: Málaga
            ciudad = "Málaga"
            lat, lon = 36.7213, -4.4214
            print(f"🔁 Usando ubicación por defecto: {ciudad} ({lat}, {lon})")

    # 3) Zona horaria
    try:
        tf = TimezoneFinder()
        tz_name = tf.timezone_at(lat=lat, lng=lon) or "Europe/Madrid"
    except Exception as e:
        print(f"⚠️ Error zona horaria: {e}")
        tz_name = "Europe/Madrid"

    print(f"✅ Ubicación final: {ciudad} ({lat}, {lon}) — TZ: {tz_name}")
    return {
        "latitud": float(lat),
        "longitud": float(lon),
        "ciudad": ciudad,
        "timezone": tz_name,
    }

# ---------------- Sol 30–40° (sin Astral) ----------------

def _declinacion_solar(dia_del_ano: int) -> float:
    # Aproximación clásica (grados)
    return 23.44 * math.sin(math.radians((360 / 365) * (dia_del_ano - 81)))

def _elevacion_solar(hora_decimal: float, decl: float, lat: float) -> float:
    # hora_decimal local (0–24). decl y lat en grados. Resultado en grados.
    H = (hora_decimal - 12.0) * 15.0  # ángulo horario (grados)
    lat_r = math.radians(lat)
    decl_r = math.radians(decl)
    H_r = math.radians(H)
    elev = math.degrees(math.asin(
        math.sin(lat_r) * math.sin(decl_r) +
        math.cos(lat_r) * math.cos(decl_r) * math.cos(H_r)
    ))
    return elev

def calcular_intervalos_optimos(lat: float, lon: float, fecha: datetime.date,
                                tz_name: str) -> tuple:
    """
    Devuelve (tramo_mañana, tramo_tarde) como tupla de (inicio, fin) datetime
    en hora local, donde elevación ∈ [30, 40]°. Paso 5 min.
    """
    tz = pytz.timezone(tz_name)
    base_local = tz.localize(datetime.datetime.combine(fecha, datetime.time(0, 0)))
    dia = fecha.timetuple().tm_yday
    decl = _declinacion_solar(dia)

    elevaciones = []
    paso = 5  # minutos
    for m in range(0, 24 * 60, paso):
        h_local = base_local + datetime.timedelta(minutes=m)
        hora_dec = h_local.hour + h_local.minute / 60.0
        elev = _elevacion_solar(hora_dec, decl, lat)
        elevaciones.append((h_local, elev))

    tramos = []
    en_tramo = False
    inicio = None
    for i, (t, e) in enumerate(elevaciones):
        if 30.0 <= e <= 40.0:
            if not en_tramo:
                en_tramo = True
                inicio = t
        else:
            if en_tramo:
                fin = elevaciones[i - 1][0]
                tramos.append((inicio, fin))
                en_tramo = False
    if en_tramo:
        tramos.append((inicio, elevaciones[-1][0]))

    mediodia_local = base_local.replace(hour=12, minute=0)
    tramo_m = next(((i, f) for i, f in tramos if f <= mediodia_local), None)
    tramo_t = next(((i, f) for i, f in tramos if i > mediodia_local), None)
    return tramo_m, tramo_t

def describir_intervalos(intervalos: tuple, ciudad: str) -> str:
    tramo_m, tramo_t = intervalos
    texto = f"☀️ Intervalos solares seguros para producir vit. D hoy en {ciudad}:"
    if tramo_m:
        im, fm = tramo_m
        texto += f"\n🌅 Mañana:\n🕒 {im.strftime('%H:%M')} - {fm.strftime('%H:%M')}"
    if tramo_t:
        it, ft = tramo_t
        texto += f"\n🌇 Tarde:\n🕒 {it.strftime('%H:%M')} - {ft.strftime('%H:%M')}"
    if not tramo_m and not tramo_t:
        texto += "\n(No hay elevación solar suficiente hoy para producir vitamina D)"
    return texto
