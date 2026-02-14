# ubicacion_y_sol.py
# Utilidades: sol (30–40º), mediodía solar y meteo (Open-Meteo).
# Sin Astral. Dependencias: requests, pytz, timezonefinder

from __future__ import annotations

import math
import datetime as dt
from typing import Optional, Tuple, List

import requests
import pytz
from timezonefinder import TimezoneFinder


# ----------------------------
# 1) Ubicación por IP (fallback del servidor)
# ----------------------------
def obtener_ubicacion_servidor_fallback() -> dict:
    """
    OJO: NO es la ubicación del usuario de Telegram.
    Solo fallback si no hay lat/lon guardados.
    """
    ciudad = None
    lat = None
    lon = None
    tzname = None

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
        ciudad = "Málaga"
        lat = 36.7213
        lon = -4.4214

    try:
        tf = TimezoneFinder()
        tzname = tf.timezone_at(lat=float(lat), lng=float(lon)) or "Europe/Madrid"
    except Exception:
        tzname = "Europe/Madrid"

    return {"latitud": float(lat), "longitud": float(lon), "ciudad": ciudad, "timezone": tzname}


# ----------------------------
# 2) Geocoding por ciudad (Open-Meteo)
# ----------------------------
def geocodificar_ciudad(ciudad: str) -> Optional[dict]:
    if not ciudad:
        return None
    try:
        url = (
            "https://geocoding-api.open-meteo.com/v1/search"
            f"?name={requests.utils.quote(ciudad)}&count=1&language=es&format=json"
        )
        r = requests.get(url, timeout=8)
        r.raise_for_status()
        data = r.json()
        results = data.get("results") or []
        if not results:
            return None
        it = results[0]
        lat = float(it["latitude"])
        lon = float(it["longitude"])
        tz = it.get("timezone") or "Europe/Madrid"
        name = it.get("name") or ciudad
        country = it.get("country")
        return {"latitud": lat, "longitud": lon, "ciudad": name, "timezone": tz, "country": country}
    except Exception:
        return None


# --------------------------------------------
# 3) Cálculo solar (elevación) sin Astral
# --------------------------------------------
def _declinacion_solar(n: int) -> float:
    return 23.44 * math.sin(math.radians((360.0 / 365.0) * (n - 81)))


def _equation_of_time_minutes(n: int) -> float:
    B = math.radians(360.0 * (n - 81) / 364.0)
    return 9.87 * math.sin(2 * B) - 7.53 * math.cos(B) - 1.5 * math.sin(B)


def _elevacion_solar_deg(lat_deg: float, decl_deg: float, hour_angle_deg: float) -> float:
    lat = math.radians(lat_deg)
    dec = math.radians(decl_deg)
    h = math.radians(hour_angle_deg)
    sin_alt = math.sin(lat) * math.sin(dec) + math.cos(lat) * math.cos(dec) * math.cos(h)
    return math.degrees(math.asin(max(-1.0, min(1.0, sin_alt))))


def _solar_hour_angle(local_dt: dt.datetime, lon: float, tzname: str, n: int) -> float:
    tz = pytz.timezone(tzname)
    noon = tz.localize(dt.datetime(local_dt.year, local_dt.month, local_dt.day, 12, 0))
    tz_hours = noon.utcoffset().total_seconds() / 3600.0

    eot = _equation_of_time_minutes(n)
    hora_decimal = local_dt.hour + local_dt.minute / 60.0 + local_dt.second / 3600.0

    L_std = 15.0 * tz_hours
    corr_min = eot + 4.0 * (lon - L_std)
    hora_solar = hora_decimal + corr_min / 60.0

    return 15.0 * (hora_solar - 12.0)


def _interp_time(t1: dt.datetime, e1: float, t2: dt.datetime, e2: float, target: float) -> dt.datetime:
    if e2 == e1:
        return t2
    frac = (target - e1) / (e2 - e1)
    frac = max(0.0, min(1.0, frac))
    return t1 + (t2 - t1) * frac


def calcular_intervalos_30_40(
    lat: float,
    lon: float,
    fecha: dt.date,
    tzname: str,
    paso_min: int = 1,
) -> Tuple[Optional[Tuple[dt.datetime, dt.datetime]], Optional[Tuple[dt.datetime, dt.datetime]]]:
    """
    Devuelve 2 tramos (mañana/tarde) donde elevación ∈ [30,40].
    Si un tramo cruza las 12:00, se parte.
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

    tramos: List[Tuple[dt.datetime, dt.datetime]] = []
    en = False
    ini: Optional[dt.datetime] = None

    for i in range(1, len(puntos)):
        t_prev, e_prev = puntos[i - 1]
        t, e = puntos[i]

        prev_in = in_band(e_prev)
        curr_in = in_band(e)

        if (not prev_in) and curr_in:
            # entrada: interpolar a 30 (normalmente)
            ini = _interp_time(t_prev, e_prev, t, e, 30.0)
            en = True

        elif prev_in and (not curr_in) and en and ini is not None:
            # salida: interpolar a 30 o 40 dependiendo por dónde sale
            target = 30.0 if e < 30.0 else 40.0
            fin = _interp_time(t_prev, e_prev, t, e, target)
            tramos.append((ini, fin))
            en = False
            ini = None

    if en and ini is not None:
        tramos.append((ini, puntos[-1][0]))

    mediodia = tz.localize(dt.datetime(fecha.year, fecha.month, fecha.day, 12, 0))

    tramo_m: Optional[Tuple[dt.datetime, dt.datetime]] = None
    tramo_t: Optional[Tuple[dt.datetime, dt.datetime]] = None

    for a, b in tramos:
        if a < mediodia < b:
            tramo_m = (a, mediodia)
            tramo_t = (mediodia, b)
        else:
            if b <= mediodia:
                if (tramo_m is None) or (b > tramo_m[1]):
                    tramo_m = (a, b)
            if a >= mediodia:
                if (tramo_t is None) or (a < tramo_t[0]):
                    tramo_t = (a, b)

    return tramo_m, tramo_t


def calcular_mediodia_solar(
    lat: float,
    lon: float,
    fecha: dt.date,
    tzname: str,
    paso_min: int = 1,
) -> Tuple[dt.datetime, float]:
    tz = pytz.timezone(tzname)
    n = fecha.timetuple().tm_yday
    decl = _declinacion_solar(n)
    base = tz.localize(dt.datetime(fecha.year, fecha.month, fecha.day, 0, 0))

    best_t = base
    best_e = -999.0

    for m in range(0, 24 * 60, paso_min):
        t = base + dt.timedelta(minutes=m)
        h_angle = _solar_hour_angle(t, lon, tzname, n)
        elev = _elevacion_solar_deg(lat, decl, h_angle)
        if elev > best_e:
            best_e = elev
            best_t = t

    return best_t, float(best_e)


# ---------------------------------------
# 4) Texto: intervalos + mediodía solar
# ---------------------------------------
def describir_intervalos_30_40(
    intervalos: Tuple[
        Optional[Tuple[dt.datetime, dt.datetime]],
        Optional[Tuple[dt.datetime, dt.datetime]],
    ],
    ciudad: str,
) -> str:
    maniana, tarde = intervalos
    texto = f"🌤 Ventanas 30–40° en {ciudad}:"
    if maniana:
        a, b = maniana
        texto += f"\n🌅 Mañana: {a.strftime('%H:%M')}–{b.strftime('%H:%M')}"
    if tarde:
        a, b = tarde
        texto += f"\n🌇 Tarde: {a.strftime('%H:%M')}–{b.strftime('%H:%M')}"
    if not maniana and not tarde:
        texto += "\n(No hay elevación suficiente hoy para 30°)"
    return texto


def describir_intervalos_y_mediodia(
    lat: float,
    lon: float,
    fecha: dt.date,
    tzname: str,
    ciudad: str,
) -> str:
    tramos = calcular_intervalos_30_40(lat, lon, fecha, tzname)
    txt = describir_intervalos_30_40(tramos, ciudad)
    t_noon, elev_max = calcular_mediodia_solar(lat, lon, fecha, tzname)
    txt += f"\n\n🧭 Mediodía solar: {t_noon.strftime('%H:%M')} (altura máx ≈ {elev_max:.1f}°)"
    return txt


# ------------------------------------------------
# 5) Pronóstico meteo horario vía Open-Meteo
# ------------------------------------------------
def obtener_pronostico_diario(
    fecha: dt.date,
    lat: float,
    lon: float,
    tzname: str,
) -> Optional[dict]:
    try:
        url = (
            "https://api.open-meteo.com/v1/forecast"
            f"?latitude={lat:.4f}&longitude={lon:.4f}"
            "&hourly=cloudcover,precipitation_probability"
            f"&start_date={fecha.isoformat()}&end_date={fecha.isoformat()}"
            f"&timezone={tzname}"
        )
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        data = r.json()
        return data.get("hourly")
    except Exception:
        return None


def _parse_hourly_time(iso: str, tzname: str) -> Optional[dt.datetime]:
    # Open-Meteo a veces devuelve naive local (sin offset).
    try:
        t = dt.datetime.fromisoformat(iso)
    except Exception:
        try:
            t = dt.datetime.strptime(iso, "%Y-%m-%dT%H:%M")
        except Exception:
            return None

    if t.tzinfo is None:
        try:
            tz = pytz.timezone(tzname)
            t = tz.localize(t)
        except Exception:
            pass
    return t


def _avg_in_range(
    times_iso: List[str],
    values: List[Optional[float]],
    inicio: dt.datetime,
    fin: dt.datetime,
    tzname: str,
) -> Optional[int]:
    if not times_iso or not values:
        return None
    sel: List[float] = []
    for iso, val in zip(times_iso, values):
        if val is None:
            continue
        t = _parse_hourly_time(iso, tzname)
        if t is None:
            continue
        # inicio/fin son aware; t ahora también
        if inicio <= t <= fin:
            sel.append(float(val))
    if not sel:
        return None
    return int(round(sum(sel) / len(sel)))


def resumen_meteo_en_intervalos(
    intervalos: Tuple[
        Optional[Tuple[dt.datetime, dt.datetime]],
        Optional[Tuple[dt.datetime, dt.datetime]],
    ],
    hourly: Optional[dict],
    tzname: str,
) -> Tuple[Optional[int], Optional[int]]:
    if not hourly:
        return None, None

    times = hourly.get("time") or []
    clouds = hourly.get("cloudcover") or []
    pprec = hourly.get("precipitation_probability") or []

    partes = []
    for tramo in intervalos:
        if not tramo:
            continue
        a, b = tramo
        c = _avg_in_range(times, clouds, a, b, tzname)
        p = _avg_in_range(times, pprec, a, b, tzname)
        if c is not None or p is not None:
            partes.append((c, p))

    if not partes:
        return None, None

    c_vals = [x for x, _ in partes if x is not None]
    p_vals = [y for _, y in partes if y is not None]

    c_avg = int(round(sum(c_vals) / len(c_vals))) if c_vals else None
    p_avg = int(round(sum(p_vals) / len(p_vals))) if p_vals else None
    return c_avg, p_avg


def formatear_meteo_en_tramos(
    intervalos: Tuple[
        Optional[Tuple[dt.datetime, dt.datetime]],
        Optional[Tuple[dt.datetime, dt.datetime]],
    ],
    hourly: Optional[dict],
    tzname: str,
) -> str:
    c, p = resumen_meteo_en_intervalos(intervalos, hourly, tzname)
    if c is None and p is None:
        return ""
    parts = []
    if c is not None:
        parts.append(f"☁️ Nubosidad media en ventanas: {c}%")
    if p is not None:
        parts.append(f"🌧 Prob. lluvia media en ventanas: {p}%")
    return "\n" + "\n".join(parts)
