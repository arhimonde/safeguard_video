#!/bin/bash

echo "🔍 Ejecutando Diagnóstico Integral de la Jetson..."

echo "--- 1. Verificando dispositivos de video (/dev/video*) ---"
ls -l /dev/video* 2>/dev/null
if [ $? -ne 0 ]; then
    echo "❌ ¡No se encontraron dispositivos /dev/video!"
else
    echo "✅ Se encontraron dispositivos /dev/video."
fi

echo "--- 2. Verificando v4l2-ctl (v4l-utils) ---"
if command -v v4l2-ctl &> /dev/null; then
    echo "✅ v4l2-ctl está instalado."
    v4l2-ctl --list-devices
else
    echo "❌ v4l2-ctl NO está instalado. Instálalo con 'sudo apt install v4l-utils'."
fi

echo "--- 3. Verificando GStreamer nvarguscamerasrc ---"
if gst-inspect-1.0 nvarguscamerasrc &> /dev/null; then
    echo "✅ nvarguscamerasrc está disponible."
else
    echo "❌ nvarguscamerasrc NO se encontró. ¿Es esta una Jetson con JetPack instalado?"
fi

echo "--- 4. Verificando módulos del kernel (nv*) ---"
lsmod | grep nv | head -n 5

echo "--- 5. Verificando libcusparseLt (Búsqueda heredada) ---"
# Buscar en ubicaciones típicas
SEARCH_PATHS=(
    "/usr/lib/aarch64-linux-gnu"
    "/usr/lib/aarch64-linux-gnu/nvidia"
    "/usr/local/cuda-12.6/lib64"
    "/usr/local/cuda-12/lib64"
    "/usr/local/cuda/lib64"
)

for path in "${SEARCH_PATHS[@]}"; do
    # echo "Buscando en $path..."
    find "$path" -name "libcusparseLt*" 2>/dev/null
done

echo "--- 6. Verificando disponibilidad del índice PIP ---"
curl -s https://pypi.jetson-ai-lab.io/jp6/cu126/index.html | grep -i torch | head -n 5

echo "--- Fin del Diagnóstico ---"
