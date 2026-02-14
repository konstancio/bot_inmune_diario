# enviar_consejo.py
# Cron cada 5 min: envía el consejo diario cuando should_send_now(chat) sea True.
# Variables útiles:
# - FORCE_SEND=1 -> ignora la ventana horaria (envía ahora)
# - FORCE_TODAY=1 -> ignora "ya enviado hoy" (solo tiene sentido con FORCE_SEND)

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

FORCE_SEND = (os.getenv("FORCE_SEND") or "").strip() == "1"
FORCE_TODAY = (os.getenv("FORCE_TODAY") or "").strip() == "1"


def tg_send(chat_id: str, text: str) -> None:
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    r = requests.post(
        url,
        json={"chat_id": str(chat_id), "text": text, "disable_web_page_preview": True},
        timeout=20,
    )
    if r.status_code >= 400:
        logger.error(f"Telegram error {r.status_code}: {r.text[:300]}")
    r.raise_for_status()


def weekday_es(d: dt.date) -> str:
    return ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"][d.weekday()]


def _coerce_single_text(item) -> str:
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

    if isinstance(item, (list, tuple)):
        if not item:
            return ""
        return _coerce_single_text(random.choice(list(item)))

    return str(item).strip()


def pick_consejo(local_date: dt.date) -> str:
    """
    Usa weekday() (0=Lunes ... 6=Domingo)
    porque CONSEJOS_DIARIOS usa claves numéricas.
    """
    idx = local_date.weekday()  # 0..6

    if isinstance(CONSEJOS_DIARIOS, dict):
        bucket = CONSEJOS_DIARIOS.get(idx)
        if not bucket:
            bucket = next(iter(CONSEJOS_DIARIOS.values()))
        return _coerce_single_text(bucket)

    if isinstance(CONSEJOS_DIARIOS, list):
        return _coerce_single_text(CONSEJOS_DIARIOS)

    return _coerce_single_text(CONSEJOS_DIARIOS)


def maybe_add_header(local_date: dt.date, consejo: str) -> str:
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

    chats = repo.list_users()
    if not chats:
        logger.info("No hay usuarios en subscribers.")
        return

    now_utc = dt.datetime.now(dt.timezone.utc)

    for chat_id, chat in chats.items():
        chat_id = str(chat_id)

        try:
            # TZ del usuario (para fecha local y chequeo "ya enviado")
            tzname = (chat.get("tz") or "Europe/Madrid").strip() or "Europe/Madrid"
            try:
                import pytz
                tz = pytz.timezone(tzname)
            except Exception:
                import pytz
                tz = pytz.timezone("Europe/Madrid")
                tzname = "Europe/Madrid"

            local_date = now_utc.astimezone(tz).date()
            already = (chat.get("last_sent_iso") == local_date.isoformat())

            # 1) ¿toca enviar ahora?
            if not FORCE_SEND:
                if not repo.should_send_now(chat, now_utc=now_utc):
                    logger.info(f"[SKIP] {chat_id} no está en ventana horaria (tz={tzname})")
                    continue
            else:
                # force_send
                if already and not FORCE_TODAY:
                    logger.info(f"[SKIP] {chat_id} FORCE_SEND pero ya enviado hoy ({local_date.isoformat()})")
                    continue

            # 2) Ubicación efectiva (temporal si procede)
            lat, lon, tz_eff, city, is_temp = repo.get_effective_location(chat, now_utc=now_utc)
            city = city or "tu ciudad"
            tz_eff = (tz_eff or tzname).strip() or tzname

            consejo = maybe_add_header(local_date, pick_consejo(local_date))

            # Si no hay coords, enviamos solo consejo y recordatorio
            if lat is None or lon is None:
                msg = (
                    f"{consejo}\n\n"
                    f"📍 No tengo GPS configurado.\n"
                    f"Usa /setloc lat lon tz [Ciudad] o define una ubicación temporal."
                )
                tg_send(chat_id, msg)
                repo.mark_sent_today(chat_id, local_date)
                logger.info(f"✅ Enviado SIN GPS a {chat_id} ({city}) {local_date.isoformat()} tz={tz_eff}")
                continue

            lat = float(lat)
            lon = float(lon)

            # 3) Sol + mediodía solar
            tramos = calcular_intervalos_30_40(lat, lon, local_date, tz_eff)
            bloque_sol = describir_intervalos_y_mediodia(lat, lon, local_date, tz_eff, city)

            # 4) Meteo
            hourly = obtener_pronostico_diario(local_date, lat, lon, tz_eff)
            bloque_meteo = formatear_meteo_en_tramos(tramos, hourly, tz_eff)

            # 5) Nota si es ubicación temporal
            nota_loc = "\n\n📍 Ubicación temporal activa (viaje)." if is_temp else ""

            msg = consejo + "\n\n" + bloque_sol
            if bloque_meteo:
                msg += bloque_meteo
            msg += nota_loc

            tg_send(chat_id, msg)
            repo.mark_sent_today(chat_id, local_date)

            logger.info(f"✅ Enviado a {chat_id} ({city}) {local_date.isoformat()} tz={tz_eff}")

        except Exception as e:
            logger.exception(f"❌ Error enviando a {chat_id}: {e}")


if __name__ == "__main__":
    main()
