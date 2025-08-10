# usuarios_repo.py
# Gestión sencilla de usuarios en JSON + lógica de envío a las 9:00 locales (ventana 10 min)

import json
from pathlib import Path
from typing import Dict, Optional, Any
from datetime import datetime, date, timezone
import re
import pytz

USUARIOS_FILE = Path("usuarios.json")
VALID_LANG = {"es", "en", "fr", "it", "de", "pt", "nl", "ru", "sr", "hr", "bs", "sh"}

# ----------------- Utilidades básicas de almacenamiento -----------------

def _load_raw() -> Dict[str, Any]:
    if not USUARIOS_FILE.exists():
        return {"suscriptores": {}}
    with USUARIOS_FILE.open("r", encoding="utf-8") as f:
        return json.load(f)

def _save_raw(data: Dict[str, Any]) -> None:
    USUARIOS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def list_users() -> Dict[str, dict]:
    return _load_raw().get("suscriptores", {})

def ensure_user(chat_id: str) -> dict:
    data = _load_raw()
    sus = data.setdefault("suscriptores", {})
    u = sus.setdefault(chat_id, {
        "lang": "es",            # idioma (ISO-2)
        "city": None,            # nombre ciudad (opcional si hay lat/lon)
        "lat": None,             # float
        "lon": None,             # float
        "tz": "Europe/Madrid",   # zona horaria
        "last_sent_iso": None,   # fecha local (ISO) del último envío
        "send_hour_local": 9     # hora local preferida (0-23)
    })
    _save_raw(data)
    return u

def subscribe(chat_id: str) -> dict:
    return ensure_user(chat_id)

def unsubscribe(chat_id: str) -> None:
    data = _load_raw()
    if chat_id in data.get("suscriptores", {}):
        del data["suscriptores"][chat_id]
        _save_raw(data)

# ----------------- Preferencias del usuario -----------------

def set_lang(chat_id: str, lang: str) -> bool:
    lang = (lang or "").lower().strip()
    if not re.fullmatch(r"[a-z]{2}", lang):
        return False
    u = ensure_user(chat_id)
    u["lang"] = lang
    data = _load_raw()
    data["suscriptores"][chat_id] = u
    _save_raw(data)
    return True

def set_city(chat_id: str, city: Optional[str]) -> None:
    u = ensure_user(chat_id)
    u["city"] = city
    data = _load_raw()
    data["suscriptores"][chat_id] = u
    _save_raw(data)

def set_location(chat_id: str, lat: float, lon: float, tz: str, city_hint: Optional[str] = None) -> None:
    u = ensure_user(chat_id)
    u["lat"] = float(lat)
    u["lon"] = float(lon)
    u["tz"] = tz or "Europe/Madrid"
    if city_hint:
        u["city"] = city_hint
    data = _load_raw()
    data["suscriptores"][chat_id] = u
    _save_raw(data)

def set_send_hour(chat_id: str, hour_local: int) -> None:
    try:
        hour_local = int(hour_local)
    except Exception:
        hour_local = 9
    hour_local = max(0, min(23, hour_local))
    u = ensure_user(chat_id)
    u["send_hour_local"] = hour_local
    data = _load_raw()
    data["suscriptores"][chat_id] = u
    _save_raw(data)

# ----------------- Control de envío diario -----------------

def mark_sent_today(chat_id: str, local_date: date) -> None:
    u = ensure_user(chat_id)
    u["last_sent_iso"] = local_date.isoformat()
    data = _load_raw()
    data["suscriptores"][chat_id] = u
    _save_raw(data)

def should_send_now(chat: dict, now_utc: Optional[datetime] = None) -> bool:
    """
    Lógica para ejecutar el cron cada 5 min:
      - Convierte now_utc a hora local del usuario (chat["tz"])
      - Envía si: local_hour == send_hour_local y 0<=min<10 (ventana 10 min)
      - Y si aún no se envió hoy (comparando fecha local con last_sent_iso)
    """
    tzname = chat.get("tz") or "Europe/Madrid"
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

# ----------------- Migración segura de estructuras antiguas -----------------

def migrate_fill_defaults() -> None:
    """
    Añade campos que falten a usuarios existentes. Idempotente.
    """
    data = _load_raw()
    sus = data.setdefault("suscriptores", {})
    changed = False
    for uid, u in sus.items():
        if "lang" not in u: u["lang"] = "es"; changed = True
        if "city" not in u: u["city"] = None; changed = True
        if "lat" not in u: u["lat"] = None; changed = True
        if "lon" not in u: u["lon"] = None; changed = True
        if "tz" not in u: u["tz"] = "Europe/Madrid"; changed = True
        if "last_sent_iso" not in u: u["last_sent_iso"] = None; changed = True
        if "send_hour_local" not in u: u["send_hour_local"] = 9; changed = True
    if changed:
        _save_raw(data)
