
from geopy.geocoders import Nominatim
from timezonefinder import TimezoneFinder

def obtener_ubicacion():
    {
    "latitud": 36.7213,
    "longitud": -4.4214,
    "ciudad": "Málaga",
    "timezone": "Europe/Madrid"
}


    try:
        geolocator = Nominatim(user_agent="bot_inmune_diario")
        location = geolocator.geocode(ciudad)
        
        if not location:
            print(f"No se encontró la ciudad: {ciudad}")
            return None

        lat = location.latitude
        lon = location.longitude

        print(f"✅ Ubicación detectada: {ciudad} ({lat}, {lon})")

        # Obtener zona horaria
        tf = TimezoneFinder()
        zona_horaria = tf.timezone_at(lat=lat, lng=lon)

        print(f"✅ Ubicación guardada: {ciudad} ({lat}, {lon}) - Zona horaria: {zona_horaria}")

        return {
            "latitud": lat,
            "longitud": lon,
            "zona_horaria": zona_horaria
        }

    except Exception as e:
        print(f"Error al obtener la ubicación: {e}")
        return None


