import json
import os
import stat
import threading
import time
import hashlib
import base64
from camera import VideoCamera


CAMERAS_CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cameras.json')


# Criptare simplă pentru parolele RTSP (nu necesită pachete extra)
# Folosește XOR cu cheie derivată din hash-ul sistemului — suficient pt
# a nu stoca plaintext în cameras.json. NU e criptare militară,
# dar elimină expunerea directă a credențialelor.

def _get_system_key():
    """Generează o cheie deterministă din calea absolută a proiectului."""
    return hashlib.sha256(CAMERAS_CONFIG_PATH.encode()).digest()


def encrypt_rtsp_password(password):
    """Criptează o parolă RTSP. Returnează string codificat base64."""
    if not password:
        return ''
    key = _get_system_key()
    pw_bytes = password.encode('utf-8')
    encrypted = bytes(b ^ key[i % len(key)] for i, b in enumerate(pw_bytes))
    return 'enc:' + base64.b64encode(encrypted).decode('ascii')


def decrypt_rtsp_password(encrypted):
    """Decriptează o parolă RTSP. Returnează plaintext."""
    if not encrypted or not encrypted.startswith('enc:'):
        return encrypted  # Nu e criptat (compatibilitate)
    key = _get_system_key()
    try:
        pw_bytes = base64.b64decode(encrypted[4:])
        decrypted = bytes(b ^ key[i % len(key)] for i, b in enumerate(pw_bytes))
        return decrypted.decode('utf-8')
    except Exception:
        return encrypted  # Fallback: returnează ca-is


def _encrypt_url_if_needed(url):
    """Dacă URL conține parolă plaintext, o criptează."""
    if not url or not isinstance(url, str):
        return url
    # Detectează rtsp://user:password@host
    if '://' in url and '@' in url:
        prefix, rest = url.split('://', 1)
        if '@' in rest:
            creds, host_part = rest.rsplit('@', 1)
            if ':' in creds:
                user, password = creds.split(':', 1)
                # Verifică dacă parola e deja criptată
                if not password.startswith('enc:'):
                    encrypted_pw = encrypt_rtsp_password(password)
                    return f"{prefix}://{user}:{encrypted_pw}@{host_part}"
    return url


def _decrypt_url(url):
    """Decriptează parola din URL dacă e criptată."""
    if not url or not isinstance(url, str):
        return url
    if '://' in url and '@' in url:
        prefix, rest = url.split('://', 1)
        if '@' in rest:
            creds, host_part = rest.rsplit('@', 1)
            if ':' in creds:
                user, password = creds.split(':', 1)
                decrypted_pw = decrypt_rtsp_password(password)
                return f"{prefix}://{user}:{decrypted_pw}@{host_part}"
    return url


class CameraManager:
    """
    Gestionează multiple camere (RTSP, USB, CSI, sintetice).
    Configurare din cameras.json, suportă add/remove la runtime.
    """

    def __init__(self, config_path=CAMERAS_CONFIG_PATH, max_cameras=None):
        """
        max_cameras: limită maximă de camere active simultan (din profil hardware).
                     None = fără limită (compatibilitate).
        Camerele peste limită rămân în stare 'pending' și pornesc automat
        când se eliberează loc (remove/toggle off).
        """
        self.config_path = config_path
        self.cameras = {}       # {cam_id: VideoCamera} — doar camerele ACTIVE
        self.config = []        # lista de dicționare din JSON
        self._lock = threading.Lock()
        self._next_id = 1
        self.max_cameras = max_cameras  # limită hardware

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
        """Salvează configurația curentă în cameras.json (cu parole criptate)."""
        try:
            # Criptează parolele înainte de salvare (copie, nu mută originalul)
            config_to_save = []
            for cam_cfg in self.config:
                cfg_copy = dict(cam_cfg)
                cfg_copy['url'] = _encrypt_url_if_needed(cfg_copy.get('url', ''))
                config_to_save.append(cfg_copy)
            with open(self.config_path, 'w') as f:
                json.dump(config_to_save, f, indent=4, ensure_ascii=False)
            # Restrânge permisiunile (doar owner poate citi)
            os.chmod(self.config_path, stat.S_IRUSR | stat.S_IWUSR)
        except Exception as e:
            print(f"⚠️ Eroare salvare cameras.json: {e}")

    # -----------------------------------------------------------------
    # Inițializare camere
    # -----------------------------------------------------------------

    def _start_all(self):
        """Pornește camerele din configurare, respectând limita hardware."""
        enabled_cams = [c for c in self.config if c.get('enabled', True)]
        active_count = len(self.cameras)

        for cam_cfg in enabled_cams:
            # Oprim dacă am atins limita hardware
            if self.max_cameras is not None and active_count >= self.max_cameras:
                remaining = len(enabled_cams) - active_count
                print(f"⚠️ Limită hardware: {active_count}/{self.max_cameras} camere active.")
                print(f"   {remaining} camer(e) rămân în așteptare (vor porni când se eliberează loc).")
                break
            if self._start_camera(cam_cfg):
                active_count += 1

        if not self.cameras:
            print("⚠️ Nicio cameră configurată și activă.")
            print("   Adaugă camere în cameras.json sau via API /api/camera/add")

    def _start_camera(self, cam_cfg):
        """
        Inițializează o cameră din configurație.
        Returnează True dacă a pornit, False altfel (limită atinsă sau eroare).
        """
        # Verifică limita hardware
        if self.max_cameras is not None and len(self.cameras) >= self.max_cameras:
            return False

        cam_id = cam_cfg['id']
        name = cam_cfg.get('name', f'Camera {cam_id}')
        url = _decrypt_url(cam_cfg['url'])

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
            return True
        except Exception as e:
            print(f"❌ Camera {cam_id} '{name}' eroare: {e}")
            return False

    # -----------------------------------------------------------------
    # Management camere (add/remove/toggle)
    # -----------------------------------------------------------------

    def add_camera(self, name, url, enabled=True):
        """
        Adaugă o cameră nouă la runtime.
        Dacă limita hardware e atinsă, cameră rămâne în 'pending'.
        Returnează (cam_id, camera) — camera e None dacă a rămas pending.
        """
        cam_id = self._next_id
        self._next_id += 1

        cam_cfg = {
            'id': cam_id,
            'name': name,
            'url': _encrypt_url_if_needed(url),
            'enabled': enabled
        }
        self.config.append(cam_cfg)
        self._save_config()

        if enabled:
            started = self._start_camera(cam_cfg)
            if started:
                with self._lock:
                    cam = self.cameras.get(cam_id)
                return cam_id, cam
            else:
                # Limită atinsă — cameră rămâne în așteptare
                print(f"⏳ Camera {cam_id} '{name}' în așteptare "
                      f"(limită hardware: {self.max_cameras} camere).")
                return cam_id, None
        else:
            return cam_id, None

    def _promote_next_pending(self):
        """
        Pornește următoarea cameră din așteptare dacă există loc.
        Apelat automat după remove/toggle off.
        """
        if self.max_cameras is None:
            return  # fără limită, nimic de promovat

        if len(self.cameras) >= self.max_cameras:
            return  # încă la limită

        # Găsește camerele enabled dar ne-pornite (pending)
        active_ids = set(self.cameras.keys())
        for cam_cfg in self.config:
            if cam_cfg.get('enabled', True) and cam_cfg['id'] not in active_ids:
                print(f"↗️ Promovez camera {cam_cfg['id']} '{cam_cfg.get('name')}' din așteptare.")
                self._start_camera(cam_cfg)
                return  # promovăm doar una per eliberare de loc

    def remove_camera(self, cam_id):
        """Oprește și șterge o cameră. Promovează automat următoarea din așteptare."""
        with self._lock:
            if cam_id in self.cameras:
                self.cameras[cam_id].stop()
                del self.cameras[cam_id]

        self.config = [c for c in self.config if c['id'] != cam_id]
        self._save_config()
        print(f"🗑️ Camera {cam_id} ștearsă")

        # Promovează următoarea cameră din așteptare
        self._promote_next_pending()

    def toggle_camera(self, cam_id):
        """Activează/dezactivează o cameră. Promovează automat la dezactivare."""
        for cam_cfg in self.config:
            if cam_cfg['id'] == cam_id:
                currently_enabled = cam_cfg.get('enabled', True)
                cam_cfg['enabled'] = not currently_enabled

                if not currently_enabled:
                    # Pornim — verifică dacă e loc disponibil
                    started = self._start_camera(cam_cfg)
                    if not started and self.max_cameras is not None:
                        print(f"⏳ Camera {cam_id} nu poate porni — limită hardware atinsă.")
                else:
                    # Oprim
                    with self._lock:
                        if cam_id in self.cameras:
                            self.cameras[cam_id].stop()
                            del self.cameras[cam_id]
                    # Promovează următoarea cameră din așteptare
                    self._promote_next_pending()

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
            is_enabled = cam_cfg.get('enabled', True)

            # Determină statusul real
            if cam:
                status = cam.status
            elif is_enabled and self.max_cameras is not None:
                # Enabled dar ne-pornită = în așteptare (limită hardware)
                status = 'pending'
            else:
                status = 'disabled'

            info.append({
                'id': cam_id,
                'name': cam_cfg.get('name', ''),
                'url': cam_cfg.get('url', ''),
                'enabled': is_enabled,
                'status': status,
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
