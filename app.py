# --- ACCESO REMOTE (OPCIONAL) ---
# Pentru a accesa acest server de oriunde:
# 1. Pornește tunelul: python3 loophole_tunnel.py
# 2. Folosește URL-ul .loophole.site generat.
# --------------------------------
from flask import Flask, render_template, Response, jsonify, request, redirect, url_for
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from camera import VideoCamera
from detector import ObjectDetector
from database import init_db, get_recent_incidents, get_user_by_username, get_user_by_id, create_user
from werkzeug.security import check_password_hash
import cv2
import threading
import time
import os

# Flask es el framework web que utilizamos para servir la página y la API.
app = Flask(__name__)
app.secret_key = os.urandom(24)

# Flask-Login maneja la sesión de usuario.
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    return get_user_by_id(user_id)

# Crea las tablas si no existen y asegura que haya un usuario admin.
init_db()

# Inicializar cámara
camera_source = 0
try:
    camera = VideoCamera(camera_source)
except Exception as e:
    print(f"Error al inicializar la cámara: {e}")
    camera = None

# Cargar detector YOLO (Turbo Mode para presentación)
# Preferimos .engine si existe, altfel folosim .pt
model_to_use = 'yolov8n.engine' if os.path.exists('yolov8n.engine') else 'yolov8n.pt'
detector = ObjectDetector(model_path=model_to_use, imgsz=416, half=True)

# Estado compartido entre hilos
current_stats = {
    'total_persons': 0,
    'violations': 0,
    'alerts': []
}
monitoring_active = True

# --- HILO DEDICADO PARA DETECCIÓN YOLO ---
# El frame anotado se almacena aquí, separado de la captura de cámara.
annotated_frame_lock = threading.Lock()
latest_annotated_frame = None
detection_stats_lock = threading.Lock()

def detection_thread_fn():
    """
    Hilo independiente que ejecuta inferencia YOLO continuamente.
    Esto desacopla la detección del streaming, permitiendo 60fps en el video
    aunque el modelo vaya más lento.
    """
    global latest_annotated_frame, current_stats, monitoring_active
    while True:
        if camera is None:
            time.sleep(0.1)
            continue

        frame = camera.get_frame()
        if frame is None:
            time.sleep(0.01)
            continue

        if monitoring_active:
            try:
                result_frame, stats = detector.detect(frame)
            except Exception:
                result_frame = frame.copy()
                stats = current_stats
        else:
            result_frame = frame.copy()
            cv2.putText(result_frame, "SISTEMA PAUSADO", (50, 240),
                        cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 165, 255), 2)
            stats = current_stats

        with annotated_frame_lock:
            latest_annotated_frame = result_frame
        with detection_stats_lock:
            current_stats = stats

# Iniciar hilo de detección dedicado
det_thread = threading.Thread(target=detection_thread_fn, daemon=True)
det_thread.start()

# --- GENERADOR DE STREAMING MJPEG (REMOTE OPTIMIZED) ---
JPEG_QUALITY = 50  # Optimizado para internet (menos lag)

encode_params = [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY]

def gen(camera):
    """
    Genera frames MJPEG a máxima velocidad sin limitadores (FPS infinito).
    No bloquea esperando YOLO; usa el último frame anotado disponible.
    """
    global latest_annotated_frame

    while True:
        # Limitamos a ~20FPS para que el túnel de internet no se sature
        time.sleep(0.05)
        with annotated_frame_lock:
            frame = latest_annotated_frame

        if frame is None:
            # Aún no hay frame del detector, usar directo de cámara
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
    db_incidents = get_recent_incidents(5)
    with detection_stats_lock:
        stats = current_stats.copy()
    return jsonify({
        'total_persons': stats['total_persons'],
        'violations': stats['violations'],
        'alerts': stats['alerts'],
        'recent_incidents': db_incidents
    })


if __name__ == '__main__':
    base_dir = os.path.dirname(os.path.abspath(__file__))
    save_dir = os.path.join(base_dir, 'static/captures')
    if not os.path.exists(save_dir):
        os.makedirs(save_dir, exist_ok=True)

    print("Iniciando servidor Safeguard Vision...")
    app.run(host='0.0.0.0', port=5000, debug=True, use_reloader=False)
