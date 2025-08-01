
from astral import LocationInfo
from astral.sun import sun
from astral.geocoder import lookup, database
from astral.location import Location
from datetime import datetime, timedelta
from astral import solar

def calcular_intervalos_optimos(lat, lon, hoy=None, timezone_str='Europe/Madrid'):
    if hoy is None:
        hoy = datetime.now().date()
    else:
        hoy = hoy.date()

    # Crear una ubicación personalizada
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

    # Separar en intervalos antes y después del mediodía solar
    mediodia = ciudad.noon(hoy)
    antes = [h for h in elevaciones_validas if datetime.strptime(h, "%H:%M").time() <= mediodia.time()]
    despues = [h for h in elevaciones_validas if datetime.strptime(h, "%H:%M").time() > mediodia.time()]

    return antes, despues





