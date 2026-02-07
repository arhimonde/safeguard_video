#!/bin/bash

echo "⚙️  Configurando entorno de ALTO RENDIMIENTO en Jetson Orin Nano (JetPack 6.2 / CUDA 12.6)..."

# Navegar al directorio del proyecto
cd ~/safeguard_vision

# 1. Instalar librerías de sistema ESENCIALES para CUDA 12 (Nombres directos para JP 6.2)
echo "Instalando/Reparando librerías de sistema NVIDIA..."
sudo apt update
# Intentamos múltiples nombres comunes para asegurar la instalación
sudo apt install -y libcusparse-lt0 libcusparse-lt-dev libcusparse-dev-12-6 || sudo apt install -y nvidia-cusparselt

# 2. Actualizar caché de librerías
echo "Actualizando caché de librerías..."
sudo ldconfig

# 3. Configurar variables de entorno CUDA
export PATH=/usr/local/cuda-12.6/bin:$PATH
export LD_LIBRARY_PATH=/usr/local/cuda-12.6/lib64:/usr/lib/aarch64-linux-gnu/nvidia:$LD_LIBRARY_PATH
export CUDA_HOME=/usr/local/cuda-12.6

# 4. Limpiar entorno
echo "Creando un entorno virtual (venv) LIMPIO..."
rm -rf venv
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip

# 5. Instalar GPU PyTorch y Torchvision desde URLs verificadas
echo "Instalando PyTorch/Torchvision con aceleración GPU (NVIDIA)..."
TORCH_URL="https://github.com/ultralytics/assets/releases/download/v0.0.0/torch-2.5.0a0+872d972e41.nv24.08-cp310-cp310-linux_aarch64.whl"
TORCHVISION_URL="https://github.com/ultralytics/assets/releases/download/v0.0.0/torchvision-0.20.0a0+afc54f7-cp310-cp310-linux_aarch64.whl"

pip install --no-cache-dir "$TORCH_URL"
pip install --no-cache-dir "$TORCHVISION_URL"

# 6. Verificar CUDA INMEDIATAMENTE
echo "--- Verificando CUDA en el Venv ---"
python3 -c "import torch; print('CUDA Disponible:', torch.cuda.is_available()); print('Dispositivo:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'Ninguno')"

# 7. Instalar Ultralytics y dependencias
echo "Instalando Ultralytics (Preservando GPU Torch)..."
# Instalamos normalmente, debería detectar la versión compatible de torch
pip install ultralytics
pip install -r requirements.txt

# 8. Verificación Final de GPU
echo "--- Verificación Final de GPU ---"
python3 -c "from ultralytics import YOLO; import torch; model = YOLO('yolov8n.pt'); print('YOLO está utilizando:', model.device)"

echo "✅ ¡Configuración finalizada! Por favor ejecuta ./jetson_cmd.sh perf para verificar el aumento de FPS."
