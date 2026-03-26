import cv2
import time

def test_camera(index):
    print(f"Testing camera index {index} with V4L2 backend...")
    cap = cv2.VideoCapture(index, cv2.CAP_V4L2)
    
    if not cap.isOpened():
        print(f"Failed to open camera index {index}")
        return
    
    # Try to set MJPG
    fourcc = cv2.VideoWriter_fourcc(*'MJPG')
    cap.set(cv2.CAP_PROP_FOURCC, fourcc)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    cap.set(cv2.CAP_PROP_FPS, 30)
    
    print(f"Camera {index} opened successfully.")
    print(f"Backend: {cap.getBackendName()}")
    print(f"Width: {cap.get(cv2.CAP_PROP_FRAME_WIDTH)}")
    print(f"Height: {cap.get(cv2.CAP_PROP_FRAME_HEIGHT)}")
    print(f"FPS: {cap.get(cv2.CAP_PROP_FPS)}")
    print(f"FourCC: {cap.get(cv2.CAP_PROP_FOURCC)}")
    
    ret, frame = cap.read()
    if ret:
        print("Successfully captured a frame!")
        cv2.imwrite(f"test_frame_{index}.jpg", frame)
    else:
        print("Failed to capture frame")
    
    cap.release()

if __name__ == "__main__":
    test_camera(0)
    test_camera(1)
