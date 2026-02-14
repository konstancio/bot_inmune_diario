# ubicacion_y_sol.py
# Utilidades de ubicación, sol (30–40º), mediodía solar y meteo (Open-Meteo).
# Sin Astral. Sin dependencias pesadas.

from __future__ import annotations

import math
import datetime as dt
from typing import Optional, Tuple, List, Dict, Any

import requests
import pytz
from timezonefinder import TimezoneFinder


# ----------------------------
# 1) Ubicación por IP (solo fallback del servidor)
# ----------------------------
def obtener_ubicacion_servidor_fallback() -> dict:
    """
    OJO: esto NO es la ubicación del usuario de Telegram.
    Es solo un fallback (por si no hay lat/lon del usuario).
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
# 2) Geocoding ligero por ciudad (Open-Meteo)
# ----------------------------
def geocodificar_ciudad(ciudad: str) -> Optional[dict]:
    """
    Geocodifica una ciudad por Open-Meteo Geocoding API.
    Devuelve dict: {latitud,longitud,ciudad,timezone,country} o None
    """
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
    tz_hours = noon.utcoffset().total_seconds() / 3600.0  # cambia con DST

    eot = _equation_of_time_minutes(n)  # min
    hora_decimal = local_dt.hour + local_dt.minute / 60.0 + local_dt.second / 3600.0

    L_std = 15.0 * tz_hours  # grados
    corr_min = eot + 4.0 * (lon - L_std)
    hora_solar = hora_decimal + corr_min / 60.0

    return 15.0 * (hora_solar - 12.0)

def _interp_time(t1: dt.datetime, e1: float, t2: dt.datetime, e2: float, target: float) -> dt.datetime:
    try:
        if e2 == e1:
            return t2
        frac = (target - e1) / (e2 - e1)
        frac = max(0.0, min(1.0, frac))
        return t1 + (t2 - t1) * frac
    except Exception:
        return t2


def calcular_intervalos_30_40(
    lat: float,
    lon: float,
    fecha: dt.date,
    tzname: str,
    paso_min: int = 1,
) -> List[Tuple[dt.datetime, dt.datetime]]:
    """
    Devuelve lista de tramos donde elevación ∈ [30,40], en hora local tz-aware.
    (Lista, no (mañana,tarde), para que el caller pueda formatear bonito.)
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
            target = 30.0 if e_prev < 30.0 else 40.0
            ini = _interp_time(t_prev, e_prev, t, e, target)
            en = True

        elif prev_in and (not curr_in) and en and ini is not None:
            target = 30.0 if e < 30.0 else 40.0
            fin = _interp_time(t_prev, e_prev, t, e, target)
            tramos.append((ini, fin))
            en = False
            ini = None

    if en and ini is not None:
        tramos.append((ini, puntos[-1][0]))

    return tramos


def calcular_mediodia_solar(
    lat: float,
    lon: float,
    fecha: dt.date,
    tzname: str,
    paso_min: int = 1,
) -> Tuple[dt.datetime, float]:
    """
    Estima el mediodía solar como el instante de máxima elevación del día.
    Devuelve: (datetime_local tz-aware, elev_max_deg)
    """
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
# 4) Texto solar (ventanas + mediodía solar)
# ---------------------------------------
def describir_intervalos_y_mediodia(
    lat: float,
    lon: float,
    fecha: dt.date,
    tzname: str,
    ciudad: str,
) -> str:
    """
    Devuelve texto con:
    - tramos 30–40° (mañana/tarde si aplica)
    - mediodía solar (hora)
    - altura máxima del día (°)
    """
    tz = pytz.timezone(tzname)
    tramos = calcular_intervalos_30_40(lat, lon, fecha, tzname, paso_min=1)
    noon_dt, elev_max = calcular_mediodia_solar(lat, lon, fecha, tzname, paso_min=1)

    lines = [f"🌤 Ventanas 30–40° en {ciudad}:"]

    if not tramos:
        # Si no hay tramos, puede ser porque max < 30 (latitud/estación)
        if elev_max < 30.0:
            lines.append("(Hoy el Sol no llega a 30° sobre el horizonte)")
        else:
            lines.append("(Hoy no hay tramo continuo dentro de 30–40°)")
    else:
        # etiquetamos mañana/tarde respecto a mediodía solar real
        manana_parts = []
        tarde_parts = []
        for a, b in tramos:
            if b <= noon_dt:
                manana_parts.append((a, b))
            elif a >= noon_dt:
                tarde_parts.append((a, b))
            else:
                manana_parts.append((a, noon_dt))
                tarde_parts.append((noon_dt, b))

        def fmt(parts):
            return ", ".join([f"{x.strftime('%H:%M')}–{y.strftime('%H:%M')}" for x, y in parts])

        if manana_parts:
            lines.append(f"🌅 Mañana: {fmt(manana_parts)}")
        if tarde_parts:
            lines.append(f"🌇 Tarde: {fmt(tarde_parts)}")

    lines.append(f"🧭 Mediodía solar: {noon_dt.strftime('%H:%M')} (altura máx ≈ {elev_max:.1f}°)")
    return "\n".join(lines)


# ------------------------------------------------
# 5) Pronóstico meteo horario vía Open-Meteo
# ------------------------------------------------
def obtener_pronostico_diario(
    fecha: dt.date,
    lat: float,
    lon: float,
    tzname: str,
) -> Optional[dict]:
    """
    Devuelve dict hourly con arrays:
      'time','cloudcover','precipitation_probability'
    """
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


def _avg_in_range(
    times_iso: List[str],
    values: List[Optional[float]],
    inicio: dt.datetime,
    fin: dt.datetime,
) -> Optional[int]:
    """
    Media simple (redondeada) en [inicio, fin] evitando naive/aware mismatch.
    """
    if not times_iso or not values:
        return None

    tzinfo = inicio.tzinfo
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

        # Open-Meteo suele venir naive local: le ponemos la tz del intervalo
        if t.tzinfo is None and tzinfo is not None:
            t = t.replace(tzinfo=tzinfo)

        if inicio <= t <= fin:
            sel.append(float(val))

    if not sel:
        return None
    return int(round(sum(sel) / len(sel)))


def formatear_meteo_en_tramos(
    tramos: List[Tuple[dt.datetime, dt.datetime]],
    hourly: Optional[dict],
) -> str:
    """
    Devuelve bloque texto con nubosidad/lluvia media durante los tramos 30–40°.
    """
    if not tramos or not hourly:
        return ""

    times = hourly.get("time") or []
    clouds = hourly.get("cloudcover") or []
    pprec = hourly.get("precipitation_probability") or []

    if not times or not clouds:
        return ""

    lines = ["☁️ Meteo durante las ventanas 30–40°:"]
    for a, b in tramos:
        c = _avg_in_range(times, clouds, a, b)
        p = _avg_in_range(times, pprec, a, b)
        if c is None and p is None:
            continue
        estado = "despejado"
        icon = "☀️"
        if c is not None:
            if c >= 80:
                estado = "muy nuboso"
                icon = "☁️"
            elif c >= 40:
                estado = "parcial"
                icon = "⛅️"
        c_txt = f"nubes {c}%" if c is not None else "nubes —"
        p_txt = f"lluvia {p}%" if p is not None else "lluvia —"
        lines.append(f"• {a.strftime('%H:%M')}–{b.strftime('%H:%M')}: {icon} {estado} ({c_txt}, {p_txt})")

    return "\n".join(lines) if len(lines) > 1 else ""
