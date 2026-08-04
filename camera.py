import cv2
import time
import numpy as np
import threading
import os


class SyntheticCamera:
    """Cameră sintetică pentru testare (fără hardware)."""

    def __init__(self):
        self.width = 640
        self.height = 480
        self.frame_count = 0
        self.status = 'online'
        print("Cameră Sintetică inițializată (Mod Simulare)...")

    def read(self):
        frame = np.zeros((self.height, self.width, 3), dtype=np.uint8)
        self.frame_count += 1
        x = int((np.sin(self.frame_count * 0.05) + 1) * 0.5 * (self.width - 50)) + 25
        y = int((np.cos(self.frame_count * 0.05) + 1) * 0.5 * (self.height - 50)) + 25
        cv2.circle(frame, (x, y), 20, (0, 255, 255), -1)
        cv2.putText(frame, "MODO SIMULACION", (100, 50),
                    cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
        head_color = (255, 255, 255) if (self.frame_count // 30) % 2 == 0 else (50, 50, 50)
        cv2.circle(frame, (320, 200), 40, head_color, -1)
        body_color = (0, 165, 255) if (self.frame_count // 60) % 2 == 0 else (100, 100, 100)
        cv2.rectangle(frame, (280, 240), (360, 400), body_color, -1)
        return True, frame

    def release(self):
        pass


class VideoCamera:
    """
    Captură video din orice sursă: RTSP, USB, CSI, sau sintetică.
    Thread de citire continuă + reconectare automată pentru RTSP.
    """

    def __init__(self, source=0, name="Camera", reconnect_interval=5):
        """
        Args:
            source: URL RTSP, index USB (0,1,2...), sau pipeline GStreamer
            name: Nume descriptiv al camerei
            reconnect_interval: Secunde între încercările de reconectare (RTSP)
        """
        self.source = source
        self.name = name
        self.reconnect_interval = reconnect_interval
        self.video = None
        self.stopped = False
        self.frame = None
        self.grabbed = False
        self.using_synthetic = False
        self.is_rtsp = isinstance(source, str) and source.startswith('rtsp://')
        self.status = 'connecting'
        self.last_frame_time = 0
        self.fps = 0

        self._open_source()

        # Thread citire continuă
        threading.Thread(target=self._update_loop, args=(), daemon=True).start()

    def _build_csi_pipeline(self, sensor_id=0):
        """Pipeline GStreamer pentru camere CSI Jetson."""
        return (
            f"nvarguscamerasrc sensor-id={sensor_id} ! "
            f"video/x-raw(memory:NVMM), width=(int)1280, height=(int)720, "
            f"format=(string)NV12, framerate=(fraction)60/1 ! "
            f"nvvidconv flip-method=0 ! "
            f"video/x-raw, width=(int)640, height=(int)480, format=(string)BGRx ! "
            f"videoconvert ! "
            f"video/x-raw, format=(string)BGR ! appsink drop=true sync=false"
        )

    def _open_source(self):
        """Deschide sursa video cu fallback multiple."""
        if self.stopped:
            return

        # 1. RTSP direct
        if self.is_rtsp:
            self._open_rtsp()
            return

        # 2. Număr — încercăm CSI, apoi USB
        if isinstance(self.source, int):
            sources_to_try = []

            # Verificăm dacă CSI e disponibil
            if self.source == 0:
                sources_to_try.append(('csi', self._build_csi_pipeline(sensor_id=0)))
                sources_to_try.append(('usb', self.source))
            else:
                sources_to_try.append(('usb', self.source))

            for kind, src in sources_to_try:
                if kind == 'csi':
                    backend = cv2.CAP_GSTREAMER
                else:
                    if isinstance(src, int) and not os.path.exists(f"/dev/video{src}"):
                        continue
                    backend = cv2.CAP_V4L2

                try:
                    cap = cv2.VideoCapture(src, backend)
                    if cap.isOpened():
                        if kind == 'usb':
                            fourcc = cv2.VideoWriter_fourcc(*'MJPG')
                            cap.set(cv2.CAP_PROP_FOURCC, fourcc)
                            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                            cap.set(cv2.CAP_PROP_FPS, 60)

                        time.sleep(1)
                        ret, frame = cap.read()
                        if ret:
                            print(f"✅ [{self.name}] Cameră deschisă: {kind} {src}")
                            self.video = cap
                            self.status = 'online'
                            return
                        else:
                            cap.release()
                except Exception as e:
                    print(f"⚠️ [{self.name}] Eroare {kind} {src}: {e}")

        # 3. Pipeline GStreamer string
        if isinstance(self.source, str):
            try:
                cap = cv2.VideoCapture(self.source, cv2.CAP_GSTREAMER)
                if cap.isOpened():
                    time.sleep(1)
                    ret, frame = cap.read()
                    if ret:
                        print(f"✅ [{self.name}] Cameră deschisă: GStreamer")
                        self.video = cap
                        self.status = 'online'
                        return
                    else:
                        cap.release()
            except Exception as e:
                print(f"⚠️ [{self.name}] Eroare GStreamer: {e}")

        # 4. Fallback: cameră sintetică
        print(f"⚠️ [{self.name}] Nicio cameră găsită. Sintetică activată.")
        self.video = SyntheticCamera()
        self.using_synthetic = True
        self.status = 'synthetic'

    def _open_rtsp(self):
        """Deschide stream RTSP cu buffer optimizat pentru latență mică."""
        try:
            cap = cv2.VideoCapture(self.source, cv2.CAP_FFMPEG)
            if cap.isOpened():
                # Optimizări RTSP pentru latență mică
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                cap.set(cv2.CAP_PROP_FPS, 15)

                time.sleep(0.5)
                ret, frame = cap.read()
                if ret:
                    print(f"✅ [{self.name}] RTSP conectat: {self.source}")
                    self.video = cap
                    self.status = 'online'
                    return
                else:
                    cap.release()
            print(f"⚠️ [{self.name}] RTSP nu răspunde: {self.source}")
            self.status = 'error'
        except Exception as e:
            print(f"⚠️ [{self.name}] RTSP eroare: {e}")
            self.status = 'error'

    def _update_loop(self):
        """Buclă principală de citire cu reconectare RTSP automată."""
        retry_timer = 0

        while not self.stopped:
            if self.video is None:
                time.sleep(0.1)
                continue

            self.grabbed, self.frame = self.video.read()

            if self.grabbed and self.frame is not None:
                now = time.time()
                if self.last_frame_time > 0:
                    delta = now - self.last_frame_time
                    self.fps = 1.0 / delta if delta > 0 else 0
                self.last_frame_time = now
                retry_timer = 0

                if self.status != 'online' and not self.using_synthetic:
                    self.status = 'online'
                    print(f"✅ [{self.name}] Stream recuperat")
            else:
                # Frame pierdut
                if not self.using_synthetic:
                    self.status = 'reconnecting'

                    # Reconectare RTSP
                    if self.is_rtsp and retry_timer <= 0:
                        retry_timer = self.reconnect_interval
                        print(f"🔄 [{self.name}] Reconectare RTSP în {self.reconnect_interval}s...")
                        try:
                            self.video.release()
                        except Exception:
                            pass
                        self._open_rtsp()

                    if retry_timer > 0:
                        time.sleep(0.5)
                        retry_timer -= 0.5
                else:
                    time.sleep(0.016)

    def get_frame(self):
        """Returnează ultimul frame capturat."""
        return self.frame

    def get_jpeg_frame(self, quality=50):
        """Returnează ultimul frame encodat JPEG."""
        image = self.get_frame()
        if image is None:
            return None
        ret, jpeg = cv2.imencode('.jpg', image,
                                   [cv2.IMWRITE_JPEG_QUALITY, quality])
        return jpeg.tobytes() if ret else None

    def stop(self):
        """Oprește captura și eliberează resursele."""
        self.stopped = True
        if hasattr(self.video, 'release'):
            try:
                self.video.release()
            except Exception:
                pass
        self.status = 'offline'

    def __del__(self):
        self.stop()
