#!/usr/bin/env python3
from camera import VideoCamera
import time

print("Probando el streaming de VideoCamera...")
camera = VideoCamera(0)

print("Capturando 10 cuadros...")
for i in range(10):
    frame = camera.get_frame()
    if frame is not None:
        print(f"Cuadro {i}: forma={frame.shape}, mín={frame.min()}, máx={frame.max()}")
    else:
        print(f"Cuadro {i}: Nulo (None)")
    time.sleep(0.1)

print("✅ ¡Prueba de cámara completada!")
