# configuracion_ubicacion.py
import json
from geopy.geocoders import Nominatim
import requests

def obtener_ubicacion():
    try:
        ip_info = requests.get("https://ipinfo.io/json").json()
        ciudad = ip_info["city"]
        loc = ip_info["loc"]
        latitud, longitud = map(float, loc.split(","))
        print(f"🌍 Ubicación detectada: {ciudad} ({latitud}, {longitud})")
    except Exception:
        print("❗ No se pudo detectar la ubicación automáticamente.")
        ciudad = input("Introduce tu ciudad manualmente: ")
        geolocator = Nominatim(user_agent="consejos_inmunes")
        location = geolocator.geocode(ciudad)
        if not location:
            print("No se pudo encontrar esa ciudad.")
            return
        latitud = location.latitude
        longitud = location.longitude

    datos = {
        "ciudad": ciudad,
        "latitud": latitud,
        "longitud": longitud
    }

    with open("ubicacion.json", "w") as f:
        json.dump(datos, f)

    print(f"✅ Ubicación guardada: {ciudad} ({latitud}, {longitud})")

if __name__ == "__main__":
    obtener_ubicacion()


