# enviar_consejo.py  — versión multiusuario con traducción de intervalos

import os
import asyncio
import random
import datetime

from telegram import Bot
from geopy.geocoders import Nominatim
from timezonefinder import TimezoneFinder
from deep_translator import LibreTranslator

from consejos_diarios import consejos
from usuarios_repo import get_all_users   # Debe devolver lista de dicts: {"chat_id","lang","city"}
from ubicacion_y_sol import (
    calcular_intervalos_optimos,   # si ya migraste a 30–40°, cambia por calcular_intervalos_30_40
    describir_intervalos,          # genera texto (ES) para los tramos
)

# ──────────────────────────────────────────────────────────────────────────────
# Utilidades
# ──────────────────────────────────────────────────────────────────────────────

def _normaliza_idioma(code: str) -> str:
    """Normaliza códigos de idioma; mapea alias comunes a ISO-2."""
    if not code:
        return "es"
    code = code.strip().lower()
    alias = {
        "sh": "sr",  # serbocroata → serbio (proxy)
        "sc": "sr",
        "srp": "sr",
        "cro": "hr",
        "ser": "sr",
        "bos": "bs",
        "pt-br": "pt",
    }
    return alias.get(code, code)

def traducir(texto: str, lang_destino: str) -> str:
    """Traduce desde ES a lang_destino. Si ya es 'es' o falla, devuelve original."""
    dest = _normaliza_idioma(lang_destino)
    if dest == "es":
        return texto
    try:
        tr = LibreTranslator(source="es", target=dest)
        return tr.translate(texto)
    except Exception as e:
        print(f"[WARN] Traducción fallida a '{dest}': {e}")
        return texto

def geolocalizar_ciudad(ciudad: str):
    """
    Devuelve (lat, lon, timezone_str, nombre_mostrable) para una ciudad.
    Si falla, usa Málaga como reserva.
    """
    if not ciudad:
        ciudad = "Málaga"

    try:
        geolocator = Nominatim(user_agent="bot_inmune_diario_multi")
        loc = geolocator.geocode(ciudad)
        if not loc:
            raise ValueError("Ciudad no encontrada")

        lat, lon = loc.latitude, loc.longitude
        tf = TimezoneFinder()
        tz = tf.timezone_at(lat=lat, lng=lon) or "Europe/Madrid"
        nombre = loc.address.split(",")[0] if loc.address else ciudad
        print(f"✅ Geolocalizada {ciudad} -> ({lat:.4f}, {lon:.4f}), tz={tz}")
        return lat, lon, tz, nombre
    except Exception as e:
        print(f"⚠️ Geolocalización fallida para '{ciudad}': {e}. Usando Málaga por defecto.")
        # Fallback Málaga
        lat, lon = 36.7213028, -4.4216366
        tz, nombre = "Europe/Madrid", "Málaga"
        return lat, lon, tz, nombre

# ──────────────────────────────────────────────────────────────────────────────
# Consejo base del día (ES)
# ──────────────────────────────────────────────────────────────────────────────

def consejo_y_referencia_del_dia() -> tuple[str, str]:
    """Selecciona aleatoriamente un bloque (consejo + ref) del día (ES)."""
    idx_dia = datetime.datetime.now().weekday()  # 0=lun .. 6=dom
    pares = consejos[idx_dia]
    indices = list(range(0, len(pares), 2))
    idx = random.choice(indices)
    return pares[idx], pares[idx + 1]

# ──────────────────────────────────────────────────────────────────────────────
# Envío por Telegram a un usuario
# ──────────────────────────────────────────────────────────────────────────────

BOT_TOKEN = os.getenv("BOT_TOKEN")

async def enviar_a_usuario(bot: Bot, user: dict, base_consejo: str, base_ref: str):
    """
    Envía el mensaje a un usuario:
      user = {"chat_id": "...", "lang": "es|en|ru|sr|...", "city": "Málaga|Zagreb|..."}
    """
    chat_id = str(user.get("chat_id", "")).strip()
    if not chat_id:
        print("⛔ Usuario sin chat_id. Saltando…")
        return

    lang = _normaliza_idioma(user.get("lang", "es"))
    ciudad_pedida = user.get("city", "Málaga")

    # Ubicación por ciudad del usuario
    lat, lon, tz, ciudad_mostrar = geolocalizar_ciudad(ciudad_pedida)

    # Intervalos solares (si ya tienes la versión 30–40°, usa esa función en su lugar)
    fecha = datetime.date.today()
    tramos = calcular_intervalos_optimos(lat, lon, fecha, tz)  # <- sustituye por calcular_intervalos_30_40 si toca
    texto_intervalos_es = describir_intervalos(tramos, ciudad_mostrar)  # texto en español
    texto_intervalos_tr = traducir(texto_intervalos_es, lang)           # traducimos también los intervalos

    # Traducción consejo + referencia al idioma del usuario
    consejo_t = traducir(base_consejo, lang)
    ref_t     = traducir(base_ref, lang)

    # Mensaje final
    mensaje = f"{consejo_t}\n\n{ref_t}\n\n{texto_intervalos_tr}"

    try:
        await bot.send_message(chat_id=chat_id, text=mensaje)
        print(f"📤 Enviado a {chat_id} ({ciudad_mostrar}, {lang})")
    except Exception as e:
        print(f"❌ Error enviando a {chat_id}: {e}")

# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────

async def main():
    if not BOT_TOKEN:
        print("❌ FALTA BOT_TOKEN en variables de entorno.")
        return

    usuarios = get_all_users()
    if not usuarios:
        print("⚠️ No hay usuarios en usuarios_repo.get_all_users(). Nada que enviar.")
        return

    base_consejo, base_ref = consejo_y_referencia_del_dia()
    bot = Bot(token=BOT_TOKEN)

    # Enviar secuencialmente (puedes paralelizar con gather si es necesario)
    for u in usuarios:
        await enviar_a_usuario(bot, u, base_consejo, base_ref)
        await asyncio.sleep(0.4)  # pequeño respiro para evitar rate limits

if __name__ == "__main__":
    asyncio.run(main())
