# enviar_consejo.py — CRON diario multiusuario
# Vitamina D (30–40°), meteo, nutrición por estación, traducción + HISTÓRICO en Postgres

import os
import asyncio
import datetime as dt
from typing import Optional, Tuple, Dict, Any, List

import pytz
from telegram import Bot
from deep_translator import LibreTranslator

from consejos_diarios import consejos
from consejos_nutri import CONSEJOS_NUTRI
from usuarios_repo import init_db, list_users, should_send_now, mark_sent_today

from ubicacion_y_sol import (
    obtener_ubicacion,
    calcular_intervalos_optimos,
    obtener_pronostico_diario,
)

# ======= (opcional) histórico en Postgres =======
# Usa la MISMA DATABASE_DSN que ya usas en usuarios_repo.py
DATABASE_DSN = os.getenv("DATABASE_DSN")

try:
    import psycopg2
except Exception:
    psycopg2 = None


# ================= ENV =================

BOT_TOKEN = os.getenv("BOT_TOKEN")
FORCE_SEND = os.getenv("FORCE_SEND", "0").strip() == "1"
ONLY_CHAT_ID = os.getenv("ONLY_CHAT_ID")
PING_ON_START = os.getenv("PING_ON_START", "0").strip() == "1"
CANAL_CHAT_ID = os.getenv("CANAL_CHAT_ID")  # opcional


# ================= Idiomas =================

VALID_LANG = {"es", "en", "fr", "it", "de", "pt", "nl", "sr", "ru"}

_LANG_ALIAS = {
    "sh": "sr", "sc": "sr", "srp": "sr", "hr": "sr", "bs": "sr",
    "pt-br": "pt",
    "es-es": "es", "en-us": "en", "en-gb": "en",
}

def _norm_lang(code: Optional[str]) -> str:
    if not code:
        return "es"
    code = (code or "").strip().lower()
    code = _LANG_ALIAS.get(code, code)
    return code if code in VALID_LANG else "es"

def traducir(texto: str, lang: Optional[str]) -> str:
    dest = _norm_lang(lang)
    if dest == "es":
        return texto
    try:
        return LibreTranslator(source="es", target=dest).translate(texto)
    except Exception:
        return texto


# ================= Estación =================

def estacion_del_anio(fecha: dt.date, lat: float) -> str:
    m = fecha.month
    norte = lat >= 0
    if norte:
        return ("Invierno","Invierno","Invierno",
                "Primavera","Primavera","Primavera",
                "Verano","Verano","Verano",
                "Otoño","Otoño","Otoño")[m-1]
    else:
        return ("Verano","Verano","Verano",
                "Otoño","Otoño","Otoño",
                "Invierno","Invierno","Invierno",
                "Primavera","Primavera","Primavera")[m-1]

def pick_nutri(est: str, chat_id: str, fecha: dt.date) -> str:
    ops = CONSEJOS_NUTRI.get(est)
    if not ops:
        return "Prioriza alimentos reales y, si procede, alimentos fortificados en vitamina D."
    if isinstance(ops, str):
        return ops
    ops = list(ops)
    idx = (hash(str(chat_id)) + fecha.toordinal()) % len(ops)
    return ops[idx]


# ================= Consejo diario =================

def consejo_del_dia(now_local: dt.datetime) -> Tuple[str, str]:
    lista = consejos[now_local.weekday()]
    pares = [lista[i:i+2] for i in range(0, len(lista), 2)]
    idx = now_local.date().toordinal() % len(pares)
    return pares[idx][0], pares[idx][1]


# ================= Helpers meteo por ventanas =================

Tramo = Optional[Tuple[dt.datetime, dt.datetime]]

def _parse_iso_local(iso: str) -> Optional[dt.datetime]:
    try:
        return dt.datetime.fromisoformat(iso)
    except Exception:
        try:
            return dt.datetime.strptime(iso, "%Y-%m-%dT%H:%M")
        except Exception:
            return None

def _max_in_range(times: List[str], values: List[Any], a: dt.datetime, b: dt.datetime) -> Optional[float]:
    sel: List[float] = []
    for iso, v in zip(times, values):
        if v is None:
            continue
        t = _parse_iso_local(str(iso))
        if not t:
            continue
        if a <= t <= b:
            try:
                sel.append(float(v))
            except Exception:
                pass
    return max(sel) if sel else None

def _meteo_mala_en_ventanas(hourly: Optional[dict], tramo_m: Tramo, tramo_t: Tramo) -> Tuple[bool, Optional[float], Optional[float]]:
    """
    Decide meteo mala mirando SOLO dentro de las ventanas 30–40°.
    Regla conservadora:
      - max_nubes >= 85%  o  max_lluvia_prob >= 50%  => mala
    Devuelve: (mala, max_nubes, max_lluvia_prob) en las ventanas combinadas.
    """
    if not hourly:
        return False, None, None

    times = hourly.get("time") or []
    clouds = hourly.get("cloudcover") or []
    pprec = hourly.get("precipitation_probability") or []

    max_cloud = None
    max_pp = None

    for tramo in (tramo_m, tramo_t):
        if not tramo:
            continue
        a, b = tramo
        mc = _max_in_range(times, clouds, a, b)
        mp = _max_in_range(times, pprec, a, b)

        if mc is not None:
            max_cloud = mc if max_cloud is None else max(max_cloud, mc)
        if mp is not None:
            max_pp = mp if max_pp is None else max(max_pp, mp)

    mala = False
    if max_cloud is not None and max_cloud >= 85:
        mala = True
    if max_pp is not None and max_pp >= 50:
        mala = True

    return mala, max_cloud, max_pp


# ================= Histórico (Postgres) =================

def _hist_enabled() -> bool:
    return bool(DATABASE_DSN) and (psycopg2 is not None)

def _hist_conn():
    # autocommit para evitar líos con REINDEX/otros
    conn = psycopg2.connect(DATABASE_DSN)  # type: ignore
    conn.autocommit = True
    return conn

def init_hist():
    if not _hist_enabled():
        return
    try:
        with _hist_conn() as conn, conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS solar_history (
                    chat_id TEXT NOT NULL,
                    date DATE NOT NULL,
                    city TEXT,
                    lat DOUBLE PRECISION,
                    lon DOUBLE PRECISION,
                    tz TEXT,
                    win_m_start TIMESTAMPTZ,
                    win_m_end   TIMESTAMPTZ,
                    win_t_start TIMESTAMPTZ,
                    win_t_end   TIMESTAMPTZ,
                    has_window BOOLEAN NOT NULL DEFAULT FALSE,
                    meteo_bad  BOOLEAN NOT NULL DEFAULT FALSE,
                    cloud_max  DOUBLE PRECISION,
                    precip_prob_max DOUBLE PRECISION,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    PRIMARY KEY(chat_id, date)
                );
            """)
    except Exception as e:
        print(f"[WARN] init_hist: {e}")

def save_hist(
    chat_id: str,
    fecha: dt.date,
    ciudad: Optional[str],
    lat: float,
    lon: float,
    tzname: str,
    tramo_m: Tramo,
    tramo_t: Tramo,
    has_window: bool,
    meteo_bad: bool,
    cloud_max: Optional[float],
    precip_prob_max: Optional[float],
):
    if not _hist_enabled():
        return
    try:
        with _hist_conn() as conn, conn.cursor() as cur:
            cur.execute("""
                INSERT INTO solar_history (
                    chat_id, date, city, lat, lon, tz,
                    win_m_start, win_m_end, win_t_start, win_t_end,
                    has_window, meteo_bad, cloud_max, precip_prob_max, updated_at
                )
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,now())
                ON CONFLICT (chat_id, date) DO UPDATE SET
                    city=EXCLUDED.city,
                    lat=EXCLUDED.lat,
                    lon=EXCLUDED.lon,
                    tz=EXCLUDED.tz,
                    win_m_start=EXCLUDED.win_m_start,
                    win_m_end=EXCLUDED.win_m_end,
                    win_t_start=EXCLUDED.win_t_start,
                    win_t_end=EXCLUDED.win_t_end,
                    has_window=EXCLUDED.has_window,
                    meteo_bad=EXCLUDED.meteo_bad,
                    cloud_max=EXCLUDED.cloud_max,
                    precip_prob_max=EXCLUDED.precip_prob_max,
                    updated_at=now();
            """, (
                str(chat_id), fecha, ciudad, float(lat), float(lon), tzname,
                tramo_m[0] if tramo_m else None,
                tramo_m[1] if tramo_m else None,
                tramo_t[0] if tramo_t else None,
                tramo_t[1] if tramo_t else None,
                bool(has_window), bool(meteo_bad),
                cloud_max, precip_prob_max,
            ))
    except Exception as e:
        print(f"[WARN] save_hist: {e}")


# ================= Texto solar =================

def _fmt_tramo(prefix: str, tramo: Tramo) -> str:
    if not tramo:
        return ""
    a, b = tramo
    return f"\n{prefix}: {a.strftime('%H:%M')}–{b.strftime('%H:%M')}"

def texto_horas_30_40(ciudad: str, tramo_m: Tramo, tramo_t: Tramo) -> str:
    txt = f"📌 Horas con el Sol entre 30° y 40° en {ciudad}:"
    if tramo_m:
        txt += _fmt_tramo("🌅 Mañana", tramo_m)
    if tramo_t:
        txt += _fmt_tramo("🌇 Tarde", tramo_t)
    return txt


# ================= Envío =================

async def enviar_a_usuario(bot: Bot, chat_id: str, prefs: dict, now_utc: dt.datetime):

    if ONLY_CHAT_ID and str(chat_id) != str(ONLY_CHAT_ID):
        return

    tzname = (prefs.get("tz") or "Europe/Madrid").strip()
    try:
        tz = pytz.timezone(tzname)
    except Exception:
        tzname = "Europe/Madrid"
        tz = pytz.timezone(tzname)

    now_local = now_utc.astimezone(tz)
    hoy = now_local.date()

    # --- control de envío ---
    if not FORCE_SEND and not should_send_now(prefs, now_utc):
        return
    if FORCE_SEND and prefs.get("last_sent_iso") == hoy.isoformat():
        return

    # --- ubicación ---
    lat = prefs.get("lat")
    lon = prefs.get("lon")
    ciudad = prefs.get("city")

    if lat is None or lon is None:
        ub = obtener_ubicacion()
        lat, lon = ub["latitud"], ub["longitud"]
        ciudad = ciudad or ub.get("ciudad")

    lat = float(lat)
    lon = float(lon)
    ciudad = ciudad or "tu zona"

    # --- cálculo solar (paso 1 minuto para capturar ventanas cortas) ---
    try:
        tramo_m, tramo_t = calcular_intervalos_optimos(
            lat=lat,
            lon=lon,
            fecha=hoy,
            tzname=tzname,
            paso_min=1,
        )
    except TypeError:
        # Por si tu versión antigua no acepta paso_min:
        tramo_m, tramo_t = calcular_intervalos_optimos(
            lat=lat,
            lon=lon,
            fecha=hoy,
            tzname=tzname,
        )

    hay_30_40 = bool(tramo_m or tramo_t)

    # --- meteo (mirando dentro de las ventanas 30–40) ---
    try:
        hourly = obtener_pronostico_diario(hoy, lat, lon, tzname)
    except Exception:
        hourly = None

    meteo_mala, cloud_max, pprob_max = _meteo_mala_en_ventanas(hourly, tramo_m, tramo_t)

    # --- histórico (se guarda SIEMPRE, incluso si no se envía por hora; aquí ya hemos decidido enviar) ---
    save_hist(
        chat_id=str(chat_id),
        fecha=hoy,
        ciudad=ciudad,
        lat=lat,
        lon=lon,
        tzname=tzname,
        tramo_m=tramo_m,
        tramo_t=tramo_t,
        has_window=hay_30_40,
        meteo_bad=meteo_mala,
        cloud_max=cloud_max,
        precip_prob_max=pprob_max,
    )

    # --- construir mensaje solar según casos ---
    if not hay_30_40:
        texto_solar = (
            f"☁️ En tu latitud hoy no podrás producir vitamina D: "
            f"el Sol no subirá por encima de 30° sobre el horizonte en {ciudad}."
        )
        est = estacion_del_anio(hoy, lat)
        extra = f"\n\n🍽️ Consejo nutricional de {est}:\n{pick_nutri(est, str(chat_id), hoy)}"

    elif meteo_mala:
        detalle = []
        if cloud_max is not None:
            detalle.append(f"nubes máx. {int(round(cloud_max))}%")
        if pprob_max is not None:
            detalle.append(f"lluvia máx. {int(round(pprob_max))}%")
        suf = f" ({', '.join(detalle)})" if detalle else ""

        texto_solar = (
            "☁️ Hoy no se espera una ventana útil para sintetizar vitamina D por las condiciones meteorológicas"
            f"{suf}.\n"
            "📌 Aun así, estas son las horas en las que el Sol estaría entre 30° y 40° (si el cielo estuviera despejado):\n\n"
            f"{texto_horas_30_40(ciudad, tramo_m, tramo_t)}"
        )
        est = estacion_del_anio(hoy, lat)
        extra = f"\n\n🍽️ Consejo nutricional de {est}:\n{pick_nutri(est, str(chat_id), hoy)}"

    else:
        texto_solar = (
            "🌞 Intervalos solares seguros para producir vit. D (30–40°):\n\n"
            f"{texto_horas_30_40(ciudad, tramo_m, tramo_t)}"
        )
        extra = ""

    # --- consejo del día + referencia ---
    consejo, ref = consejo_del_dia(now_local)
    dia = ["Lunes","Martes","Miércoles","Jueves","Viernes","Sábado","Domingo"][now_local.weekday()]

    mensaje_es = (
        f"🧠 Consejo para hoy ({dia}):\n{consejo}\n\n"
        f"📚 *Referencia:* {ref}\n\n"
        f"{texto_solar}{extra}"
    )

    mensaje = traducir(mensaje_es, prefs.get("lang"))

    # Ping opcional
    if PING_ON_START:
        try:
            await bot.send_message(chat_id, "✅ Ping de diagnóstico (PING_ON_START activo).")
        except Exception:
            pass

    # Envío usuario
    await bot.send_message(chat_id, mensaje)

    # Marcar “enviado hoy” para no repetir
    mark_sent_today(chat_id, hoy)

    # Opcional: canal
    if CANAL_CHAT_ID:
        try:
            await bot.send_message(CANAL_CHAT_ID, mensaje)
        except Exception:
            pass


# ================= Main =================

async def main():
    if not BOT_TOKEN:
        raise RuntimeError("❌ Falta BOT_TOKEN")

    init_db()
    init_hist()

    users = list_users()
    if not users:
        print("ℹ️ No hay suscriptores.")
        return

    bot = Bot(BOT_TOKEN)
    now_utc = dt.datetime.now(dt.timezone.utc)

    for uid, prefs in users.items():
        try:
            await enviar_a_usuario(bot, uid, prefs, now_utc)
        except Exception as e:
            print(f"❌ Error en {uid}: {e}")

if __name__ == "__main__":
    asyncio.run(main())
