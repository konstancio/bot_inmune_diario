from astral import LocationInfo
from astral.sun import sun
from datetime import datetime, timedelta, timezone

def calcular_intervalos_optimos(lat, lon, hoy=None, timezone_str='Europe/Madrid'):
    if hoy is None:
        hoy = datetime.now().date()

    ciudad = LocationInfo(name="Ciudad", region="Región", timezone=timezone_str, latitude=lat, longitude=lon)
    s = sun(ciudad.observer, date=hoy, tzinfo=ciudad.timezone)

    elevaciones = []
    hora_actual = s['sunrise']
    fin = s['sunset']

    while hora_actual <= fin:
        altitud = ciudad.solar_elevation(hora_actual)
        if 30 <= altitud <= 40:
            elevaciones.append(hora_actual.strftime('%H:%M'))
        hora_actual += timedelta(minutes=10)

    # Dividir los intervalos en antes y después del mediodía solar
    mediodia = s['noon']
    antes = [h for h in elevaciones if datetime.strptime(h, '%H:%M').time() <= mediodia.time()]
    despues = [h for h in elevaciones if datetime.strptime(h, '%H:%M').time() > mediodia.time()]

    return antes, despues


