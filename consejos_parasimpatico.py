# consejos_parasimpatico.py
# Prácticas breves para activar el sistema parasimpático (anti-estrés).
# No requiere dependencias. Úsalo desde tu bot para proponer ejercicios guiados.

from __future__ import annotations
from typing import List, Dict, Any, Optional
import random

# Cada consejo es un dict con:
# id, nombre, dur_min, momento, contexto, pasos[list[str]], nota_seguridad[str|None], evidencia[str|None]
CONSEJOS_PARASIMPATICO: List[Dict[str, Any]] = [

    {
        "id": "resp_4_6",
        "nombre": "Respiración 4-6 (coherencia cardíaca)",
        "dur_min": 3,
        "momento": "cualquiera",
        "contexto": "oficina",
        "pasos": [
            "Siéntate cómodo, hombros sueltos.",
            "Inhala por la nariz durante 4 segundos.",
            "Exhala lenta y completamente por la nariz o la boca durante 6 segundos.",
            "Repite el ciclo de 4-6 durante 3–5 minutos manteniendo una respiración silenciosa.",
        ],
        "nota_seguridad": "Si mareas, reduce el tiempo de exhalación a 5s y respira con suavidad.",
        "evidencia": "Coherence breathing 6 ciclos/min → ↑variabilidad cardíaca (HRV) y calma autonómica."
    },

    {
        "id": "resp_caja",
        "nombre": "Respiración en caja 4-4-4-4",
        "dur_min": 2,
        "momento": "cualquiera",
        "contexto": "oficina",
        "pasos": [
            "Inhala 4 segundos.",
            "Retén 4 segundos (suave, sin tensión).",
            "Exhala 4 segundos.",
            "Retén con pulmones vacíos 4 segundos.",
            "Repite 2–4 minutos.",
        ],
        "nota_seguridad": "Evita retenciones largas si estás embarazada o con problemas respiratorios.",
        "evidencia": "Técnica de control respiratorio que modula el tono vagal."
    },

    {
        "id": "suspiros_fisiologicos",
        "nombre": "2 Suspiros fisiológicos + exhalación larga",
        "dur_min": 1,
        "momento": "pico_estrés",
        "contexto": "cualquiera",
        "pasos": [
            "Inhala por la nariz hasta ~80% de tus pulmones.",
            "Haz una mini-inhala breve adicional por la nariz para 'llenar' la parte alta.",
            "Exhala larga y progresiva por la boca.",
            "Haz 3–5 repeticiones. Notarás alivio rápido de la tensión.",
        ],
        "nota_seguridad": None,
        "evidencia": "El 'physiological sigh' reduce CO₂ y activa reflejos calmantes."
    },

    {
        "id": "relaj_muscular",
        "nombre": "Relajación muscular progresiva (mano-hombros-cara)",
        "dur_min": 4,
        "momento": "tarde",
        "contexto": "oficina",
        "pasos": [
            "Aprieta puños 5 segundos y suelta 10; siente la diferencia.",
            "Eleva hombros 5 segundos y suelta 10.",
            "Frunce la cara con suavidad 5 segundos y suelta 10.",
            "Repite el ciclo completo 2 veces.",
        ],
        "nota_seguridad": "Evita contracciones dolorosas si tienes lesión.",
        "evidencia": "PMR (Jacobson) reduce activación simpática y ansiedad somática."
    },

    {
        "id": "zumbido_vagal",
        "nombre": "Zumbido/Hum para el nervio vago",
        "dur_min": 2,
        "momento": "cualquiera",
        "contexto": "casa",
        "pasos": [
            "Inhala por la nariz.",
            "Exhala emitiendo un zumbido suave 'mmmm' o 'om' que vibre en garganta y rostro.",
            "Manténlo 6–8 s; repite 8–10 veces.",
        ],
        "nota_seguridad": "Bajo volumen si estás en la oficina 😉.",
        "evidencia": "Vibración laríngea y exhalación prolongada → ↑tono vagal."
    },

    {
        "id": "agua_fresca_cara",
        "nombre": "Reflejo de inmersión: agua fresca en la cara",
        "dur_min": 1,
        "momento": "pico_estrés",
        "contexto": "baño",
        "pasos": [
            "Moja cara con agua fresca 10–20°C o aplica compresa fría en mejillas y zona bajo ojos.",
            "Respira lento por la nariz 1–2 minutos.",
        ],
        "nota_seguridad": "Evita frío extremo si tienes problemas cardíacos o migrañas desencadenadas por frío.",
        "evidencia": "Reflejo trigémino → bradicardia suave y activación parasimpática."
    },

    {
        "id": "body_scan_2m",
        "nombre": "Body-scan de 2 minutos",
        "dur_min": 2,
        "momento": "noche",
        "contexto": "cama",
        "pasos": [
            "Cierra los ojos y recorre el cuerpo de pies a cabeza.",
            "En cada zona, inspira 3 s y al exhalar suelta la tensión.",
            "Si aparecen pensamientos, vuelve amable al cuerpo.",
        ],
        "nota_seguridad": None,
        "evidencia": "Atención interoceptiva reduce rumiación y baja arousal."
    },

    {
        "id": "gratitud_3",
        "nombre": "3 cosas buenas (gratitud breve)",
        "dur_min": 2,
        "momento": "noche",
        "contexto": "cama",
        "pasos": [
            "Piensa o escribe 3 cosas que salieron bien hoy y por qué.",
            "Respira 4-6 mientras evocarlas 30–60 s cada una.",
        ],
        "nota_seguridad": None,
        "evidencia": "Prácticas de gratitud mejoran afecto positivo y sueño."
    },

    {
        "id": "estir_gato_camel",
        "nombre": "Estiramiento suave (gato-camello)",
        "dur_min": 3,
        "momento": "mañana",
        "contexto": "casa",
        "pasos": [
            "A cuatro apoyos, arquea espalda (gato) al exhalar.",
            "Inhala y baja el abdomen (camello).",
            "Ritmo 5–6 ciclos/min durante 2–3 minutos.",
        ],
        "nota_seguridad": "Evita si hay dolor lumbar agudo; mueve con suavidad.",
        "evidencia": "Movimiento respirado + ritmo lento → ↑tono parasimpático."
    },

    {
        "id": "pausa_360",
        "nombre": "Pausa 360º (vista amplia + respiración nasal)",
        "dur_min": 1,
        "momento": "oficina",
        "contexto": "oficina",
        "pasos": [
            "Levanta la mirada de la pantalla y suaviza el enfoque (visión panorámica).",
            "Respira por la nariz 6 ciclos lentos mientras mantienes el campo visual amplio.",
        ],
        "nota_seguridad": None,
        "evidencia": "Visión periférica reduce foco de amenaza y activa redes calmantes."
    },
]

# -------- Helpers de selección y formato --------

def _match(c: Dict[str, Any], momento: Optional[str], contexto: Optional[str], max_min: Optional[int]) -> bool:
    if momento and c["momento"] not in (momento, "cualquiera", "oficina"):
        return False
    if contexto and c["contexto"] not in (contexto, "cualquiera"):
        return False
    if max_min is not None and c["dur_min"] > max_min:
        return False
    return True

def consejo_aleatorio(filtro: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    filtro opcional: {"momento": "noche|tarde|mañana|pico_estrés|oficina",
                      "contexto": "oficina|casa|baño|cama|cualquiera",
                      "max_min": 3}
    """
    if filtro is None:
        return random.choice(CONSEJOS_PARASIMPATICO)
    momento = filtro.get("momento")
    contexto = filtro.get("contexto")
    max_min = filtro.get("max_min")
    cand = [c for c in CONSEJOS_PARASIMPATICO if _match(c, momento, contexto, max_min)]
    return random.choice(cand) if cand else random.choice(CONSEJOS_PARASIMPATICO)

def sugerir_por_tiempo(minutos: int, contexto: Optional[str] = None) -> Dict[str, Any]:
    cand = [c for c in CONSEJOS_PARASIMPATICO if c["dur_min"] <= minutos and (not contexto or c["contexto"] in (contexto, "cualquiera"))]
    return random.choice(cand) if cand else consejo_aleatorio()

def sugerir_para_noche() -> Dict[str, Any]:
    cand = [c for c in CONSEJOS_PARASIMPATICO if c["momento"] == "noche"]
    return random.choice(cand) if cand else consejo_aleatorio()

def sugerir_en_oficina(max_min: int = 3) -> Dict[str, Any]:
    cand = [c for c in CONSEJOS_PARASIMPATICO if c["contexto"] == "oficina" and c["dur_min"] <= max_min]
    return random.choice(cand) if cand else consejo_aleatorio({"contexto": "oficina"})

def formatear_consejo(c: Dict[str, Any]) -> str:
    pasos_txt = "\n".join([f"{i+1}. {p}" for i, p in enumerate(c["pasos"])])
    nota = f"\n\nℹ️ {c['nota_seguridad']}" if c.get("nota_seguridad") else ""
    evid = f"\n\n📚 {c['evidencia']}" if c.get("evidencia") else ""
    return (
        f"🧘 {c['nombre']} · {c['dur_min']} min\n"
        f"{pasos_txt}"
        f"{nota}{evid}"
    )

# -------- Ejemplos de uso rápido --------
# consejo = consejo_aleatorio({"max_min": 2, "contexto": "oficina"})
# print(formatear_consejo(consejo))
#
# consejo = sugerir_para_noche()
# print(formatear_consejo(consejo))
#
# consejo = sugerir_por_tiempo(1)
# print(formatear_consejo(consejo))