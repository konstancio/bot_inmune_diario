# ubicacion_y_sol.py
# Utilidades: intervalos solares 30–40°, mediodía solar, altura máxima y meteo (Open-Meteo).
# Sin Astral. Enfocado a uso en Railway.
from __future__ import annotations

import math
import datetime as dt
from typing import Optional, Tuple, List

import requests
import pytz
from timezonefinder import TimezoneFinder


# ----------------------------
# 1) Ubicación con fallback
# ----------------------------
def obtener_ubicacion() -> dict:
    """
    Intenta IP -> ipapi.co; si falla, cae a Málaga.
    Devuelve: {"latitud","longitud","ciudad","timezone"}
    OJO: en Railway esto suele dar ubicación del datacenter (no del usuario).
    Por eso, en multiusuario debes usar lat/lon guardadas por usuario (DB).
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
        ciudad = "Málaga"
        lat = 36.7213
        lon = -4.4214

    tzname = "Europe/Madrid"
    try:
        tf = TimezoneFinder()
        tzname = tf.timezone_at(lat=float(lat), lng=float(lon)) or "Europe/Madrid"
    except Exception:
        tzname = "Europe/Madrid"

    return {
        "latitud": float(lat),
        "longitud": float(lon),
        "ciudad": ciudad,
        "timezone": tzname,
    }


# --------------------------------------------
# 2) Cálculo solar (aprox. Cooper + EoT)
# --------------------------------------------
def _declinacion_solar(n: int) -> float:
    """Declinación aprox (Cooper). n: día del año (1..366). Devuelve grados."""
    return 23.44 * math.sin(math.radians((360.0 / 365.0) * (n - 81)))


def _equation_of_time_minutes(n: int) -> float:
    """Ecuación del tiempo (minutos). Aproximación clásica."""
    B = math.radians(360.0 * (n - 81) / 364.0)
    return 9.87 * math.sin(2 * B) - 7.53 * math.cos(B) - 1.5 * math.sin(B)


def _elevacion_solar_deg(lat_deg: float, decl_deg: float, hour_angle_deg: float) -> float:
    """Elevación (grados) desde latitud, declinación y ángulo horario."""
    lat = math.radians(lat_deg)
    dec = math.radians(decl_deg)
    h = math.radians(hour_angle_deg)
    sin_alt = math.sin(lat) * math.sin(dec) + math.cos(lat) * math.cos(dec) * math.cos(h)
    return math.degrees(math.asin(max(-1.0, min(1.0, sin_alt))))


def _solar_hour_angle(local_dt: dt.datetime, lon: float, tzname: str, n: int) -> float:
    """
    Ángulo horario (grados) aplicando EoT y corrección por longitud.
    local_dt debe ser aware en tz local.
    """
    tz = pytz.timezone(tzname)

    # offset horario real del día (incluye DST)
    noon_local = tz.localize(dt.datetime(local_dt.year, local_dt.month, local_dt.day, 12, 0))
    tz_hours = noon_local.utcoffset().total_seconds() / 3600.0

    eot = _equation_of_time_minutes(n)  # min
    hora_decimal = local_dt.hour + local_dt.minute / 60.0 + local_dt.second / 3600.0

    # longitud estándar del huso
    L_std = 15.0 * tz_hours  # grados

    # corrección en minutos
    corr_min = eot + 4.0 * (lon - L_std)

    hora_solar = hora_decimal + corr_min / 60.0
    return 15.0 * (hora_solar - 12.0)


def calcular_intervalos_optimos(
    lat: float,
    lon: float,
    fecha: dt.date,
    tzname: str,
    paso_min: int = 1,
) -> Tuple[Optional[Tuple[dt.datetime, dt.datetime]], Optional[Tuple[dt.datetime, dt.datetime]]]:
    """
    Devuelve dos tramos (mañana/tarde) donde la elevación solar está entre 30° y 40° (incl.).
    Se recorre el día a paso_min e interpola entradas/salidas para no perder ventanas cortas.
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

    def interp_time(t1: dt.datetime, e1: float, t2: dt.datetime, e2: float, target: float) -> dt.datetime:
        try:
            if e2 == e1:
                return t2
            frac = (target - e1) / (e2 - e1)
            frac = max(0.0, min(1.0, frac))
            return t1 + (t2 - t1) * frac
        except Exception:
            return t2

    tramos: List[Tuple[dt.datetime, dt.datetime]] = []
    en = False
    ini: Optional[dt.datetime] = None

    for i in range(1, len(puntos)):
        t_prev, e_prev = puntos[i - 1]
        t, e = puntos[i]
        prev_in = in_band(e_prev)
        curr_in = in_band(e)

        if (not prev_in) and curr_in:
            target = 30.0 if e_prev < 30.0 else 40.0
            ini = interp_time(t_prev, e_prev, t, e, target)
            en = True

        elif prev_in and (not curr_in) and en and ini is not None:
            target = 30.0 if e < 30.0 else 40.0
            fin = interp_time(t_prev, e_prev, t, e, target)
            tramos.append((ini, fin))
            en = False
            ini = None

    if en and ini is not None:
        tramos.append((ini, puntos[-1][0]))

    mediodia = tz.localize(dt.datetime(fecha.year, fecha.month, fecha.day, 12, 0))
    tramo_m = next(((a, b) for a, b in tramos if b <= mediodia), None)
    tramo_t = next(((a, b) for a, b in tramos if a > mediodia), None)

    return tramo_m, tramo_t


def describir_intervalos(
    intervalos: Tuple[
        Optional[Tuple[dt.datetime, dt.datetime]],
        Optional[Tuple[dt.datetime, dt.datetime]],
    ],
    ciudad: str,
) -> str:
    maniana, tarde = intervalos
    texto = f"☀️ Ventanas 30–40° en {ciudad}:"
    if maniana:
        a, b = maniana
        texto += f"\n🌅 Mañana: {a.strftime('%H:%M')}–{b.strftime('%H:%M')}"
    if tarde:
        a, b = tarde
        texto += f"\n🌇 Tarde: {a.strftime('%H:%M')}–{b.strftime('%H:%M')}"
    if not maniana and not tarde:
        texto += "\n(No hay elevación suficiente hoy para 30°)"
    return texto


def mediodia_solar_y_altura_max(
    lat: float,
    lon: float,
    fecha: dt.date,
    tzname: str,
) -> Tuple[dt.datetime, float]:
    """
    Devuelve (hora_local_mediodia_solar_aprox, elevacion_max_aprox_en_grados)
    Calculado buscando el minuto con mayor elevación entre 10:00 y 14:00 local.
    """
    tz = pytz.timezone(tzname)
    n = fecha.timetuple().tm_yday
    decl = _declinacion_solar(n)

    base = tz.localize(dt.datetime(fecha.year, fecha.month, fecha.day, 10, 0))
    best_t = base
    best_e = -999.0

    for m in range(0, 4 * 60):
        t = base + dt.timedelta(minutes=m)
        h = _solar_hour_angle(t, lon, tzname, n)
        e = _elevacion_solar_deg(lat, decl, h)
        if e > best_e:
            best_e = e
            best_t = t

    return best_t, float(best_e)


# ------------------------------------------------
# 3) Pronóstico meteo diario vía Open-Meteo (free)
# ------------------------------------------------
def obtener_pronostico_diario(
    fecha: dt.date,
    lat: float,
    lon: float,
    tzname: str,
) -> Optional[dict]:
    """
    Devuelve hourly dict con arrays: time, cloudcover, precipitation_probability
    en la TZ solicitada.
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


def _avg_in_range(
    times_iso: List[str],
    values: List[Optional[float]],
    inicio: dt.datetime,
    fin: dt.datetime,
) -> Optional[int]:
    if not times_iso or not values:
        return None
    sel: List[float] = []
    for iso, val in zip(times_iso, values):
        if val is None:
            continue
        try:
            t = dt.datetime.fromisoformat(iso)
        except Exception:
            try:
                t = dt.datetime.strptime(iso, "%Y-%m-%dT%H:%M")
            except Exception:
                continue
        if inicio <= t <= fin:
            sel.append(float(val))
    if not sel:
        return None
    return int(round(sum(sel) / len(sel)))


def formatear_intervalos_meteo(
    intervalos: Tuple[
        Optional[Tuple[dt.datetime, dt.datetime]],
        Optional[Tuple[dt.datetime, dt.datetime]],
    ],
    hourly: Optional[dict],
) -> str:
    if not hourly:
        return ""

    times = hourly.get("time") or []
    clouds = hourly.get("cloudcover") or []
    pprec = hourly.get("precipitation_probability") or []

    maniana, tarde = intervalos

    def etiqueta(c: Optional[int], p: Optional[int]) -> str:
        if c is None and p is None:
            return ""
        icon = "☀️"
        if c is not None:
            if c >= 80:
                icon = "☁️"
            elif c >= 40:
                icon = "⛅️"
        estado = "despejado" if (c is not None and c < 30) else ("nuboso" if c is not None and c >= 70 else "parcial")
        ctxt = f"nubes {c}%" if c is not None else "nubes —"
        ptxt = f"lluvia {p}%" if p is not None else "lluvia —"
        return f"{icon} {estado}, {ctxt}, {ptxt}"

    lineas: List[str] = []
    if maniana:
        a, b = maniana
        c = _avg_in_range(times, clouds, a, b)
        p = _avg_in_range(times, pprec, a, b)
        lineas.append(f"   🌅 Meteo (mañana): {etiqueta(c, p)}")
    if tarde:
        a, b = tarde
        c = _avg_in_range(times, clouds, a, b)
        p = _avg_in_range(times, pprec, a, b)
        lineas.append(f"   🌇 Meteo (tarde): {etiqueta(c, p)}")

    return ("\n" + "\n".join(lineas)) if lineas else ""
