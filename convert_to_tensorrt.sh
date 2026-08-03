#!/bin/bash

echo "🔧 Conversie YOLO11n la TensorRT pentru performanță maximă..."

cd ~/safeguard_vision
source venv/bin/activate

# Descărcare model YOLO11n dacă nu există
if [ ! -f "yolo11n.pt" ]; then
    echo "Descărcare YOLO11n.pt..."
    python3 -c "from ultralytics import YOLO; YOLO('yolo11n.pt')"
fi

# Export YOLO11n la TensorRT format optimizat pentru Jetson
echo "Export YOLO11n la TensorRT (FP16, imgsz=640)..."
python3 << 'PYTHON_SCRIPT'
from ultralytics import YOLO
import torch

print(f"CUDA Available: {torch.cuda.is_available()}")
print(f"Device: {torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU'}")

# Încărcare model
model = YOLO('yolo11n.pt')

# Export la TensorRT cu FP16 pentru Jetson
print("Export la TensorRT (poate dura câteva minute)...")
model.export(
    format='engine',  # TensorRT
    half=True,        # FP16 (2x mai rapid pe Jetson)
    imgsz=640,        # Rezoluție nativă pentru precizie maximă
    device=0,         # GPU
    workspace=4,       # 4GB workspace
    verbose=True
)

print("✅ Model TensorRT exportat: yolo11n.engine")
PYTHON_SCRIPT

echo "✅ Conversie TensorRT completă!"
echo "Modelul 'yolo11n.engine' este gata pentru inferență rapidă."
