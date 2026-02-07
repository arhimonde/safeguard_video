import cv2
import time
import numpy as np
import threading

# Clase de Cámara Sintética (Simulada)
# Se utiliza cuando no se encuentra una cámara física disponible.
class SyntheticCamera:
    def __init__(self):
        self.width = 640
        self.height = 480
        self.frame_count = 0
        print("Inicializando Cámara Sintética (Modo Simulación)...")

    def read(self):
        # Crear un cuadro vacío (negro)
        frame = np.zeros((self.height, self.width, 3), dtype=np.uint8)
        
        self.frame_count += 1
        # Lógica para animar un círculo amarillo moviéndose
        x = int((np.sin(self.frame_count * 0.05) + 1) * 0.5 * (self.width - 50)) + 25
        y = int((np.cos(self.frame_count * 0.05) + 1) * 0.5 * (self.height - 50)) + 25
        
        cv2.circle(frame, (x, y), 20, (0, 255, 255), -1)
        cv2.putText(frame, "MODO SIMULACION", (100, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
        
        # Simular una "persona" con cambios de equipo EPP
        head_color = (255, 255, 255) if (self.frame_count // 30) % 2 == 0 else (50, 50, 50) 
        cv2.circle(frame, (320, 200), 40, head_color, -1)
        
        body_color = (0, 165, 255) if (self.frame_count // 60) % 2 == 0 else (100, 100, 100) 
        cv2.rectangle(frame, (280, 240), (360, 400), body_color, -1)
        
        cv2.putText(frame, "¡Apunta la camara a una persona para probar!", (50, 450), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        
        return True, frame

    def release(self):
        pass

# Clase Principal de Cámara de Video con Hilos (Threading)
# Esta clase gestiona la captura de video en un hilo separado para no bloquear el procesamiento de la IA.
class VideoCamera:
    def __init__(self, source=0):
        self.video = None
        self.stopped = False
        self.frame = None
        self.grabbed = False
        self.using_synthetic = False
        
        # Configuración del pipeline de GStreamer para Jetson Orin Nano (CSI)
        jetson_csi_pipeline = (
            "nvarguscamerasrc sensor-id=0 ! "
            "video/x-raw(memory:NVMM), width=(int)1280, height=(int)720, format=(string)NV12, framerate=(fraction)60/1 ! "
            "nvvidconv flip-method=0 ! "
            "video/x-raw, width=(int)640, height=(int)480, format=(string)BGRx ! "
            "videoconvert ! "
            "video/x-raw, format=(string)BGR ! appsink drop=true sync=false"
        )
        
        # Fuentes para intentar abrir (CSI, USB Video1, USB Video2, Video0)
        sources_to_try = [jetson_csi_pipeline, 1, 2, 0]
        
        for idx in sources_to_try:
            print(f"Intentando abrir fuente: {idx}")
            try:
                if isinstance(idx, int):
                    import os
                    if not os.path.exists(f"/dev/video{idx}"):
                         continue
                
                # Usar GStreamer para el pipeline de Jetson, V4L2 para cámaras USB
                backend = cv2.CAP_GSTREAMER if isinstance(idx, str) else cv2.CAP_V4L2
                cap = cv2.VideoCapture(idx, backend)
                
                if cap.isOpened():
                    if isinstance(idx, int):
                        # Configuración para cámaras USB (V4L2)
                        fourcc = cv2.VideoWriter_fourcc(*'MJPG')
                        cap.set(cv2.CAP_PROP_FOURCC, fourcc)
                        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                        cap.set(cv2.CAP_PROP_FPS, 60) 

                    time.sleep(1) # Esperar a que la cámara se estabilice
                    ret, frame = cap.read()
                    if ret:
                        print(f"✅ Cámara abierta EXITOSAMENTE: {idx}")
                        self.video = cap
                        break
                    else:
                        cap.release()
            except Exception as e:
                print(f"‼️ Excepción al abrir {idx}: {e}")

        if self.video is None:
            print("Error: No se encontró ninguna cámara. Cambiando a Cámara Sintética.")
            self.video = SyntheticCamera()
            self.using_synthetic = True
        
        # Iniciar hilo de lectura continua
        threading.Thread(target=self.update, args=(), daemon=True).start()

    def update(self):
        """
        Bucle infinito que captura cuadros de la cámara en segundo plano.
        """
        while True:
            if self.stopped:
                return
            
            self.grabbed, self.frame = self.video.read()
            if not self.grabbed and not self.using_synthetic:
                self.stop()
            
            # Pequeña pausa para no saturar la CPU en modo sintético
            if self.using_synthetic:
                time.sleep(0.016) # Aproximadamente 60 FPS

    def get_frame(self):
        """
        Devuelve el último cuadro capturado por el hilo de actualización.
        """
        return self.frame

    def get_jpeg_frame(self):
        """
        Devuelve el último cuadro codificado en JPEG.
        """
        image = self.get_frame()
        if image is None:
            return None
        ret, jpeg = cv2.imencode('.jpg', image)
        return jpeg.tobytes()

    def stop(self):
        """
        Detiene la captura y libera la cámara.
        """
        self.stopped = True
        if hasattr(self.video, 'release'):
            self.video.release()

    def __del__(self):
        self.stop()
