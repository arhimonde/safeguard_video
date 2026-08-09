"""
Detectare hardware + profil de performanță.

La pornire detectează automat pe ce Jetson (sau CPU) rulează aplicația
și returnează parametrii optimi: target_total_fps, imgsz, device, INT8.

Astfel codul se adaptează singur — fără modificări manuale la schimbarea
hardware-ului.
"""
import os

# Tabel profiluri (bazat pe TOPS oficiali NVIDIA + benchmark-uri YOLO11n)
# Cheie: string care apare în numele modelului Jetson
# Valoare: dict cu parametrii optimi
_PROFILES = [
    # (pattern, name, target_total_fps, imgsz, supports_int8, max_cameras)
    {'pattern': 'orin agx',         'name': 'AGX Orin 64GB',  'fps': 200, 'imgsz': 480, 'int8': True,  'max_cam': 20},
    {'pattern': 'agx orin',         'name': 'AGX Orin 64GB',  'fps': 200, 'imgsz': 480, 'int8': True,  'max_cam': 20},
    {'pattern': 'orin nx',          'name': 'Orin NX 16GB',   'fps': 110, 'imgsz': 480, 'int8': True,  'max_cam': 11},
    {'pattern': 'orin nano 8gb',    'name': 'Orin Nano 8GB',  'fps': 50,  'imgsz': 416, 'int8': True,  'max_cam': 5},
    {'pattern': 'orin nano',        'name': 'Orin Nano',      'fps': 40,  'imgsz': 416, 'int8': True,  'max_cam': 4},
    {'pattern': 'xavier agx',       'name': 'AGX Xavier',     'fps': 80,  'imgsz': 416, 'int8': False, 'max_cam': 8},
    {'pattern': 'agx xavier',       'name': 'AGX Xavier',     'fps': 80,  'imgsz': 416, 'int8': False, 'max_cam': 8},
    {'pattern': 'xavier nx',        'name': 'Xavier NX',      'fps': 50,  'imgsz': 416, 'int8': False, 'max_cam': 5},
    {'pattern': 'nanodeveloper',    'name': 'Jetson Nano',    'fps': 15,  'imgsz': 320, 'int8': False, 'max_cam': 1},
    {'pattern': 'jetson nano',      'name': 'Jetson Nano',    'fps': 15,  'imgsz': 320, 'int8': False, 'max_cam': 1},
]

# Profil fallback (PC fără GPU, MAC, server CPU-only)
_CPU_PROFILE = {
    'name': 'CPU (fără GPU)',
    'target_total_fps': 10,
    'imgsz': 320,
    'supports_int8': False,
    'max_cameras': 1,
    'device': 'cpu',
}


def _read_jetson_model():
    """Citește /proc/device-tree/model. Returnează string sau None."""
    try:
        with open('/proc/device-tree/model', 'r') as f:
            return f.read().strip().lower()
    except (FileNotFoundError, PermissionError, OSError):
        return None


def _get_gpu_name():
    """Returnează numele GPU-ului CUDA sau None."""
    try:
        import torch
        if torch.cuda.is_available():
            return torch.cuda.get_device_name(0).lower()
    except Exception:
        pass
    return None


def detect_jetson_profile():
    """
    Detectează hardware-ul la pornire și returnează un profil de performanță.

    Returnează dict cu:
        name              -- numele afișabil (ex: 'AGX Orin 64GB')
        target_total_fps  -- FPS total estimat pentru YOLO11n + TensorRT
        imgsz             -- rezoluție inferență optimă (320/416/480)
        supports_int8     -- dacă suportă TensorRT INT8
        max_cameras       -- număr maxim recomandat de camere
        device            -- 'cuda:0' sau 'cpu'
        is_jetson         -- bool
    """
    model_str = _read_jetson_model()

    # 1. Detectare Jetson via /proc/device-tree/model
    if model_str:
        for prof in _PROFILES:
            if prof['pattern'] in model_str:
                return {
                    'name': prof['name'],
                    'target_total_fps': prof['fps'],
                    'imgsz': prof['imgsz'],
                    'supports_int8': prof['int8'],
                    'max_cameras': prof['max_cam'],
                    'device': 'cuda:0',
                    'is_jetson': True,
                }
        # E Jetson dar nu-l recunoaștem — profil conservator
        return {
            'name': f'Jetson necunoscut ({model_str[:40]})',
            'target_total_fps': 30,
            'imgsz': 416,
            'supports_int8': False,
            'max_cameras': 3,
            'device': 'cuda:0',
            'is_jetson': True,
        }

    # 2. Fallback: detectare GPU CUDA (PC cu GPU NVIDIA, non-Jetson)
    gpu_name = _get_gpu_name()
    if gpu_name:
        # GPU desktop/server — performant, dar nu Jetson
        return {
            'name': f'GPU: {gpu_name[:50]}',
            'target_total_fps': 150,
            'imgsz': 480,
            'supports_int8': True,
            'max_cameras': 15,
            'device': 'cuda:0',
            'is_jetson': False,
        }

    # 3. Fallback final: CPU-only
    return dict(_CPU_PROFILE, is_jetson=False)
