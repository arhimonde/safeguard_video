#!/bin/bash

echo "🚀 Ejecutando Diagnóstico de Rendimiento en la Jetson..."

# Navegar al directorio del proyecto y activar venv
cd ~/safeguard_vision
source venv/bin/activate

# Verificar CUDA con Python
python3 -c "
import torch
import time
from ultralytics import YOLO
import numpy as np

print(f'--- Información de PyTorch ---')
print(f'Versión de PyTorch: {torch.__version__}')
print(f'CUDA Disponible: {torch.cuda.is_available()}')
if torch.cuda.is_available():
    print(f'Dispositivo CUDA: {torch.cuda.get_device_name(0)}')
    device = 'cuda'
else:
    print(f'⚠️ ADVERTENCIA: CUDA NO ENCONTRADO. Ejecutando en CPU.')
    device = 'cpu'

print(f'\n--- Prueba de Rendimiento YOLO11 ---')
model = YOLO('yolo11n.pt')
model.to(device)

# Crear imagen ficticia para el benchmark
dummy_img = np.zeros((480, 640, 3), dtype=np.uint8)

# Calentamiento
print('Calentando modelo...')
for _ in range(5):
    model(dummy_img, verbose=False)

# Prueba de velocidad de inferencia (20 cuadros)
print('Realizando benchmark...')
start = time.time()
for _ in range(20):
    model(dummy_img, verbose=False)
end = time.time()

avg_inference = (end - start) / 20
print(f'Tiempo promedio de inferencia: {avg_inference*1000:.2f} ms')
print(f'FPS Estimados: {1/avg_inference:.2f}')
"

echo "--- Carga del Sistema ---"
if command -v tegrastats >/dev/null; then
    timeout -s SIGINT 2s tegrastats
else
    uptime
fi
