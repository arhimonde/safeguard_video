import cv2
import sys

# Función para probar un índice de cámara específico
# Intenta abrir la cámara, leer un frame y luego cierra la conexión.
def test_camera(index):
    print(f"Probando cámara índice {index}...")
    cap = cv2.VideoCapture(index)
    if not cap.isOpened():
        print(f"[-] Fallo al abrir la cámara {index}")
        return False
    
    ret, frame = cap.read()
    if not ret:
        print(f"[-] Fallo al leer frame de la cámara {index}")
        return False
        
    print(f"[+] Frame capturado exitosamente de la cámara {index}")
    print(f"    Resolución: {frame.shape[1]}x{frame.shape[0]}")
    cap.release()
    return True

if __name__ == "__main__":
    print("Versión de OpenCV:", cv2.__version__)
    
    # Intentar índices típicos (0 = defecto, 1 = externa, -1 = cualquiera)
    indices = [0, 1, -1]
    
    success_any = False
    for idx in indices:
        if test_camera(idx):
            success_any = True
            
    if not success_any:
        print("\nFATAL: No se encontró ninguna cámara funcionando en los índices estándar.")
        sys.exit(1)
    else:
        print("\nÉxito: Al menos una cámara está funcionando.")
