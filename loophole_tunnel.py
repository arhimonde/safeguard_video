import os
import subprocess
import sys
import time
import signal

# Configuración de Loophole
# Permite acceder al servidor local desde internet de forma gratuita.
# Para el primer uso, es posible que debas loguearte: ./loophole account login

def start_loophole():
    """
    Inicia un túnel HTTP usando el binario de Loophole para exponer el puerto local 5000.
    """
    port = 5000
    print(f" * Iniciando túnel Loophole en el puerto {port}...")
    
    # Ejecutamos loophole como un subproceso
    # El comando 'http' crea un túnel para el puerto especificado
    cmd = ["./loophole", "http", str(port)]
    
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
            print(f" [Loophole] {line.strip()}")
            if "https://" in line and "loophole.site" in line:
                # Extraer la URL de la línea (usualmente al final)
                parts = line.split()
                for part in parts:
                    if part.startswith("https://"):
                        public_url = part
                        break
                if public_url:
                    break
        
        if public_url:
            print(f"\n🚀 URL Pública: {public_url}")
            return process, public_url
        else:
            print("❌ No se pudo extraer la URL de Loophole.")
            process.terminate()
            return None, None
            
    except FileNotFoundError:
        print("❌ Error: No se encontró el binario 'loophole'. asegúrate de haberlo descargado.")
        return None, None
    except Exception as e:
        print(f"❌ Error al iniciar Loophole: {e}")
        return None, None

if __name__ == "__main__":
    print("========================================")
    print("   Safeguard Vision - Remote Access     ")
    print("========================================\n")
    
    loop_proc, url = start_loophole()
    
    if not url:
        print("Asegúrate de haber descargado el binario de Loophole.")
        sys.exit(1)
        
    print("Iniciando aplicación Flask...")
    
    try:
        # Importar la app de Flask
        from app import app
        import os
        os.makedirs('static/captures', exist_ok=True)
        
        # Ejecutar la app
        app.run(host='0.0.0.0', port=5000, use_reloader=False)
    except KeyboardInterrupt:
        print("\nCerrando túnel y servidor...")
    finally:
        if loop_proc:
            loop_proc.terminate()
            print("Túnel Loophole cerrado.")
