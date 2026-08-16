#!/bin/bash

# --- CONFIGURACIÓN ---
JETSON_USER="georgegabor"
JETSON_IP="192.168.1.223"
REMOTE_PATH="~/safeguard_vision_alpha"
JETSON_PASS="1" 
# ---------------------

# Wrapper para SSH con contraseña automática
if command -v sshpass &> /dev/null; then
    SSH_CMD="sshpass -p $JETSON_PASS ssh"
else
    echo "⚠️ 'sshpass' no está instalado. Se pedirá la contraseña manualmente."
    SSH_CMD="ssh"
fi

COMANDO=$1

case $COMANDO in
    "setup")
        echo "🔧 Iniciando configuración remota en Jetson..."
        $SSH_CMD -t $JETSON_USER@$JETSON_IP "bash $REMOTE_PATH/remote_setup_jetson.sh"
        ;;
    "start")
        echo "▶️ Iniciando Safeguard Vision Alpha en Jetson (Modo ULTRA)..."
        $SSH_CMD -t $JETSON_USER@$JETSON_IP "sudo -S <<< '$JETSON_PASS' nvpmodel -m 0; sudo -S <<< '$JETSON_PASS' jetson_clocks; export LD_LIBRARY_PATH=/usr/local/cuda/lib64:/usr/lib/aarch64-linux-gnu/tegra:\$LD_LIBRARY_PATH; cd $REMOTE_PATH && python3 app.py"
        ;;
    "remote")
        echo "🌐 Iniciando Safeguard Vision con Acceso Remoto ULTRA (Loophole)..."
        $SSH_CMD -t $JETSON_USER@$JETSON_IP "sudo -S <<< '$JETSON_PASS' nvpmodel -m 0; sudo -S <<< '$JETSON_PASS' jetson_clocks; export LD_LIBRARY_PATH=/usr/local/cuda/lib64:/usr/lib/aarch64-linux-gnu/tegra:\$LD_LIBRARY_PATH; cd $REMOTE_PATH && python3 loophole_tunnel.py"
        ;;
    "stop")
        echo "⏹️ Deteniendo Safeguard Vision en Jetson..."
        $SSH_CMD $JETSON_USER@$JETSON_IP "pkill -f 'python3 app.py' || true; sudo -S <<< '$JETSON_PASS' fuser -k 5000/tcp || true"
        ;;
    "status")
        echo "📊 Verificando estado en Jetson..."
        $SSH_CMD $JETSON_USER@$JETSON_IP "ps aux | grep 'python3 app.py' | grep -v grep"
        ;;
    "diag")
        echo "🔍 Ejecutando checklist de testare en Jetson..."
        $SSH_CMD -t $JETSON_USER@$JETSON_IP "bash $REMOTE_PATH/jetson_test_checklist.sh"
        ;;
    "perf")
        echo "🚀 Ejecutando prueba de rendimiento en Jetson..."
        $SSH_CMD -t $JETSON_USER@$JETSON_IP "bash $REMOTE_PATH/jetson_perf.sh"
        ;;
    *)
        echo "Uso: $0 {setup|start|remote|stop|status|diag|perf}"
        exit 1
        ;;
esac
