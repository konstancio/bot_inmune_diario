# enviar_consejo.py
# Envío diario multiusuario: consejo + sol 30–40° + mediodía solar (hora + altura máxima) + meteo.
# IMPORTANTE: Usa ubicación del usuario (DB), NO la IP del servidor (Railway).

import os
import math
import asyncio
import datetime as dt
from typing import Optional, Tuple, List

import pytz
import requests
from telegram import Bot
from timezonefinder import TimezoneFinder

from geopy.geocoders import Nominatim

import usuarios_repo as repo
from consejos_diarios import CONSEJOS_DIARIOS  # <- asegúrate de tener tu lista aquí


BOT_TOKEN = os.getenv("BOT_TOKEN")
ONLY_CHAT_ID = os.getenv("ONLY_CHAT_ID")  # opcional: para pruebas


# --------------------------
# Geocoding + TZ from coords
# --------------------------

_geolocator = Nominatim(user_agent="consejos-inmunes-bot", timeout=10)

def _tz_from_coords(lat: float, lon: float) -> str:
    try:
        tf = TimezoneFinder()
        return tf.timezone_at(lat=lat, lng=lon) or "Europe/Madrid"
    except Exception:
        return "Europe/Madrid"

def _geocode_city(city: str) -> Optional[Tuple[float, float, str]]:
    """
    Devuelve (lat, lon, display_name) o None
    """
    if not city:
        return None
    try:
        loc = _geolocator.geocode(city, exactly_one=True, language="es")
        if not loc:
            return None
        return float(loc.latitude), float(loc.longitude), str(loc.address)
    except Exception:
        return None


# --------------------------
# Sol: banda 30–40 + mediodía
# (duplicamos cálculo para no depender de splits a 12:00)
# --------------------------

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

def calcular_banda_y_mediodia(
    lat: float,
    lon: float,
    fecha: dt.date,
    tzname: str,
    paso_min: int = 1,
) -> Tuple[List[Tuple[dt.datetime, dt.datetime]], dt.datetime, float]:
    """
    Devuelve:
      - lista de tramos donde elevación está entre 30 y 40 (incl.)
      - mediodía solar (instante de máxima elevación)
      - elevación máxima del día (grados)
    """
    tz = pytz.timezone(tzname)
    n = fecha.timetuple().tm_yday
    decl = _declinacion_solar(n)

    base = tz.localize(dt.datetime(fecha.year, fecha.month, fecha.day, 0, 0))
    points: List[Tuple[dt.datetime, float]] = []

    max_e = -999.0
    max_t = base

    for m in range(0, 24 * 60, paso_min):
        t = base + dt.timedelta(minutes=m)
        h = _solar_hour_angle(t, lon, tzname, n)
        e = _elevacion_solar_deg(lat, decl, h)
        points.append((t, e))
        if e > max_e:
            max_e = e
            max_t = t

    def in_band(e: float) -> bool:
        return 30.0 <= e <= 40.0

    tramos: List[Tuple[dt.datetime, dt.datetime]] = []
    en = False
    ini: Optional[dt.datetime] = None

    for i in range(1, len(points)):
        t0, e0 = points[i - 1]
        t1, e1 = points[i]
        prev_in = in_band(e0)
        curr_in = in_band(e1)

        if (not prev_in) and curr_in:
            target = 30.0 if e0 < 30.0 else 40.0
            ini = _interp_time(t0, e0, t1, e1, target)
            en = True

        elif prev_in and (not curr_in) and en and ini is not None:
            target = 30.0 if e1 < 30.0 else 40.0
            fin = _interp_time(t0, e0, t1, e1, target)
            tramos.append((ini, fin))
            en = False
            ini = None

    if en and ini is not None:
        tramos.append((ini, points[-1][0]))

    return tramos, max_t, float(max_e)

def _format_tramos(tramos: List[Tuple[dt.datetime, dt.datetime]], ciudad: str) -> str:
    if not tramos:
        return f"☁️ Hoy no hay ventanas 30–40° en {ciudad} (la altura máxima no llega a 30°)."

    lines = [f"🌤 Ventanas 30–40° en {ciudad}:"]
    for a, b in tramos:
        lines.append(f"• {a.strftime('%H:%M')}–{b.strftime('%H:%M')}")
    return "\n".join(lines)


# --------------------------
# Meteo (Open-Meteo)
# --------------------------

def obtener_pronostico_diario(fecha: dt.date, lat: float, lon: float, tzname: str) -> Optional[dict]:
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

def _avg_in_range(times_iso: List[str], values: List[Optional[float]], inicio: dt.datetime, fin: dt.datetime) -> Optional[int]:
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
        # t es naive en zona local (Open-Meteo devuelve en tzname); los tramos también son locales
        if inicio <= t <= fin:
            sel.append(float(val))
    if not sel:
        return None
    return int(round(sum(sel) / len(sel)))

def resumir_meteo_para_tramos(tramos: List[Tuple[dt.datetime, dt.datetime]], hourly: Optional[dict]) -> str:
    if not hourly or not tramos:
        return ""

    times = hourly.get("time") or []
    clouds = hourly.get("cloudcover") or []
    pprec = hourly.get("precipitation_probability") or []

    # promedio global ponderado simple (por tramo)
    cloud_vals = []
    rain_vals = []

    for a, b in tramos:
        c = _avg_in_range(times, clouds, a, b)
        p = _avg_in_range(times, pprec, a, b)
        if c is not None:
            cloud_vals.append(c)
        if p is not None:
            rain_vals.append(p)

    if not cloud_vals and not rain_vals:
        return ""

    c_mean = int(round(sum(cloud_vals) / len(cloud_vals))) if cloud_vals else None
    p_mean = int(round(sum(rain_vals) / len(rain_vals))) if rain_vals else None

    icon = "☀️"
    estado = "despejado"
    if c_mean is not None:
        if c_mean >= 80:
            icon, estado = "☁️", "muy nuboso"
        elif c_mean >= 40:
            icon, estado = "⛅️", "parcial"

    parts = []
    if c_mean is not None:
        parts.append(f"nubes {c_mean}%")
    if p_mean is not None:
        parts.append(f"lluvia {p_mean}%")

    extra = ""
    # Nota prudente: nubosidad muy alta puede reducir UVB (sin llamar “teórico” a nada)
    if c_mean is not None and c_mean >= 80:
        extra = "\n📌 Con nubosidad muy alta, la síntesis de vitamina D puede ser baja aunque la elevación sea suficiente."

    return f"{icon} Meteo en las ventanas: {estado} ({', '.join(parts)}){extra}"


# --------------------------
# Consejo
# --------------------------

def elegir_consejo(chat_id: str, fecha: dt.date) -> str:
    # estable por día+usuario (no random “puro”, pero varía por usuario y día)
    idx = (hash(chat_id) + fecha.toordinal()) % len(CONSEJOS_DIARIOS)
    return CONSEJOS_DIARIOS[idx]

def _limpiar_temp_caducada(chat_id: str, user: dict, now_utc: dt.datetime) -> None:
    until = user.get("temp_until_iso")
    if not until:
        return
    try:
        until_dt = dt.datetime.fromisoformat(until)
        if until_dt.tzinfo is None:
            until_dt = until_dt.replace(tzinfo=dt.timezone.utc)
        if now_utc >= until_dt:
            repo.clear_temp_location(chat_id)
    except Exception:
        # si está corrupta, la limpiamos
        repo.clear_temp_location(chat_id)

def _resolver_ubicacion_usuario(user: dict, chat_id: str, now_utc: dt.datetime) -> Tuple[float, float, str, str]:
    """
    Devuelve (lat, lon, tzname, ciudad_mostrable)
    """
    _limpiar_temp_caducada(chat_id, user, now_utc)

    lat, lon, tzname, city, is_temp = repo.get_effective_location(user, now_utc)

    # si hay coords, ok
    if lat is not None and lon is not None:
        tzname = tzname or _tz_from_coords(lat, lon)
        ciudad = city or ("Ubicación temporal" if is_temp else "Tu ubicación")
        return float(lat), float(lon), tzname, ciudad

    # si no hay coords pero hay city, geocodificar
    if city:
        g = _geocode_city(city)
        if g:
            glat, glon, addr = g
            tz = _tz_from_coords(glat, glon)
            # guardamos como persistente “suave” para evitar Amsterdam en adelante
            repo.set_location(chat_id, glat, glon, tz, city_hint=city)
            return glat, glon, tz, city

    # fallback Málaga
    return 36.7213, -4.4214, "Europe/Madrid", "Málaga"


async def enviar_a_usuario(bot: Bot, chat_id: str, prefs: dict, now_utc: dt.datetime):
    if ONLY_CHAT_ID and str(chat_id) != str(ONLY_CHAT_ID):
        return

    if not repo.should_send_now(prefs, now_utc):
        return

    # ubicación efectiva
    lat, lon, tzname, ciudad = _resolver_ubicacion_usuario(prefs, chat_id, now_utc)
    tz = pytz.timezone(tzname)
    hoy = now_utc.astimezone(tz).date()

    # consejo del día
    consejo = elegir_consejo(chat_id, hoy)

    # sol
    tramos, solar_noon_dt, max_elev = calcular_banda_y_mediodia(lat, lon, hoy, tzname, paso_min=1)

    sol_txt = _format_tramos(tramos, ciudad)
    noon_txt = f"🧭 Mediodía solar: {solar_noon_dt.strftime('%H:%M')} (altura máxima ≈ {max_elev:.1f}°)"

    # meteo
    hourly = obtener_pronostico_diario(hoy, lat, lon, tzname)
    meteo_txt = resumir_meteo_para_tramos(tramos, hourly)

    # mensaje final (sin “teórico”)
    mensaje = (
        f"🧠 Consejo para hoy ({hoy.strftime('%A')}):\n"
        f"{consejo}\n\n"
        f"{sol_txt}\n"
        f"{noon_txt}"
    )
    if meteo_txt:
        mensaje += f"\n{meteo_txt}"

    await bot.send_message(chat_id=chat_id, text=mensaje)

    # marcar enviado
    repo.mark_sent_today(chat_id, hoy)


async def main():
    if not BOT_TOKEN:
        raise RuntimeError("Falta BOT_TOKEN")

    repo.init_db()
    repo.migrate_fill_defaults()

    users = repo.list_users()
    bot = Bot(BOT_TOKEN)
    now_utc = dt.datetime.now(dt.timezone.utc)

    for uid, prefs in users.items():
        try:
            await enviar_a_usuario(bot, uid, prefs, now_utc)
        except Exception as e:
            print(f"❌ Error diario {uid}: {e}")


if __name__ == "__main__":
    asyncio.run(main())
