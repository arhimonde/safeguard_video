#!/bin/bash
# Script para reparar el entorno virtual en la Jetson Orin Nano

source venv/bin/activate

echo "🔧 Reparando dependencias para evitar bloqueos..."

# 1. Forzar NumPy < 2.0 (OpenCV y PyTorch en Jetson lo prefieren)
pip install "numpy<2.0" --force-reinstall

# 2. Instalar una versión compatible de OpenCV que no exija NumPy 2.x
# En Jetson, solemos usar la versión del sistema o una compilada que no sea la de pip 4.10+
pip uninstall -y opencv-python opencv-python-headless
pip install "opencv-python==4.8.0.76"

# 3. Solucionar el problema de TensorRT
# Ultralytics intenta instalarlo si no lo encuentra. 
# En Jetson está en el sistema. Vamos a linkearlo.
PYTHON_VER=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
DIST_PACKAGES="/usr/lib/python${PYTHON_VER}/dist-packages"
VENV_PACKAGES="venv/lib/python${PYTHON_VER}/site-packages"

echo "🔗 Vinculando TensorRT del sistema al venv..."
cp -r ${DIST_PACKAGES}/tensorrt* ${VENV_PACKAGES}/ 2>/dev/null || true
cp -r ${DIST_PACKAGES}/graphsurgeon* ${VENV_PACKAGES}/ 2>/dev/null || true
cp -r ${DIST_PACKAGES}/uff* ${VENV_PACKAGES}/ 2>/dev/null || true

# 4. Verificar instalaciones
echo "📊 Verificación de versiones:"
python3 -c "import numpy; import cv2; import tensorrt; print(f'NumPy: {numpy.__version__}'); print(f'OpenCV: {cv2.__version__}'); print(f'TensorRT: {tensorrt.__version__}')"

echo "✅ Reparación completada."
