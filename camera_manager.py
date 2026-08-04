import json
import os
import threading
import time
from camera import VideoCamera


CAMERAS_CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cameras.json')


class CameraManager:
    """
    Gestionează multiple camere (RTSP, USB, CSI, sintetice).
    Configurare din cameras.json, suportă add/remove la runtime.
    """

    def __init__(self, config_path=CAMERAS_CONFIG_PATH):
        self.config_path = config_path
        self.cameras = {}       # {cam_id: VideoCamera}
        self.config = []        # lista de dicționare din JSON
        self._lock = threading.Lock()
        self._next_id = 1

        # Încarcă configurare și inițializează camerele
        self._load_config()
        self._start_all()

    # -----------------------------------------------------------------
    # Configurare JSON
    # -----------------------------------------------------------------

    def _load_config(self):
        """Încarcă camerele din cameras.json."""
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r') as f:
                    self.config = json.load(f)
                # Determină next_id
                if self.config:
                    self._next_id = max(c.get('id', 0) for c in self.config) + 1
                print(f"✅ Configurare încărcată: {len(self.config)} camere")
            except Exception as e:
                print(f"⚠️ Eroare citire cameras.json: {e}")
                self.config = []
        else:
            print(f"ℹ️ cameras.json nu există la {self.config_path}")
            self.config = []
            self._save_config()

    def _save_config(self):
        """Salvează configurația curentă în cameras.json."""
        try:
            with open(self.config_path, 'w') as f:
                json.dump(self.config, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"⚠️ Eroare salvare cameras.json: {e}")

    # -----------------------------------------------------------------
    # Inițializare camere
    # -----------------------------------------------------------------

    def _start_all(self):
        """Pornește toate camerele din configurare."""
        for cam_cfg in self.config:
            if cam_cfg.get('enabled', True):
                self._start_camera(cam_cfg)

        if not self.cameras:
            print("⚠️ Nicio cameră configurată și activă.")
            print("   Adaugă camere în cameras.json sau via API /api/camera/add")

    def _start_camera(self, cam_cfg):
        """Inițializează o cameră din configurație."""
        cam_id = cam_cfg['id']
        name = cam_cfg.get('name', f'Camera {cam_id}')
        url = cam_cfg['url']

        # Detectează tipul sursei
        if isinstance(url, str) and url.startswith('rtsp://'):
            source = url
        elif isinstance(url, int):
            source = url
        elif isinstance(url, str) and url.isdigit():
            source = int(url)
        else:
            source = 0  # fallback local

        try:
            camera = VideoCamera(source=source, name=name)
            with self._lock:
                self.cameras[cam_id] = camera
            print(f"📹 Camera {cam_id} '{name}' pornită (sursa: {source})")
        except Exception as e:
            print(f"❌ Camera {cam_id} '{name}' eroare: {e}")

    # -----------------------------------------------------------------
    # Management camere (add/remove/toggle)
    # -----------------------------------------------------------------

    def add_camera(self, name, url, enabled=True):
        """
        Adaugă o cameră nouă la runtime.
        Returnează (cam_id, camera) sau (None, error).
        """
        cam_id = self._next_id
        self._next_id += 1

        cam_cfg = {
            'id': cam_id,
            'name': name,
            'url': url,
            'enabled': enabled
        }
        self.config.append(cam_cfg)
        self._save_config()

        if enabled:
            self._start_camera(cam_cfg)
            with self._lock:
                cam = self.cameras.get(cam_id)
            return cam_id, cam
        else:
            return cam_id, None

    def remove_camera(self, cam_id):
        """Oprește și șterge o cameră."""
        with self._lock:
            if cam_id in self.cameras:
                self.cameras[cam_id].stop()
                del self.cameras[cam_id]

        self.config = [c for c in self.config if c['id'] != cam_id]
        self._save_config()
        print(f"🗑️ Camera {cam_id} ștearsă")

    def toggle_camera(self, cam_id):
        """Activează/dezactivează o cameră."""
        for cam_cfg in self.config:
            if cam_cfg['id'] == cam_id:
                currently_enabled = cam_cfg.get('enabled', True)
                cam_cfg['enabled'] = not currently_enabled

                if not currently_enabled:
                    # Pornim
                    self._start_camera(cam_cfg)
                else:
                    # Oprim
                    with self._lock:
                        if cam_id in self.cameras:
                            self.cameras[cam_id].stop()
                            del self.cameras[cam_id]

                self._save_config()
                return cam_cfg['enabled']
        return None

    # -----------------------------------------------------------------
    # Acces camere
    # -----------------------------------------------------------------

    def get_camera(self, cam_id):
        """Returnează obiectul VideoCamera pentru un ID."""
        with self._lock:
            return self.cameras.get(cam_id)

    def get_frame(self, cam_id):
        """Returnează ultimul frame de la o cameră."""
        cam = self.get_camera(cam_id)
        return cam.get_frame() if cam else None

    def get_all_cameras_info(self):
        """Returnează info despre toate camerele (config + status)."""
        info = []
        for cam_cfg in self.config:
            cam_id = cam_cfg['id']
            cam = self.cameras.get(cam_id)
            info.append({
                'id': cam_id,
                'name': cam_cfg.get('name', ''),
                'url': cam_cfg.get('url', ''),
                'enabled': cam_cfg.get('enabled', True),
                'status': cam.status if cam else 'disabled',
                'fps': round(cam.fps, 1) if cam else 0
            })
        return info

    def get_active_camera_ids(self):
        """Returnează lista de ID-uri ale camerelor active."""
        with self._lock:
            return list(self.cameras.keys())

    @property
    def active_count(self):
        """Numărul de camere active."""
        return len(self.cameras)

    @property
    def total_count(self):
        """Numărul total de camere în configurare."""
        return len(self.config)

    # -----------------------------------------------------------------
    # Cleanup
    # -----------------------------------------------------------------

    def stop_all(self):
        """Oprește toate camerele."""
        with self._lock:
            for cam_id, cam in self.cameras.items():
                try:
                    cam.stop()
                except Exception:
                    pass
            self.cameras.clear()
        print("🛑 Toate camerele oprite")
