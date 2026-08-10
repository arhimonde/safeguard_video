# Safeguard Vision

Sistem de monitorizare PPE (cască + vestă) pentru medii industriale, optimizat pentru NVIDIA Jetson. Detectare multi-cameră în timp real cu YOLO11n + TensorRT INT8, analiză HSV pentru PPE, tracking persoane, și sistem anti-recidivă.

## Funcții principale

- **Multi-cameră** — până la 25 camere RTSP/USB/CSI cu limită adaptivă după hardware
- **Auto-detectare Jetson** — FPS, rezoluție, device se adaptează automat (AGX Orin → Jetson Nano)
- **YOLO11n + TensorRT INT8** — 200 FPS pe AGX Orin 64GB, ~15 FPS pe Jetson Nano
- **HSV PPE detection** — cască + vestă via color-space analysis (zero cost GPU)
- **Person tracking** — IoU + buffer 5 frame-uri (decizie stabilă, zero flickering)
- **Soft tracking** — persoana alertată e ignorată până iese din cadru
- **Sistem anti-recidivă** — escaladare: 1a abatere=warning, 2a=danger, 3a=critical+notificare
- **Notificări externe** — Telegram + Email la severity critical
- **GDPR** — endpoints pentru ștergere date, auto-delete capturi > 30 zile
- **Securitate** — licență cod acces, criptare RTSP, rate limiting, CORS restrictiv
- **Protecție cod** — ofuscare PyArmor (bytecode criptat AES)
- **Remote access** — Loophole tunnel pentru acces din exterior

## Instalare rapidă

### Pe PC/Mac (dezvoltare)
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python3 license.py --set COD_ACCES
python3 app.py
```

### Pe NVIDIA Jetson (producție)
```bash
# 1. Deploy cod de pe PC
bash deploy_to_jetson.sh

# 2. Pe Jetson — setup complet (CUDA, PyTorch GPU, Ultralytics)
bash remote_setup_jetson.sh

# 3. Conversie TensorRT INT8 (2x mai rapid)
bash convert_to_tensorrt.sh

# 4. Set cod acces + pornire
python3 license.py --set COD_ACCES
python3 app.py
```

Vezi [LICENSE_GUIDE.md](LICENSE_GUIDE.md) pentru detalii licență + ofuscare.

## Acces

- **Local**: `http://localhost:5000`
- **Remote**: `python3 loophole_tunnel.py` → URL `.loophole.site`
- **Login**: prima pornire creează `admin` / `admin123` (se schimbă automat la prima logare)

## Configurare

### cameras.json (gitignored — conține credențiale RTSP)
```json
[
  {"id": 1, "name": "Intrare", "url": "rtsp://admin:pass@192.168.1.101:554/stream1", "enabled": true},
  {"id": 2, "name": "Depozit A", "url": "rtsp://admin:pass@192.168.1.102:554/stream1", "enabled": true}
]
```
Parolele RTSP sunt criptate automat (XOR + base64) la salvare. Permisiuni `chmod 600`.

### config.json (gitignored — notificări + CORS)
Vezi `config.example.json` pentru template. Conține:
- Telegram Bot token + chat ID
- SMTP (email) configurație
- CORS allowed origins

## Arhitectură

```
┌─────────────────────────────────────────────┐
│  Browser (WebSocket + MJPEG)                │
└──────────────────┬──────────────────────────┘
                   │ Flask + SocketIO
┌──────────────────┴──────────────────────────┐
│  app.py                                     │
│  ├── CameraManager (cameras.json)           │
│  │   └── VideoCamera × N (RTSP threads)     │
│  │       └── Limită max_cameras (hardware)  │
│  ├── ObjectDetector (YOLO11n + TensorRT)    │
│  │   ├── Motion pre-filter (skip GPU)       │
│  │   ├── PersonTracker × N (IoU + history)   │
│  │   ├── HSV PPE (cască + vestă, CPU)       │
│  │   └── Escaladare anti-recidivă           │
│  ├── Notifier (Telegram + Email)            │
│  └── Database (SQLite: incidents, users,    │
│      violations_log)                         │
└─────────────────────────────────────────────┘
```

## Fișiere principale

| Fișier | Rol |
|---|---|
| `app.py` | Server Flask + WebSocket + rute API |
| `detector.py` | YOLO11n + HSV PPE + tracking + escaladare |
| `camera.py` | VideoCamera (RTSP/USB/CSI + auto-reconnect) |
| `camera_manager.py` | Manager multi-cameră + limită hardware |
| `jetson_profile.py` | Auto-detectare hardware + profiluri |
| `database.py` | SQLite: incidents, users, violations_log |
| `notifier.py` | Telegram + Email alerte |
| `logger_config.py` | Logging structurat cu rotare |
| `license.py` | Cod de acces + verificare |
| `obfuscate.sh` | Ofuscare PyArmor (bytecode criptat) |

## Scripturi Jetson

| Script | Rol |
|---|---|
| `deploy_to_jetson.sh` | rsync cod → Jetson |
| `remote_setup_jetson.sh` | Setup complet (CUDA, PyTorch, Ultralytics) |
| `convert_to_tensorrt.sh` | Export YOLO11n → TensorRT INT8 |
| `jetson_cmd.sh` | Comenzi remote (setup/start/remote/stop/diag/perf) |
| `jetson_diag.sh` | Diagnostic hardware |
| `jetson_perf.sh` | Benchmark YOLO11n |
| `jetson_max_perf.sh` | MAXN power mode + jetson_clocks |
| `fix_opencv.sh` | OpenCV GStreamer pe Jetson |
| `install_cusparselt.sh` | cuSPARSELt pentru PyTorch GPU |

## Performanță estimată

| Hardware | FPS total | imgsz | Max camere | INT8 |
|---|---|---|---|---|
| AGX Orin 64GB | ~200 | 480 | 20 | ✅ |
| AGX Orin 32GB | ~170 | 480 | 17 | ✅ |
| Orin NX 16GB | ~110 | 480 | 11 | ✅ |
| Orin Nano 8GB | ~50 | 416 | 5 | ✅ |
| AGX Xavier | ~80 | 416 | 8 | ❌ |
| Jetson Nano | ~15 | 320 | 1 | ❌ |
| CPU (fără GPU) | ~10 | 320 | 1 | ❌ |


## Licență

Vezi [LICENSE](LICENSE) pentru detalii.
Protecția codului sursă: [LICENSE_GUIDE.md](LICENSE_GUIDE.md).
