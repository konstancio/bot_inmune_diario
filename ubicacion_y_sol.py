# ubicacion_y_sol.py
# Utilidades de ubicación, sol (30–40º), mediodía solar y meteo
# Sin dependencias astronómicas pesadas (no Astral)

from __future__ import annotations

import math
import datetime as dt
from typing import Optional, Tuple, List

import requests
import pytz
from timezonefinder import TimezoneFinder


# =====================================================
# 1) UBICACIÓN (IP → fallback Málaga)
# =====================================================

def obtener_ubicacion() -> dict:
    """
    Intenta IP -> ipapi.co; si falla, cae a Málaga.
    Devuelve:
      {
        "latitud": float,
        "longitud": float,
        "ciudad": str,
        "timezone": str
      }
    """
    ciudad = None
    lat = None
    lon = None

    try:
        ip = requests.get("https://api.ipify.org", timeout=4).text.strip()
        r = requests.get(f"https://ipapi.co/{ip}/json/", timeout=6)
        r.raise_for_status()
        data = r.json()

        ciudad = data.get("city")
        lat = data.get("latitude")
        lon = data.get("longitude")

        if not (ciudad and isinstance(lat, (int, float)) and isinstance(lon, (int, float))):
            raise ValueError("Datos IP incompletos")

    except Exception:
        # Fallback fijo Málaga
        ciudad = "Málaga"
        lat = 36.7213
        lon = -4.4214

    try:
        tf = TimezoneFinder()
        tzname = tf.timezone_at(lat=lat, lng=lon) or "Europe/Madrid"
    except Exception:
        tzname = "Europe/Madrid"

    return {
        "latitud": float(lat),
        "longitud": float(lon),
        "ciudad": ciudad,
        "timezone": tzname,
    }


# =====================================================
# 2) ASTRONOMÍA SOLAR BÁSICA
# =====================================================

def _declinacion_solar(n: int) -> float:
    """Declinación solar aproximada (Cooper). Devuelve grados."""
    return 23.44 * math.sin(math.radians((360.0 / 365.0) * (n - 81)))


def _equation_of_time_minutes(n: int) -> float:
    """Ecuación del tiempo (minutos)."""
    B = math.radians(360.0 * (n - 81) / 364.0)
    return 9.87 * math.sin(2 * B) - 7.53 * math.cos(B) - 1.5 * math.sin(B)


def _elevacion_solar_deg(lat_deg: float, decl_deg: float, hour_angle_deg: float) -> float:
    lat = math.radians(lat_deg)
    dec = math.radians(decl_deg)
    h = math.radians(hour_angle_deg)
    sin_alt = math.sin(lat) * math.sin(dec) + math.cos(lat) * math.cos(dec) * math.cos(h)
    return math.degrees(math.asin(max(-1.0, min(1.0, sin_alt))))


def _solar_hour_angle(local_dt: dt.datetime, lon: float, tzname: str, n: int) -> float:
    """
    Ángulo horario solar (grados) usando EoT y longitud.
    local_dt debe ser aware en hora local.
    """
    tz = pytz.timezone(tzname)
    noon = tz.localize(dt.datetime(local_dt.year, local_dt.month, local_dt.day, 12, 0))
    tz_hours = noon.utcoffset().total_seconds() / 3600.0

    eot = _equation_of_time_minutes(n)

    hora_decimal = (
        local_dt.hour +
        local_dt.minute / 60.0 +
        local_dt.second / 3600.0
    )

    L_std = 15.0 * tz_hours
    corr_min = eot + 4.0 * (lon - L_std)
    hora_solar = hora_decimal + corr_min / 60.0

    return 15.0 * (hora_solar - 12.0)


# =====================================================
# 3) MEDIODÍA SOLAR REAL
# =====================================================

def calcular_mediodia_solar(
    fecha: dt.date,
    lon: float,
    tzname: str,
) -> dt.datetime:
    """
    Devuelve el instante de mediodía solar real (máxima elevación).
    """
    tz = pytz.timezone(tzname)
    n = fecha.timetuple().tm_yday
    eot = _equation_of_time_minutes(n)

    noon = tz.localize(dt.datetime(fecha.year, fecha.month, fecha.day, 12, 0))
    tz_hours = noon.utcoffset().total_seconds() / 3600.0
    L_std = 15.0 * tz_hours

    corr_min = eot + 4.0 * (lon - L_std)
    solar_noon = noon + dt.timedelta(minutes=corr_min)

    return solar_noon


# =====================================================
# 4) INTERVALOS 30–40° (INCLUSIVO)
# =====================================================

def calcular_intervalos_optimos(
    lat: float,
    lon: float,
    fecha: dt.date,
    tzname: str,
    paso_min: int = 1,
) -> Tuple[
    Optional[Tuple[dt.datetime, dt.datetime]],
    Optional[Tuple[dt.datetime, dt.datetime]],
]:
    """
    Devuelve (tramo_mañana, tramo_tarde) donde la elevación solar
    está entre 30° y 40° (ambos incluidos).
    """
    tz = pytz.timezone(tzname)
    n = fecha.timetuple().tm_yday
    decl = _declinacion_solar(n)

    base = tz.localize(dt.datetime(fecha.year, fecha.month, fecha.day, 0, 0))
    puntos: List[Tuple[dt.datetime, float]] = []

    for m in range(0, 24 * 60, paso_min):
        t = base + dt.timedelta(minutes=m)
        h_angle = _solar_hour_angle(t, lon, tzname, n)
        elev = _elevacion_solar_deg(lat, decl, h_angle)
        puntos.append((t, elev))

    def in_band(e: float) -> bool:
        return 30.0 <= e <= 40.0

    def interp_time(t1, e1, t2, e2, target):
        if e2 == e1:
            return t2
        frac = (target - e1) / (e2 - e1)
        frac = max(0.0, min(1.0, frac))
        return t1 + (t2 - t1) * frac

    tramos: List[Tuple[dt.datetime, dt.datetime]] = []
    en = False
    ini = None

    for i in range(1, len(puntos)):
        t_prev, e_prev = puntos[i - 1]
        t, e = puntos[i]

        prev_in = in_band(e_prev)
        curr_in = in_band(e)

        if not prev_in and curr_in:
            target = 30.0 if e_prev < 30.0 else 40.0
            ini = interp_time(t_prev, e_prev, t, e, target)
            en = True

        elif prev_in and not curr_in and en and ini:
            target = 30.0 if e < 30.0 else 40.0
            fin = interp_time(t_prev, e_prev, t, e, target)
            tramos.append((ini, fin))
            en = False
            ini = None

    if en and ini:
        tramos.append((ini, puntos[-1][0]))

    mediodia = calcular_mediodia_solar(fecha, lon, tzname)

    tramo_m = next(((a, b) for a, b in tramos if b <= mediodia), None)
    tramo_t = next(((a, b) for a, b in tramos if a > mediodia), None)

    return tramo_m, tramo_t


# =====================================================
# 5) METEO (OPEN-METEO)
# =====================================================

def obtener_pronostico_diario(
    fecha: dt.date,
    lat: float,
    lon: float,
    tzname: str,
) -> Optional[dict]:
    """
    Devuelve hourly cloudcover y precipitation_probability.
    """
    try:
        url = (
            "https://api.open-meteo.com/v1/forecast"
            f"?latitude={lat:.4f}&longitude={lon:.4f}"
            "&hourly=cloudcover,precipitation_probability"
            f"&start_date={fecha.isoformat()}&end_date={fecha.isoformat()}"
            f"&timezone={tzname}"
        )
        r = requests.get(url, timeout=8)
        r.raise_for_status()
        data = r.json()
        return data.get("hourly")
    except Exception:
        return None
