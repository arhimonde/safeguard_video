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

# Inicialización de la aplicación Flask
# Flask es el framework web que utilizamos para servir la página y la API.
app = Flask(__name__)
app.secret_key = 'super_secret_key_for_demo' # Cambiar esto en producción por una clave segura

# Configuración de Flask-Login
# Flask-Login maneja la sesión de usuario (inicio de sesión, cierre de sesión, cookies).
login_manager = LoginManager()
login_manager.init_app(app)
# Define la vista a la que se redirigirá si el usuario no ha iniciado sesión
login_manager.login_view = 'login'

# Cargador de usuario para Flask-Login
# Esta función es llamada por Flask-Login para obtener el objeto usuario a partir del ID almacenado en la sesión.
@login_manager.user_loader
def load_user(user_id):
    return get_user_by_id(user_id)

# Inicializar Base de Datos y Usuario Administrador
# Crea las tablas si no existen y asegura que haya un usuario admin.
init_db()

# Inicializar Cámara y Detector
# Intentamos acceder a la cámara (índice 0).
camera_source = 0 
try:
    camera = VideoCamera(camera_source)
except Exception as e:
    print(f"Error al inicializar la cámara: {e}")
    camera = None

# Inicializamos el detector de objetos (YOLO) con optimizaciones para Jetson
# Para máxima velocidad (60 FPS), usa 'yolov8n.engine' después de ejecutar optimize_for_60fps.sh
# Para balance velocidad/precisión, usa imgsz=416 con el modelo .pt
detector = ObjectDetector(model_path='yolov8n.engine', imgsz=416, half=True)

# Estadísticas actuales globales
# Almacena el estado actual de la detección para compartirlo entre el hilo de la cámara y la API.
current_stats = {
    'total_persons': 0,
    'violations': 0,
    'alerts': []
}

# Variable de control para activar/desactivar el monitoreo (detección)
monitoring_active = True

# Función generadora de cuadros (frames) de video
# Esta función captura cuadros de la cámara, ejecuta la detección (si está activa) y devuelve el cuadro codificado como MJPEG.
def gen(camera):
    global current_stats, monitoring_active
    while True:
        # Si la cámara no se inicializó correctamente, esperamos y reintentamos
        if camera is None:
            time.sleep(1)
            continue
            
        # Obtener un cuadro de la cámara
        frame = camera.get_frame()
        if frame is None:
            time.sleep(0.1)
            continue
        
        # Solo ejecutar la detección si el monitoreo está activo
        if monitoring_active:
            # El detector devuelve el cuadro con cajas dibujadas y las estadísticas
            annotated_frame, stats = detector.detect(frame)
            current_stats = stats
        else:
            # Si el monitoreo está pausado, mostramos el video normal con un mensaje de PAUSA.
            # Esto ahorra recursos de procesamiento del modelo YOLO.
            annotated_frame = frame.copy()
            cv2.putText(annotated_frame, "SISTEMA PAUSADO", (50, 240), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 165, 255), 2)
            
        # Codificar el cuadro a formato JPEG para enviarlo al navegador
        ret, jpeg = cv2.imencode('.jpg', annotated_frame)
        frame_bytes = jpeg.tobytes()
        
        # 'yield' devuelve el cuadro en el formato multipart necesario para el streaming MJPEG
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n\r\n')

# Ruta API para activar/desactivar el monitoreo
# Recibe una solicitud JSON con la acción 'start' o 'stop'.
# Requiere que el usuario haya iniciado sesión.
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

# Rutas de la Aplicación Web

# Ruta de Inicio de Sesión
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        user = get_user_by_username(username)
        # Verificamos si el usuario existe y si la contraseña coincide
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            return redirect(url_for('index'))
        else:
            return render_template('login.html', error="Usuario o contraseña incorrectos")
            
    return render_template('login.html')

# Ruta de Cierre de Sesión
@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

# Ruta Principal (Panel de Control)
@app.route('/')
@login_required
def index():
    return render_template('index.html')

# Ruta de la Transmisión de Video
# Esta ruta es la fuente (src) de la etiqueta <img> en el panel.
@app.route('/video_feed')
@login_required
def video_feed():
    if camera is None:
        return "Cámara no disponible", 503
    return Response(gen(camera),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

# Ruta API para obtener estadísticas en tiempo real
# El frontend llama a esta ruta periódicamente para actualizar los contadores e incidentes.
@app.route('/api/stats')
@login_required
def get_stats():
    # Obtenemos los incidentes más recientes de la base de datos
    db_incidents = get_recent_incidents(5)
    return jsonify({
        'total_persons': current_stats['total_persons'],
        'violations': current_stats['violations'],
        'alerts': current_stats['alerts'], 
        'recent_incidents': db_incidents
    })

# Punto de entrada principal
if __name__ == '__main__':
    # Crear directorio para capturas si no existe (ruta absoluta basada en el script)
    base_dir = os.path.dirname(os.path.abspath(__file__))
    save_dir = os.path.join(base_dir, 'static/captures')
    if not os.path.exists(save_dir):
        os.makedirs(save_dir, exist_ok=True)
        
    # Ejecutar la aplicación en el puerto 5000, accesible desde cualquier IP (0.0.0.0)
    print("Iniciando servidor Safeguard Vision...")
    app.run(host='0.0.0.0', port=5000, debug=True, use_reloader=False)
