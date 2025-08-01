from astral.sun import sun
from astral.location import Observer
from astral import sun as astral_sun
from datetime import datetime, timedelta
from astral import solar

def calcular_intervalos_optimos(lat, lon, hoy=None, timezone_str='Europe/Madrid'):
    if hoy is None:
        hoy = datetime.now().date()
    elif isinstance(hoy, datetime):
        hoy = hoy.date()

    observer = Observer(latitude=lat, longitude=lon)
    s = astral_sun.sun(observer, date=hoy, tzinfo=timezone_str)

    elevaciones = []
    hora_actual = s['sunrise']
    fin = s['sunset']

    while hora_actual <= fin:
        altitud = solar.elevation(observer, hora_actual)
        if 30 <= altitud <= 40:
            elevaciones.append(hora_actual.strftime('%H:%M'))
        hora_actual += timedelta(minutes=10)

    mediodia = s['noon']
    antes = [h for h in elevaciones if datetime.strptime(h, '%H:%M').time() <= mediodia.time()]
    despues = [h for h in elevaciones if datetime.strptime(h, '%H:%M').time() > mediodia.time()]

    return antes, despues



