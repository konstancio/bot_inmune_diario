import requests
from geopy.geocoders import Nominatim
from timezonefinder import TimezoneFinder

def obtener_ubicacion():
    try:
        # Intentar obtener la IP pública
        ip = requests.get("https://api.ipify.org").text

        # Usar IP para obtener datos de geolocalización
        response = requests.get(f"https://ipapi.co/{ip}/json/")
        data = response.json()

        ciudad = data.get("city")
        lat = data.get("latitude")
        lon = data.get("longitude")

        if not ciudad or not lat or not lon:
            raise ValueError("Datos incompletos desde IP. Se usará fallback.")

        print(f"✅ Ubicación detectada: {ciudad} ({lat}, {lon})")

    except Exception as e:
        print(f"⚠️ Error al obtener ubicación por IP: {e}")
        print("🔁 Usando ubicación por defecto: Málaga")
        ciudad = "Málaga"
        geolocator = Nominatim(user_agent="bot_inmune_diario")
        location = geolocator.geocode(ciudad)

        if not location:
            print("❌ No se pudo geolocalizar Málaga. Abortando.")
            return None

        lat = location.latitude
        lon = location.longitude
        print(f"✅ Ubicación por defecto: {ciudad} ({lat}, {lon})")

    # Obtener zona horaria a partir de lat/lon
    try:
        tf = TimezoneFinder()
        zona_horaria = tf.timezone_at(lat=lat, lng=lon)
    except Exception as e:
        print(f"❌ Error al obtener la zona horaria: {e}")
        zona_horaria = "Europe/Madrid"

    print(f"✅ Ubicación guardada: {ciudad} ({lat}, {lon}) - Zona horaria: {zona_horaria}")

    return {
        "latitud": lat,
        "longitud": lon,
        "ciudad": ciudad,
        "timezone": zona_horaria
    }


