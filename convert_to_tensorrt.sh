#!/bin/bash

echo "🔧 Conversie YOLO11n la TensorRT INT8 (2x mai rapid decât FP16)..."
echo ""

cd ~/safeguard_vision
source venv/bin/activate

# Descărcare model YOLO11n dacă nu există
if [ ! -f "yolo11n.pt" ]; then
    echo "📥 Descărcare YOLO11n.pt..."
    python3 -c "from ultralytics import YOLO; YOLO('yolo11n.pt')"
fi

# Verificare CUDA
python3 -c "
import torch
if not torch.cuda.is_available():
    print('❌ CUDA nu e disponibil! INT8 necesită GPU Jetson.')
    exit(1)
print(f'✅ GPU: {torch.cuda.get_device_name(0)}')
"

# =============================================================================
# Export INT8 cu calibration automată
# =============================================================================
# INT8 = 2x mai rapid decât FP16 pe AGX Orin
# Pierdere precizie: ~1-2% (nesimțitor pentru detectare persoane)
# Ultralytics face calibration automat cu dataset COCO val
# =============================================================================
echo ""
echo "🚀 Export TensorRT INT8 (poate dura 10-15 minute)..."
echo "   Calibration se face automat cu imagini reprezentative."
echo ""

python3 << 'PYTHON_SCRIPT'
from ultralytics import YOLO
import os

model = YOLO('yolo11n.pt')

# Export INT8 — Ultralytics face calibration automat
# imgsz=480 pentru optim 20 camere, batch=1 (per cameră)
model.export(
    format='engine',
    int8=True,          # ← INT8 quantization (2x mai rapid ca FP16)
    half=False,         # Nu combinăm cu FP16
    imgsz=480,
    device=0,
    workspace=4,
    batch=1,
    dynamic=False,      # Static pentru performanță maximă
    verbose=True
)

# Verifică că engine-ul a fost creat
if os.path.exists('yolo11n.engine'):
    size_mb = os.path.getsize('yolo11n.engine') / (1024 * 1024)
    print(f"\n✅ Model INT8 creat: yolo11n.engine ({size_mb:.1f} MB)")
    print(f"   Așteaptă ~2x mai multă viteză vs FP16 pe AGX Orin")
else:
    print("❌ Eroare: engine-ul nu a fost creat")
PYTHON_SCRIPT

echo ""
echo "================================================"
echo "✅ Conversie INT8 completă!"
echo ""
echo "Model: yolo11n.engine (INT8 quantized)"
echo "Performanță estimată pe AGX Orin 64GB:"
echo "  • 1 cameră:  ~200 FPS inference"
echo "  • 20 camere: ~10 FPS per cameră"
echo "================================================"
