from camera import VideoCamera
import time
import cv2

print("Testing VideoCamera class initialization...")
cam = VideoCamera()

if cam.using_synthetic:
    print("FAILED: Falling back to Synthetic Camera")
else:
    print("SUCCESS: Physical camera initialized!")
    frame = cam.get_frame()
    if frame is not None:
        print(f"Captured frame shape: {frame.shape}")
        cv2.imwrite("test_frame_class.jpg", frame)
    else:
        print("Camera initialized but no frame returned yet.")

cam.stop()
