# consejos_parasimpatico.py
# 60 consejos para activar el sistema parasimpático (relajación y sueño).
# Rotación diaria determinista y traducción automática opcional.

from __future__ import annotations
import datetime
from typing import Optional, List
try:
    from deep_translator import LibreTranslator
except Exception:
    LibreTranslator = None  # por si no está disponible en algún entorno

# ------------------ lista de 60 consejos (ES) ------------------

CONSEJOS_PARASIMPATICO: List[str] = [
    # Respiración y ritmo
    "Respiración diafragmática: inhala 4s por la nariz, retén 2s, exhala 6s por la boca durante 5 minutos.",
    "Técnica 4-7-8: inhala 4s, retén 7s, exhala 8s. Repite 4 ciclos.",
    "Respiración en caja: 4s inhalar, 4s retener, 4s exhalar, 4s retener. 3–5 minutos.",
    "Coherencia cardíaca: 6 respiraciones por minuto, 5 minutos (≈ 5s inhalar, 5s exhalar).",
    "Suspiro fisiológico: doble inhalación nasal (2ª corta) + exhalación larga por la boca. Haz 5 repeticiones.",
    "Respiración alterna (nadi shodhana): alterna fosas nasales 4–4–6 (inhala-retén-exhala) por 3 minutos.",
    "Exhalaciones largas: exhala el doble de tiempo que inhalas durante 2–3 minutos.",
    "Cuenta respiraciones del 1 al 10 (inhalas=1, exhalas=2…). Si te distraes, vuelve al 1 sin juzgar.",

    # Relajación muscular y cuerpo
    "Relajación progresiva de Jacobson: tensa y suelta pies, piernas, abdomen, hombros y cara (5s/10s).",
    "Estiramiento cervical suave: oreja al hombro 15s por lado, respirando lento.",
    "Auto-masaje de hombros y trapecios con respiración lenta durante 2 minutos.",
    "Piernas en la pared (Viparita Karani) 3–5 minutos para favorecer el retorno venoso.",
    "Postura del niño (yoga) 2–3 minutos con respiración nasal lenta.",
    "Balanceo suave sentado: microbalanceos laterales sincronizados con la respiración 2 minutos.",
    "Movilidad torácica: manos detrás de la cabeza, abre costillas al inhalar, suelta al exhalar, 10 veces.",
    "Rodillos o pelota blanda en planta del pie 1–2 minutos por lado para soltar tensión global.",

    # Mindfulness / escaneo / atención
    "Body scan de 3 minutos: recorre el cuerpo de pies a cabeza soltando tensión en cada zona.",
    "Atención a sonidos: 2 minutos escuchando el ambiente sin etiquetar.",
    "Visualización calmante: imagina un lugar seguro (playa/bosque) con todo detalle 3–5 minutos.",
    "Gratitud de 3 cosas: recuerda tres momentos agradables del día y respíralos 30s cada uno.",
    "Meditación guiada corta (5–10 min) con foco en la respiración.",
    "Observa 5-4-3-2-1: 5 cosas que ves, 4 que sientes, 3 que oyes, 2 que hueles, 1 que saboreas.",

    # Higiene del sueño y entorno
    "Baja las luces y activa modo cálido 60 minutos antes de acostarte.",
    "Evita pantallas brillantes 30–60 minutos antes de dormir.",
    "Mantén la habitación fresca (18–20 °C) y oscura.",
    "Rutina 3-2-1: no cenar fuerte 3h antes, no trabajo 2h antes, no pantallas 1h antes.",
    "Ducha tibia 10–15 minutos antes de la cama para favorecer la caída de temperatura corporal interna.",
    "Ventila 5 minutos el dormitorio antes de acostarte.",
    "Pon el móvil en modo avión o déjalo fuera del dormitorio.",

    # Rituales y hábitos suaves
    "Infusión relajante (manzanilla, tila, pasiflora o lavanda) 30 minutos antes.",
    "Lee 10–15 minutos un libro tranquilo en papel.",
    "Diario breve: escribe lo pendiente para ‘sacarlo’ de la cabeza.",
    "Aromaterapia con 1–2 gotas de lavanda en difusor o almohada.",
    "Música ambiental suave (volumen bajo) durante 10 minutos.",
    "Luz de sal o lámpara cálida como único punto de luz nocturno.",
    "Pijama cómodo y sábanas agradables: señales de seguridad al cuerpo.",

    # Nervio vago / estímulos sensoriales
    "Zumbido ‘mmmm’ en la exhalación (bhramari) 6–8 repeticiones para vibrar senos y garganta.",
    "Enjuague bucal suave y respiración nasal lenta para relajar mandíbula y lengua.",
    "Compresa templada en abdomen o nuca 5 minutos.",
    "Agua fresca en la cara 10–20°C 30–60s para activar reflejo de inmersión.",
    "Masticación lenta y consciente de un bocado blando (si todavía no cenaste).",
    "Auto-abrazo cruzado (estimulación propioceptiva) 60–90s con respiración lenta.",

    # Movimiento suave y luz
    "Paseo corto al atardecer (10–15 min) para bajar el cortisol.",
    "Estiramiento gato-camello (espalda) 2–3 minutos al ritmo de la respiración.",
    "Respiración + balanceo de tobillos sentado en cama 1–2 minutos.",
    "Saludo al sol extremadamente suave x3 con respiración lenta (si no hay molestias).",

    # Gestión cognitiva/emocional
    "Planifica mañana en 3 puntos simples; cierra el cuaderno y suelta.",
    "Reformula preocupaciones como tareas concretas y pequeñas.",
    "Autocompasión: habla contigo como hablarías con un buen amigo durante 1 minuto.",
    "Limita noticias/temas activadores por la noche; pospón para mañana.",
    "Declara un ‘corte de rumiación’ y vuelve a la respiración cuando te sorprendas pensando en bucle.",

    # Alimentación/hábitos suaves
    "Cena ligera rica en triptófano (pavo, huevo, yogur) y carbohidrato complejo moderado.",
    "Evita cafeína a partir de las 15:00–16:00.",
    "Reduce alcohol por la noche; altera el sueño profundo.",
    "Hidrátate moderadamente; evita grandes cantidades justo antes de dormir.",
    "Magnesio en la cena si lo usas habitualmente (consulta profesional si dudas).",

    # Microhábitos y entorno social
    "Acuéstate y levántate a horas consistentes, incluso fines de semana (±1h).",
    "Crea una frase puente: “Ahora toca descansar; mañana continúo”. Repítela 5 veces con respiración lenta.",
    "Desordena menos: dedica 3 minutos a dejar el dormitorio recogido; reduce estímulos.",
    "Usa tapones o máscara si ruido/luz interfieren.",
    "Abrazo de 20 segundos con tu pareja o abrazo a ti mismo con respiración lenta.",

    # Extras de atención plena
    "Atiende a 10 respiraciones completas contando solo las exhalaciones.",
    "Practica ‘visión panorámica’: relaja la mirada y amplía el campo visual durante 60–90s.",
    "Siente el peso del cuerpo en el colchón; nota 5 puntos de apoyo mientras respiras lento.",
    "Imagina que cada exhalación ‘apaga’ la tensión en hombros y cuello.",
    "Coloca una mano en el pecho y otra en el abdomen; sincroniza manos con cada respiración.",

    # Cierre de día
    "Elige una intención amable para mañana y suéltala con una exhalación larga.",
    "Agradece mentalmente a tu cuerpo por lo que te permitió hacer hoy.",
]

# ------------------ utilidades de idioma ------------------

_VALID_LANG = {"es","en","fr","it","de","pt","nl","sr","ru"}

_ALIAS = {
    "sh":"sr","sc":"sr","srp":"sr","hr":"sr","bs":"sr",
    "pt-br":"pt",
}

def _norm_lang(code: Optional[str]) -> str:
    if not code:
        return "es"
    code = code.strip().lower().split("-")[0]
    return _ALIAS.get(code, code)

def _traducir(texto: str, lang: Optional[str]) -> str:
    """Traducción opcional vía LibreTranslator. Si falla o lang es 'es', retorna el original."""
    dest = _norm_lang(lang)
    if not texto or dest == "es" or dest not in _VALID_LANG or LibreTranslator is None:
        return texto
    try:
        return LibreTranslator(source="es", target=dest).translate(texto)
    except Exception:
        return texto

# ------------------ API principal ------------------

def sugerir_para_noche(dia: int | None = None, lang: Optional[str] = None) -> str:
    """
    Devuelve un consejo (traducido si pasas `lang`).
    - Selección determinista por día (sin repetir hasta cubrir los 60).
    - `dia`: si no se pasa, usa date.toordinal() del día actual.
    """
    if dia is None:
        dia = datetime.date.today().toordinal()
    idx = dia % len(CONSEJOS_PARASIMPATICO)
    texto = CONSEJOS_PARASIMPATICO[idx]
    return _traducir(texto, lang)

def formatear_consejo(texto: str, lang: Optional[str] = None) -> str:
    """
    Devuelve el texto formateado con encabezado y traducción opcional.
    Si `texto` ya viene traducido, puedes llamar con lang=None.
    """
    encabezado = "🌙 Consejo para relajar tu sistema parasimpático esta noche:"
    encabezado = _traducir(encabezado, lang)
    cuerpo = _traducir(texto, lang) if lang else texto
    return f"{encabezado}\n\n{cuerpo}"
