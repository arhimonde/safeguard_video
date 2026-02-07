#!/bin/bash

# --- CONFIGURACIÓN ---
# IMPORTANTE: Actualiza estos valores con los detalles de tu Jetson
JETSON_USER="georgegabor"
JETSON_IP="192.168.1.223"
REMOTE_PATH="~/safeguard_vision" # No cambiamos la ruta en el NVIDIA, solo en el local
# ---------------------

echo "🚀 Iniciando despliegue en Jetson Orin Nano ($JETSON_IP)..."

# Usar rsync para sincronizar archivos, excluyendo directorios innecesarios
rsync -avz --progress \
    --exclude 'venv' \
    --exclude '__pycache__' \
    --exclude '.git' \
    --exclude '.gemini' \
    --exclude 'safeguard.db' \
    --exclude 'deploy_to_jetson.sh' \
    ./ $JETSON_USER@$JETSON_IP:$REMOTE_PATH

if [ $? -eq 0 ]; then
    echo "✅ ¡Despliegue exitoso!"
    echo "Siguiente paso: Ejecuta ./jetson_cmd.sh setup para instalar dependencias en la Jetson."
else
    echo "❌ El despliegue falló. Por favor verifica la IP y la conexión SSH."
fi
