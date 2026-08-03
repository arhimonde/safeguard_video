#!/bin/bash

echo "🚀 Optimizare completă pentru performanță maximă"
echo "================================================"

cd ~/safeguard_vision

# Pas 1: Jetson în mod maxim performanță
echo ""
echo "Pas 1: Jetson mod energie MAXN..."
echo "1" | sudo -S nvpmodel -m 0
echo "1" | sudo -S jetson_clocks

# Pas 2: Descărcare YOLO11n dacă nu există
if [ ! -f "yolo11n.pt" ]; then
    echo ""
    echo "Pas 2: Descărcare YOLO11n..."
    source venv/bin/activate
    python3 -c "from ultralytics import YOLO; YOLO('yolo11n.pt')"
else
    echo ""
    echo "Pas 2: YOLO11n.pt deja există"
fi

# Pas 3: Conversie TensorRT dacă nu există
echo ""
echo "Pas 3: Conversie YOLO11n la TensorRT..."
if [ ! -f "yolo11n.engine" ]; then
    source venv/bin/activate
    python3 << 'PYTHON_SCRIPT'
from ultralytics import YOLO
import torch

print(f"CUDA disponibil: {torch.cuda.is_available()}")

# Încărcare și export TensorRT
model = YOLO('yolo11n.pt')
print("Export TensorRT (FP16, 640x640)...")
model.export(
    format='engine',
    half=True,
    imgsz=640,
    device=0,
    workspace=4,
    verbose=True
)
print("✅ Model TensorRT: yolo11n.engine")
PYTHON_SCRIPT
else
    echo "✅ Model TensorRT deja există"
fi

# Pas 4: Benchmark
echo ""
echo "Pas 4: Test performanță..."
source venv/bin/activate
python3 << 'PYTHON_SCRIPT'
from ultralytics import YOLO
import torch
import time
import numpy as np

print(f"\n--- Info GPU ---")
print(f"CUDA: {torch.cuda.is_available()}")
print(f"Device: {torch.cuda.get_device_name(0)}")

# Test cu TensorRT
model = YOLO('yolo11n.engine' if torch.cuda.is_available() else 'yolo11n.pt')

# Frame fictiv
frame = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)

# Warmup
print("\nWarmup...")
for _ in range(10):
    _ = model(frame, imgsz=640, half=True, verbose=False)

# Benchmark
print("Benchmark (100 inferențe)...")
times = []
for _ in range(100):
    start = time.time()
    _ = model(frame, imgsz=640, half=True, verbose=False)
    times.append(time.time() - start)

avg_time = np.mean(times) * 1000
fps = 1000 / avg_time

print(f"\n--- Rezultate ---")
print(f"Timp mediu inferență: {avg_time:.2f} ms")
print(f"FPS estimați: {fps:.2f}")
print(f"Target detecție: 18 FPS (~{1000/18:.2f} ms per frame)")
print(f"(cu frame decimation x2 = ~{fps/2:.1f} FPS efectivi pe video)")

if fps >= 36:
    print("✅ Excelent! Mai mult decât suficient pentru 18 FPS target.")
elif fps >= 18:
    print("✅ OK! Suficient pentru target.")
else:
    print("⚠️ Sub target. Consideră imgsz=416 sau INT8 quantization.")
PYTHON_SCRIPT

echo ""
echo "================================================"
echo "Optimizare completă!"
echo "Pentru a folosi modelul:"
echo "  detector = ObjectDetector('yolo11n.engine', imgsz=640, half=True)"
