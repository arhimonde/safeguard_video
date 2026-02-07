#!/bin/bash

# --- CONFIGURACIÓN ---
JETSON_USER="georgegabor"
JETSON_IP="192.168.1.223"
REMOTE_PATH="~/safeguard_vision"
# ---------------------

COMANDO=$1

case $COMANDO in
    "setup")
        echo "🔧 Iniciando configuración remota en Jetson..."
        ssh -t $JETSON_USER@$JETSON_IP "bash $REMOTE_PATH/remote_setup_jetson.sh"
        ;;
    "start")
        echo "▶️ Iniciando Safeguard Vision en Jetson..."
        ssh $JETSON_USER@$JETSON_IP "/bin/bash -c 'cd $REMOTE_PATH && [ -f venv/bin/activate ] && . venv/bin/activate && python3 app.py' "
        ;;
    "remote")
        echo "🌐 Iniciando Safeguard Vision con Acceso Remoto (ngrok)..."
        ssh $JETSON_USER@$JETSON_IP "/bin/bash -c 'cd $REMOTE_PATH && [ -f venv/bin/activate ] && . venv/bin/activate && python3 ngrok_tunnel.py' "
        ;;
    "stop")
        echo "⏹️ Deteniendo Safeguard Vision en Jetson..."
        ssh $JETSON_USER@$JETSON_IP "pkill -f 'python3 app.py' || true; sudo fuser -k 5000/tcp || true"
        ;;
    "status")
        echo "📊 Verificando estado en Jetson..."
        ssh $JETSON_USER@$JETSON_IP "ps aux | grep 'python3 app.py' | grep -v grep"
        ;;
    "diag")
        echo "🔍 Ejecutando diagnósticos en Jetson..."
        ssh -t $JETSON_USER@$JETSON_IP "bash $REMOTE_PATH/jetson_diag.sh"
        ;;
    "perf")
        echo "🚀 Ejecutando prueba de rendimiento en Jetson..."
        ssh -t $JETSON_USER@$JETSON_IP "bash $REMOTE_PATH/jetson_perf.sh"
        ;;
    *)
        echo "Uso: $0 {setup|start|remote|stop|status|diag|perf}"
        exit 1
        ;;
esac
