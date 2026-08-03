from ultralytics import YOLO
import cv2
import numpy as np
import time
import os
from datetime import datetime
from collections import deque
from database import log_incident


# =============================================================================
# Person Tracker — ID-uri stabile + soft tracking (ignoră după foto)
# =============================================================================

class PersonTracker:
    """
    Urmărește persoane între frame-uri folosind overlap IoU.
    Buffer circular cu istoric PPE pentru fiecare ID → decizie stabilă.

    Soft tracking: după ce o persoană primește o alertă (foto salvată),
    este marcată ca 'alerted' și ignorată pentru violații ulterioare
    până când dispare din cadru (iese din fundal) și revine.
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
        x1 = max(a[0], b[0])
        y1 = max(a[1], b[1])
        x2 = min(a[2], b[2])
        y2 = min(a[3], b[3])
        inter = max(0, x2 - x1) * max(0, y2 - y1)
        area_a = (a[2] - a[0]) * (a[3] - a[1])
        area_b = (b[2] - b[0]) * (b[3] - b[1])
        union = area_a + area_b - inter
        return inter / union if union > 0 else 0.0

    def _find_best_match(self, bbox):
        best_id = None
        best_iou = self.iou_threshold
        for tid, track in self.tracks.items():
            if track['missed'] > self.max_missed:
                continue
            iou = self._iou(bbox, track['bbox'])
            if iou > best_iou:
                best_iou = iou
                best_id = tid
        return best_id

    def mark_alerted(self, tid):
        """Marchează o persoană ca 'alerted' — nu va mai genera alerte până iese și revine."""
        if tid in self.tracks:
            self.tracks[tid]['status'] = self.ALERTED

    def get_status(self, tid):
        if tid in self.tracks:
            return self.tracks[tid].get('status', self.ACTIVE)
        return self.ACTIVE

    def update(self, detections):
        """
        detections: [(bbox, has_helmet, has_vest), ...]
        Returnează: [(bbox, tid, stable_helmet, stable_vest, status), ...]
        """
        used_ids = set()
        results = []

        for bbox, has_helmet, has_vest in detections:
            tid = self._find_best_match(bbox)
            if tid is not None:
                used_ids.add(tid)
            else:
                tid = self.next_id
                self.next_id += 1

            if tid in self.tracks:
                status = self.tracks[tid].get('status', self.ACTIVE)
            else:
                status = self.ACTIVE

            self.tracks[tid] = {
                'bbox': bbox,
                'missed': 0,
                'history': self.tracks.get(tid, {}).get('history', deque(maxlen=self.history_length)),
                'status': status,
            }
            self.tracks[tid]['history'].append((has_helmet, has_vest))

            # Decizie stabilizată: majoritatea ultimelor N frame-uri
            history = list(self.tracks[tid]['history'])
            helmet_votes = sum(1 for h, _ in history if h)
            vest_votes = sum(1 for _, v in history if v)
            stable_helmet = helmet_votes > len(history) // 2
            stable_vest = vest_votes > len(history) // 2

            results.append((bbox, tid, stable_helmet, stable_vest, status))

        # Increment missed + reset alerted când persoana iese din cadru
        expired = []
        for tid in self.tracks:
            if tid not in used_ids:
                self.tracks[tid]['missed'] += 1
                # Persoana a ieșit din cadru — resetăm statusul de alerted
                if self.tracks[tid]['missed'] > 2:
                    self.tracks[tid]['status'] = self.ACTIVE
                if self.tracks[tid]['missed'] > self.max_missed:
                    expired.append(tid)
        for tid in expired:
            del self.tracks[tid]

        return results

    def reset(self):
        self.tracks = {}
        self.next_id = 0


# =============================================================================
# Object Detector — YOLO11n + PPE Model dedicat + HSV fallback
# =============================================================================

class ObjectDetector:
    def __init__(self, model_path='yolo11n.pt', imgsz=640, half=True):
        """
        Inițializează detectorul cu dublu model:
        1. YOLO11n — detectare persoane (COCO class 0)
        2. YOLO11n-PPE — detectare cască + vestă (model dedicat, opțional)

        Dacă modelul PPE nu e disponibil, face fallback la HSV heuristics
        cu cluster analysis + filtrare morfologică.
        """
        print(f"Se încarcă modelul principal: {model_path}...")

        self.is_tensorrt = model_path.endswith('.engine')
        self.imgsz = imgsz
        self.half = half

        self.model = YOLO(model_path)

        print(f"Model principal încărcat. TensorRT: {self.is_tensorrt}, "
              f"Dimensiune: {imgsz}, FP16: {half}")

        # ---- Model PPE dedicat (opțional) ----
        self.ppe_model = None
        ppe_model_path = 'yolo11n_ppe.engine' if os.path.exists('yolo11n_ppe.engine') else None
        if ppe_model_path is None and os.path.exists('yolo11n_ppe.pt'):
            ppe_model_path = 'yolo11n_ppe.pt'

        if ppe_model_path:
            print(f"Se încarcă model PPE dedicat: {ppe_model_path}...")
            try:
                self.ppe_model = YOLO(ppe_model_path)
                self.ppe_is_tensorrt = ppe_model_path.endswith('.engine')
                print(f"Model PPE încărcat. TensorRT: {self.ppe_is_tensorrt}")
            except Exception as e:
                print(f"⚠️ Model PPE nu s-a putut încărca: {e}")
                print("   Se va folosi fallback HSV.")
                self.ppe_model = None
        else:
            print("ℹ️ Niciun model PPE dedicat găsit (yolo11n_ppe.pt/engine).")
            print("   Se folosește fallback HSV cu cluster analysis.")

        # Clase COCO de interes (0 = Persoană)
        self.classes_of_interest = [0]

        # Culori interfață (BGR)
        self.colors = {
            'safe': (0, 255, 0),
            'danger': (0, 0, 255),
            'warning': (0, 255, 255),
            'vest': (255, 165, 0),
            'helmet': (255, 255, 255)
        }

        # Control spam alerte — per-person (soft tracking)
        self.last_alert_time = 0
        self.alert_cooldown = 5  # secunde minime între alerte globale

        # FPS tracking
        self.last_frame_time = time.time()
        self.frame_interval = 1.0 / 20

        # Person tracker
        self.tracker = PersonTracker(
            iou_threshold=0.3,
            history_length=5,
            max_missed=5
        )

        # Nuclee morfologice
        self._morph_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        self._morph_kernel_small = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))

        # Cache overlay zonă pericol
        self._danger_zone_cache = None
        self._danger_zone_size = None

        # Dimensiune minimă bbox
        self.min_box_size = 30

        # Dirty flag — evită re-annotation când nu s-au schimbat detectiile
        self._dirty = True

    # -----------------------------------------------------------------
    # PPE: Model dedicat
    # -----------------------------------------------------------------

    def _check_ppe_model(self, person_frame):
        """
        Verifică PPE folosind modelul YOLO dedicat pe crop-ul persoanei.
        Returnează (has_helmet, has_vest).
        """
        if self.ppe_model is None:
            return None  # Fallback la HSV

        try:
            results = self.ppe_model(
                person_frame, verbose=False,
                imgsz=320, half=self.half, device=0,
                conf=0.35
            )
            has_helmet = False
            has_vest = False

            for r in results:
                for box in r.boxes:
                    cls_id = int(box.cls[0])
                    # Mapare clase model PPE (depinde de dataset)
                    # SafetyHelmetDataset: 0=Helmet, 1=NO-Helmet
                    # Sau custom: adaptabil
                    if cls_id == 0:
                        has_helmet = True
                    elif cls_id == 2:
                        has_vest = True
                    elif cls_id == 1:
                        pass  # no-helmet class — nu ne interesează

            return has_helmet, has_vest
        except Exception:
            return None  # Eroare → fallback HSV

    # -----------------------------------------------------------------
    # PPE: HSV fallback cu cluster analysis
    # -----------------------------------------------------------------

    def _preprocess_roi(self, roi):
        if roi.size == 0:
            return roi
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        hsv[:, :, 2] = cv2.equalizeHist(hsv[:, :, 2])
        return hsv

    def _clip_bbox(self, x1, y1, x2, y2, h, w):
        return max(0, x1), max(0, y1), min(w, x2), min(h, y2)

    def _find_largest_cluster(self, mask, min_area=50):
        """
        Analizează o mască binară și returnează pixelii celui mai mare
        cluster (componentă conexă). Elimină detectii izolate de la fundal.
        """
        if mask.size == 0 or cv2.countNonZero(mask) == 0:
            return mask

        # Găsim componentele conexe
        num_labels, labels, stats_cv, centroids = cv2.connectedComponentsWithStats(
            mask, connectivity=8
        )

        # Căutăm componenta cu cea mai mare suprafață (excluzând background = label 0)
        if num_labels <= 1:
            return mask

        best_label = 1
        best_area = 0
        for label_id in range(1, num_labels):
            area = stats_cv[label_id, cv2.CC_STAT_AREA]
            if area > best_area:
                best_area = area
                best_label = label_id

        # Returnăm doar cel mai mare cluster dacă e semnificativ
        if best_area >= min_area:
            cluster_mask = np.zeros_like(mask)
            cluster_mask[labels == best_label] = 255
            return cluster_mask

        return mask

    def _analyze_color_region(self, hsv_roi, color_ranges):
        """
        Analizează o regiune HSV pentru culorile date.
        Folosește:
        - Filtrare morfologică (OPEN + CLOSE)
        - Cluster analysis (cel mai mare blob conex)
        - Scoring ponderat (densitate + compactitate + acoperire)
        """
        if hsv_roi.size == 0:
            return 0.0

        total_area = hsv_roi.shape[0] * hsv_roi.shape[1]
        if total_area == 0:
            return 0.0

        # Combinăm măștile de culoare
        combined_mask = np.zeros(hsv_roi.shape[:2], dtype=np.uint8)
        for lower, upper in color_ranges:
            mask = cv2.inRange(hsv_roi, np.array(lower), np.array(upper))
            combined_mask = cv2.bitwise_or(combined_mask, mask)

        if cv2.countNonZero(combined_mask) == 0:
            return 0.0

        # Cluster analysis: păstrăm doar cel mai mare blob
        combined_mask = self._find_largest_cluster(combined_mask, min_area=30)

        # Filtrare morfologică
        cleaned = cv2.morphologyEx(
            combined_mask, cv2.MORPH_OPEN, self._morph_kernel_small, iterations=2
        )
        cleaned = cv2.morphologyEx(
            cleaned, cv2.MORPH_CLOSE, self._morph_kernel, iterations=1
        )

        pixel_count = cv2.countNonZero(cleaned)
        if pixel_count == 0:
            return 0.0

        # Densitate
        density = pixel_count / total_area

        # Compactitate: raport post-filtrare / pre-filtrare
        raw_count = cv2.countNonZero(combined_mask)
        compactness = pixel_count / raw_count if raw_count > 0 else 0.0

        # Bonus acoperire
        coverage_bonus = min(density / 0.15, 1.0)

        # Scor final ponderat
        score = (density * 0.35 + compactness * 0.35 + coverage_bonus * 0.30)
        return min(score, 1.0)

    def _check_ppe_hsv(self, frame, x1, y1, x2, y2):
        """
        Fallback HSV cu cluster analysis.
        """
        h_frame, w_frame, _ = frame.shape
        x1, y1, x2, y2 = self._clip_bbox(x1, y1, x2, y2, h_frame, w_frame)

        box_w = x2 - x1
        box_h = y2 - y1
        if box_w < self.min_box_size or box_h < self.min_box_size:
            return False, False

        person_roi = frame[y1:y2, x1:x2]
        if person_roi.size == 0:
            return False, False

        h, w, _ = person_roi.shape

        # ROI Cască: top 25%, centrat 60%
        w_offset = int(w * 0.2)
        helmet_roi = person_roi[0:int(h * 0.25), w_offset:w - w_offset]

        # ROI Vestă: torso 20%-60%
        vest_roi = person_roi[int(h * 0.2):int(h * 0.6), :]

        if helmet_roi.size == 0 or vest_roi.size == 0:
            return False, False

        hsv_helmet = self._preprocess_roi(helmet_roi)
        hsv_vest = self._preprocess_roi(vest_roi)

        # Culori cascu
        helmet_colors = [
            ([0, 0, 200], [180, 30, 255]),      # Alb
            ([20, 50, 70], [50, 255, 255]),      # Galben
            ([0, 100, 100], [10, 255, 255]),     # Roșu 1
            ([160, 100, 100], [180, 255, 255]),  # Roșu 2
            ([90, 80, 80], [130, 255, 255]),     # Albastru
            ([10, 100, 100], [25, 255, 255]),    # Portocaliu
        ]

        # Culori vestă
        vest_colors = [
            ([10, 100, 100], [25, 255, 255]),    # Portocaliu
            ([20, 20, 50], [50, 255, 255]),      # Galben
            ([0, 100, 100], [10, 255, 255]),     # Roșu 1
            ([160, 100, 100], [180, 255, 255]),  # Roșu 2
        ]

        helmet_score = self._analyze_color_region(hsv_helmet, helmet_colors)
        vest_score = self._analyze_color_region(hsv_vest, vest_colors)

        return helmet_score > 0.18, vest_score > 0.18

    def check_ppe(self, frame, x1, y1, x2, y2):
        """
        Verifică PPE: model dedicat dacă disponibil, altfel HSV fallback.
        """
        # Încercăm modelul PPE dedicat pe crop-ul persoanei
        h_frame, w_frame, _ = frame.shape
        cx1, cy1, cx2, cy2 = self._clip_bbox(x1, y1, x2, y2, h_frame, w_frame)

        if self.ppe_model is not None and (cx2 - cx1) > 40 and (cy2 - cy1) > 40:
            person_crop = frame[cy1:cy2, cx1:cx2]
            result = self._check_ppe_model(person_crop)
            if result is not None:
                return result

        # Fallback: HSV cu cluster analysis
        return self._check_ppe_hsv(frame, x1, y1, x2, y2)

    # -----------------------------------------------------------------
    # Overlay zonă de pericol (cache)
    # -----------------------------------------------------------------

    def _get_danger_zone_overlay(self, w_img, h_img):
        if self._danger_zone_cache is not None and self._danger_zone_size == (w_img, h_img):
            return self._danger_zone_cache
        overlay = np.zeros((h_img, w_img, 3), dtype=np.uint8)
        danger_zone_x = int(w_img * 0.75)
        cv2.rectangle(overlay, (danger_zone_x, 0), (w_img, h_img), (0, 0, 255), -1)
        self._danger_zone_cache = overlay
        self._danger_zone_size = (w_img, h_img)
        return overlay

    # -----------------------------------------------------------------
    # Detectia principală
    # -----------------------------------------------------------------

    def detect(self, frame):
        if frame is None:
            return None, {}

        h_img, w_img, _ = frame.shape
        danger_zone_x = int(w_img * 0.75)

        # Inferență YOLO11n — persoane
        results = self.model(
            frame, verbose=False,
            imgsz=self.imgsz, half=self.half, device=0
        )

        raw_detections = []
        for r in results:
            for box in r.boxes:
                if int(box.cls[0]) != 0:
                    continue
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                if (x2 - x1) < self.min_box_size or (y2 - y1) < self.min_box_size:
                    continue
                has_helmet, has_vest = self.check_ppe(frame, x1, y1, x2, y2)
                raw_detections.append(((x1, y1, x2, y2), has_helmet, has_vest))

        # Tracking + stabilizare temporală + soft tracking
        tracked = self.tracker.update(raw_detections)

        # Dirty flag: adnotăm doar dacă s-au schimbat detectiile
        # (comparăm track IDs și statusuri)
        current_track_keys = {(t[1], t[2], t[3], t[4]) for t in tracked}
        if hasattr(self, '_last_track_keys') and current_track_keys == self._last_track_keys:
            # Aceleași detectii — returnăm ultimul frame fără re-annotation
            if hasattr(self, '_last_annotated'):
                # Actualizăm doar FPS-ul pe frame-ul vechi
                current_time = time.time()
                elapsed = current_time - self.last_frame_time
                fps = 1.0 / elapsed if elapsed > 0 else 0
                self.last_frame_time = current_time
                stats = {
                    'total_persons': len(tracked),
                    'violations': 0,
                    'alerts': []
                }
                return self._last_annotated, stats
        self._last_track_keys = current_track_keys
        self._dirty = True

        # Construim frame annotat
        annotated_frame = frame.copy()

        stats = {
            'total_persons': len(tracked),
            'violations': 0,
            'alerts': []
        }
        current_violations = 0
        violation_types = []
        alerted_tids = []

        for bbox, tid, stable_helmet, stable_vest, status in tracked:
            x1, y1, x2, y2 = bbox
            x_mid = (x1 + x2) // 2
            is_in_danger_zone = x_mid > danger_zone_x
            has_all_ppe = stable_helmet and stable_vest

            # Soft tracking: dacă persoana e 'alerted', nu mai contorizăm violații
            is_alerted = (status == PersonTracker.ALERTED)

            if not has_all_ppe:
                is_safe = False
                is_warning = False
            elif is_in_danger_zone:
                is_safe = False
                is_warning = True
            else:
                is_safe = True
                is_warning = False

            # Etichetă
            label_parts = []
            if not stable_helmet:
                label_parts.append("SIN CASCO")
            if not stable_vest:
                label_parts.append("SIN CHALECO")
            if is_in_danger_zone:
                label_parts.append("ZONA PELIGROSA")

            if is_safe:
                color = self.colors['safe']
                label = "Seguro"
            elif is_warning:
                color = self.colors['warning']
                reason = ", ".join(label_parts)
                label = f"AVISO: {reason}"
                if not is_alerted:
                    stats['violations'] += 1
                    current_violations += 1
                    stats['alerts'].append(f"Aviso: {reason}")
                    violation_types.append(reason)
                    alerted_tids.append(tid)
                else:
                    label += " [TRACKED]"
            else:
                color = self.colors['danger']
                reason = ", ".join(label_parts)
                label = f"PELIGRO: {reason}"
                if not is_alerted:
                    stats['violations'] += 1
                    current_violations += 1
                    stats['alerts'].append(f"Peligro: {reason}")
                    violation_types.append(reason)
                    alerted_tids.append(tid)
                else:
                    label += " [TRACKED]"

            cv2.rectangle(annotated_frame, (x1, y1), (x2, y2), color, 2)
            cv2.putText(
                annotated_frame, label, (x1, y1 - 10),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2
            )

        # Overlay zonă pericol
        overlay = self._get_danger_zone_overlay(w_img, h_img)
        cv2.addWeighted(overlay, 0.2, annotated_frame, 0.8, 0, annotated_frame)
        cv2.line(annotated_frame, (danger_zone_x, 0), (danger_zone_x, h_img), (0, 0, 255), 2)
        cv2.putText(
            annotated_frame, "ZONA DE PELIGRO", (danger_zone_x + 10, 30),
            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2
        )

        # Timestamp
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cv2.putText(
            annotated_frame, timestamp, (10, h_img - 20),
            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2
        )

        # FPS
        current_time = time.time()
        elapsed = current_time - self.last_frame_time
        fps = 1.0 / elapsed if elapsed > 0 else 0
        self.last_frame_time = current_time
        cv2.putText(
            annotated_frame, f"FPS: {int(fps)}", (10, 30),
            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2
        )

        # Model indicator
        ppe_label = "PPE: Model" if self.ppe_model else "PPE: HSV"
        cv2.putText(
            annotated_frame, ppe_label, (10, 55),
            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1
        )

        # Salvare alertă cu soft tracking
        if current_violations > 0 and (current_time - self.last_alert_time > self.alert_cooldown):
            v_type = violation_types[0] if violation_types else "Violación"
            self.save_alert(annotated_frame, v_type)
            self.last_alert_time = current_time
            # Marcăm persoanele ca alerted
            for tid in alerted_tids:
                self.tracker.mark_alerted(tid)

        # Cache ultimul frame annotat
        self._last_annotated = annotated_frame

        return annotated_frame, stats

    # -----------------------------------------------------------------
    # Salvare alertă
    # -----------------------------------------------------------------

    def save_alert(self, frame, incident_type):
        try:
            timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"capture_{timestamp_str}.jpg"
            base_dir = os.path.dirname(os.path.abspath(__file__))
            save_dir = os.path.join(base_dir, 'static/captures')
            filepath = os.path.join(save_dir, filename)
            web_path = f"captures/{filename}"
            if not os.path.exists(save_dir):
                os.makedirs(save_dir, exist_ok=True)
            if cv2.imwrite(filepath, frame):
                print(f"✅ Alertă salvată: {filepath}")
                log_incident(incident_type, web_path, f"Violación detectada: {incident_type}")
        except Exception as e:
            print(f"❌ Eroare save_alert: {e}")
