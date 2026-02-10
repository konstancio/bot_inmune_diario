# ubicacion_y_sol.py
# Utilidades de ubicación, sol (30–40º) y meteo sin dependencias pesadas.

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
        # Fallback Málaga
        ciudad = "Málaga"
        lat = 36.7213
        lon = -4.4214

    # Zona horaria por coordenadas
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
# 2) Cálculo solar (30–40°) sin Astral
# --------------------------------------------
def _declinacion_solar(n: int) -> float:
    """Declinación aprox (Cooper). n: día del año (1..366). Devuelve grados."""
    return 23.44 * math.sin(math.radians((360.0 / 365.0) * (n - 81)))


def _equation_of_time_minutes(n: int) -> float:
    """Ecuación del tiempo (minutos). Aproximación clásica (Spencer/Cooper)."""
    B = math.radians(360.0 * (n - 81) / 364.0)
    return 9.87 * math.sin(2 * B) - 7.53 * math.cos(B) - 1.5 * math.sin(B)


def _elevacion_solar_deg(lat_deg: float, decl_deg: float, hour_angle_deg: float) -> float:
    """Elevación (grados) a partir de latitud, declinación y ángulo horario (grados)."""
    lat = math.radians(lat_deg)
    dec = math.radians(decl_deg)
    h = math.radians(hour_angle_deg)
    sin_alt = math.sin(lat) * math.sin(dec) + math.cos(lat) * math.cos(dec) * math.cos(h)
    return math.degrees(math.asin(max(-1.0, min(1.0, sin_alt))))


def _tz_hours_for_date(fecha: dt.date, tzname: str) -> float:
    """Offset del huso horario (incluye DST) en esa fecha, en horas."""
    tz = pytz.timezone(tzname)
    noon = tz.localize(dt.datetime(fecha.year, fecha.month, fecha.day, 12, 0))
    return noon.utcoffset().total_seconds() / 3600.0


def _solar_noon_local_dt(fecha: dt.date, lon: float, tzname: str) -> dt.datetime:
    """
    Mediodía solar (hora civil local) = instante en que el ángulo horario es 0 (hora solar = 12).
    Derivación:
      hora_solar = hora_local + corr_min/60
      12 = hora_local + corr_min/60  =>  hora_local = 12 - corr_min/60
    donde:
      corr_min = EoT + 4*(lon - L_std)
      L_std = 15*tz_hours
    """
    n = fecha.timetuple().tm_yday
    eot = _equation_of_time_minutes(n)
    tz_hours = _tz_hours_for_date(fecha, tzname)
    L_std = 15.0 * tz_hours  # grados

    corr_min = eot + 4.0 * (lon - L_std)
    solar_noon_hour = 12.0 - (corr_min / 60.0)  # horas decimales en hora local

    # Normalizar por si cae fuera [0,24)
    while solar_noon_hour < 0:
        solar_noon_hour += 24
    while solar_noon_hour >= 24:
        solar_noon_hour -= 24

    hh = int(solar_noon_hour)
    mm = int(round((solar_noon_hour - hh) * 60.0))
    if mm == 60:
        hh = (hh + 1) % 24
        mm = 0

    tz = pytz.timezone(tzname)
    return tz.localize(dt.datetime(fecha.year, fecha.month, fecha.day, hh, mm, 0))


def obtener_mediodia_solar_y_altura_max(
    lat: float,
    lon: float,
    fecha: dt.date,
    tzname: str,
) -> Tuple[dt.datetime, float]:
    """
    Devuelve:
      - mediodía solar (datetime aware, TZ local)
      - altura máxima aproximada del Sol ese día (grados), evaluada en H=0
    """
    n = fecha.timetuple().tm_yday
    decl = _declinacion_solar(n)
    noon_dt = _solar_noon_local_dt(fecha, lon, tzname)
    alt_max = _elevacion_solar_deg(lat, decl, 0.0)  # H=0 en mediodía solar
    return noon_dt, float(alt_max)


def _solar_hour_angle(local_dt: dt.datetime, lon: float, tzname: str, n: int) -> float:
    """
    Ángulo horario (grados) aplicando EoT y corrección por longitud.
    local_dt debe estar en TZ local (aware).
    """
    tz_hours = _tz_hours_for_date(local_dt.date(), tzname)
    eot = _equation_of_time_minutes(n)  # min

    hora_decimal = local_dt.hour + local_dt.minute / 60.0 + local_dt.second / 3600.0
    L_std = 15.0 * tz_hours  # grados

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
    Devuelve dos tramos (mañana/tarde) con elevación entre 30 y 40 (incl).
    - Usa mediodía SOLAR real para separar mañana/tarde
    - Si un tramo cruza el mediodía solar, lo parte en dos.
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

    # Separar usando mediodía solar REAL
    mediodia_solar, _alt_max = obtener_mediodia_solar_y_altura_max(lat, lon, fecha, tzname)

    tramos_maniana: List[Tuple[dt.datetime, dt.datetime]] = []
    tramos_tarde: List[Tuple[dt.datetime, dt.datetime]] = []

    for a, b in tramos:
        if b <= mediodia_solar:
            tramos_maniana.append((a, b))
        elif a >= mediodia_solar:
            tramos_tarde.append((a, b))
        else:
            # Cruza mediodía solar -> partir
            tramos_maniana.append((a, mediodia_solar))
            tramos_tarde.append((mediodia_solar, b))

    tramo_m = tramos_maniana[0] if tramos_maniana else None
    tramo_t = tramos_tarde[0] if tramos_tarde else None

    return tramo_m, tramo_t


# ---------------------------------------
# 3) Texto (intervalos + mediodía solar)
# ---------------------------------------
def describir_intervalos_con_mediodia(
    intervalos: Tuple[
        Optional[Tuple[dt.datetime, dt.datetime]],
        Optional[Tuple[dt.datetime, dt.datetime]],
    ],
    ciudad: str,
    mediodia_solar: dt.datetime,
    alt_max: float,
) -> str:
    maniana, tarde = intervalos
    texto = f"🌞 Ventanas 30–40° en {ciudad}:"
    if maniana:
        a, b = maniana
        texto += f"\n🌅 Mañana: {a.strftime('%H:%M')}–{b.strftime('%H:%M')}"
    if tarde:
        a, b = tarde
        texto += f"\n🌇 Tarde: {a.strftime('%H:%M')}–{b.strftime('%H:%M')}"
    if not maniana and not tarde:
        texto += "\n(No hay elevación solar suficiente hoy para pasar de 30°)"

    texto += f"\n🧭 Mediodía solar: {mediodia_solar.strftime('%H:%M')} (altura máxima ≈ {alt_max:.1f}°)"
    return texto


# ------------------------------------------------
# 4) Pronóstico meteo diario vía Open-Meteo (free)
# ------------------------------------------------
def obtener_pronostico_diario(
    fecha: dt.date,
    lat: float,
    lon: float,
    tzname: str,
) -> Optional[dict]:
    """
    Pide a Open-Meteo nubes (%) y prob. precipitación (%) por hora del día.
    Devuelve dict con arrays 'time','cloudcover','precipitation_probability'
    en la zona horaria solicitada. Si falla, None.
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
        if "hourly" not in data:
            return None
        return data["hourly"]
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
    """
    Devuelve un texto con meteo para cada tramo.
    Usa cobertura nubosa media y prob. precipitación.
    """
    maniana, tarde = intervalos
    if not hourly:
        return ""

    times = hourly.get("time") or []
    clouds = hourly.get("cloudcover") or []
    pprec = hourly.get("precipitation_probability") or []

    def etiqueta(c: Optional[int], p: Optional[int]) -> str:
        if c is None and p is None:
            return ""
        icon = "☀️"
        if c is not None:
            if c >= 80:
                icon = "☁️"
            elif c >= 40:
                icon = "⛅️"
        ctxt = f"nubes {c}%" if c is not None else "nubes —"
        ptxt = f"lluvia {p}%" if p is not None else "lluvia —"
        estado = "despejado" if (c is not None and c < 30) else ("nuboso" if c and c >= 70 else "parcial")
        return f"({icon} {estado}, {ctxt}, {ptxt})"

    texto = ""
    if maniana:
        a, b = maniana
        c_m = _avg_in_range(times, clouds, a, b)
        p_m = _avg_in_range(times, pprec, a, b)
        texto += f"\n   🌅 {etiqueta(c_m, p_m)}"
    if tarde:
        a, b = tarde
        c_t = _avg_in_range(times, clouds, a, b)
        p_t = _avg_in_range(times, pprec, a, b)
        texto += f"\n   🌇 {etiqueta(c_t, p_t)}"

    return texto
