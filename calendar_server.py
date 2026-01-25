# calendar_server.py
# Servidor HTTP que expone un calendario iCal (.ics) para iPhone/iCloud.
# - No requiere schema extra.
# - Usa token firmado (HMAC) para no exponer tu chat_id públicamente sin control.
#
# Endpoints:
#   GET /health
#   GET /calendar.ics?chat_id=...&token=...
#
# Variables de entorno:
#   CAL_SECRET      (obligatoria)  -> clave para firmar tokens
#   TELEGRAM_BOT_URL (opcional)    -> ej: https://t.me/TuBot
#   PORT (Railway)  (opcional)     -> si no, 8080

import os
import hmac
import hashlib
import datetime as dt
from typing import Optional

from fastapi import FastAPI, Response, Query, HTTPException

CAL_SECRET = os.getenv("CAL_SECRET", "").strip()
TELEGRAM_BOT_URL = os.getenv("TELEGRAM_BOT_URL", "https://t.me/").strip()

app = FastAPI(title="ImmuneBot Calendar Server")


def _make_token(chat_id: str) -> str:
    """Token corto (16 hex) firmado con CAL_SECRET."""
    mac = hmac.new(CAL_SECRET.encode("utf-8"), chat_id.encode("utf-8"), hashlib.sha256).hexdigest()
    return mac[:16]


def _ics_escape(s: str) -> str:
    return (s or "").replace("\\", "\\\\").replace("\n", "\\n").replace(",", "\\,").replace(";", "\\;")


def _dt_utc(y: int, m: int, d: int, hh: int, mm: int) -> dt.datetime:
    # Nota: iPhone convertirá a hora local; para “clavar” hora local por usuario
    # más adelante lo afinaremos usando tz del usuario (v2).
    return dt.datetime(y, m, d, hh, mm, tzinfo=dt.timezone.utc)


def _build_ics(chat_id: str, days: int = 30) -> str:
    today = dt.date.today()
    # Por ahora: 2 eventos diarios genéricos (9:00 y 21:00).
    # Más adelante: podemos meter texto del consejo real + ventanas solares + tz por usuario.
    lines = []
    lines.append("BEGIN:VCALENDAR")
    lines.append("VERSION:2.0")
    lines.append("PRODID:-//Consejos Inmunes//Calendar//ES")
    lines.append("CALSCALE:GREGORIAN")
    lines.append("METHOD:PUBLISH")
    lines.append("X-WR-CALNAME:Consejos Inmunes (Bot)")
    lines.append("X-WR-TIMEZONE:Europe/Madrid")

    now = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    for i in range(days):
        d = today + dt.timedelta(days=i)

        # Evento 9:00
        uid1 = f"immune-{chat_id}-{d.isoformat()}@consejos-inmunes"
        dtstart1 = _dt_utc(d.year, d.month, d.day, 8, 0)   # aproximación: 9:00 Madrid ~ 8:00 UTC (dependiendo DST)
        dtend1   = _dt_utc(d.year, d.month, d.day, 8, 10)

        # Evento 21:00
        uid2 = f"sleep-{chat_id}-{d.isoformat()}@consejos-inmunes"
        dtstart2 = _dt_utc(d.year, d.month, d.day, 19, 0)  # aproximación: 21:00 Madrid ~ 19:00 UTC (dependiendo DST)
        dtend2   = _dt_utc(d.year, d.month, d.day, 19, 10)

        # 9:00
        lines.append("BEGIN:VEVENT")
        lines.append(f"UID:{uid1}")
        lines.append(f"DTSTAMP:{now}")
        lines.append(f"DTSTART:{dtstart1.strftime('%Y%m%dT%H%M%SZ')}")
        lines.append(f"DTEND:{dtend1.strftime('%Y%m%dT%H%M%SZ')}")
        lines.append("SUMMARY:" + _ics_escape("Consejo inmune del día (ver Telegram)"))
        lines.append("DESCRIPTION:" + _ics_escape(f"Abre el bot para ver el consejo: {TELEGRAM_BOT_URL}"))
        lines.append("END:VEVENT")

        # 21:00
        lines.append("BEGIN:VEVENT")
        lines.append(f"UID:{uid2}")
        lines.append(f"DTSTAMP:{now}")
        lines.append(f"DTSTART:{dtstart2.strftime('%Y%m%dT%H%M%SZ')}")
        lines.append(f"DTEND:{dtend2.strftime('%Y%m%dT%H%M%SZ')}")
        lines.append("SUMMARY:" + _ics_escape("Consejo parasimpático (ver Telegram)"))
        lines.append("DESCRIPTION:" + _ics_escape(f"Abre el bot para ver el consejo: {TELEGRAM_BOT_URL}"))
        lines.append("END:VEVENT")

    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/calendar.ics")
def calendar_ics(
    chat_id: str = Query(...),
    token: str = Query(...),
    days: int = Query(30, ge=7, le=180),
):
    if not CAL_SECRET:
        raise HTTPException(status_code=500, detail="CAL_SECRET no configurado")

    expected = _make_token(str(chat_id))
    if token != expected:
        raise HTTPException(status_code=403, detail="Token inválido")

    ics = _build_ics(str(chat_id), days=days)
    return Response(content=ics, media_type="text/calendar; charset=utf-8")