# calcular_intervalos.py
from astral import LocationInfo
from astral.sun import elevation, sun
from datetime import datetime, timedelta
import json
import pytz

def calcular_intervalo():
    with open("ubicacion.json") as f:
        datos = json.load(f)

    ciudad = datos["ciudad"]
    lat = datos["latitud"]
    lon = datos["longitud"]

    loc = LocationInfo(name=ciudad, region="",
                       timezone="Europe/Madrid", latitude=lat, longitude=lon)

    tz = pytz.timezone(loc.timezone)
    ahora = datetime.now(tz)
    fecha = ahora.date()

    s = sun(loc.observer, date=fecha, tzinfo=tz)
    mediodia = s["noon"]

    intervalo = timedelta(minutes=1)
    hora = datetime.combine(fecha, datetime.min.time()).replace(tzinfo=tz, hour=6)
    fin = datetime.combine(fecha, datetime.max.time()).replace(tzinfo=tz, hour=21)

    antes = []
    despues = []

    while hora <= fin:
        alt = elevation(loc.observer, hora)
        if 30 <= alt <= 40:
            if hora < mediodia:
                antes.append(hora)
            elif hora > mediodia:
                despues.append(hora)
        hora += intervalo

    def formatear(lista):
        if not lista:
            return None
        return f"{lista[0].strftime('%H:%M')} - {lista[-1].strftime('%H:%M')}"

    return {
        "ciudad": ciudad,
        "franja_mañana": formatear(antes),
        "franja_tarde": formatear(despues)
    }

if __name__ == "__main__":
    print(calcular_intervalo())

