from astral import LocationInfo
from astral.location import Location
from datetime import datetime, timedelta

def calcular_intervalos_optimos(lat, lon, hoy=None, timezone_str='Europe/Madrid'):
    if hoy is None:
        hoy = datetime.now().date()
    else:
        hoy = hoy.date()

    # Crear ubicación personalizada
    ubicacion = LocationInfo(name="Personalizada", region="España", timezone=timezone_str, latitude=lat, longitude=lon)
    ciudad = Location(ubicacion)

    elevaciones_validas = []
    hora_actual = ciudad.sunrise(hoy)
    fin = ciudad.sunset(hoy)

    while hora_actual <= fin:
        elevacion = ciudad.solar_elevation(hora_actual)
        if 30 <= elevacion <= 40:
            elevaciones_validas.append(hora_actual.strftime('%H:%M'))
        hora_actual += timedelta(minutes=10)

    # Mediodía solar
    mediodia = ciudad.noon(hoy)
    antes = [h for h in elevaciones_validas if datetime.strptime(h, "%H:%M").time() <= mediodia.time()]
    despues = [h for h in elevaciones_validas if datetime.strptime(h, "%H:%M").time() > mediodia.time()]

    return antes, despues
