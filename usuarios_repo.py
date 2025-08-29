# usuarios_repo.py (backend en Postgres)
# Guarda suscriptores/ajustes en Postgres: durable y compartido.

from __future__ import annotations
import os
import re
from datetime import datetime, date, timezone
from typing import Dict, Any, Optional

import psycopg2
import psycopg2.extras
import pytz

# ---- idiomas soportados (canónicos) ----
VALID_LANG = {"es", "en", "fr", "it", "de", "pt", "nl", "sr", "ru"}

# alias de entrada -> código canónico
_LANG_ALIAS = {
    "sh": "sr", "sc": "sr", "srp": "sr", "hr": "sr", "bs": "sr",  # serbio como proxy
    "pt-br": "pt"
}

# ------------------ conexión ------------------

def _get_conn():
    url = os.getenv("DATABASE_DSN") or os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_DSN (o DATABASE_URL) no está definida")
    conn = psycopg2.connect(url, sslmode="require")
    conn.autocommit = True
    return conn

def init_db() -> None:
    """Crea tablas si no existen y añade columnas nuevas si faltan (idempotente)."""
    sql = """
    CREATE TABLE IF NOT EXISTS subscribers (
        chat_id         TEXT PRIMARY KEY,
        lang            TEXT NOT NULL DEFAULT 'es',
        city            TEXT,
        lat             DOUBLE PRECISION,
        lon             DOUBLE PRECISION,
        tz              TEXT NOT NULL DEFAULT 'Europe/Madrid',
        last_sent_iso   TEXT,
        send_hour_local INTEGER NOT NULL DEFAULT 9,
        -- nuevos campos para envío nocturno
        last_sleep_sent_iso TEXT,
        sleep_hour_local    INTEGER NOT NULL DEFAULT 21,
        created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    CREATE INDEX IF NOT EXISTS idx_subs_tz ON subscribers (tz);
    """
    with _get_conn() as conn, conn.cursor() as cur:
        cur.execute(sql)
        # Por si la tabla ya existía sin las columnas nuevas (Railway antiguas):
        cur.execute("ALTER TABLE subscribers ADD COLUMN IF NOT EXISTS last_sleep_sent_iso TEXT;")
        cur.execute("ALTER TABLE subscribers ADD COLUMN IF NOT EXISTS sleep_hour_local INTEGER;")
        cur.execute("UPDATE subscribers SET sleep_hour_local = COALESCE(sleep_hour_local, 21);")

def migrate_fill_defaults() -> None:
    """
    Migración suave:
    - Rellena valores por defecto en filas existentes (incluye nocturno).
    - No altera el esquema más allá de valores.
    """
    try:
        with _get_conn() as conn, conn.cursor() as cur:
            cur.execute("""
                UPDATE subscribers
                   SET lang='es'
                 WHERE lang IS NULL OR lang=''
            """)
            cur.execute("""
                UPDATE subscribers
                   SET tz='Europe/Madrid'
                 WHERE tz IS NULL OR tz=''
            """)
            cur.execute("""
                UPDATE subscribers
                   SET send_hour_local=9
                 WHERE send_hour_local IS NULL
            """)
            cur.execute("""
                UPDATE subscribers
                   SET sleep_hour_local=21
                 WHERE sleep_hour_local IS NULL
            """)
            cur.execute("""
                UPDATE subscribers
                   SET updated_at=now()
                 WHERE updated_at IS NULL
            """)
    except Exception as e:
        print(f"[WARN] migrate_fill_defaults: {e}")

def _row_to_dict(row) -> dict:
    if not row:
        return {}
    if isinstance(row, dict):
        return dict(row)
    if hasattr(row, "keys"):
        return dict(row)
    return dict(row)

# ------------------ CRUD básico ------------------

def ensure_user(chat_id: str) -> dict:
    with _get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT * FROM subscribers WHERE chat_id=%s", (str(chat_id),))
        row = cur.fetchone()
        if row:
            return dict(row)
        cur.execute("""
            INSERT INTO subscribers (chat_id) VALUES (%s)
            ON CONFLICT (chat_id) DO NOTHING
        """, (str(chat_id),))
        cur.execute("SELECT * FROM subscribers WHERE chat_id=%s", (str(chat_id),))
        return dict(cur.fetchone())

def list_users() -> Dict[str, dict]:
    with _get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT * FROM subscribers")
        rows = cur.fetchall()
        return {r["chat_id"]: dict(r) for r in rows}

def subscribe(chat_id: str) -> dict:
    return ensure_user(chat_id)

def unsubscribe(chat_id: str) -> None:
    with _get_conn() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM subscribers WHERE chat_id=%s", (str(chat_id),))

# ------------------ Preferencias ------------------

def set_lang(chat_id: str, lang: str) -> bool:
    lang = (lang or "").strip().lower()
    lang = _LANG_ALIAS.get(lang, lang)  # normalizamos alias
    if lang not in VALID_LANG:
        return False
    with _get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            UPDATE subscribers SET lang=%s, updated_at=now() WHERE chat_id=%s
        """, (lang, str(chat_id)))
    return True

def set_city(chat_id: str, city: Optional[str]) -> None:
    with _get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            UPDATE subscribers SET city=%s, updated_at=now() WHERE chat_id=%s
        """, (city, str(chat_id)))

def set_location(chat_id: str, lat: float, lon: float, tz: str, city_hint: Optional[str] = None) -> None:
    with _get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            UPDATE subscribers
               SET lat=%s, lon=%s, tz=%s, city=COALESCE(%s, city), updated_at=now()
             WHERE chat_id=%s
        """, (float(lat), float(lon), tz or "Europe/Madrid", city_hint, str(chat_id)))

def set_send_hour(chat_id: str, hour_local: int) -> None:
    try:
        hour_local = int(hour_local)
    except Exception:
        hour_local = 9
    hour_local = max(0, min(23, hour_local))
    with _get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            UPDATE subscribers SET send_hour_local=%s, updated_at=now() WHERE chat_id=%s
        """, (hour_local, str(chat_id)))

def set_sleep_hour(chat_id: str, hour_local: int) -> None:
    """Nueva: hora local del consejo parasimpático (por defecto 21)."""
    try:
        hour_local = int(hour_local)
    except Exception:
        hour_local = 21
    hour_local = max(0, min(23, hour_local))
    with _get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            UPDATE subscribers SET sleep_hour_local=%s, updated_at=now() WHERE chat_id=%s
        """, (hour_local, str(chat_id)))

# ------------------ Control de envío diario ------------------

def mark_sent_today(chat_id: str, local_date: date) -> None:
    with _get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            UPDATE subscribers SET last_sent_iso=%s, updated_at=now() WHERE chat_id=%s
        """, (local_date.isoformat(), str(chat_id)))

def mark_sleep_sent_today(chat_id: str, local_date: date) -> None:
    with _get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            UPDATE subscribers SET last_sleep_sent_iso=%s, updated_at=now() WHERE chat_id=%s
        """, (local_date.isoformat(), str(chat_id)))

def _should_send_generic(chat: dict, target_hour_key: str, last_key: str, now_utc: Optional[datetime] = None) -> bool:
    tzname = (chat.get("tz") or "Europe/Madrid").strip()
    hour = int(chat.get(target_hour_key, 9))
    if now_utc is None:
        now_utc = datetime.now(timezone.utc)
    try:
        tz = pytz.timezone(tzname)
    except Exception:
        tz = pytz.timezone("Europe/Madrid")
    now_local = now_utc.astimezone(tz)
    local_date = now_local.date()
    last_iso = chat.get(last_key)
    already = (last_iso == local_date.isoformat())
    in_window = (now_local.hour == hour and 0 <= now_local.minute < 10)
    return in_window and not already

def should_send_now(chat: dict, now_utc: Optional[datetime] = None) -> bool:
    """Consejo diurno (9:00 por defecto)."""
    return _should_send_generic(chat, "send_hour_local", "last_sent_iso", now_utc)

def should_send_sleep_now(chat: dict, now_utc: Optional[datetime] = None) -> bool:
    """Consejo parasimpático nocturno (21:00 por defecto)."""
    return _should_send_generic(chat, "sleep_hour_local", "last_sleep_sent_iso", now_utc)

# --------- Utilidad: obtener “tu” usuario (por chat_id) ---------

def get_user(chat_id: str) -> dict:
    with _get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT * FROM subscribers WHERE chat_id=%s", (str(chat_id),))
        row = cur.fetchone()
        return dict(row) if row else {}
