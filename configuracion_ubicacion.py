import json
from geopy.geocoders import Nominatim

ciudad = input("Introduce tu ciudad: ").strip()

geolocalizador = Nominatim(user_agent="inmune_bot")
ubicacion = geolocalizador.geocode(ciudad)

if ubicacion:
    datos = {
        "latitud": ubicacion.latitude,
        "longitud": ubicacion.longitude,
        "ciudad": ciudad
    }
    with open("ubicacion.json", "w") as f:
        json.dump(datos, f)
    print(f"✅ Ubicación guardada: {ciudad} ({ubicacion.latitude}, {ubicacion.longitude})")
else:
    print("❌ Ciudad no encontrada. Intenta con otra.")
