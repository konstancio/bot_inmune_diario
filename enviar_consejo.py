# enviar_consejo.py
# Cron cada 5 min: envía el consejo diario cuando should_send_now(chat) sea True.

from __future__ import annotations

import os
import random
import datetime as dt
import logging
import requests

import usuarios_repo as repo

from ubicacion_y_sol import (
    calcular_intervalos_30_40,
    describir_intervalos_y_mediodia,
    obtener_pronostico_diario,
    formatear_meteo_en_tramos,
)

from consejos_diarios import CONSEJOS_DIARIOS  # tu contenido

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("enviar_consejo")

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("❌ Falta BOT_TOKEN en variables de entorno")

def tg_send(chat_id: str, text: str) -> None:
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    r = requests.post(
        url,
        json={"chat_id": str(chat_id), "text": text, "disable_web_page_preview": True},
        timeout=20,
    )
    r.raise_for_status()

def weekday_es(d: dt.date) -> str:
    return ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"][d.weekday()]

def _coerce_single_text(item) -> str:
    """
    Evita el desastre de Telegram mostrando listas/dicts.
    """
    if item is None:
        return ""
    if isinstance(item, str):
        return item.strip()
    if isinstance(item, dict):
        txt = (item.get("texto") or item.get("text") or "").strip()
        ref = (item.get("referencia") or item.get("ref") or "").strip()
        parts = []
        if txt:
            parts.append(txt)
        if ref:
            parts.append(f"📚 Referencia: {ref}")
        return "\n\n".join(parts).strip()
    # si viene una lista/tupla, elige un elemento y vuelve a convertir
    if isinstance(item, (list, tuple)):
        if not item:
            return ""
        return _coerce_single_text(random.choice(list(item)))
    return str(item).strip()

def pick_consejo(local_date: dt.date) -> str:
    """
    Soporta:
    - dict por día ("Lunes"...)-> list[str|dict]
    - list[str|dict]
    """
    if isinstance(CONSEJOS_DIARIOS, dict):
        k = weekday_es(local_date)
        bucket = CONSEJOS_DIARIOS.get(k) or CONSEJOS_DIARIOS.get(k.lower())
        if bucket is None:
            # fallback: cualquier bucket
            bucket = next(iter(CONSEJOS_DIARIOS.values()))
        return _coerce_single_text(bucket)

    if isinstance(CONSEJOS_DIARIOS, list):
        return _coerce_single_text(CONSEJOS_DIARIOS)

    return _coerce_single_text(CONSEJOS_DIARIOS)

def maybe_add_header(local_date: dt.date, consejo: str) -> str:
    """
    Si el consejo YA trae un encabezado tipo "Consejo para hoy",
    no añadimos otro.
    """
    low = consejo.lower()
    if "consejo para hoy" in low:
        return consejo.strip()
    return f"🧠 Consejo para hoy ({weekday_es(local_date)}):\n{consejo}".strip()

def main():
    # Asegura tabla/columnas (idempotente)
    try:
        repo.init_db()
        repo.migrate_fill_defaults()
    except Exception as e:
        logger.warning(f"[WARN] init_db/migrate: {e}")

    chats = repo.list_users()  # dict {chat_id: chat_dict}
    if not chats:
        logger.info("No hay usuarios en subscribers.")
        return

    now_utc = dt.datetime.now(dt.timezone.utc)

    for chat_id, chat in chats.items():
        chat_id = str(chat_id)
        try:
            # 1) ¿toca enviar ahora?
            if not repo.should_send_now(chat, now_utc=now_utc):
                continue

            # 2) Fecha local del usuario (usando su tz)
            tzname = (chat.get("tz") or "Europe/Madrid").strip() or "Europe/Madrid"
            try:
                import pytz
                tz = pytz.timezone(tzname)
            except Exception:
                import pytz
                tz = pytz.timezone("Europe/Madrid")
                tzname = "Europe/Madrid"

            local_date = now_utc.astimezone(tz).date()

            # 3) Ubicación efectiva (temporal si procede)
            lat, lon, tz_eff, city, is_temp = repo.get_effective_location(chat, now_utc=now_utc)
            city = city or "tu ciudad"
            tz_eff = (tz_eff or tzname).strip() or tzname

            consejo = pick_consejo(local_date)
            consejo = maybe_add_header(local_date, consejo)

            # Si no hay coords, enviamos solo consejo y recordatorio
            if lat is None or lon is None:
                msg = (
                    f"{consejo}\n\n"
                    f"📍 No tengo GPS configurado.\n"
                    f"Usa /setloc lat lon tz [Ciudad] o una ubicación temporal (si la tienes implementada)."
                )
                tg_send(chat_id, msg)
                repo.mark_sent_today(chat_id, local_date)
                continue

            lat = float(lat); lon = float(lon)

            # 4) Sol + mediodía solar + altura máxima
            tramos = calcular_intervalos_30_40(lat, lon, local_date, tz_eff)
            bloque_sol = describir_intervalos_y_mediodia(lat, lon, local_date, tz_eff, city)

            # 5) Meteo (si disponible)
            hourly = obtener_pronostico_diario(local_date, lat, lon, tz_eff)
            bloque_meteo = formatear_meteo_en_tramos(tramos, hourly)

            # 6) Nota si es ubicación temporal
            nota_loc = ""
            if is_temp:
                nota_loc = "\n\n📍 Ubicación temporal activa (viaje)."

            msg = consejo + "\n\n" + bloque_sol
            if bloque_meteo:
                msg += "\n" + bloque_meteo
            if nota_loc:
                msg += nota_loc

            tg_send(chat_id, msg)
            repo.mark_sent_today(chat_id, local_date)

            logger.info(f"✅ Enviado a {chat_id} ({city}) {local_date.isoformat()} tz={tz_eff}")

        except Exception as e:
            logger.exception(f"❌ Error enviando a {chat_id}: {e}")

if __name__ == "__main__":
    main()
