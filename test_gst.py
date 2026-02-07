import cv2
import time
import sys
import os

def test_gstreamer_pipeline():
    print("Información de compilación de OpenCV:")
    print(cv2.getBuildInformation())

    # Definición del pipeline desde camera.py
    pipeline = (
        "nvarguscamerasrc sensor-id=0 ! "
        "video/x-raw(memory:NVMM), width=(int)1280, height=(int)720, format=(string)NV12, framerate=(fraction)30/1 ! "
        "nvvidconv flip-method=0 ! "
        "video/x-raw, width=(int)640, height=(int)480, format=(string)BGRx ! "
        "videoconvert ! "
        "video/x-raw, format=(string)BGR ! appsink drop=1"
    )

    print(f"\nProbando Pipeline de GStreamer:\n{pipeline}")

    try:
        cap = cv2.VideoCapture(pipeline, cv2.CAP_GSTREAMER)
        if not cap.isOpened():
            print("❌ Error: No se pudo abrir la captura de video.")
            return

        print("✅ Captura de video abierta exitosamente.")
        
        # Intentar leer cuadros
        print("Intentando leer 10 cuadros...")
        for i in range(10):
            ret, frame = cap.read()
            if not ret:
                print(f"❌ Error: Fallo al leer el cuadro {i+1}")
                time.sleep(1)
                continue
            
            print(f"✅ Cuadro {i+1} leído exitosamente. Forma: {frame.shape}")
            time.sleep(0.1)

        cap.release()
        print("Prueba completada.")

    except Exception as e:
        print(f"‼️ Excepción: {e}")

if __name__ == "__main__":
    test_gstreamer_pipeline()
