from astral import LocationInfo
from astral.sun import elevation
from datetime import datetime, timedelta

def calcular_intervalos_optimos(ciudad, latitud, longitud, tz):
    location = LocationInfo(ciudad, "España", tz, latitud, longitud)

    hoy = datetime.now().date()
    minutos_totales = 24 * 60
    intervalo = 5  # minutos
    instantes = [datetime.combine(hoy, datetime.min.time()) + timedelta(minutes=i) for i in range(0, minutos_totales, intervalo)]

    intervalos_validos = []
    intervalo_actual = []

    for instante in instantes:
        alt = elevation(instante, location.observer)
        if 30 <= alt <= 40:
            intervalo_actual.append(instante)
        else:
            if len(intervalo_actual) >= 2:
                intervalos_validos.append((intervalo_actual[0], intervalo_actual[-1]))
            intervalo_actual = []

    if len(intervalo_actual) >= 2:
        intervalos_validos.append((intervalo_actual[0], intervalo_actual[-1]))

    return intervalos_validos

