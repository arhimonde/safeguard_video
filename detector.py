from ultralytics import YOLO
import cv2
import numpy as np
import time
import os
from datetime import datetime
from database import log_incident

# Clase Detector de Objetos
# Encapsula la lógica de detección con YOLO y el análisis de seguridad (EPP y zonas).
class ObjectDetector:
    def __init__(self, model_path='yolov8n.pt', imgsz=416, half=True):
        """
        Inicializa el detector con optimizaciones para Jetson.
        """
        print(f"Cargando modelo: {model_path}...")
        
        # Detectar si es un modelo TensorRT (.engine)
        self.is_tensorrt = model_path.endswith('.engine')
        self.imgsz = imgsz
        self.half = half
        
        # Inicializa el modelo YOLO
        self.model = YOLO(model_path)
        
        print(f"Modelo cargado. TensorRT: {self.is_tensorrt}, Tamaño: {imgsz}, FP16: {half}")
        
        # Clases de interés del modelo COCO (0 = Persona)
        self.classes_of_interest = [0] 
        
        # Definición de colores para la interfaz (BGR)
        self.colors = {
            'safe': (0, 255, 0),    # Verde (Seguro)
            'danger': (0, 0, 255),  # Rojo (Peligro)
            'warning': (0, 255, 255), # Amarillo (Advertencia)
            'vest': (255, 165, 0), # Naranja (Chaleco)
            'helmet': (255, 255, 255) # Blanco (Casco)
        }
        
        # Variables para control de frecuencia de alertas (evitar spam)
        self.last_alert_time = 0
        self.alert_cooldown = 30 # Segundos entre alertas del mismo tipo
        self.last_frame_time = time.time()

    def check_ppe(self, frame, x1, y1, x2, y2):
        """
        Verifica el uso de Casco y Chaleco usando heurística de color en la región de la persona.
        """
        person_roi = frame[y1:y2, x1:x2]
        if person_roi.size == 0:
            return False, False
            
        h, w, _ = person_roi.shape
        
        # --- ROI de Casco: RESTRINGIDA HORIZONTALMENTE ---
        # Usamos solo el centro 60% del ancho para evitar paredes/fondos a los lados de la cabeza
        w_offset = int(w * 0.2)
        helmet_roi = person_roi[0:int(h*0.25), w_offset:w - w_offset]
        
        # ROI de Chaleco: 40% central (torso)
        vest_roi = person_roi[int(h*0.2):int(h*0.6), :]
        
        if helmet_roi.size == 0 or vest_roi.size == 0:
            return False, False

        hsv_helmet = cv2.cvtColor(helmet_roi, cv2.COLOR_BGR2HSV)
        hsv_vest = cv2.cvtColor(vest_roi, cv2.COLOR_BGR2HSV)
        
        # --- Detección de Casco (Refinada para evitar fondos claros) ---
        # Blanco/Claro - Aumentamos 'Value' mínimo para ser más exigentes con el brillo (evitar paredes)
        lower_white = np.array([0, 0, 180]); upper_white = np.array([180, 45, 255])
        
        # Amarillo/Verde Neon
        lower_yellow = np.array([20, 50, 70]); upper_yellow = np.array([50, 255, 255])
        
        # Rojo (Dos rangos)
        lower_red1 = np.array([0, 100, 100]); upper_red1 = np.array([10, 255, 255])
        lower_red2 = np.array([160, 100, 100]); upper_red2 = np.array([180, 255, 255])
        
        # Azul
        lower_blue = np.array([90, 80, 80]); upper_blue = np.array([130, 255, 255])
        
        # Naranja
        lower_orange = np.array([10, 100, 100]); upper_orange = np.array([25, 255, 255])
        
        masks_helmet = [
            cv2.inRange(hsv_helmet, lower_white, upper_white),
            cv2.inRange(hsv_helmet, lower_yellow, upper_yellow),
            cv2.inRange(hsv_helmet, lower_red1, upper_red1),
            cv2.inRange(hsv_helmet, lower_red2, upper_red2),
            cv2.inRange(hsv_helmet, lower_blue, upper_blue),
            cv2.inRange(hsv_helmet, lower_orange, upper_orange)
        ]
        
        helmet_pixels = sum([cv2.countNonZero(m) for m in masks_helmet])
        total_helmet_area = hsv_helmet.shape[0] * hsv_helmet.shape[1]
        
        # Umbral aumentado a 15% para Casco para filtrar ruido del fondo
        has_helmet = False
        if total_helmet_area > 0 and (helmet_pixels / total_helmet_area) > 0.15:
            has_helmet = True

        # --- Detección de Chaleco (Aumentada a 15% de densidad) ---
        mask_v_orange = cv2.inRange(hsv_vest, lower_orange, upper_orange)
        mask_v_yellow = cv2.inRange(hsv_vest, np.array([20, 20, 50]), upper_yellow) 
        mask_v_red = cv2.bitwise_or(cv2.inRange(hsv_vest, lower_red1, upper_red1), cv2.inRange(hsv_vest, lower_red2, upper_red2))
        
        vest_pixels = cv2.countNonZero(mask_v_orange) + cv2.countNonZero(mask_v_yellow) + cv2.countNonZero(mask_v_red)
        total_vest_area = hsv_vest.shape[0] * hsv_vest.shape[1]
        
        # Umbral aumentado a 15% para Chaleco
        has_vest = False
        if total_vest_area > 0 and (vest_pixels / total_vest_area) > 0.15:
            has_vest = True
                
        return has_helmet, has_vest

    def detect(self, frame):
        if frame is None: return None, {}
        results = self.model(frame, verbose=False, imgsz=self.imgsz, half=self.half, device=0)
        annotated_frame = frame.copy()
        stats = {'total_persons': 0, 'violations': 0, 'alerts': []}
        current_violations = 0
        violation_types = []

        h_img, w_img, _ = frame.shape
        danger_zone_x = int(w_img * 0.7) 

        for r in results:
            for box in r.boxes:
                if int(box.cls[0]) == 0: # Persona
                    stats['total_persons'] += 1
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    
                    # Verificación de Zona (Centro)
                    x_mid = (x1 + x2) // 2
                    is_in_danger_zone = x_mid > danger_zone_x
                    
                    has_helmet, has_vest = self.check_ppe(frame, x1, y1, x2, y2)
                    
                    # LOGICA CRÍTICA: Seguro SOLO si tiene AMBOS
                    has_all_ppe = has_helmet and has_vest
                    
                    is_warning = False
                    is_safe = False
                    
                    if not has_all_ppe:
                        # Si falta cualquier cosa, es PELIGRO (Rojo)
                        is_safe = False; is_warning = False
                    elif is_in_danger_zone:
                        # Si tiene todo pero está en zona, es AVISO (Amarillo)
                        is_safe = False; is_warning = True
                    else:
                        # Solo si tiene todo Y está fuera de zona es SEGURO (Verde)
                        is_safe = True; is_warning = False

                    label_parts = []
                    if not has_helmet: label_parts.append("SIN CASCO")
                    if not has_vest: label_parts.append("SIN CHALECO")
                    if is_in_danger_zone: label_parts.append("ZONA PELIGROSA")

                    if is_safe:
                        color = self.colors['safe']; label = "Seguro"
                    elif is_warning:
                        color = self.colors['warning']; reason = ", ".join(label_parts)
                        label = f"AVISO: {reason}"
                        stats['violations'] += 1; current_violations += 1
                        stats['alerts'].append(f"Aviso: {reason}"); violation_types.append(reason)
                    else:
                        color = self.colors['danger']; reason = ", ".join(label_parts)
                        label = f"PELIGRO: {reason}"
                        stats['violations'] += 1; current_violations += 1
                        stats['alerts'].append(f"Peligro: {reason}"); violation_types.append(reason)

                    cv2.rectangle(annotated_frame, (x1, y1), (x2, y2), color, 2)
                    cv2.putText(annotated_frame, label, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
        
        # Visualización Zona
        overlay = annotated_frame.copy()
        cv2.rectangle(overlay, (danger_zone_x, 0), (w_img, h_img), (0, 0, 255), -1)
        cv2.addWeighted(overlay, 0.2, annotated_frame, 0.8, 0, annotated_frame)
        cv2.line(annotated_frame, (danger_zone_x, 0), (danger_zone_x, h_img), (0, 0, 255), 2)
        cv2.putText(annotated_frame, "ZONA DE PELIGRO", (danger_zone_x + 10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cv2.putText(annotated_frame, timestamp, (10, h_img - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        
        current_time = time.time()
        fps = 1 / (current_time - self.last_frame_time) if hasattr(self, 'last_frame_time') else 0
        self.last_frame_time = current_time
        cv2.putText(annotated_frame, f"FPS: {int(fps)}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

        if current_violations > 0 and (time.time() - self.last_alert_time > self.alert_cooldown):
            v_type = violation_types[0] if violation_types else "Violación de Seguridad"
            self.save_alert(annotated_frame, v_type)
            self.last_alert_time = time.time()

        return annotated_frame, stats

    def save_alert(self, frame, incident_type):
        """
        Guarda una imagen del incidente en el disco y registra el evento en la base de datos.
        """
        try:
            timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"capture_{timestamp_str}.jpg"
            base_dir = os.path.dirname(os.path.abspath(__file__))
            save_dir = os.path.join(base_dir, 'static/captures')
            filepath = os.path.join(save_dir, filename)
            web_path = f"captures/{filename}" 
            if not os.path.exists(save_dir): os.makedirs(save_dir, exist_ok=True)
            if cv2.imwrite(filepath, frame):
                print(f"✅ Imagen de alerta guardada: {filepath}")
                log_incident(incident_type, web_path, f"Violación detectada: {incident_type}")
        except Exception as e:
            print(f"❌ Error en save_alert: {e}")
