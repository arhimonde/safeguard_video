#!/bin/bash

echo "🚀 Optimización Completa de Rendimiento para 60 FPS"
echo "===================================================="

cd ~/safeguard_vision

# Paso 1: Configurar Jetson en modo de máximo rendimiento
echo ""
echo "Paso 1: Configurando Jetson en modo de energía MAXN..."
echo "1" | sudo -S nvpmodel -m 0
echo "1" | sudo -S jetson_clocks

# Paso 2: Convertir modelo a TensorRT (si no se ha hecho aún)
echo ""
echo "Paso 2: Convirtiendo YOLOv8 a TensorRT..."
if [ ! -f "yolov8n.engine" ]; then
    source venv/bin/activate
    python3 << 'PYTHON_SCRIPT'
from ultralytics import YOLO
import torch

print(f"CUDA disponible: {torch.cuda.is_available()}")

# Cargar y exportar a TensorRT
model = YOLO('yolov8n.pt')
print("Exportando a TensorRT (FP16, 416x416)...")
model.export(
    format='engine',
    half=True,
    imgsz=416,
    device=0,
    workspace=4,
    verbose=True
)
print("✅ Modelo TensorRT creado: yolov8n.engine")
PYTHON_SCRIPT
else
    echo "✅ El modelo TensorRT ya existe"
fi

# Paso 3: Probar rendimiento
echo ""
echo "Paso 3: Evaluando rendimiento..."
source venv/bin/activate
python3 << 'PYTHON_SCRIPT'
from ultralytics import YOLO
import torch
import time
import numpy as np

print(f"\n--- Información de la GPU ---")
print(f"CUDA Disponible: {torch.cuda.is_available()}")
print(f"Dispositivo: {torch.cuda.get_device_name(0)}")

# Probar con el modelo TensorRT
model = YOLO('yolov8n.engine' if torch.cuda.is_available() else 'yolov8n.pt')

# Crear cuadro ficticio (dummy frame)
frame = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)

# Calentamiento (Warm up)
print("\nCalentando modelo...")
for _ in range(10):
    _ = model(frame, imgsz=416, half=True, verbose=False)

# Prueba de velocidad (Benchmark)
print("Realizando benchmark...")
times = []
for _ in range(100):
    start = time.time()
    _ = model(frame, imgsz=416, half=True, verbose=False)
    times.append(time.time() - start)

avg_time = np.mean(times) * 1000
fps = 1000 / avg_time

print(f"\n--- Resultados de Rendimiento ---")
print(f"Tiempo promedio de inferencia: {avg_time:.2f} ms")
print(f"FPS Estimados: {fps:.2f}")
print(f"Objetivo: 60 FPS ({16.67:.2f} ms por cuadro)")

if fps >= 60:
    print("✅ ¡Objetivo alcanzado!")
elif fps >= 50:
    print("⚠️ Cerca del objetivo - podría alcanzar 60 FPS con optimización de cámara")
else:
    print(f"ℹ️ Mejora de velocidad actual: {fps/34.6:.1f}x respecto al original")
PYTHON_SCRIPT

echo ""
echo "===================================================="
echo "¡Optimización completada!"
echo "Para usar el modelo optimizado, actualiza app.py para usar:"
echo "  detector = ObjectDetector('yolov8n.engine', imgsz=416, half=True)"
