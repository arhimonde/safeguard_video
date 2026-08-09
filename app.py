# --- ACCES REMOT (OPȚIONAL) ---
# Pentru a accesa serverul de oriunde:
# 1. Pornește tunelul: python3 loophole_tunnel.py
# 2. Folosește URL-ul .loophole.site generat.
from flask import (Flask, render_template, Response, jsonify,
                   request, redirect, url_for)
from flask_login import (LoginManager, login_user, login_required,
                         logout_user, current_user)
from flask_socketio import SocketIO, emit
from camera_manager import CameraManager
from detector import ObjectDetector
from jetson_profile import detect_jetson_profile
from database import (init_db, get_recent_incidents, get_user_by_username,
                      get_user_by_id, change_password,
                      delete_violations_by_date, delete_violations_by_hash)
from werkzeug.security import check_password_hash
import cv2
import threading
import time
import os
from collections import defaultdict
from functools import wraps

app = Flask(__name__)

# Secret key persistent — nu se regenerează la restart
_SECRET_KEY_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.secret_key')
if os.path.exists(_SECRET_KEY_PATH):
    with open(_SECRET_KEY_PATH, 'rb') as f:
        app.secret_key = f.read()
else:
    app.secret_key = os.urandom(24)
    with open(_SECRET_KEY_PATH, 'wb') as f:
        f.write(app.secret_key)
    os.chmod(_SECRET_KEY_PATH, 0o600)

# CORS restrictiv pe WebSocket — citește origins din config.json
def _get_allowed_origins():
    import json as _json
    try:
        cfg_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.json')
        with open(cfg_path, 'r') as f:
            cfg = _json.load(f)
            return cfg.get('allowed_origins', [])
    except (FileNotFoundError, _json.JSONDecodeError):
        pass
    return ["http://localhost:5000", "http://127.0.0.1:5000"]

socketio = SocketIO(app, cors_allowed_origins=_get_allowed_origins(), async_mode='threading')

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    return get_user_by_id(user_id)

init_db()

# Forcează schimbarea parolei la prima logare
@app.before_request
def enforce_password_change():
    if current_user.is_authenticated and current_user.must_change_password:
        if request.endpoint not in ('change_password', 'logout', 'static'):
            return redirect(url_for('change_password'))

# CONFIGURARE MODEL YOLO
# Alege mărimea modelului în funcție de scenariu:
#
#   'n' (nano)   → MAX camere (25+). Cea mai rapidă. Recomandat pt multi-camerá.
#   's' (small)  → 5-8 camere. Echilibru viteză/precizie.
#   'm' (medium) → 3-4 camere. Precizie mai bună la distanță.
#   'l' (large)  → 1-2 camere. Precizie maximă, mai lent.
#   'x' (xlarge) → 1 cameră. Cea mai precisă, cea mai lentă.
#
# Format preferat: TensorRT (.engine) dacă există, altfel PyTorch (.pt)
# CONVERSIE INT8: rulează `bash convert_to_tensorrt.sh` pentru 2x mai multă viteză
YOLO_VERSION = 'yolo11'
YOLO_SIZE = 'n'           # 'n', 's', 'm', 'l', 'x'

# Inițializare Camera Manager + Detector
# Detectare hardware — parametri se adaptează automat (Jetson / GPU / CPU)
hw = detect_jetson_profile()
camera_manager = CameraManager(max_cameras=hw['max_cameras'])

model_base = f"{YOLO_VERSION}{YOLO_SIZE}"
model_to_use = f"{model_base}.engine" if os.path.exists(f"{model_base}.engine") else f"{model_base}.pt"
# half=False: modelul .engine (INT8/FP16) e deja optimizat; FP16 forțat ar cauza eroare pe INT8
detector = ObjectDetector(model_path=model_to_use, half=False)

# Stare globală per cameră
# {cam_id: {'annotated_frame': np.array, 'stats': dict, 'monitoring': bool}}
cameras_state = {}
state_lock = threading.Lock()

def init_camera_state(cam_id):
    """Inițializează starea pentru o cameră nouă."""
    with state_lock:
        cameras_state[cam_id] = {
            'annotated_frame': None,
            'stats': {'total_persons': 0, 'violations': 0, 'alerts': [],
                      'camera_id': cam_id},
            'monitoring': True
        }

for cam_id in camera_manager.get_active_camera_ids():
    init_camera_state(cam_id)

# WebSocket broadcast
_last_ws_broadcast = 0
_ws_broadcast_interval = 1.0

def broadcast_stats():
    """Trimite stats agregate (toate camerele) prin WebSocket."""
    global _last_ws_broadcast
    now = time.time()
    if now - _last_ws_broadcast < _ws_broadcast_interval:
        return
    _last_ws_broadcast = now

    cameras_info = camera_manager.get_all_cameras_info()
    total_persons = 0
    total_violations = 0
    all_alerts = []

    with state_lock:
        for cam_id, state in cameras_state.items():
            stats = state['stats']
            total_persons += stats.get('total_persons', 0)
            total_violations += stats.get('violations', 0)
            for alert in stats.get('alerts', []):
                all_alerts.append(f"[Cam {cam_id}] {alert}")

    db_incidents = get_recent_incidents(10)

    socketio.emit('stats_update', {
        'total_persons': total_persons,
        'violations': total_violations,
        'alerts': all_alerts[-10:],
        'recent_incidents': db_incidents,
        'cameras': cameras_info
    }, namespace='/monitor')

# Thread detecție per cameră
def detection_thread_fn(cam_id):
    """
    Thread dedicat pentru o cameră.
    FPS adaptiv în funcție de numărul total de camere active.
    """
    while True:
        num_cams = camera_manager.active_count
        target_fps = detector.get_fps_per_camera(num_cams)
        frame_interval = 1.0 / target_fps
        loop_start = time.time()

        camera = camera_manager.get_camera(cam_id)
        if camera is None:
            # Cameră eliminată — ieșim
            print(f"🛑 Thread detecție oprit pentru camera {cam_id}")
            return

        frame = camera.get_frame()
        if frame is None:
            time.sleep(0.05)
            continue

        # Verifică dacă monitorizarea e activă pentru această cameră
        with state_lock:
            cam_state = cameras_state.get(cam_id)
            monitoring = cam_state['monitoring'] if cam_state else True

        if monitoring:
            try:
                result_frame, stats = detector.detect(frame, cam_id)
            except Exception as e:
                print(f"❌ Eroare detecție cam {cam_id}: {e}")
                result_frame = frame.copy()
                stats = {'total_persons': 0, 'violations': 0, 'alerts': [],
                         'camera_id': cam_id}
        else:
            result_frame = frame.copy()
            cv2.putText(result_frame, "PAUSADA", (50, 240),
                        cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 165, 255), 2)
            stats = {'total_persons': 0, 'violations': 0, 'alerts': [],
                     'camera_id': cam_id}

        with state_lock:
            if cam_id in cameras_state:
                cameras_state[cam_id]['annotated_frame'] = result_frame
                cameras_state[cam_id]['stats'] = stats
                cameras_state[cam_id]['frame_timestamp'] = time.time()

        broadcast_stats()

        # FPS stabilizat
        elapsed = time.time() - loop_start
        sleep_time = max(0, frame_interval - elapsed)
        if sleep_time > 0:
            time.sleep(sleep_time)


def start_detection_thread(cam_id):
    """Pornește thread-ul de detecție pentru o cameră."""
    init_camera_state(cam_id)
    t = threading.Thread(target=detection_thread_fn, args=(cam_id,), daemon=True)
    t.start()
    print(f"▶️ Thread detecție pornit pentru camera {cam_id}")
    return t

_detection_threads = {}
for cam_id in camera_manager.get_active_camera_ids():
    _detection_threads[cam_id] = start_detection_thread(cam_id)

# Streaming MJPEG per cameră
def get_stream_quality(num_cameras):
    """
    Calitate stream adaptivă în funcție de numărul de camere active.
    Mai puține camere = calitate mai bună (lățime de bandă permite).
    """
    if num_cameras <= 3:
        return 80, 20    # calitate maximă, 20 FPS
    elif num_cameras <= 10:
        return 60, 12    # calitate medie, 12 FPS
    else:
        return 40, 8     # compresie pentru multi-cameră, 8 FPS

def gen(cam_id):
    """Generator MJPEG pentru o cameră specifică."""
    last_num_cams = -1
    jpeg_quality = 40
    stream_fps = 8
    import numpy as _np

    while True:
        # Re-calibrează parametri stream când se schimbă numărul de camere
        num_cams = camera_manager.active_count
        if num_cams != last_num_cams:
            last_num_cams = num_cams
            jpeg_quality, stream_fps = get_stream_quality(num_cams)
            encode_params = [cv2.IMWRITE_JPEG_QUALITY, jpeg_quality]

        stream_interval = 1.0 / stream_fps
        stream_start = time.time()

        with state_lock:
            cam_state = cameras_state.get(cam_id)
            frame = cam_state['annotated_frame'] if cam_state else None
            frame_ts = cam_state.get('frame_timestamp', 0) if cam_state else 0

        if frame is None:
            camera = camera_manager.get_camera(cam_id)
            if camera is not None:
                frame = camera.get_frame()
            if frame is None:
                time.sleep(0.02)
                continue

        # NO SIGNAL: dacă frame-ul e > 3 secunde vechi, afișează overlay
        frame_age = time.time() - frame_ts if frame_ts > 0 else 0
        if frame_age > 3.0:
            h, w = 480, 640
            try:
                h, w = frame.shape[:2]
            except Exception:
                pass
            no_signal_frame = _np.zeros((h, w, 3), dtype=_np.uint8)
            cv2.putText(no_signal_frame, "NO SIGNAL", (w // 2 - 100, h // 2),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 0, 255), 3)
            ret, jpeg = cv2.imencode('.jpg', no_signal_frame, encode_params)
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + jpeg.tobytes() + b'\r\n')
            elapsed = time.time() - stream_start
            sleep_time = max(0, stream_interval - elapsed)
            if sleep_time > 0:
                time.sleep(sleep_time)
            continue

        ret, jpeg = cv2.imencode('.jpg', frame, encode_params)
        if not ret:
            continue

        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + jpeg.tobytes() + b'\r\n')

        elapsed = time.time() - stream_start
        sleep_time = max(0, stream_interval - elapsed)
        if sleep_time > 0:
            time.sleep(sleep_time)

# Rute Flask

# --- Rate limiting simplu pentru /login (fără dependențe externe) ---
_login_attempts = defaultdict(list)  # {ip: [timestamp, ...]}
_LOGIN_MAX_ATTEMPTS = 5
_LOGIN_WINDOW = 60  # secunde


def login_rate_limit(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        ip = request.remote_addr or 'unknown'
        now = time.time()
        # Curățăm încercările expirate
        _login_attempts[ip] = [t for t in _login_attempts[ip] if now - t < _LOGIN_WINDOW]
        if len(_login_attempts[ip]) >= _LOGIN_MAX_ATTEMPTS:
            return render_template('login.html',
                                   error="Prea multe încercări. Încearcă din nou peste un minut."), 429
        _login_attempts[ip].append(now)
        return f(*args, **kwargs)
    return decorated


@app.route('/login', methods=['GET', 'POST'])
@login_rate_limit
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = get_user_by_username(username)
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            if user.must_change_password:
                return redirect(url_for('change_password'))
            return redirect(url_for('index'))
        return render_template('login.html', error="Usuario o contraseña incorrectos")
    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))


@app.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    if request.method == 'POST':
        current = request.form.get('current_password', '')
        new_pw = request.form.get('new_password', '')
        confirm = request.form.get('confirm_password', '')
        if not current or not new_pw or not confirm:
            return render_template('change_password.html',
                                   error="Toate câmpurile sunt obligatorii")
        if not check_password_hash(current_user.password_hash, current):
            return render_template('change_password.html',
                                   error="Parola curentă este incorectă")
        if len(new_pw) < 8:
            return render_template('change_password.html',
                                   error="Parola nouă trebuie să aibă minim 8 caractere")
        if new_pw != confirm:
            return render_template('change_password.html',
                                   error="Parolele nu coincid")
        if change_password(current_user.id, new_pw):
            return render_template('change_password.html',
                                   success="Parolă schimbată cu succes!")
        return render_template('change_password.html',
                               error="Eroare la salvarea parolei")
    return render_template('change_password.html')


@app.route('/')
@login_required
def index():
    return render_template('index.html',
                           cameras=camera_manager.get_all_cameras_info())


@app.route('/video_feed/<int:cam_id>')
@login_required
def video_feed(cam_id):
    camera = camera_manager.get_camera(cam_id)
    if camera is None:
        return "Cámara no disponible", 404
    return Response(gen(cam_id),
                    mimetype='multipart/x-mixed-replace; boundary=frame')



@app.route('/api/stats')
@login_required
def get_stats():
    """Stats agregate (toate camerele)."""
    cameras_info = camera_manager.get_all_cameras_info()
    total_persons = 0
    total_violations = 0

    with state_lock:
        for cam_id, state in cameras_state.items():
            total_persons += state['stats'].get('total_persons', 0)
            total_violations += state['stats'].get('violations', 0)

    return jsonify({
        'total_persons': total_persons,
        'violations': total_violations,
        'cameras': cameras_info,
        'recent_incidents': get_recent_incidents(10)
    })


@app.route('/api/camera/<int:cam_id>/stats')
@login_required
def get_camera_stats(cam_id):
    """Stats pentru o cameră specifică."""
    with state_lock:
        cam_state = cameras_state.get(cam_id)
        if cam_state is None:
            return jsonify({'error': 'Camera not found'}), 404
        stats = cam_state['stats'].copy()
    return jsonify({
        'stats': stats,
        'recent_incidents': get_recent_incidents(10, camera_id=cam_id)
    })



@app.route('/api/cameras')
@login_required
def list_cameras():
    """Lista toate camerele cu status."""
    return jsonify({'cameras': camera_manager.get_all_cameras_info()})


@app.route('/api/camera/add', methods=['POST'])
@login_required
def add_camera():
    """Adaugă o cameră nouă la runtime."""
    data = request.json
    name = data.get('name', f'Camera nouă')
    url = data.get('url')

    if not url:
        return jsonify({'error': 'URL necesar'}), 400

    cam_id, camera = camera_manager.add_camera(name=name, url=url)
    if cam_id:
        start_detection_thread(cam_id)
        return jsonify({
            'status': 'ok',
            'camera_id': cam_id,
            'info': camera_manager.get_all_cameras_info()
        })
    return jsonify({'error': 'Eroare adăugare cameră'}), 500


@app.route('/api/camera/<int:cam_id>/toggle', methods=['POST'])
@login_required
def toggle_camera(cam_id):
    """Activează/dezactivează o cameră."""
    new_state = camera_manager.toggle_camera(cam_id)
    if new_state is None:
        return jsonify({'error': 'Camera nu există'}), 404

    if new_state:
        # Reactivată — pornim thread detecție
        if cam_id not in _detection_threads or not _detection_threads[cam_id].is_alive():
            _detection_threads[cam_id] = start_detection_thread(cam_id)
    else:
        # Dezactivată — oprim thread
        if cam_id in cameras_state:
            with state_lock:
                cameras_state[cam_id]['monitoring'] = False

    return jsonify({'status': 'ok', 'enabled': new_state})


@app.route('/api/camera/<int:cam_id>/remove', methods=['POST'])
@login_required
def remove_camera(cam_id):
    """Șterge o cameră."""
    camera_manager.remove_camera(cam_id)
    detector.remove_tracker(cam_id)
    with state_lock:
        cameras_state.pop(cam_id, None)
    return jsonify({'status': 'ok'})


@app.route('/api/camera/<int:cam_id>/monitor', methods=['POST'])
@login_required
def toggle_monitor_camera(cam_id):
    """Pauză/reluare monitorizare pentru o cameră."""
    data = request.json
    action = data.get('action')
    with state_lock:
        if cam_id in cameras_state:
            cameras_state[cam_id]['monitoring'] = (action == 'start')
            return jsonify({'status': 'ok',
                            'monitoring': cameras_state[cam_id]['monitoring']})
    return jsonify({'error': 'Camera nu există'}), 404


# Health check (pentru systemd / monitoring extern)

_START_TIME = time.time()


@app.route('/health')
def health():
    """Endpoint public pentru health check — nu necesită autentificare."""
    uptime = round(time.time() - _START_TIME, 1)
    info = {
        'status': 'ok',
        'uptime_seconds': uptime,
        'active_cameras': camera_manager.active_count,
        'total_cameras': camera_manager.total_count,
        'max_cameras': hw['max_cameras'],
        'hardware': hw['name'],
        'model': model_to_use
    }
    # Adaugă info memorie dacă psutil e disponibil
    try:
        import psutil
        mem = psutil.virtual_memory()
        info['memory_percent'] = mem.percent
        info['memory_used_gb'] = round(mem.used / (1024**3), 1)
        info['cpu_percent'] = psutil.cpu_percent(interval=0.1)
    except ImportError:
        pass
    return jsonify(info)


# GDPR endpoints + Auto-delete capturi

CAPTURE_RETENTION_DAYS = 30


@app.route('/api/gdpr/delete-captures', methods=['POST'])
@login_required
def gdpr_delete_captures():
    """Șterge capturi și log-uri dintr-un interval de date."""
    from_date = request.json.get('from_date')
    to_date = request.json.get('to_date')
    if not from_date or not to_date:
        return jsonify({'error': 'from_date și to_date sunt obligatorii'}), 400
    deleted = delete_violations_by_date(from_date, to_date)
    # Șterge și fișierele imagine din interval
    import glob
    base_dir = os.path.dirname(os.path.abspath(__file__))
    capture_dir = os.path.join(base_dir, 'static/captures')
    removed_files = 0
    if os.path.isdir(capture_dir):
        for f in glob.glob(os.path.join(capture_dir, '*.jpg')):
            mtime = os.path.getmtime(f)
            from_ts = time.mktime(time.strptime(from_date, '%Y-%m-%d'))
            to_ts = time.mktime(time.strptime(to_date, '%Y-%m-%d')) + 86400
            if from_ts <= mtime <= to_ts:
                os.remove(f)
                removed_files += 1
    return jsonify({'deleted_logs': deleted, 'deleted_files': removed_files})


@app.route('/api/gdpr/delete-person', methods=['POST'])
@login_required
def gdpr_delete_person():
    """Șterge toate abaterile pentru un person_hash specific."""
    person_hash = request.json.get('person_hash')
    if not person_hash:
        return jsonify({'error': 'person_hash este obligatoriu'}), 400
    deleted = delete_violations_by_hash(person_hash)
    return jsonify({'deleted': deleted})


def _auto_delete_old_captures():
    """Șterge capturi mai vechi de CAPTURE_RETENTION_DAYS. Rulează o dată pe zi."""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    capture_dir = os.path.join(base_dir, 'static/captures')
    if not os.path.isdir(capture_dir):
        return
    cutoff = time.time() - (CAPTURE_RETENTION_DAYS * 86400)
    removed = 0
    for f in os.listdir(capture_dir):
        if not f.endswith('.jpg'):
            continue
        filepath = os.path.join(capture_dir, f)
        if os.path.getmtime(filepath) < cutoff:
            os.remove(filepath)
            removed += 1
    if removed > 0:
        print(f"🗑️ Auto-delete: {removed} capturi mai vechi de {CAPTURE_RETENTION_DAYS} zile șterse.")


def _auto_delete_thread():
    """Background thread pentru ștergerea automată a capturilor."""
    while True:
        _auto_delete_old_captures()
        time.sleep(86400)  # verifică o dată pe zi


# Export rapoarte + Statistici istorice
import csv
import io as _io

@app.route('/api/report')
@login_required
def export_report():
    """Export incidente ca CSV sau JSON."""
    from database import get_recent_incidents
    fmt = request.args.get('format', 'json')
    limit = int(request.args.get('limit', 1000))
    incidents = get_recent_incidents(limit=limit)
    if fmt == 'csv':
        output = _io.StringIO()
        writer = csv.DictWriter(output, fieldnames=['id', 'timestamp', 'type', 'image_path', 'details', 'camera_id'])
        writer.writeheader()
        writer.writerows(incidents)
        return Response(output.getvalue(), mimetype='text/csv',
                        headers={'Content-Disposition': 'attachment; filename=safeguard_report.csv'})
    return jsonify(incidents)


@app.route('/api/stats/violations')
@login_required
def violation_stats():
    """Statistici abateri pentru dashboard (ultimele N zile)."""
    from database import get_violation_stats
    days = int(request.args.get('days', 7))
    return jsonify(get_violation_stats(days=days))


# WebSocket events

@socketio.on('connect', namespace='/monitor')
def ws_connect():
    if current_user.is_authenticated:
        # Trimite stats curente imediat
        cameras_info = camera_manager.get_all_cameras_info()
        emit('stats_update', {
            'total_persons': 0,
            'violations': 0,
            'alerts': [],
            'cameras': cameras_info,
            'recent_incidents': get_recent_incidents(10)
        })
    else:
        emit('error', {'message': 'Neautorizat'})
        return False


@socketio.on('disconnect', namespace='/monitor')
def ws_disconnect():
    pass


if __name__ == '__main__':
    base_dir = os.path.dirname(os.path.abspath(__file__))
    save_dir = os.path.join(base_dir, 'static/captures')
    if not os.path.exists(save_dir):
        os.makedirs(save_dir, exist_ok=True)

    # Pornire thread auto-delete capturi
    t = threading.Thread(target=_auto_delete_thread, daemon=True)
    t.start()

    # Banner de pornire cu profilul hardware detectat
    print("=" * 60)
    print("  Safeguard Vision - Multi-Cameră")
    print("=" * 60)
    print(f"🖥️  Hardware: {hw['name']}")
    print(f"⚡  Target: {hw['target_total_fps']} FPS total | "
          f"imgsz: {hw['imgsz']} | INT8: {'da' if hw['supports_int8'] else 'nu'}")
    print(f"📹 Limită camere: {camera_manager.active_count}/{hw['max_cameras']} active "
          f"({camera_manager.total_count} configurate)")
    print(f"📊 Model: {model_to_use}")
    print(f"🎯 FPS per cameră: {detector.get_fps_per_camera(camera_manager.active_count)}")
    print(f"🔌 WebSocket: activat")
    print(f"🔒 GDPR: auto-delete capturi > {CAPTURE_RETENTION_DAYS} zile")
    print("=" * 60)

    socketio.run(app, host='0.0.0.0', port=5000,
                 debug=False, allow_unsafe_werkzeug=True)
