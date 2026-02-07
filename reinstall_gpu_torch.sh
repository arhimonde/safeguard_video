#!/bin/bash

echo "🔧 Reinstalando GPU PyTorch tras la corrección de cuSPARSELt..."

cd ~/safeguard_vision
source venv/bin/activate

# 1. Desinstalar torch/torchvision actual
echo "Eliminando PyTorch solo para CPU..."
pip uninstall -y torch torchvision

# 2. Reinstalar versiones con soporte GPU
echo "Instalando GPU PyTorch 2.5.0..."
TORCH_URL="https://github.com/ultralytics/assets/releases/download/v0.0.0/torch-2.5.0a0+872d972e41.nv24.08-cp310-cp310-linux_aarch64.whl"
TORCHVISION_URL="https://github.com/ultralytics/assets/releases/download/v0.0.0/torchvision-0.20.0a0+afc54f7-cp310-cp310-linux_aarch64.whl"

pip install --no-cache-dir "$TORCH_URL"
pip install --no-cache-dir "$TORCHVISION_URL"

# 3. Probar CUDA
echo "--- Probando CUDA ---"
python3 -c "import torch; print('CUDA Disponible:', torch.cuda.is_available()); print('Dispositivo:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'Ninguno')"

# 4. Probar YOLO
echo "--- Probando YOLO ---"
python3 -c "from ultralytics import YOLO; model = YOLO('yolov8n.pt'); print('Dispositivo YOLO:', model.device)"

echo "✅ ¡GPU PyTorch reinstalado exitosamente!"
