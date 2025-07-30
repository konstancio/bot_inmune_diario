import json
from geopy.geocoders import Nominatim
from timezonefinder import TimezoneFinder

# Solicita la ciudad
ciudad = input("Introduce tu ciudad: ")

# Obtiene coordenadas
geolocalizador = Nominatim(user_agent="consejo_inmune_bot")
ubicacion = geolocalizador.geocode(ciudad)

if not ubicacion:
    print("❌ No se ha podido encontrar la ciudad. Inténtalo con otra.")
    exit()

latitud = ubicacion.latitude
longitud = ubicacion.longitude

# Calcula zona horaria
tf = TimezoneFinder()
zona_horaria = tf.timezone_at(lng=longitud, lat=latitud)

# Guarda en archivo JSON
datos = {
    "ciudad": ciudad,
    "latitud": latitud,
    "longitud": longitud,
    "zona_horaria": zona_horaria
}

with open("ubicacion.json", "w") as f:
    json.dump(datos, f, indent=4)

print(f"✅ Ubicación guardada: {ciudad} ({latitud}, {longitud}) en zona horaria {zona_horaria}")
