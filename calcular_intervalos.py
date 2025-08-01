from astral import LocationInfo
from astral.sun import sun, elevation
from datetime import datetime, timedelta

def calcular_intervalos_optimos(lat, lon, hoy=None, timezone_str='Europe/Madrid'):
    if hoy is None:
        hoy = datetime.now()

    ciudad = LocationInfo(name="Ciudad", region="Región", timezone=timezone_str, latitude=lat, longitude=lon)
    s = sun(ciudad.observer, date=hoy.date(), tzinfo=ciudad.timezone)

    elevaciones = []
    hora_actual = s['sunrise']
    fin = s['sunset']

    while hora_actual <= fin:
        altitud = elevation(lat, lon, hora_actual)
        if 30 <= altitud <= 40:
            elevaciones.append(hora_actual)
        hora_actual += timedelta(minutes=10)

    # Separar antes y después del mediodía solar
    mediodia = s['noon']
    antes = [h for h in elevaciones if h <= mediodia]
    despues = [h for h in elevaciones if h > mediodia]

    # Agrupar en intervalos contiguos
    def agrupar_intervalos(lista):
        if not lista:
            return []
        intervalos = []
        inicio = anterior = lista[0]
        for hora in lista[1:]:
            if (hora - anterior).seconds > 600:  # más de 10 minutos sin datos = nuevo bloque
                intervalos.append((inicio, anterior + timedelta(minutes=10)))
                inicio = hora
            anterior = hora
        intervalos.append((inicio, anterior + timedelta(minutes=10)))
        return intervalos

    return agrupar_intervalos(antes) + agrupar_intervalos(despues)



