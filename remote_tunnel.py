import subprocess
import time
import sys
import os
import threading
from app import app

def start_serveo(port=5000):
    """
    Inicia un túnel HTTP usando serveo.net (vía SSH) para exponer el puerto local a internet.
    """
    print(f"🚀 Iniciando túnel Serveo en el puerto {port}...")
    
    # Comando SSH para serveo.net
    cmd = ["ssh", "-o", "StrictHostKeyChecking=no", "-R", f"80:localhost:{port}", "serveo.net"]
    
    try:
        # Iniciamos el proceso
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )
        
        # Hilo para capturar la URL de la salida de serveo
        def monitor_output():
            for line in iter(process.stdout.readline, ''):
                line = line.strip()
                if "Forwarding HTTP traffic from" in line:
                    url = line.split("from")[-1].strip()
                    print(f"\n🌍 URL PÚBLICA DISPONIBLE: {url}")
                    print(f"🌍 Copia este enlace para acceder desde cualquier lugar.\n")
                elif line:
                    print(f"[Serveo] {line}")

        t = threading.Thread(target=monitor_output, daemon=True)
        t.start()
        
        print("⏳ Conectando con Serveo...")
        time.sleep(3) # Breve espera para establecer conexión
        return process
    except Exception as e:
        print(f"❌ Error al iniciar serveo: {e}")
        sys.exit(1)

if __name__ == "__main__":
    print("Iniciando Safeguard Vision con Acceso Remoto (Serveo)...")
    
    # Asegurar que existe el directorio de capturas
    os.makedirs('static/captures', exist_ok=True)
    
    # Iniciar túnel
    tunnel_proc = start_serveo(5000)
    
    try:
        # Iniciar App Flask
        app.run(host='0.0.0.0', port=5000, use_reloader=False)
    finally:
        print("\n🛑 Cerrando túnel...")
        if tunnel_proc:
            tunnel_proc.terminate()
