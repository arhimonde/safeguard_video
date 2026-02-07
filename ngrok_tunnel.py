from pyngrok import ngrok, conf
import sys
import time
from app import app
import threading

# Configuración de ngrok
# Permite acceder al servidor local desde internet. Útil para demostraciones remotas.
# Debes configurar tu token de autenticación via CLI antes de usar: 
# ngrok config add-authtoken <TU_TOKEN>
# O puedes descomentar la línea de abajo y pegar tu token:
# conf.get_default().auth_token = "TU_TOKEN_AQUI"

def start_tunnel():
    """
    Inicia un túnel HTTP usando ngrok para exponer el puerto local 5000 a internet.
    """
    # Puerto donde corre nuestra aplicación Flask
    port = 5000
    
    # Establecer conexión y obtener la URL pública
    public_url = ngrok.connect(port).public_url
    print(f" * URL Pública: {public_url}")
    print(f" * Accede a tu panel de control desde cualquier lugar usando este enlace.")
    return public_url

if __name__ == "__main__":
    print("Iniciando Safeguard Vision con Acceso Remoto...")
    
    # Iniciar túnel ngrok
    try:
        url = start_tunnel()
    except Exception as e:
        print(f"Error al verificar ngrok: {e}")
        print("Asegúrate de tener un authtoken de ngrok configurado.")
        print("Ejecuta: ngrok config add-authtoken <TOKEN>")
        sys.exit(1)

    # Ejecutar Aplicación Flask
    # Usamos este script como punto de entrada para el acceso remoto.
    import os
    os.makedirs('static/captures', exist_ok=True)
    # Iniciamos Flask sin el reloader automático para evitar que se reinicie el túnel ngrok constantemente.
    app.run(host='0.0.0.0', port=5000, use_reloader=False) 

