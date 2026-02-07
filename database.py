import sqlite3
import os
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin

# Configuración de Rutas de Base de Datos
# Usamos una ruta absoluta para asegurar que la base de datos se ubique correctamente.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'safeguard.db')

# Clase Usuario
# Implementa UserMixin para compatibilidad con Flask-Login (gestión de sesiones).
class User(UserMixin):
    def __init__(self, id, username, password_hash):
        self.id = id
        self.username = username
        self.password_hash = password_hash

# Inicialización de la Base de Datos
# Crea las tablas necesarias (incidentes y usuarios) si no existen.
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Tabla de Incidentes
    # Almacena el registro de violaciones de seguridad detectadas.
    c.execute('''
        CREATE TABLE IF NOT EXISTS incidents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            type TEXT NOT NULL,     -- Tipo de incidente (ej. "Sin Casco")
            image_path TEXT,        -- Ruta a la captura de pantalla
            details TEXT
        )
    ''')
    
    # Tabla de Usuarios
    # Almacena credenciales de acceso para el sistema.
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL  -- Hash de la contraseña
        )
    ''')
    
    conn.commit()
    conn.close()
    print("Base de datos inicializada (Incidentes y Usuarios).")
    
    # Crear usuario administrador por defecto si no existe
    create_user("admin", "admin123")

# Registrar un Incidente
# Guarda un nuevo registro en la tabla 'incidents'.
def log_incident(incident_type, image_path, details=""):
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        timestamp = datetime.now().isoformat()
        c.execute('INSERT INTO incidents (timestamp, type, image_path, details) VALUES (?, ?, ?, ?)',
                  (timestamp, incident_type, image_path, details))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Error al registrar incidente: {e}")

# Obtener Incidentes Recientes
# Recupera los últimos 'limit' incidentes para mostrar en el panel.
def get_recent_incidents(limit=10):
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('SELECT * FROM incidents ORDER BY id DESC LIMIT ?', (limit,))
        rows = c.fetchall()
        conn.close()
        
        incidents = []
        for row in rows:
            incidents.append({
                'id': row[0],
                'timestamp': row[1],
                'type': row[2],
                'image_path': row[3],
                'details': row[4]
            })
        return incidents
    except Exception as e:
        print(f"Error al obtener incidentes: {e}")
        return []

# Gestión de Usuarios

# Crear Nuevo Usuario
# Cifra la contraseña antes de guardarla para mayor seguridad.
def create_user(username, password):
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        # Verificar si ya existe el usuario
        c.execute('SELECT id FROM users WHERE username = ?', (username,))
        if c.fetchone():
            conn.close()
            return False 
            
        hashed_pw = generate_password_hash(password)
        c.execute('INSERT INTO users (username, password) VALUES (?, ?)', (username, hashed_pw))
        conn.commit()
        conn.close()
        print(f"Usuario '{username}' creado exitosamente.")
        return True
    except Exception as e:
        print(f"Error al crear usuario: {e}")
        return False

# Obtener Usuario por Nombre
def get_user_by_username(username):
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('SELECT id, username, password FROM users WHERE username = ?', (username,))
        row = c.fetchone()
        conn.close()
        
        if row:
            return User(id=row[0], username=row[1], password_hash=row[2])
        return None
    except Exception as e:
        print(f"Error al obtener usuario: {e}")
        return None

# Obtener Usuario por ID
def get_user_by_id(user_id):
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('SELECT id, username, password FROM users WHERE id = ?', (user_id,))
        row = c.fetchone()
        conn.close()
        
        if row:
            return User(id=row[0], username=row[1], password_hash=row[2])
        return None
    except Exception as e:
        print(f"Error al obtener usuario por id: {e}")
        return None
