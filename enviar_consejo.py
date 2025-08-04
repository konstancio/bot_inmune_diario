import os
import random
import asyncio
from datetime import date, datetime, timedelta
import telegram
from telegram import Bot
from zoneinfo import ZoneInfo
from consejos_diarios import consejos
from ubicacion_y_sol import (
    obtener_ubicacion,
    obtener_intervalos_solares,
    obtener_meteorologia,
    formatear_intervalo,
    hora_dentro_intervalo,
)

# ========== Config ==========
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID") or CHAT_ID
CYCLE_START = os.getenv("CYCLE_START", date.today().isoformat())
CYCLE_LENGTH_DAYS = int(os.getenv("CYCLE_LENGTH_DAYS", "28"))

# ========== Consejo del día ==========

def obtener_consejo_del_dia(dia_semana):
    conjunto = consejos[dia_semana]
    consejo = random.choice([x for i, x in enumerate(conjunto) if i % 2 == 0])
    referencia = next(x for x in conjunto if x.startswith("📚") or x.startswith("🧬"))
    return consejo.strip(), referencia.strip()

# ========== Consejo nutricional profesional por estación ==========
def consejo_nutricional_estacional(mes):
    if mes in (12, 1, 2):
        return (
            "🌰 *Estrategia sin sol (invierno):* Aumenta alimentos con vitamina D y apoyo inmune.\n"
            "• Pescados azules: caballa, sardina, boquerón.\n"
            "• Marisco: mejillón, almeja.\n"
            "• Lácteos/enriquecidos y huevos.\n"
            "• Verduras: col rizada, brócoli, coliflor.\n"
            "• Cítricos: naranja, mandarina.\n"
            "_Considera suplemento si la exposición es baja durante semanas._"
        )
    elif mes in (3, 4, 5):
        return (
            "🌿 *Estrategia sin sol (primavera):* Refuerza microbiota y vitamina D.\n"
            "• Caballa, sardina, bonito.\n"
            "• Espárragos, alcachofa, guisantes.\n"
            "• Fresas, fermentados, huevos.\n"
            "_Mantén rutinas de sueño y comidas regulares._"
        )
    elif mes in (6, 7, 8):
        return (
            "🏖️ *Estrategia sin sol (verano nublado):* Mantén fuentes de D y antioxidantes.\n"
            "• Sardina, boquerón, caballa.\n"
            "• Melón, sandía, higos.\n"
            "• Tomate, pimiento, pepino.\n"
            "_Hidratación adecuada y calidad de sueño._"
        )
    else:
        return (
            "🍁 *Estrategia sin sol (otoño):* Prioriza omega‑3 y fitoquímicos.\n"
            "• Caballa, sardina, bonito.\n"
            "• Setas, calabaza, boniato.\n"
            "• Granada, frutos secos.\n"
            "_Adapta rutinas a menor luz solar._"
        )

# ========== Aviso editorial ==========

def dias_restantes_de_ciclo(hoy_date, start_str, length_days):
    try:
        start = date.fromisoformat(start_str)
    except Exception:
        start = hoy_date
    try:
        L = int(length_days)
    except Exception:
        L = 28
    transcurridos = (hoy_date - start).days
    if transcurridos < 0:
        transcurridos = 0
    idx = transcurridos % L
    restantes = L - 1 - idx
    return restantes

async def avisar_fin_ciclo_si_corresponde(hoy_date, bot):
    restantes = dias_restantes_de_ciclo(hoy_date, CYCLE_START, CYCLE_LENGTH_DAYS)
    if restantes in (2, 1):
        txt = (
            f"⚠️ *Aviso editorial* | Quedan *{restantes} día(s)* para completar el ciclo "
            f"de consejos ({CYCLE_LENGTH_DAYS} días). Considera subir nuevos contenidos."
        )
        try:
            await bot.send_message(chat_id=ADMIN_CHAT_ID, text=txt, parse_mode="Markdown")
        except Exception as e:
            print(f"Error enviando aviso fin de ciclo: {e}")

# ========== Generar mensaje ==========
async def main_envio():
    bot = Bot(token=BOT_TOKEN)

    # Fecha y consejo
    hoy = date.today()
    dia_semana = hoy.weekday()
    consejo, referencia = obtener_consejo_del_dia(dia_semana)

    # Ubicación
    ubicacion_geo, ubicacion = obtener_ubicacion()

    # Intervalos solares
    antes, despues = obtener_intervalos_solares(ubicacion_geo, hoy)

    # Meteo
    texto_meteo, aviso_nubes_alta = obtener_meteorologia(ubicacion_geo, antes + despues)

    # Construcción del mensaje
    mensaje = f"📗 Consejo para hoy ({ubicacion['dia_nombre']}):\n{consejo}\n\n"
    mensaje += f"{referencia}\n\n"
    mensaje += f"🌞 *Intervalos solares seguros para producir vit. D hoy ({ubicacion['ciudad']}):*\n"
    if antes:
        mensaje += f"🌅 Mañana: {formatear_intervalo(antes[0])} - {formatear_intervalo(antes[-1])}\n"
    if despues:
        mensaje += f"🌇 Tarde: {formatear_intervalo(despues[0])} - {formatear_intervalo(despues[-1])}"
    if texto_meteo:
        mensaje += f" ({texto_meteo})"
    mensaje += "\n"

    # Añadir estrategia nutricional si es necesario
    if (not antes and not despues) or aviso_nubes_alta:
        if not antes and not despues:
            mensaje += "⚠️ Hoy el Sol no alcanza 30° de elevación.\n"
        else:
            mensaje += "⚠️ Nubosidad muy alta: posible baja síntesis de vitamina D.\n"
        mensaje += consejo_nutricional_estacional(hoy.month) + "\n"

    # Aviso de fin de ciclo
    await avisar_fin_ciclo_si_corresponde(hoy, bot)

    # Envío del mensaje
    await bot.send_message(chat_id=CHAT_ID, text=mensaje, parse_mode="Markdown")

# ========== Ejecutar ==========
if BOT_TOKEN and CHAT_ID:
    try:
        asyncio.run(main_envio())
        print("✅ Mensaje enviado por Telegram.")
    except Exception as e:
        print(f"❌ Error al enviar mensaje: {e}")
else:
    print("❌ Faltan BOT_TOKEN o CHAT_ID")
