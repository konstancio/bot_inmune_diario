from astral import solar_elevation
from datetime import datetime, timedelta

def calcular_intervalos_optimos(lat, lon, fecha=None):
    if fecha is None:
        fecha = datetime.now()
    inicio_dia = fecha.replace(hour=0, minute=0, second=0, microsecond=0)
    intervalos = []
    paso = timedelta(minutes=5)

    t = inicio_dia
    while t < inicio_dia + timedelta(days=1):
        elevacion = solar_elevation(t, lat, lon)
        if 30 <= elevacion <= 40:
            intervalos.append(t)
        t += paso

    mañana = [h for h in intervalos if h.hour < 12]
    tarde = [h for h in intervalos if h.hour > 12]

    def reducir_intervalos(lista):
        if not lista:
            return None
        return (lista[0].strftime("%H:%M"), lista[-1].strftime("%H:%M"))

    return reducir_intervalos(mañana), reducir_intervalos(tarde)
