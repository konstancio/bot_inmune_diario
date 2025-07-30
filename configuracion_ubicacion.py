import os

def obtener_ubicacion():
    """
    Obtiene el nombre de la ciudad desde una variable de entorno.
    Si no se encuentra, usa 'Málaga' como valor por defecto.
    """
    ciudad = os.getenv("CIUDAD", "Málaga")
    return ciudad

