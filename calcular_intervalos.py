from astral import LocationInfo
from astral.sun import elevation
from datetime import datetime, timedelta

def calcular_intervalos_optimos(latitud, longitud, hoy=None):
    if hoy is None:
        hoy = datetime.now().date()

    ciudad = LocationInfo(name="Ubicacion", region="Ubicacion", timezone="UTC", latitude=latitud, longitude=longitud)
    hora = datetime(hoy.year, hoy.month, hoy.day, 6, 0)

    intervalo = timedelta(minutes=10)
    hora_fin = datetime(hoy.year, hoy.month, hoy.day, 22, 0)

    antes_del_medio_dia = []
    despues_del_medio_dia = []

    while hora <= hora_fin:
        altitud = elevation(observer=(latitud, longitud), date_and_time=hora)

        if 30 <= altitud <= 40:
            if hora < datetime(hoy.year, hoy.month, hoy.day, 12, 0):
                antes_del_medio_dia.append(hora.time())
            else:
                despues_del_medio_dia.append(hora.time())

        hora += intervalo

    return antes_del_medio_dia, despues_del_medio_dia

    }

if __name__ == "__main__":
    print(calcular_intervalo())

