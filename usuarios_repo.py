# usuarios_repo.py (backend en Postgres)
# Guarda suscriptores/ajustes en Postgres: durable y compartido.

from __future__ import annotations
import os
import json
import re
from datetime import datetime, date, timezone
from typing import Dict, Any, Optional

import psycopg2
import psycopg2.extras
import pytz

VALID_LANG = {"es", "en", "fr", "it", "de", "pt", "nl"}

# ------------------ conexión ------------------

def _get_conn():
    url = os.getenv("DATABASE_DSN")
    if not url:
        raise RuntimeError("DATABASE_DSN no está definida")
    # habilitamos autocommmit para DDL sencillo
    conn = psycopg2.connect(url, sslmode="require")
    conn.autocommit = True
    return conn

def init_db() -> None:
    """Crea tablas si no existen (idempotente). Llamar al arrancar."""
    sql = """
    CREATE TABLE IF NOT EXISTS subscribers (
        chat_id        TEXT PRIMARY KEY,
        lang           TEXT NOT NULL DEFAULT 'es',
        city           TEXT,
        lat            DOUBLE PRECISION,
        lon            DOUBLE PRECISION,
        tz             TEXT NOT NULL DEFAULT 'Europe/Madrid',
        last_sent_iso  TEXT,
        send_hour_local INTEGER NOT NULL DEFAULT 9,
        created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    CREATE INDEX IF NOT EXISTS idx_subs_tz ON subscribers (tz);
    """
    with _get_conn() as conn, conn.cursor() as cur:
        cur.execute(sql)

def _row_to_dict(row) -> dict:
    if not row:
        return {}
    keys = [desc.name for desc in row.cursor_description] if hasattr(row, "cursor_description") else None
    if isinstance(row, dict):
        return dict(row)
    if hasattr(row, "keys"):
        return dict(row)
    # psycopg2 cursor default -> tuple; usamos extras para dict. Por si acaso:
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
    lang = (lang or "").lower().strip()
    if not re.fullmatch(r"[a-z]{2}", lang):
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

# ------------------ Control de envío diario ------------------

def mark_sent_today(chat_id: str, local_date: date) -> None:
    with _get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            UPDATE subscribers SET last_sent_iso=%s, updated_at=now() WHERE chat_id=%s
        """, (local_date.isoformat(), str(chat_id)))

def should_send_now(chat: dict, now_utc: Optional[datetime] = None) -> bool:
    """
    Para el cron cada 5 min:
      - Convierte now_utc a hora local del usuario (chat["tz"])
      - Envía si: local_hour == send_hour_local y 0<=min<10 (ventana 10 min)
      - Y si aún no se envió hoy (comparando fecha local con last_sent_iso)
    """
    tzname = (chat.get("tz") or "Europe/Madrid").strip()
    send_hour = int(chat.get("send_hour_local", 9))

    if now_utc is None:
        now_utc = datetime.now(timezone.utc)
    try:
        tz = pytz.timezone(tzname)
    except Exception:
        tz = pytz.timezone("Europe/Madrid")
        tzname = "Europe/Madrid"

    now_local = now_utc.astimezone(tz)
    local_date = now_local.date()
    last_sent_iso = chat.get("last_sent_iso")
    already_sent_today = (last_sent_iso == local_date.isoformat())
    in_window = (now_local.hour == send_hour and 0 <= now_local.minute < 10)
    return in_window and not already_sent_today

# --------- Utilidad: obtener “tu” usuario (por chat_id) ---------

def get_user(chat_id: str) -> dict:
    with _get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT * FROM subscribers WHERE chat_id=%s", (str(chat_id),))
        row = cur.fetchone()
        return dict(row) if row else {}

def migrate_fill_defaults() -> None:
    """
    Migración idempotente para asegurar columnas esperadas en 'subscribers'.
    No falla si ya existen.
    """
    with _get_conn() as conn, conn.cursor() as cur:
        cur.execute("ALTER TABLE IF EXISTS subscribers ADD COLUMN IF NOT EXISTS lang TEXT NOT NULL DEFAULT 'es';")
        cur.execute("ALTER TABLE IF EXISTS subscribers ADD COLUMN IF NOT EXISTS city TEXT;")
        cur.execute("ALTER TABLE IF EXISTS subscribers ADD COLUMN IF NOT EXISTS lat DOUBLE PRECISION;")
        cur.execute("ALTER TABLE IF EXISTS subscribers ADD COLUMN IF NOT EXISTS lon DOUBLE PRECISION;")
        cur.execute("ALTER TABLE IF EXISTS subscribers ADD COLUMN IF NOT EXISTS tz TEXT NOT NULL DEFAULT 'Europe/Madrid';")
        cur.execute("ALTER TABLE IF EXISTS subscribers ADD COLUMN IF NOT EXISTS last_sent_iso TEXT;")
        cur.execute("ALTER TABLE IF EXISTS subscribers ADD COLUMN IF NOT EXISTS send_hour_local INTEGER NOT NULL DEFAULT 9;")
        cur.execute("ALTER TABLE IF EXISTS subscribers ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT now();")
        cur.execute("ALTER TABLE IF EXISTS subscribers ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now();")
        # Índice útil si no existe
        cur.execute("CREATE INDEX IF NOT EXISTS idx_subs_tz ON subscribers (tz);")
