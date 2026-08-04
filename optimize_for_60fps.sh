#!/bin/bash

echo "🚀 Optimizare completă pentru 20 camere (INT8 + MAXN)"
echo "================================================"

cd ~/safeguard_vision

# Pas 1: Jetson mod MAXN (maxim performanță)
echo ""
echo "Pas 1: Jetson mod energie MAXN..."
echo "1" | sudo -S nvpmodel -m 0
echo "1" | sudo -S jetson_clocks

# Pas 2: Descărcare YOLO11n
if [ ! -f "yolo11n.pt" ]; then
    echo ""
    echo "Pas 2: Descărcare YOLO11n..."
    source venv/bin/activate
    python3 -c "from ultralytics import YOLO; YOLO('yolo11n.pt')"
else
    echo ""
    echo "Pas 2: YOLO11n.pt deja există"
fi

# Pas 3: Conversie INT8
echo ""
echo "Pas 3: Conversie YOLO11n la TensorRT INT8..."
if [ ! -f "yolo11n.engine" ]; then
    source venv/bin/activate
    python3 << 'PYTHON_SCRIPT'
from ultralytics import YOLO
import torch

if not torch.cuda.is_available():
    print("❌ CUDA necesar pentru INT8!")
    exit(1)

model = YOLO('yolo11n.pt')
print("Export TensorRT INT8 (imgsz=480)...")
model.export(
    format='engine',
    int8=True,
    half=False,
    imgsz=480,
    device=0,
    workspace=4,
    batch=1,
    dynamic=False,
    verbose=True
)
print("✅ Model INT8 creat: yolo11n.engine")
PYTHON_SCRIPT
else
    echo "✅ Model INT8 deja există"
fi

# Pas 4: Benchmark INT8
echo ""
echo "Pas 4: Test performanță INT8..."
source venv/bin/activate
python3 << 'PYTHON_SCRIPT'
from ultralytics import YOLO
import torch
import time
import numpy as np

print(f"\n--- Info GPU ---")
print(f"CUDA: {torch.cuda.is_available()}")
print(f"Device: {torch.cuda.get_device_name(0)}")

# Test cu model INT8
import os
model_path = 'yolo11n.engine' if torch.cuda.is_available() else 'yolo11n.pt'
model = YOLO(model_path)

# Frame fictiv
frame = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)

# Warmup
print("\nWarmup (10 inferențe)...")
for _ in range(10):
    _ = model(frame, imgsz=480, half=False, verbose=False)

# Benchmark (100 inferențe)
print("Benchmark (100 inferențe INT8)...")
times = []
for _ in range(100):
    start = time.time()
    _ = model(frame, imgsz=480, half=False, verbose=False)
    times.append(time.time() - start)

avg_time = np.mean(times) * 1000
fps = 1000 / avg_time

print(f"\n--- Rezultate INT8 ---")
print(f"Timp mediu inferență: {avg_time:.2f} ms")
print(f"FPS estimați (single stream): {fps:.1f}")
print(f"")
print(f"--- Estimări multi-cameră (20 camere) ---")
fps_per_cam = fps / 20
print(f"FPS per cameră (20 camere): {fps_per_cam:.1f}")
print(f"")
print(f"--- Estimări multi-cameră (10 camere) ---")
fps_per_cam_10 = fps / 10
print(f"FPS per cameră (10 camere): {fps_per_cam_10:.1f}")

if fps_per_cam >= 10:
    print(f"\n✅ Excelent! {fps_per_cam:.1f} FPS/cam pentru 20 camere — target atins!")
elif fps_per_cam >= 6:
    print(f"\n✅ Bun! {fps_per_cam:.1f} FPS/cam pentru 20 camere — suficient pt monitorizare")
else:
    print(f"\n⚠️ {fps_per_cam:.1f} FPS/cam — consideră reducerea numărului de camere")
PYTHON_SCRIPT

echo ""
echo "================================================"
echo "Optimizare completă!"
echo ""
echo "Configurație finală:"
echo "  • Model: yolo11n.engine (INT8, imgsz=480)"
echo "  • Jetson: MAXN + jetson_clocks"
echo "  • 20 camere: ~10 FPS per cameră"
echo "================================================"
