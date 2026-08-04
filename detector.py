from ultralytics import YOLO
import cv2
import numpy as np
import time
import os
import threading
from datetime import datetime
from collections import deque
from database import log_incident


# =============================================================================
# Person Tracker — ID-uri stabile + soft tracking per cameră
# =============================================================================

class PersonTracker:
    """
    Urmărește persoane între frame-uri prin overlap IoU.
    Buffer istoric PPE → decizie stabilă (zero flickering).
    Soft tracking: persoana alertată e ignorată până iese din cadru.
    """

    ALERTED = 'alerted'
    ACTIVE = 'active'

    def __init__(self, iou_threshold=0.3, history_length=5, max_missed=5):
        self.iou_threshold = iou_threshold
        self.history_length = history_length
        self.max_missed = max_missed
        self.tracks = {}
        self.next_id = 0

    def _iou(self, a, b):
        x1 = max(a[0], b[0]); y1 = max(a[1], b[1])
        x2 = min(a[2], b[2]); y2 = min(a[3], b[3])
        inter = max(0, x2 - x1) * max(0, y2 - y1)
        area_a = (a[2] - a[0]) * (a[3] - a[1])
        area_b = (b[2] - b[0]) * (b[3] - b[1])
        union = area_a + area_b - inter
        return inter / union if union > 0 else 0.0

    def _find_best_match(self, bbox):
        best_id = None; best_iou = self.iou_threshold
        for tid, track in self.tracks.items():
            if track['missed'] > self.max_missed:
                continue
            iou = self._iou(bbox, track['bbox'])
            if iou > best_iou:
                best_iou = iou; best_id = tid
        return best_id

    def mark_alerted(self, tid):
        if tid in self.tracks:
            self.tracks[tid]['status'] = self.ALERTED

    def update(self, detections):
        used_ids = set(); results = []

        for bbox, has_helmet, has_vest in detections:
            tid = self._find_best_match(bbox)
            if tid is not None:
                used_ids.add(tid)
            else:
                tid = self.next_id; self.next_id += 1

            if tid in self.tracks:
                status = self.tracks[tid].get('status', self.ACTIVE)
            else:
                status = self.ACTIVE

            self.tracks[tid] = {
                'bbox': bbox, 'missed': 0,
                'history': self.tracks.get(tid, {}).get(
                    'history', deque(maxlen=self.history_length)),
                'status': status,
            }
            self.tracks[tid]['history'].append((has_helmet, has_vest))

            history = list(self.tracks[tid]['history'])
            stable_helmet = sum(1 for h, _ in history if h) > len(history) // 2
            stable_vest = sum(1 for _, v in history if v) > len(history) // 2

            results.append((bbox, tid, stable_helmet, stable_vest, status))

        expired = []
        for tid in self.tracks:
            if tid not in used_ids:
                self.tracks[tid]['missed'] += 1
                if self.tracks[tid]['missed'] > 2:
                    self.tracks[tid]['status'] = self.ACTIVE
                if self.tracks[tid]['missed'] > self.max_missed:
                    expired.append(tid)
        for tid in expired:
            del self.tracks[tid]

        return results

    def reset(self):
        self.tracks = {}; self.next_id = 0


# =============================================================================
# Object Detector — YOLO11n + HSV PPE (optimizat pentru 20 camere)
# =============================================================================

class ObjectDetector:
    def __init__(self, model_path='yolo11n.pt', imgsz=480, half=True):
        """
        Detector optimizat pentru MULTI-CAMERĂ (până la 25):
        - YOLO11n pentru detectare persoane (model partajat)
        - HSV cu cluster analysis pentru PPE (CPU, zero cost GPU)
        - PersonTracker per cameră
        - FPS adaptiv: target_total_fps / num_cameras
        """
        print(f"Se încarcă modelul: {model_path}...")
        self.is_tensorrt = model_path.endswith('.engine')
        self.imgsz = imgsz
        self.half = half

        self.model = YOLO(model_path)
        print(f"Model încărcat. TensorRT: {self.is_tensorrt}, "
              f"imgsz: {imgsz}, FP16: {half}")

        self.classes_of_interest = [0]
        self.colors = {
            'safe': (0, 255, 0), 'danger': (0, 0, 255),
            'warning': (0, 255, 255)
        }

        # Per-camera state
        self.trackers = {}
        self.alert_times = {}
        self.alert_cooldown = 5
        self._trackers_lock = threading.Lock()

        # FPS adaptiv — optimizat pentru 20 camere pe AGX Orin
        # YOLO11n + TensorRT INT8 = ~200 FPS pe AGX Orin 64GB
        # 200 FPS / 20 camere = 10 FPS per cameră
        self.target_total_fps = 200
        self.last_frame_time = time.time()

        # Nuclee morfologice (pre-calculate)
        self._morph_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        self._morph_kernel_small = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))

        # Cache overlay zonă pericol
        self._danger_zone_cache = None
        self._danger_zone_size = None
        self.min_box_size = 30

    # -----------------------------------------------------------------
    # Per-camera tracker management
    # -----------------------------------------------------------------

    def get_tracker(self, cam_id):
        with self._trackers_lock:
            if cam_id not in self.trackers:
                self.trackers[cam_id] = PersonTracker()
            return self.trackers[cam_id]

    def remove_tracker(self, cam_id):
        with self._trackers_lock:
            self.trackers.pop(cam_id, None)
            self.alert_times.pop(cam_id, None)

    def get_fps_per_camera(self, num_cameras):
        """Calculează FPS adaptiv per cameră."""
        if num_cameras <= 0:
            return 20
        # 1 cameră = cap 20 FPS, multi-cameră = distribuit
        fps = min(self.target_total_fps // num_cameras, 20)
        return max(fps, 3)  # minim 3 FPS per cameră

    # -----------------------------------------------------------------
    # PPE: HSV cu cluster analysis + scoring (CPU only)
    # -----------------------------------------------------------------

    def _preprocess_roi(self, roi):
        """Normalizare iluminiere prin histogram equalization pe canalul V."""
        if roi.size == 0:
            return roi
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        hsv[:, :, 2] = cv2.equalizeHist(hsv[:, :, 2])
        return hsv

    def _clip_bbox(self, x1, y1, x2, y2, h, w):
        return max(0, x1), max(0, y1), min(w, x2), min(h, y2)

    def _find_largest_cluster(self, mask, min_area=50):
        """
        Găsește cel mai mare blob conex (componentă conexă).
        Elimină pixelii izolați de la fundaluri colorate.
        """
        if mask.size == 0 or cv2.countNonZero(mask) == 0:
            return mask
        num_labels, labels, stats_cv, _ = cv2.connectedComponentsWithStats(
            mask, connectivity=8)
        if num_labels <= 1:
            return mask
        best_label = 1; best_area = 0
        for label_id in range(1, num_labels):
            area = stats_cv[label_id, cv2.CC_STAT_AREA]
            if area > best_area:
                best_area = area; best_label = label_id
        if best_area >= min_area:
            cluster = np.zeros_like(mask)
            cluster[labels == best_label] = 255
            return cluster
        return mask

    def _analyze_color_region(self, hsv_roi, color_ranges):
        """
        Scoring de încredere [0.0, 1.0] bazat pe:
        - densitate (cât de multă culoare)
        - compactitate (cât de grupată)
        - acoperire (raport față de prag)
        """
        if hsv_roi.size == 0:
            return 0.0
        total_area = hsv_roi.shape[0] * hsv_roi.shape[1]
        if total_area == 0:
            return 0.0

        combined = np.zeros(hsv_roi.shape[:2], dtype=np.uint8)
        for lower, upper in color_ranges:
            combined = cv2.bitwise_or(combined, cv2.inRange(
                hsv_roi, np.array(lower), np.array(upper)))
        if cv2.countNonZero(combined) == 0:
            return 0.0

        # Cluster analysis: păstrăm doar cel mai mare blob
        combined = self._find_largest_cluster(combined, min_area=30)

        # Filtrare morfologică
        cleaned = cv2.morphologyEx(combined, cv2.MORPH_OPEN,
                                   self._morph_kernel_small, iterations=2)
        cleaned = cv2.morphologyEx(cleaned, cv2.MORPH_CLOSE,
                                   self._morph_kernel, iterations=1)

        pixel_count = cv2.countNonZero(cleaned)
        if pixel_count == 0:
            return 0.0

        density = pixel_count / total_area
        raw_count = cv2.countNonZero(combined)
        compactness = pixel_count / raw_count if raw_count > 0 else 0.0
        coverage_bonus = min(density / 0.15, 1.0)
        return min(density * 0.35 + compactness * 0.35 + coverage_bonus * 0.30, 1.0)

    def _check_ppe_hsv(self, frame, x1, y1, x2, y2):
        """Verifică cască + vestă prin HSV cu cluster analysis."""
        h_frame, w_frame, _ = frame.shape
        x1, y1, x2, y2 = self._clip_bbox(x1, y1, x2, y2, h_frame, w_frame)
        if (x2 - x1) < self.min_box_size or (y2 - y1) < self.min_box_size:
            return False, False

        person_roi = frame[y1:y2, x1:x2]
        if person_roi.size == 0:
            return False, False
        h, w, _ = person_roi.shape

        # ROI Cască: top 25%, centrat 60% lățime
        w_off = int(w * 0.2)
        helmet_roi = person_roi[0:int(h * 0.25), w_off:w - w_off]

        # ROI Vestă: torso 20%-60%
        vest_roi = person_roi[int(h * 0.2):int(h * 0.6), :]

        if helmet_roi.size == 0 or vest_roi.size == 0:
            return False, False

        hsv_helmet = self._preprocess_roi(helmet_roi)
        hsv_vest = self._preprocess_roi(vest_roi)

        # Culori cascu (alb, galben, roșu, albastru, portocaliu)
        helmet_colors = [
            ([0, 0, 200], [180, 30, 255]),         # Alb
            ([20, 50, 70], [50, 255, 255]),         # Galben
            ([0, 100, 100], [10, 255, 255]),        # Roșu 1
            ([160, 100, 100], [180, 255, 255]),     # Roșu 2
            ([90, 80, 80], [130, 255, 255]),        # Albastru
            ([10, 100, 100], [25, 255, 255]),       # Portocaliu
        ]

        # Culori vestă (portocaliu, galben, roșu)
        vest_colors = [
            ([10, 100, 100], [25, 255, 255]),       # Portocaliu
            ([20, 20, 50], [50, 255, 255]),         # Galben
            ([0, 100, 100], [10, 255, 255]),        # Roșu 1
            ([160, 100, 100], [180, 255, 255]),     # Roșu 2
        ]

        helmet_score = self._analyze_color_region(hsv_helmet, helmet_colors)
        vest_score = self._analyze_color_region(hsv_vest, vest_colors)

        return helmet_score > 0.18, vest_score > 0.18

    def check_ppe(self, frame, x1, y1, x2, y2):
        """PPE = doar HSV (optimizat pentru multi-cameră, zero cost GPU)."""
        return self._check_ppe_hsv(frame, x1, y1, x2, y2)

    # -----------------------------------------------------------------
    # Overlay cache
    # -----------------------------------------------------------------

    def _get_danger_zone_overlay(self, w_img, h_img):
        if self._danger_zone_cache is not None and self._danger_zone_size == (w_img, h_img):
            return self._danger_zone_cache
        overlay = np.zeros((h_img, w_img, 3), dtype=np.uint8)
        cv2.rectangle(overlay, (int(w_img * 0.75), 0), (w_img, h_img), (0, 0, 255), -1)
        self._danger_zone_cache = overlay
        self._danger_zone_size = (w_img, h_img)
        return overlay

    # -----------------------------------------------------------------
    # Detectia principală (per cameră)
    # -----------------------------------------------------------------

    def detect(self, frame, cam_id):
        if frame is None:
            return None, {}

        h_img, w_img, _ = frame.shape
        danger_zone_x = int(w_img * 0.75)

        # YOLO inferență — doar persoane
        results = self.model(frame, verbose=False,
                             imgsz=self.imgsz, half=self.half, device=0)

        raw_detections = []
        for r in results:
            for box in r.boxes:
                if int(box.cls[0]) != 0:
                    continue
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                if (x2 - x1) < self.min_box_size or (y2 - y1) < self.min_box_size:
                    continue
                # PPE pe HSV (CPU, zero cost GPU)
                has_helmet, has_vest = self.check_ppe(frame, x1, y1, x2, y2)
                raw_detections.append(((x1, y1, x2, y2), has_helmet, has_vest))

        # Tracking per cameră
        tracker = self.get_tracker(cam_id)
        tracked = tracker.update(raw_detections)

        annotated_frame = frame.copy()
        stats = {'total_persons': len(tracked), 'violations': 0, 'alerts': [],
                 'camera_id': cam_id}
        current_violations = 0
        violation_types = []
        alerted_tids = []

        for bbox, tid, s_helmet, s_vest, status in tracked:
            x1, y1, x2, y2 = bbox
            x_mid = (x1 + x2) // 2
            in_danger = x_mid > danger_zone_x
            has_all = s_helmet and s_vest
            is_alerted = (status == PersonTracker.ALERTED)

            if not has_all:
                is_safe = False; is_warning = False
            elif in_danger:
                is_safe = False; is_warning = True
            else:
                is_safe = True; is_warning = False

            label_parts = []
            if not s_helmet: label_parts.append("SIN CASCO")
            if not s_vest: label_parts.append("SIN CHALECO")
            if in_danger: label_parts.append("ZONA PELIGROSA")

            if is_safe:
                color = self.colors['safe']; label = "Seguro"
            elif is_warning:
                color = self.colors['warning']
                reason = ", ".join(label_parts)
                label = f"AVISO: {reason}"
                if not is_alerted:
                    stats['violations'] += 1; current_violations += 1
                    stats['alerts'].append(f"Aviso: {reason}")
                    violation_types.append(reason); alerted_tids.append(tid)
                else:
                    label += " [T]"
            else:
                color = self.colors['danger']
                reason = ", ".join(label_parts)
                label = f"PELIGRO: {reason}"
                if not is_alerted:
                    stats['violations'] += 1; current_violations += 1
                    stats['alerts'].append(f"Peligro: {reason}")
                    violation_types.append(reason); alerted_tids.append(tid)
                else:
                    label += " [T]"

            cv2.rectangle(annotated_frame, (x1, y1), (x2, y2), color, 2)
            cv2.putText(annotated_frame, label, (x1, y1 - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)

        # Overlay zonă pericol (cache-uit)
        overlay = self._get_danger_zone_overlay(w_img, h_img)
        cv2.addWeighted(overlay, 0.2, annotated_frame, 0.8, 0, annotated_frame)
        cv2.line(annotated_frame, (danger_zone_x, 0), (danger_zone_x, h_img), (0, 0, 255), 2)
        cv2.putText(annotated_frame, "ZONA DE PELIGRO", (danger_zone_x + 10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

        # Timestamp + FPS
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cv2.putText(annotated_frame, timestamp, (10, h_img - 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        now = time.time()
        elapsed = now - self.last_frame_time
        fps = 1.0 / elapsed if elapsed > 0 else 0
        self.last_frame_time = now
        cv2.putText(annotated_frame, f"FPS: {int(fps)}", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

        # Alertă cu soft tracking per cameră
        if current_violations > 0:
            last_alert = self.alert_times.get(cam_id, 0)
            if now - last_alert > self.alert_cooldown:
                v_type = violation_types[0] if violation_types else "Violación"
                self.save_alert(annotated_frame, v_type, cam_id)
                self.alert_times[cam_id] = now
                for tid in alerted_tids:
                    tracker.mark_alerted(tid)

        return annotated_frame, stats

    # -----------------------------------------------------------------
    # Salvare alertă
    # -----------------------------------------------------------------

    def save_alert(self, frame, incident_type, cam_id=None):
        try:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            cam_suffix = f"_cam{cam_id}" if cam_id else ""
            filename = f"capture{cam_suffix}_{ts}.jpg"
            base_dir = os.path.dirname(os.path.abspath(__file__))
            save_dir = os.path.join(base_dir, 'static/captures')
            filepath = os.path.join(save_dir, filename)
            web_path = f"captures/{filename}"
            if not os.path.exists(save_dir):
                os.makedirs(save_dir, exist_ok=True)
            if cv2.imwrite(filepath, frame):
                print(f"✅ [Cam {cam_id}] Alertă salvată: {filename}")
                log_incident(incident_type, web_path,
                             f"Violación detectada: {incident_type}",
                             camera_id=cam_id)
        except Exception as e:
            print(f"❌ Eroare save_alert: {e}")
