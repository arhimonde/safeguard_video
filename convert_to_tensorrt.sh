#!/bin/bash

echo "🔧 Converting YOLOv8 to TensorRT for Maximum Speed..."

cd ~/safeguard_vision
source venv/bin/activate

# Export YOLOv8 to TensorRT format optimized for Jetson
echo "Exporting YOLOv8n to TensorRT (FP16)..."
python3 << 'PYTHON_SCRIPT'
from ultralytics import YOLO
import torch

print(f"CUDA Available: {torch.cuda.is_available()}")
print(f"Device: {torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU'}")

# Load the model
model = YOLO('yolov8n.pt')

# Export to TensorRT with FP16 precision for Jetson
print("Exporting to TensorRT (this may take a few minutes)...")
model.export(
    format='engine',  # TensorRT
    half=True,        # FP16 precision (2x faster on Jetson)
    imgsz=416,        # Smaller input size for speed
    device=0,         # Use GPU
    workspace=4,      # 4GB workspace
    verbose=True
)

print("✅ TensorRT model exported as: yolov8n.engine")
print("This model will be 2-3x faster than the original!")
PYTHON_SCRIPT

echo "✅ TensorRT conversion complete!"
echo "The model 'yolov8n.engine' is now ready for ultra-fast inference."
