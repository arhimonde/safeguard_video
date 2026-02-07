#!/bin/bash
set -e

# 1. Instalar OpenCV de NVIDIA (versión JetPack)
echo "📦 Instalando NVIDIA OpenCV..."
# Eliminar versión genérica si está presente
sudo apt remove -y python3-opencv || true
sudo apt autoremove -y

# Instalar meta-paquete nvidia-opencv
sudo apt update
sudo apt install -y nvidia-opencv

# 2. Desinstalar pip opencv del venv (Ya debería estar hecho, pero aseguramos)
if [ -d venv ]; then

    echo "🗑️ Asegurando la eliminación de pip opencv..."
    source venv/bin/activate
    pip uninstall -y opencv-python opencv-python-headless || true
else
    echo "⚠️ ¡No se encontró el entorno virtual (venv)! Saliendo."
    exit 1
fi

# 3. Encontrar el DIRECTORIO de cv2 del sistema
echo "🔎 Localizando el directorio cv2 del sistema..."
# Probablemente esté aquí según exploraciones previas
SYSTEM_CV2_DIR="/usr/lib/python3.10/dist-packages/cv2"

if [ ! -d "$SYSTEM_CV2_DIR" ]; then
    echo "⚠️ El directorio específico $SYSTEM_CV2_DIR no existe. Buscando..."
    SYSTEM_CV2_DIR=$(find /usr/lib/python3* -name "cv2" -type d 2>/dev/null | grep "dist-packages/cv2" | head -n 1)
fi

if [ -z "$SYSTEM_CV2_DIR" ]; then
    echo "❌ No se pudo encontrar el directorio cv2 del sistema."
    exit 1
fi

echo "Directorio cv2 del sistema encontrado: $SYSTEM_CV2_DIR"

# 4. Enlazar al entorno virtual (venv)
VENV_SITE_PACKAGES=$(find venv/lib -name "site-packages" -type d | head -n 1)
echo "🔗 Enlazando a site-packages del venv: $VENV_SITE_PACKAGES"

if [ -d "$VENV_SITE_PACKAGES" ]; then
    # Eliminar cualquier archivo/dir/enlace de cv2 existente en el venv
    rm -rf "$VENV_SITE_PACKAGES/cv2" "$VENV_SITE_PACKAGES/cv2.so"
    
    # Crear enlace simbólico válido
    ln -sfn "$SYSTEM_CV2_DIR" "$VENV_SITE_PACKAGES/cv2"
    
    echo "✅ Enlazado exitosamente (Modo Directorio)."
else
    echo "❌ ¡No se encontró site-packages en el venv!"
    exit 1
fi

echo "✅ Corrección de OpenCV aplicada. Verificando..."
# Asegurarnos de que no estamos usando una instalación residual de pip si la desinstalación falló
python3 -c "import cv2; print('Archivo OpenCV:', cv2.__file__); print('Soporte GStreamer:', 'SÍ' if 'GStreamer: YES' in cv2.getBuildInformation() else 'NO')"
