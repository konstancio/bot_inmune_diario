
# enviar_consejo.py — envío diario (multiusuario) con ventanas 30–40°, meteo y mediodía solar

from __future__ import annotations

import os
import asyncio
import datetime as dt
from typing import Any, Dict, Optional, Tuple, Union

import pytz
from telegram import Bot

import usuarios_repo as repo

from ubicacion_y_sol import (
    geocodificar_ciudad,
    obtener_ubicacion_servidor_fallback,
    calcular_intervalos_30_40,
    describir_intervalos_30_40,
    calcular_mediodia_solar,
    obtener_pronostico_diario,
    resumen_meteo_en_intervalos,
    hay_mucha_nube,
)

from consejos_diarios import CONSEJOS_DIARIOS  # <-- ajusta si tu constante se llama distinto

BOT_TOKEN = os.getenv("BOT_TOKEN")
ONLY_CHAT_ID = os.getenv("ONLY_CHAT_ID")  # opcional para pruebas


# ----------------------------
# 1) Normalizar consejo (evita “listas” impresas y duplicados raros)
# ----------------------------
def _normaliza_consejo(item: Any) -> Tuple[str, str]:
    """
    Devuelve (texto, referencia) SIEMPRE como strings.
    Acepta:
      - dict con claves típicas
      - tuple/list (texto, ref)
      - string simple
      - lista de dicts/strings -> se queda con el primero
    """
    if item is None:
        return ("(Consejo no disponible)", "")

    # Si viene una lista (lo que te estaba pasando), nos quedamos con 1
    if isinstance(item, list) and item:
        item = item[0]

    if isinstance(item, dict):
        texto = (
            item.get("texto")
            or item.get("consejo")
            or item.get("tip")
            or item.get("message")
            or ""
        )
        ref = item.get("ref") or item.get("referencia") or item.get("citation") or ""
        return (str(texto).strip(), str(ref).strip())

    if isinstance(item, (tuple, list)) and len(item) >= 2:
        return (str(item[0]).strip(), str(item[1]).strip())

    # string plano
    return (str(item).strip(), "")


def elegir_consejo_para_fecha(chat_id: str, fecha_local: dt.date) -> Tuple[str, str]:
    """
    Selección determinista: un consejo por usuario y día.
    Sea como sea tu estructura de CONSEJOS_DIARIOS, lo normalizamos.
    """
    # índice determinista estable
    idx = (hash(chat_id) + fecha_local.toordinal()) % max(1, len(CONSEJOS_DIARIOS))
    item = CONSEJOS_DIARIOS[idx]
    texto, ref = _normaliza_consejo(item)

    # “cinturón y tirantes”: evita textos vacíos
    if not texto:
        texto = "(Consejo no disponible)"
    return texto, ref


# ----------------------------
# 2) Resolución de ubicación POR USUARIO
# ----------------------------
def resolver_ubicacion_usuario(prefs: Dict[str, Any]) -> Tuple[float, float, str, str]:
    """
    Devuelve (lat, lon, tzname, ciudad)
    Prioridad:
      1) lat/lon/tz guardados en DB
      2) geocoding por city
      3) fallback servidor (último recurso)
    """
    lat = prefs.get("lat")
    lon = prefs.get("lon")
    tzname = (prefs.get("tz") or "").strip() or None
    ciudad = (prefs.get("city") or "").strip() or None

    # 1) GPS persistente (DB)
    if isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
        tzname = tzname or "Europe/Madrid"
        ciudad = ciudad or "tu zona"
        return float(lat), float(lon), tzname, ciudad

    # 2) ciudad -> geocode
    if ciudad:
        g = geocodificar_ciudad(ciudad)
        if g:
            return float(g["latitud"]), float(g["longitud"]), g.get("timezone") or "Europe/Madrid", g.get("ciudad") or ciudad

    # 3) fallback servidor
    fb = obtener_ubicacion_servidor_fallback()
    return fb["latitud"], fb["longitud"], fb["timezone"], fb["ciudad"]


# ----------------------------
# 3) Construcción del mensaje diario
# ----------------------------
def construir_mensaje_diario(
    chat_id: str,
    prefs: Dict[str, Any],
    now_utc: dt.datetime,
) -> str:
    lat, lon, tzname, ciudad = resolver_ubicacion_usuario(prefs)
    tz = pytz.timezone(tzname)
    hoy_local = now_utc.astimezone(tz).date()

    texto_consejo, ref = elegir_consejo_para_fecha(chat_id, hoy_local)

    # Ventanas 30–40°
    intervalos = calcular_intervalos_30_40(lat, lon, hoy_local, tzname, paso_min=1)
    texto_intervalos = describir_intervalos_30_40(intervalos, ciudad)

    # Mediodía solar (máxima elevación)
    t_noon, elev_max = calcular_mediodia_solar(lat, lon, hoy_local, tzname, paso_min=1)
    linea_noon = f"🧭 Mediodía solar: {t_noon.strftime('%H:%M')} (altura máx ≈ {elev_max:.1f}°)"

    # Meteo (nubes/lluvia) SOLO en las ventanas 30–40
    hourly = obtener_pronostico_diario(hoy_local, lat, lon, tzname)
    nubes, lluvia = resumen_meteo_en_intervalos(intervalos, hourly)

    aviso_meteo = ""
    if nubes is not None:
        # Mensaje claro: la ventana existe físicamente, pero la nubosidad puede fastidiar UVB
        if hay_mucha_nube(nubes):
            aviso_meteo = (
                f"\n☁️ En esas ventanas se espera nubosidad alta (≈ {nubes}%"
                + (f", lluvia {lluvia}%" if lluvia is not None else "")
                + "). Puede reducir la síntesis de vitamina D."
            )
        else:
            aviso_meteo = (
                f"\n⛅️ En esas ventanas: nubes ≈ {nubes}%"
                + (f", lluvia {lluvia}%" if lluvia is not None else "")
                + "."
            )

    # Consejo nutricional “de invierno” solo si NO hay ventanas 30–40 (por elevación)
    maniana, tarde = intervalos
    hay_ventana = bool(maniana or tarde)

    consejo_nutri = ""
    if not hay_ventana:
        consejo_nutri = (
            "\n🍽 Consejo nutricional (si hoy no hay 30–40°): "
            "prioriza pescado azul, huevos y alimentos fortificados con vitamina D."
        )

    # Formato final (sin duplicar etiquetas)
    msg = (
        f"🧠 Consejo para hoy ({t_noon.strftime('%A')}):\n"
        f"{texto_consejo}\n\n"
        + (f"📚 Referencia:\n{ref}\n\n" if ref else "")
        + f"{texto_intervalos}\n"
        + f"{linea_noon}"
        + (aviso_meteo if aviso_meteo else "")
        + (consejo_nutri if consejo_nutri else "")
    )

    # Pequeño ajuste: nombres de día en español (si tu sistema no los da)
    # (Opcional: lo dejo simple para no complicar)
    return msg


# ----------------------------
# 4) Envío
# ----------------------------
async def enviar_a_usuario(bot: Bot, chat_id: str, prefs: Dict[str, Any], now_utc: dt.datetime) -> None:
    if ONLY_CHAT_ID and str(chat_id) != str(ONLY_CHAT_ID):
        return

    # ✅ Ventana: usa tu lógica de repo (hora local del usuario + no repetir)
    if not repo.should_send_now(prefs, now_utc):
        return

    tzname = (prefs.get("tz") or "Europe/Madrid").strip()
    tz = pytz.timezone(tzname)
    hoy_local = now_utc.astimezone(tz).date()

    msg = construir_mensaje_diario(chat_id, prefs, now_utc)
    await bot.send_message(chat_id=str(chat_id), text=msg)

    repo.mark_sent_today(str(chat_id), hoy_local)


async def main() -> None:
    if not BOT_TOKEN:
        raise RuntimeError("Falta BOT_TOKEN")

    repo.init_db()
    users = repo.list_users()
    bot = Bot(BOT_TOKEN)
    now_utc = dt.datetime.now(dt.timezone.utc)

    for uid, prefs in users.items():
        try:
            await enviar_a_usuario(bot, uid, prefs, now_utc)
        except Exception as e:
            print(f"❌ Error diario {uid}: {e}")


if __name__ == "__main__":
    asyncio.run(main())
