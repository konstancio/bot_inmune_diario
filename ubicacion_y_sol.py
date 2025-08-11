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
        tzname = tf.timezone_at(lat=lat, lng=lon) or "Europe/Madrid"
    except Exception:
        tzname = "Europe/Madrid"

    return {
        "latitud": float(lat),
        "longitud": float(lon),
        "ciudad": ciudad,
        "timezone": tzname,
    }


# --------------------------------------------
# 2) Cálculo de intervalos 30–40° sin Astral
# --------------------------------------------
def _declinacion_solar(n: int) -> float:
    """
    Declinación aprox (Cooper). n: día del año (1..366). Devuelve grados.
    """
    # Fórmula: δ = 23.44° * sin( 2π (n-81) / 365 )
    return 23.44 * math.sin(math.radians((360.0 / 365.0) * (n - 81)))


def _equation_of_time_minutes(n: int) -> float:
    """
    Ecuación del tiempo (minutos). Aproximación clásica (Spencer/Cooper).
    """
    B = math.radians(360.0 * (n - 81) / 364.0)
    # 9.87 sin(2B) - 7.53 cos(B) - 1.5 sin(B)  -> minutos
    return 9.87 * math.sin(2 * B) - 7.53 * math.cos(B) - 1.5 * math.sin(B)


def _elevacion_solar_deg(lat_deg: float, decl_deg: float, hour_angle_deg: float) -> float:
    """
    Elevación (grados) a partir de latitud, declinación y ángulo horario (grados).
    """
    lat = math.radians(lat_deg)
    dec = math.radians(decl_deg)
    h = math.radians(hour_angle_deg)
    sin_alt = math.sin(lat) * math.sin(dec) + math.cos(lat) * math.cos(dec) * math.cos(h)
    return math.degrees(math.asin(max(-1.0, min(1.0, sin_alt))))


def _solar_hour_angle(local_dt: dt.datetime, lon: float, tzname: str, n: int) -> float:
    """
    Ángulo horario (grados) aplicando EoT y corrección por longitud.
    local_dt debe estar en TZ local (aware).
    """
    tz = pytz.timezone(tzname)
    # Offset horario (cambia con DST)
    noon = tz.localize(dt.datetime(local_dt.year, local_dt.month, local_dt.day, 12, 0))
    tz_hours = noon.utcoffset().total_seconds() / 3600.0  # horas

    # EoT en minutos
    eot = _equation_of_time_minutes(n)  # min

    # Hora local en decimal
    hora_decimal = local_dt.hour + local_dt.minute / 60.0 + local_dt.second / 3600.0

    # Longitud estándar del huso
    L_std = 15.0 * tz_hours  # grados

    # Corrección (min) = EoT + 4*(lon - L_std)
    corr_min = eot + 4.0 * (lon - L_std)

    # Hora solar = hora local + corrección (en horas)
    hora_solar = hora_decimal + corr_min / 60.0

    # Ángulo horario
    return 15.0 * (hora_solar - 12.0)


def calcular_intervalos_optimos(
    lat: float,
    lon: float,
    fecha: dt.date,
    tzname: str,
    paso_min: int = 3,
) -> Tuple[Optional[Tuple[dt.datetime, dt.datetime]], Optional[Tuple[dt.datetime, dt.datetime]]]:
    """
    Recorre el día a 'paso_min' y devuelve dos tramos (mañana/tarde)
    con elevación entre 30 y 40 grados. Datetimes tz-aware.
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

    # Detectar tramos [30,40]
    tramos: List[Tuple[dt.datetime, dt.datetime]] = []
    en = False
    ini: Optional[dt.datetime] = None

    def _clamp40(a: float) -> float:
        # si quieres cortar exactamente en 30/40 podrías interpolar;
        # para simplicidad usamos bordes discretos
        return a

    for i, (t, e) in enumerate(puntos):
        if 30.0 <= e <= 40.0:
            if not en:
                ini = t
                en = True
        else:
            if en:
                fin = puntos[i - 1][0]
                tramos.append((ini, fin))  # type: ignore
                en = False
    if en:
        tramos.append((ini, puntos[-1][0]))  # type: ignore

    # Separar antes/después del mediodía local
    mediodia = tz.localize(dt.datetime(fecha.year, fecha.month, fecha.day, 12, 0))
    tramo_m = next(((a, b) for a, b in tramos if b <= mediodia), None)
    tramo_t = next(((a, b) for a, b in tramos if a > mediodia), None)
    return tramo_m, tramo_t


# ---------------------------------------
# 3) Formato simple de intervalos (texto)
# ---------------------------------------
def describir_intervalos(
    intervalos: Tuple[
        Optional[Tuple[dt.datetime, dt.datetime]],
        Optional[Tuple[dt.datetime, dt.datetime]],
    ],
    ciudad: str,
) -> str:
    maniana, tarde = intervalos
    texto = f"☀️ Intervalos solares seguros para producir vit. D hoy en {ciudad}:"
    if maniana:
        a, b = maniana
        texto += f"\n🌅 Mañana:\n🕒 {a.strftime('%H:%M')} - {b.strftime('%H:%M')}"
    if tarde:
        a, b = tarde
        texto += f"\n🌇 Tarde:\n🕒 {a.strftime('%H:%M')} - {b.strftime('%H:%M')}"
    if not maniana and not tarde:
        texto += "\n(No hay elevación solar suficiente hoy para producir vitamina D)"
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
    """
    Media simple (redondeada) de 'values' cuyos 'times_iso' caen en [inicio, fin].
    """
    if not times_iso or not values:
        return None
    sel: List[float] = []
    for iso, val in zip(times_iso, values):
        if val is None:
            continue
        try:
            t = dt.datetime.fromisoformat(iso)
        except Exception:
            # Open-Meteo usa 'YYYY-MM-DDTHH:00'
            try:
                t = dt.datetime.strptime(iso, "%Y-%m-%dT%H:%M")
            except Exception:
                continue
        # t es naive en esa cadena; asúmelo en misma TZ que intervalos (ya son locales)
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
        # Sin datos
        return ""

    times = hourly.get("time") or []
    clouds = hourly.get("cloudcover") or []
    pprec = hourly.get("precipitation_probability") or []

    def etiqueta(c: Optional[int], p: Optional[int]) -> str:
        if c is None and p is None:
            return ""
        # icono simple por nubes
        icon = "☀️"
        if c is not None:
            if c >= 80:
                icon = "☁️"
            elif c >= 40:
                icon = "⛅️"
        # texto
        ctxt = f"nubes {c}%" if c is not None else "nubes —"
        ptxt = f"lluvia {p}%" if p is not None else "lluvia —"
        estado = "despejado" if (c is not None and c < 30) else ("nuboso" if c and c >= 70 else "parcial")
        return f" ({icon} {estado}, {ctxt}, {ptxt})"

    texto = ""

    if maniana:
        a, b = maniana
        c_m = _avg_in_range(times, clouds, a, b)
        p_m = _avg_in_range(times, pprec, a, b)
        texto += f"\n      {etiqueta(c_m, p_m)}"
    if tarde:
        a, b = tarde
        c_t = _avg_in_range(times, clouds, a, b)
        p_t = _avg_in_range(times, pprec, a, b)
        texto += f"\n      {etiqueta(c_t, p_t)}"

    return texto
