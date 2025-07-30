from geopy.geocoders import Nominatim
from timezonefinder import TimezoneFinder

def obtener_ubicacion():
    # Puedes cambiar aquí el nombre de la ciudad si quieres fijarlo manualmente
    ciudad = "Málaga"

    geolocator = Nominatim(user_agent="bot_inmune_diario")
    location = geolocator.geocode(ciudad)

    if not location:
        raise ValueError(f"No se pudo obtener la ubicación para la ciudad: {ciudad}")

    tf = TimezoneFinder()
    timezone = tf.timezone_at(lng=location.longitude, lat=location.latitude)

    if not timezone:
        raise ValueError("No se pudo determinar la zona horaria.")

    return {
        "latitud": location.latitude,
        "longitud": location.longitude,
        "timezone": timezone
    }


