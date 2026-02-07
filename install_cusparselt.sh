#!/bin/bash

echo "⚙️ Instalando cuSPARSELt para JetPack 6.2 / CUDA 12.6..."

# Navegar al directorio del proyecto
cd ~/safeguard_vision

# Verificar si la librería ya existe
if ldconfig -p | grep -q "libcusparseLt.so.0"; then
    echo "✅ cuSPARSELt ya está instalado"
    ldconfig -p | grep libcusparseLt
    exit 0
fi

echo "Descargando cuSPARSELt para Jetson (aarch64)..."

# Crear directorio temporal
mkdir -p /tmp/cusparselt_install
cd /tmp/cusparselt_install

# Descargar cuSPARSELt 0.6.3.2 para aarch64
wget https://developer.download.nvidia.com/compute/cusparselt/redist/libcusparse_lt/linux-aarch64/libcusparse_lt-linux-aarch64-0.6.3.2-archive.tar.xz

# Extraer
tar -xf libcusparse_lt-linux-aarch64-0.6.3.2-archive.tar.xz

# Copiar librerías al directorio CUDA (requiere sudo con contraseña)
echo "Instalando librerías (requiere contraseña de sudo '1')..."
echo "1" | sudo -S cp -r libcusparse_lt-linux-aarch64-0.6.3.2-archive/lib/* /usr/local/cuda-12.6/lib64/
echo "1" | sudo -S cp -r libcusparse_lt-linux-aarch64-0.6.3.2-archive/include/* /usr/local/cuda-12.6/include/

# Actualizar caché de librerías
echo "1" | sudo -S ldconfig

# Limpieza
cd ~
rm -rf /tmp/cusparselt_install

echo "✅ ¡cuSPARSELt instalado con éxito!"
echo "--- Verificando instalación ---"
ldconfig -p | grep -i cusparse
