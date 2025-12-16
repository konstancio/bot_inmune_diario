# solar_repo.py
# Histórico diario de ventanas solares por usuario (flexible a cualquier ciudad/latitud).
# Requiere: DATABASE_DSN en variables de entorno (igual que usuarios_repo.py)

from __future__ import annotations

import os
import datetime as dt
from typing import Optional, Tuple

import psycopg2

Tramo = Optional[Tuple[dt.datetime, dt.datetime]]


def _get_conn():
    dsn = os.getenv("DATABASE_DSN")
    if not dsn:
        raise RuntimeError("DATABASE_DSN no está definida")
    return psycopg2.connect(dsn)


def init_solar_history() -> None:
    """
    Crea la tabla solar_history si no existe.
    PK (chat_id, date_local) => 1 fila por usuario y día local.
    """
    with _get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
        CREATE TABLE IF NOT EXISTS solar_history (
            chat_id TEXT NOT NULL,
            date_local DATE NOT NULL,
            city TEXT,
            lat DOUBLE PRECISION,
            lon DOUBLE PRECISION,
            tz TEXT,

            has_30_40 BOOLEAN NOT NULL,
            meteo_ok BOOLEAN NOT NULL,
            reason TEXT NOT NULL,  -- 'ok' | 'meteo' | 'latitud'

            morning_start TIMESTAMPTZ,
            morning_end   TIMESTAMPTZ,
            afternoon_start TIMESTAMPTZ,
            afternoon_end   TIMESTAMPTZ,

            created_at TIMESTAMPTZ DEFAULT now(),
            PRIMARY KEY (chat_id, date_local)
        );
        """)
    print("✅ init_solar_history: tabla solar_history lista.")


def upsert_solar_history(
    chat_id: str,
    date_local: dt.date,
    city: Optional[str],
    lat: Optional[float],
    lon: Optional[float],
    tz: Optional[str],
    has_30_40: bool,
    meteo_ok: bool,
    reason: str,
    tramo_m: Tramo,
    tramo_t: Tramo,
) -> None:
    """
    Guarda/actualiza el histórico del día.
    - reason debe ser: 'ok' | 'meteo' | 'latitud'
    """
    m_start = m_end = t_start = t_end = None
    if tramo_m:
        m_start, m_end = tramo_m
    if tramo_t:
        t_start, t_end = tramo_t

    with _get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
        INSERT INTO solar_history (
            chat_id, date_local, city, lat, lon, tz,
            has_30_40, meteo_ok, reason,
            morning_start, morning_end, afternoon_start, afternoon_end
        )
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (chat_id, date_local) DO UPDATE SET
            city = EXCLUDED.city,
            lat = EXCLUDED.lat,
            lon = EXCLUDED.lon,
            tz = EXCLUDED.tz,
            has_30_40 = EXCLUDED.has_30_40,
            meteo_ok = EXCLUDED.meteo_ok,
            reason = EXCLUDED.reason,
            morning_start = EXCLUDED.morning_start,
            morning_end = EXCLUDED.morning_end,
            afternoon_start = EXCLUDED.afternoon_start,
            afternoon_end = EXCLUDED.afternoon_end;
        """, (
            str(chat_id), date_local, city, lat, lon, tz,
            bool(has_30_40), bool(meteo_ok), str(reason),
            m_start, m_end, t_start, t_end
        ))
    print(f"🗓️ solar_history guardado: chat_id={chat_id} date={date_local} reason={reason}")