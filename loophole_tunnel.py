import os
import random
import re
import subprocess
import sys
import time

def start_loophole():
    """
    Inicia un túnel HTTP usando el binario de Loophole para exponer el puerto local 5000.
    """
    port = 5000
    print(f" * Iniciando túnel Loophole en el puerto {port}...")
    
    # Ejecutamos loophole como un subproceso con un hostname específico para mayor estabilidad
    suffix = random.randint(1000, 9999)
    custom_host = f"safeguard-vision-{suffix}"
    cmd = ["./loophole", "http", str(port), "--hostname", custom_host]
    
    try:
        process = subprocess.Popen(
            cmd, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True
        )
        
        # Buscamos la URL generada en la salida del comando
        public_url = None
        start_time = time.time()
        timeout = 30 # Esperar máximo 30 segundos
        
        while time.time() - start_time < timeout:
            line = process.stdout.readline()
            if not line:
                break
            line_strip = line.strip()
            if line_strip:
                print(f" [Loophole] {line_strip}")
            
            # Buscamos la línea que contiene el reenvío (Forwarding)
            if "Forwarding" in line_strip and "https://" in line_strip:
                # Extraer la URL de la línea
                urls = re.findall(r'https://[a-zA-Z0-9.-]+\.loophole\.site', line_strip)
                if urls:
                    public_url = urls[0]
                    break
        
        if public_url:
            print(f"\n🚀 URL Pública: {public_url}")
            return process, public_url
        else:
            print("❌ No se pudo extraer la URL de Loophole a tiempo.")
            process.terminate()
            return None, None
            
    except FileNotFoundError:
        print("❌ Error: No se encontró el binario 'loophole'. asegúrate de haberlo descargado.")
        return None, None
    except Exception as e:
        print(f"❌ Error al iniciar Loophole: {e}")
        return None, None

if __name__ == "__main__":
    from license import check_license_noninteractive, check_license
    if not check_license_noninteractive():
        if not check_license():
            print("Acces refuzat.")
            sys.exit(1)

    print("========================================")
    print("   Safeguard Vision - Remote Access     ")
    print("========================================\n")
    
    loop_proc, url = start_loophole()
    
    if not url:
        print("Asegúrate de haber descargado el binario de Loophole.")
        sys.exit(1)
        
    print("Iniciando aplicación Flask + WebSocket...")
    
    try:
        # Importar la app y socketio de Flask
        from app import app, socketio
        os.makedirs('static/captures', exist_ok=True)
        
        # Ejecutar la app con SocketIO (necesario para WebSocket en tiempo real)
        socketio.run(app, host='0.0.0.0', port=5000,
                     debug=False, allow_unsafe_werkzeug=True)
    except KeyboardInterrupt:
        print("\nCerrando túnel y servidor...")
    finally:
        if loop_proc:
            loop_proc.terminate()
            print("Túnel Loophole cerrado.")
