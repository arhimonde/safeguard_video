# Safeguard Vision Alpha

Sistema de monitorización de EPI (casco y chaleco) para entornos industriales, optimizado para NVIDIA Jetson. Detección multicanal en tiempo real con YOLO11n + TensorRT INT8; recibe alertas por Telegram y Email cuando se detectan incumplimientos de seguridad.

## Funcionalidades principales

- **Multicámara** — hasta 25 cámaras RTSP/USB/CSI con límite adaptativo según el hardware
- **Auto‑detección Jetson** — FPS, resolución y dispositivo se adaptan automáticamente (AGX Orin → Jetson Nano)
- **YOLO11n + TensorRT INT8** — ~200 FPS en AGX Orin 64GB, ~15 FPS en Jetson Nano
- **Detección EPI por HSV** — casco + chaleco mediante análisis del espacio de color (sin coste de GPU)
- **Seguimiento de personas** — IoU + búfer de 5 frames (decisión estable, sin flicker)
- **Soft tracking** — la persona marcada se ignora hasta que salga del cuadro
- **Sistema anti‑recidiva** — escalado: 1.ª falta = warning, 2.ª = danger, 3.ª = critical + notificación
- **Notificaciones externas** — Telegram + Email en severidad critical
- **GDPR** — endpoints para eliminación de datos, borrado automático de capturas > 30 días
- **Seguridad** — código de acceso por licencia, cifrado RTSP, rate limiting, CORS restrictivo
- **Protección del código** — ofuscación con PyArmor (bytecode cifrado AES)
- **Acceso remoto** — túnel Loophole para acceso externo

## Instalación rápida

### En PC/Mac (desarrollo)
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python3 license.py --set COD_ACCES
python3 app.py
```

### En NVIDIA Jetson (producción)
```bash
# 1. Desplegar código desde el PC
bash deploy_to_jetson.sh

# 2. En Jetson — instalación completa (CUDA, PyTorch GPU, Ultralytics)
bash remote_setup_jetson.sh

# 3. Conversión a TensorRT INT8 (2x más rápido)
bash convert_to_tensorrt.sh

# 4. Establecer código de acceso y arrancar
python3 license.py --set COD_ACCES
python3 app.py
```

Consulta [LICENSE_GUIDE.md](LICENSE_GUIDE.md) para detalles sobre licencia y ofuscación.

## Acceso

- **Local**: `http://localhost:5000`
- **Remoto**: `python3 loophole_tunnel.py` → URL `.loophole.site`
- **Login**: el primer arranque crea `admin` / `admin123` (se cambia automáticamente en el primer login)

## Configuración

### cameras.json (ignorados por git — contiene credenciales RTSP)
```json
[
  {"id": 1, "name": "Intrare", "url": "rtsp://admin:pass@192.168.1.101:554/stream1", "enabled": true},
  {"id": 2, "name": "Depozit A", "url": "rtsp://admin:pass@192.168.1.102:554/stream1", "enabled": true}
]
```
Las contraseñas RTSP se cifran automáticamente (XOR + base64) al guardar. Permisos `chmod 600`.

### config.json (ignorados por git — notificaciones + CORS)
Consulta `config.example.json` como plantilla. Contiene:
- Token del bot de Telegram + chat ID
- Configuración SMTP (email)
- Orígenes permitidos en CORS

## Arquitectura

```
┌─────────────────────────────────────────────┐
│  Browser (WebSocket + MJPEG)                │
└──────────────────┬──────────────────────────┘
                   │ Flask + SocketIO
┌──────────────────┴──────────────────────────┐
│  app.py                                     │
│  ├── CameraManager (cameras.json)           │
│  │   └── VideoCamera × N (RTSP threads)     │
│  │       └── Límite max_cameras (hardware)  │
│  ├── ObjectDetector (YOLO11n + TensorRT)    │
│  │   ├── Motion pre-filter (skip GPU)       │
│  │   ├── PersonTracker × N (IoU + history)  │
│  │   ├── HSV PPE (casco + chaleco, CPU)     │
│  │   └── Escalado anti-recidiva             │
│  ├── Notifier (Telegram + Email)            │
│  └── Database (SQLite: incidents, users,    │
│      violations_log)                         │
└─────────────────────────────────────────────┘
```

## Archivos principales

| Archivo | Rol |
|---|---|
| `app.py` | Servidor Flask + WebSocket + rutas API |
| `detector.py` | YOLO11n + HSV PPE + tracking + escalado |
| `camera.py` | VideoCamera (RTSP/USB/CSI + reconexión automática) |
| `camera_manager.py` | Gestor multicámara + límite por hardware |
| `jetson_profile.py` | Auto-detección de hardware + perfiles |
| `database.py` | SQLite: incidents, users, violations_log |
| `notifier.py` | Alertas Telegram + Email |
| `logger_config.py` | Logging estructurado con rotación |
| `license.py` | Código de acceso + verificación |
| `obfuscate.sh` | Ofuscación con PyArmor (bytecode cifrado) |

## Scripts para Jetson

| Script | Rol |
|---|---|
| `deploy_to_jetson.sh` | rsync código → Jetson |
| `remote_setup_jetson.sh` | Setup completo (CUDA, PyTorch, Ultralytics) |
| `convert_to_tensorrt.sh` | Exportar YOLO11n → TensorRT INT8 |
| `jetson_cmd.sh` | Comandos remotos (setup/start/remote/stop/diag/perf) |
| `jetson_perf.sh` | Benchmark YOLO11n |
| `fix_opencv.sh` | OpenCV GStreamer en Jetson |
| `jetson_test_checklist.sh` | 12 comprobaciones automáticas en Jetson |

## Rendimiento estimado

| Hardware | FPS total | imgsz | Max cámaras | INT8 |
|---|---:|---:|---:|---:|
| AGX Orin 64GB | ~200 | 480 | 20 | ✅ |
| AGX Orin 32GB | ~170 | 480 | 17 | ✅ |
| Orin NX 16GB | ~110 | 480 | 11 | ✅ |
| Orin Nano 8GB | ~50 | 416 | 5 | ✅ |
| AGX Xavier | ~80 | 416 | 8 | ❌ |
| Jetson Nano | ~15 | 320 | 1 | ❌ |
| CPU (sin GPU) | ~10 | 320 | 1 | ❌ |

## Licencia

Consulta [LICENSE](LICENSE) para detalles.
Protección del código fuente: [LICENSE_GUIDE.md](LICENSE_GUIDE.md).
