# usuarios_repo.py (backend en Postgres)
# Guarda suscriptores/ajustes en Postgres: durable y compartido.
# Incluye ubicación persistente + ubicación temporal (con caducidad).

from __future__ import annotations

import os
from datetime import datetime, date, timezone
from typing import Dict, Optional, Tuple

import psycopg2
import psycopg2.extras
import pytz

# ---- idiomas soportados (canónicos) ----
VALID_LANG = {"es", "en", "fr", "it", "de", "pt", "nl", "sr", "ru"}

_LANG_ALIAS = {
    "sh": "sr", "sc": "sr", "srp": "sr", "hr": "sr", "bs": "sr",
    "pt-br": "pt",
}

# ------------------ conexión ------------------

def _get_conn():
    url = os.getenv("DATABASE_DSN") or os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_DSN (o DATABASE_URL) no está definida")
    conn = psycopg2.connect(url, sslmode="require")
    conn.autocommit = True
    return conn

# ------------------ schema / migraciones ------------------

def init_db() -> None:
    """
    Crea tabla si no existe + añade columnas si faltan (idempotente).
    """
    base_sql = """
    CREATE TABLE IF NOT EXISTS subscribers (
        chat_id             TEXT PRIMARY KEY,
        lang                TEXT NOT NULL DEFAULT 'es',
        city                TEXT,
        lat                 DOUBLE PRECISION,
        lon                 DOUBLE PRECISION,
        tz                  TEXT NOT NULL DEFAULT 'Europe/Madrid',

        last_sent_iso        TEXT,
        send_hour_local      INTEGER NOT NULL DEFAULT 9,

        -- nocturno parasimpático
        last_sleep_sent_iso  TEXT,
        sleep_hour_local     INTEGER NOT NULL DEFAULT 21,

        created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    CREATE INDEX IF NOT EXISTS idx_subs_tz ON subscribers (tz);
    """
    with _get_conn() as conn, conn.cursor() as cur:
        cur.execute(base_sql)

        # ---- añadir columnas nuevas (por si existían versiones antiguas) ----
        cur.execute("ALTER TABLE subscribers ADD COLUMN IF NOT EXISTS last_sent_iso TEXT;")
        cur.execute("ALTER TABLE subscribers ADD COLUMN IF NOT EXISTS send_hour_local INTEGER;")
        cur.execute("ALTER TABLE subscribers ADD COLUMN IF NOT EXISTS last_sleep_sent_iso TEXT;")
        cur.execute("ALTER TABLE subscribers ADD COLUMN IF NOT EXISTS sleep_hour_local INTEGER;")

        # ---- ubicación temporal ----
        cur.execute("ALTER TABLE subscribers ADD COLUMN IF NOT EXISTS temp_city TEXT;")
        cur.execute("ALTER TABLE subscribers ADD COLUMN IF NOT EXISTS temp_lat DOUBLE PRECISION;")
        cur.execute("ALTER TABLE subscribers ADD COLUMN IF NOT EXISTS temp_lon DOUBLE PRECISION;")
        cur.execute("ALTER TABLE subscribers ADD COLUMN IF NOT EXISTS temp_tz TEXT;")
        cur.execute("ALTER TABLE subscribers ADD COLUMN IF NOT EXISTS temp_until_iso TEXT;")

        # defaults suaves
        cur.execute("UPDATE subscribers SET send_hour_local = COALESCE(send_hour_local, 9);")
        cur.execute("UPDATE subscribers SET sleep_hour_local = COALESCE(sleep_hour_local, 21);")

def migrate_fill_defaults() -> None:
    """
    Rellena defaults si hay NULLs.
    """
    try:
        with _get_conn() as conn, conn.cursor() as cur:
            cur.execute("UPDATE subscribers SET lang='es' WHERE lang IS NULL OR lang='';")
            cur.execute("UPDATE subscribers SET tz='Europe/Madrid' WHERE tz IS NULL OR tz='';")
            cur.execute("UPDATE subscribers SET send_hour_local=9 WHERE send_hour_local IS NULL;")
            cur.execute("UPDATE subscribers SET sleep_hour_local=21 WHERE sleep_hour_local IS NULL;")
            cur.execute("UPDATE subscribers SET updated_at=now() WHERE updated_at IS NULL;")
    except Exception as e:
        print(f"[WARN] migrate_fill_defaults: {e}")

# ------------------ CRUD básico ------------------

def ensure_user(chat_id: str) -> dict:
    with _get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT * FROM subscribers WHERE chat_id=%s", (str(chat_id),))
        row = cur.fetchone()
        if row:
            return dict(row)

        cur.execute("INSERT INTO subscribers (chat_id) VALUES (%s) ON CONFLICT DO NOTHING;", (str(chat_id),))
        cur.execute("SELECT * FROM subscribers WHERE chat_id=%s", (str(chat_id),))
        return dict(cur.fetchone())

def list_users() -> Dict[str, dict]:
    with _get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT * FROM subscribers;")
        rows = cur.fetchall()
        return {r["chat_id"]: dict(r) for r in rows}

def get_user(chat_id: str) -> dict:
    with _get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT * FROM subscribers WHERE chat_id=%s", (str(chat_id),))
        row = cur.fetchone()
        return dict(row) if row else {}

def subscribe(chat_id: str) -> dict:
    return ensure_user(chat_id)

def unsubscribe(chat_id: str) -> None:
    with _get_conn() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM subscribers WHERE chat_id=%s", (str(chat_id),))

# ------------------ Preferencias ------------------

def set_lang(chat_id: str, lang: str) -> bool:
    lang = (lang or "").strip().lower()
    lang = _LANG_ALIAS.get(lang, lang)
    if lang not in VALID_LANG:
        return False
    with _get_conn() as conn, conn.cursor() as cur:
        cur.execute("UPDATE subscribers SET lang=%s, updated_at=now() WHERE chat_id=%s;", (lang, str(chat_id)))
    return True

def set_city(chat_id: str, city: Optional[str]) -> None:
    with _get_conn() as conn, conn.cursor() as cur:
        cur.execute("UPDATE subscribers SET city=%s, updated_at=now() WHERE chat_id=%s;", (city, str(chat_id)))

def set_send_hour(chat_id: str, hour_local: int) -> None:
    try:
        hour_local = int(hour_local)
    except Exception:
        hour_local = 9
    hour_local = max(0, min(23, hour_local))
    with _get_conn() as conn, conn.cursor() as cur:
        cur.execute("UPDATE subscribers SET send_hour_local=%s, updated_at=now() WHERE chat_id=%s;",
                    (hour_local, str(chat_id)))

def set_sleep_hour(chat_id: str, hour_local: int) -> None:
    try:
        hour_local = int(hour_local)
    except Exception:
        hour_local = 21
    hour_local = max(0, min(23, hour_local))
    with _get_conn() as conn, conn.cursor() as cur:
        cur.execute("UPDATE subscribers SET sleep_hour_local=%s, updated_at=now() WHERE chat_id=%s;",
                    (hour_local, str(chat_id)))

def clear_temp_location(chat_id: str) -> None:
    with _get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            UPDATE subscribers
               SET temp_city=NULL, temp_lat=NULL, temp_lon=NULL, temp_tz=NULL, temp_until_iso=NULL,
                   updated_at=now()
             WHERE chat_id=%s
        """, (str(chat_id),))

def set_location(chat_id: str, lat: float, lon: float, tz: str, city_hint: Optional[str] = None) -> None:
    """
    Ubicación persistente. Al fijarla, limpiamos temporal (si existía).
    """
    tz = (tz or "Europe/Madrid").strip() or "Europe/Madrid"
    with _get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            UPDATE subscribers
               SET lat=%s, lon=%s, tz=%s, city=COALESCE(%s, city),
                   temp_city=NULL, temp_lat=NULL, temp_lon=NULL, temp_tz=NULL, temp_until_iso=NULL,
                   updated_at=now()
             WHERE chat_id=%s
        """, (float(lat), float(lon), tz, city_hint, str(chat_id)))

def set_temp_location(chat_id: str, lat: float, lon: float, tz: str, until_utc: datetime, city_hint: Optional[str] = None) -> None:
    """
    Ubicación temporal (p.ej. viaje) válida hasta until_utc (UTC).
    """
    tz = (tz or "Europe/Madrid").strip() or "Europe/Madrid"
    until_iso = until_utc.astimezone(timezone.utc).isoformat()
    with _get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            UPDATE subscribers
               SET temp_lat=%s, temp_lon=%s, temp_tz=%s,
                   temp_city=COALESCE(%s, temp_city),
                   temp_until_iso=%s,
                   updated_at=now()
             WHERE chat_id=%s
        """, (float(lat), float(lon), tz, city_hint, until_iso, str(chat_id)))

def get_effective_location(chat: dict, now_utc: Optional[datetime] = None) -> Tuple[Optional[float], Optional[float], str, Optional[str], bool]:
    """
    Devuelve (lat, lon, tz, city, is_temp), eligiendo temporal si no ha caducado.
    Si la temporal caducó, NO la borra aquí (eso lo hace el caller si quiere).
    """
    if now_utc is None:
        now_utc = datetime.now(timezone.utc)

    # temporal
    temp_until = chat.get("temp_until_iso")
    if temp_until:
        try:
            until_dt = datetime.fromisoformat(temp_until)
            if until_dt.tzinfo is None:
                until_dt = until_dt.replace(tzinfo=timezone.utc)
            if now_utc < until_dt:
                lat = chat.get("temp_lat")
                lon = chat.get("temp_lon")
                tz = (chat.get("temp_tz") or chat.get("tz") or "Europe/Madrid").strip()
                city = chat.get("temp_city") or chat.get("city")
                if lat is not None and lon is not None:
                    return float(lat), float(lon), tz or "Europe/Madrid", city, True
        except Exception:
            pass

    # persistente
    lat = chat.get("lat")
    lon = chat.get("lon")
    tz = (chat.get("tz") or "Europe/Madrid").strip() or "Europe/Madrid"
    city = chat.get("city")
    if lat is not None and lon is not None:
        return float(lat), float(lon), tz, city, False

    # sin coords
    return None, None, tz, city, False

# ------------------ Control de envío diario/nocturno ------------------

def mark_sent_today(chat_id: str, local_date: date) -> None:
    with _get_conn() as conn, conn.cursor() as cur:
        cur.execute("UPDATE subscribers SET last_sent_iso=%s, updated_at=now() WHERE chat_id=%s;",
                    (local_date.isoformat(), str(chat_id)))

def mark_sleep_sent_today(chat_id: str, local_date: date) -> None:
    with _get_conn() as conn, conn.cursor() as cur:
        cur.execute("UPDATE subscribers SET last_sleep_sent_iso=%s, updated_at=now() WHERE chat_id=%s;",
                    (local_date.isoformat(), str(chat_id)))

def should_send_now(chat: dict, now_utc: Optional[datetime] = None) -> bool:
    """
    Cron cada 5 min:
    - Convierte now_utc a hora local del usuario (chat["tz"])
    - Envía si: local_hour == send_hour_local y 0<=min<30
    - y si aún no se envió hoy (last_sent_iso == fecha local)
    """
    if now_utc is None:
        now_utc = datetime.now(timezone.utc)

    tzname = (chat.get("tz") or "Europe/Madrid").strip() or "Europe/Madrid"
    try:
        tz = pytz.timezone(tzname)
    except Exception:
        tz = pytz.timezone("Europe/Madrid")
        tzname = "Europe/Madrid"

    send_hour = int(chat.get("send_hour_local", 9))
    now_local = now_utc.astimezone(tz)
    local_date = now_local.date()

    already = (chat.get("last_sent_iso") == local_date.isoformat())
    in_window = (now_local.hour == send_hour and 0 <= now_local.minute < 30)
    return in_window and not already

def should_send_sleep_now(chat: dict, now_utc: Optional[datetime] = None) -> bool:
    """
    Nocturno parasimpático: por defecto 21:00 local.
    Ventana 0..10 min (para cron de 5 min va perfecto).
    """
    if now_utc is None:
        now_utc = datetime.now(timezone.utc)

    tzname = (chat.get("tz") or "Europe/Madrid").strip() or "Europe/Madrid"
    try:
        tz = pytz.timezone(tzname)
    except Exception:
        tz = pytz.timezone("Europe/Madrid")

    sleep_hour = int(chat.get("sleep_hour_local", 21))
    now_local = now_utc.astimezone(tz)
    local_date = now_local.date()

    already = (chat.get("last_sleep_sent_iso") == local_date.isoformat())
    in_window = (now_local.hour == sleep_hour and 0 <= now_local.minute < 10)
    return in_window and not already
