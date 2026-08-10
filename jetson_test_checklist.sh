#!/bin/bash
# Checklist de testare + diagnosticare pe Jetson.
# Verifică că tot codul funcționează corect pe hardware real.
# Utilizare: bash jetson_test_checklist.sh

cd "$(dirname "$0")"
source venv/bin/activate 2>/dev/null

PASS=0
FAIL=0
ok() { echo "✅ $1"; PASS=$((PASS+1)); }
ko() { echo "❌ $1"; FAIL=$((FAIL+1)); }

echo "========================================"
echo "  SAFEGUARD VISION — CHECKLIST JETSON"
echo "========================================"
echo ""

# 1. Python + pip
if command -v python3 &>/dev/null; then ok "Python3: $(python3 --version 2>&1)"; else ko "Python3 lipsă"; fi

# 2. CUDA
python3 -c "import torch; print(torch.cuda.is_available())" 2>/dev/null | grep -q True && ok "CUDA disponibil (torch)" || ko "CUDA indisponibil (torch)"
nvidia-smi -L 2>/dev/null | head -1 && ok "nvidia-smi" || echo "ℹ️  nvidia-smi indisponibil (normal pe Jetson)"

# 3. OpenCV + GStreamer
python3 -c "
import cv2
print('OpenCV:', cv2.__version__)
print('GStreamer:', 'da' if 'GStreamer' in cv2.getBuildInformation() else 'nu')
" 2>/dev/null && ok "OpenCV import" || ko "OpenCV import eșuat"

# 4. Ultralytics + YOLO
python3 -c "from ultralytics import YOLO; m=YOLO('yolo11n.pt'); print('YOLO11n încărcat, device:', m.device)" 2>/dev/null && ok "YOLO11n" || ko "YOLO11n indisponibil"

# 5. TensorRT engine (dacă există)
if [ -f "yolo11n.engine" ]; then ok "TensorRT engine: yolo11n.engine există"; else echo "ℹ️  TensorRT engine lipsă — rulează bash convert_to_tensorrt.sh"; fi

# 6. Flask + SocketIO
python3 -c "import flask; import flask_socketio; import flask_login; print('Flask:', flask.__version__)" 2>/dev/null && ok "Flask + SocketIO" || ko "Flask indisponibil"

# 7. Psutil (health check)
python3 -c "import psutil; print('Memoria:', psutil.virtual_memory().percent, '%')" 2>/dev/null && ok "psutil" || echo "ℹ️  psutil lipsă (health check fară memorie info)"

# 8. SQLite
python3 -c "
import sqlite3, os
db = 'safeguard.db'
if os.path.exists(db): print('DB există')
else: print('DB va fi creat la pornire')
" 2>/dev/null && ok "SQLite + safeguard.db" || ko "SQLite eșuat"

# 9. License
if [ -f ".license" ]; then ok "Licență setată (.license)"; else echo "ℹ️  Licență nesetată — python3 license.py --set COD"; fi

# 10. cameras.json
python3 -c "
import json, os
if not os.path.exists('cameras.json'):
    print('cameras.json LIPSE — creează cu format [{\"id\":1,\"name\":\"Test\",\"url\":\"rtsp://...\"}]')
    exit(1)
with open('cameras.json') as f:
    cams = json.load(f)
print(f'cameras.json: {len(cams)} camere')
" 2>/dev/null && ok "cameras.json valid" || ko "cameras.json invalid/lipsă"

# 11. Import toate module
python3 -c "
import app, detector, camera, camera_manager, database, jetson_profile, notifier, logger_config
print('Toate modulele import OK')
" 2>/dev/null && ok "Import toate module" || ko "Import module eșuat"

# 12. Hardware profile
python3 -c "
from jetson_profile import detect_jetson_profile
p = detect_jetson_profile()
print(f'Hardware: {p[\"name\"]}')
print(f'FPS target: {p[\"target_total_fps\"]}')
print(f'imgsz: {p[\"imgsz\"]}')
print(f'device: {p[\"device\"]}')
print(f'Max camere: {p[\"max_cameras\"]}')
" 2>/dev/null && ok "Hardware profile detectat" || ko "Hardware profile eșuat"

echo ""
echo "========================================"
echo "  REZULTAT: $PASS OK / $FAIL EȘUATE"
echo "========================================"

if [ "$FAIL" -gt 0 ]; then
    echo "⚠️  Remedieri:"
    [ ! -f "yolo11n.engine" ] && echo "   bash convert_to_tensorrt.sh"
    python3 -c "import torch" 2>/dev/null || { echo "   bash remote_setup_jetson.sh"; }
    [ ! -f ".license" ] && echo "   python3 license.py --set COD"
    python3 -c "import cv2" 2>/dev/null || echo "   bash fix_opencv.sh"
else
    echo "🎉 Totul e OK. Poți porni: python3 app.py"
fi
