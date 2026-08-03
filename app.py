# --- ACCES REMOT (OPȚIONAL) ---
# Pentru a accesa serverul de oriunde:
# 1. Pornește tunelul: python3 loophole_tunnel.py
# 2. Folosește URL-ul .loophole.site generat.
# --------------------------------
from flask import Flask, render_template, Response, jsonify, request, redirect, url_for
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from flask_socketio import SocketIO, emit
from camera import VideoCamera
from detector import ObjectDetector
from database import init_db, get_recent_incidents, get_user_by_username, get_user_by_id, create_user
from werkzeug.security import check_password_hash
import cv2
import threading
import time
import os

app = Flask(__name__)
app.secret_key = os.urandom(24)

# WebSocket suport — înlocuiește AJAX polling cu push în timp real
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# Sesiuni utilizator
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    return get_user_by_id(user_id)

# Inițializare bază de date + utilizator admin
init_db()

# =============================================================================
# Inițializare cameră
# =============================================================================
camera_source = 0
try:
    camera = VideoCamera(camera_source)
except Exception as e:
    print(f"Eroare inițializare cameră: {e}")
    camera = None

# =============================================================================
# Inițializare detector YOLO11n
# Preferim .engine (TensorRT) dacă există, altfel .pt (PyTorch)
# =============================================================================
model_to_use = 'yolo11n.engine' if os.path.exists('yolo11n.engine') else 'yolo11n.pt'
detector = ObjectDetector(model_path=model_to_use, imgsz=640, half=True)

# =============================================================================
# Configurare detecție
# =============================================================================
TARGET_DETECT_FPS = 18       # FPS target pentru inferență
FRAME_SKIP = 2               # Procesăm fiecare al N-lea frame

# =============================================================================
# Stare partajată între thread-uri
# =============================================================================
current_stats = {
    'total_persons': 0,
    'violations': 0,
    'alerts': []
}
monitoring_active = True

annotated_frame_lock = threading.Lock()
latest_annotated_frame = None
detection_stats_lock = threading.Lock()

# =============================================================================
# WebSocket: trimite stats automat la fiecare detecție (fără polling)
# =============================================================================
_ws_broadcast_interval = 1.0  # broadcast la maxim 1x/sec
_last_ws_broadcast = 0

def broadcast_stats(stats):
    """Trimite stats prin WebSocket către toți clienții conectați."""
    global _last_ws_broadcast
    now = time.time()
    if now - _last_ws_broadcast < _ws_broadcast_interval:
        return
    _last_ws_broadcast = now
    db_incidents = get_recent_incidents(5)
    socketio.emit('stats_update', {
        'total_persons': stats['total_persons'],
        'violations': stats['violations'],
        'alerts': stats['alerts'],
        'recent_incidents': db_incidents
    }, namespace='/monitor', room=None)


# =============================================================================
# Thread dedicat detecție YOLO11n — frame decimation + FPS stabilizat
# =============================================================================
def detection_thread_fn():
    """
    Thread independent cu inferență YOLO11n + PPE.
    - Frame decimation: procesează fiecare al N-lea frame
    - FPS stabilizat: sleep calculat precis
    - WebSocket broadcast: stats trimise automat (nu polling)
    """
    global latest_annotated_frame, current_stats, monitoring_active

    frame_interval = 1.0 / TARGET_DETECT_FPS
    frame_counter = 0

    while True:
        loop_start = time.time()

        if camera is None:
            time.sleep(0.1)
            continue

        frame = camera.get_frame()
        if frame is None:
            time.sleep(0.01)
            continue

        frame_counter += 1

        # Frame decimation
        if frame_counter % FRAME_SKIP != 0:
            elapsed = time.time() - loop_start
            sleep_time = max(0, frame_interval - elapsed)
            time.sleep(sleep_time)
            continue

        # Inferență
        if monitoring_active:
            try:
                result_frame, stats = detector.detect(frame)
            except Exception as e:
                print(f"Eroare detecție: {e}")
                result_frame = frame.copy()
                stats = current_stats.copy()
        else:
            result_frame = frame.copy()
            cv2.putText(result_frame, "SISTEMA PAUSADO", (50, 240),
                        cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 165, 255), 2)
            stats = {'total_persons': 0, 'violations': 0, 'alerts': []}

        # Update stare partajată
        with annotated_frame_lock:
            latest_annotated_frame = result_frame
        with detection_stats_lock:
            current_stats = stats

        # Broadcast stats via WebSocket
        broadcast_stats(stats)

        # FPS stabilizat
        elapsed = time.time() - loop_start
        sleep_time = max(0, frame_interval - elapsed)
        if sleep_time > 0:
            time.sleep(sleep_time)

# Pornire thread detecție
det_thread = threading.Thread(target=detection_thread_fn, daemon=True)
det_thread.start()

# =============================================================================
# Streaming MJPEG (optimizat)
# =============================================================================
JPEG_QUALITY = 50
STREAM_TARGET_FPS = 15  # Redus de la 20 → lățime de bandă mai mică

encode_params = [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY]

def gen(camera):
    """
    Generator MJPEG la FPS constant.
    Folosește ultimul frame annotat — nu așteaptă YOLO.
    """
    global latest_annotated_frame
    stream_interval = 1.0 / STREAM_TARGET_FPS

    while True:
        stream_start = time.time()

        with annotated_frame_lock:
            frame = latest_annotated_frame

        if frame is None:
            if camera is not None:
                frame = camera.get_frame()
            if frame is None:
                time.sleep(0.01)
                continue

        ret, jpeg = cv2.imencode('.jpg', frame, encode_params)
        if not ret:
            continue

        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + jpeg.tobytes() + b'\r\n')

        # FPS stabilizat
        elapsed = time.time() - stream_start
        sleep_time = max(0, stream_interval - elapsed)
        if sleep_time > 0:
            time.sleep(sleep_time)

# =============================================================================
# Rute Flask
# =============================================================================

@app.route('/api/toggle_monitor', methods=['POST'])
@login_required
def toggle_monitor():
    global monitoring_active
    data = request.json
    action = data.get('action')

    if action == 'start':
        monitoring_active = True
    elif action == 'stop':
        monitoring_active = False

    return jsonify({'status': 'ok', 'active': monitoring_active})


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        user = get_user_by_username(username)
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            return redirect(url_for('index'))
        else:
            return render_template('login.html', error="Usuario o contraseña incorrectos")

    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))


@app.route('/')
@login_required
def index():
    return render_template('index.html')


@app.route('/video_feed')
@login_required
def video_feed():
    if camera is None:
        return "Cámara no disponible", 503
    return Response(gen(camera),
                    mimetype='multipart/x-mixed-replace; boundary=frame')


@app.route('/api/stats')
@login_required
def get_stats():
    """Fallback HTTP endpoint — WebSocket e principalul canal."""
    db_incidents = get_recent_incidents(5)
    with detection_stats_lock:
        stats = current_stats.copy()
    return jsonify({
        'total_persons': stats['total_persons'],
        'violations': stats['violations'],
        'alerts': stats['alerts'],
        'recent_incidents': db_incidents
    })


# =============================================================================
# WebSocket events
# =============================================================================

@socketio.on('connect', namespace='/monitor')
def ws_connect():
    """Client conectat — trimitem stats curente imediat."""
    if current_user.is_authenticated:
        with detection_stats_lock:
            stats = current_stats.copy()
        db_incidents = get_recent_incidents(5)
        emit('stats_update', {
            'total_persons': stats['total_persons'],
            'violations': stats['violations'],
            'alerts': stats['alerts'],
            'recent_incidents': db_incidents
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

    print("Pornire server Safeguard Vision...")
    print(f"Model: {model_to_use}")
    print(f"PPE Model: {'yolo11n_ppe' if detector.ppe_model else 'HSV fallback'}")
    print(f"Target detecție: {TARGET_DETECT_FPS} FPS (fiecare al {FRAME_SKIP}-lea frame)")
    print(f"Streaming: {STREAM_TARGET_FPS} FPS, JPEG quality: {JPEG_QUALITY}")
    print(f"WebSocket: activat (push stats în timp real)")

    # Folosim socketio.run în loc de app.run pentru WebSocket
    socketio.run(app, host='0.0.0.0', port=5000, debug=False, allow_unsafe_werkzeug=True)
