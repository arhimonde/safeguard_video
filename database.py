import sqlite3
import os
from datetime import datetime
from werkzeug.security import generate_password_hash
from flask_login import UserMixin

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'safeguard.db')


class User(UserMixin):
    def __init__(self, id, username, password_hash, must_change_password=False):
        self.id = id
        self.username = username
        self.password_hash = password_hash
        self.must_change_password = must_change_password


def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Tabelă Incidente (cu camera_id pentru multi-cameră)
    c.execute('''
        CREATE TABLE IF NOT EXISTS incidents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            type TEXT NOT NULL,
            image_path TEXT,
            details TEXT,
            camera_id INTEGER DEFAULT NULL
        )
    ''')

    # Adaugă coloana camera_id dacă nu există (migration)
    try:
        c.execute("ALTER TABLE incidents ADD COLUMN camera_id INTEGER DEFAULT NULL")
    except sqlite3.OperationalError:
        pass  # Coloana deja există

    # Tabelă Utilizatori
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL
        )
    ''')

    # Adaugă coloana must_change_password dacă nu există (migration)
    try:
        c.execute("ALTER TABLE users ADD COLUMN must_change_password INTEGER DEFAULT 1")
    except sqlite3.OperationalError:
        pass  # Coloana deja există

    conn.commit()
    conn.close()
    print("Bază de date inițializată (Incidente + Utilizatori).")
    create_user("admin", "admin123")


def log_incident(incident_type, image_path, details="", camera_id=None):
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        timestamp = datetime.now().isoformat()
        c.execute(
            'INSERT INTO incidents (timestamp, type, image_path, details, camera_id) '
            'VALUES (?, ?, ?, ?, ?)',
            (timestamp, incident_type, image_path, details, camera_id)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Error log_incident: {e}")


def get_recent_incidents(limit=10, camera_id=None):
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        if camera_id is not None:
            c.execute(
                'SELECT * FROM incidents WHERE camera_id=? ORDER BY id DESC LIMIT ?',
                (camera_id, limit))
        else:
            c.execute('SELECT * FROM incidents ORDER BY id DESC LIMIT ?', (limit,))
        rows = c.fetchall()
        conn.close()

        incidents = []
        for row in rows:
            incidents.append({
                'id': row[0], 'timestamp': row[1], 'type': row[2],
                'image_path': row[3], 'details': row[4],
                'camera_id': row[5] if len(row) > 5 else None
            })
        return incidents
    except Exception as e:
        print(f"Error get_recent_incidents: {e}")
        return []


def create_user(username, password):
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('SELECT id FROM users WHERE username = ?', (username,))
        if c.fetchone():
            conn.close(); return False
        hashed_pw = generate_password_hash(password)
        c.execute('INSERT INTO users (username, password) VALUES (?, ?)',
                  (username, hashed_pw))
        conn.commit(); conn.close()
        print(f"Utilizator '{username}' creat.")
        return True
    except Exception as e:
        print(f"Error create_user: {e}")
        return False


def get_user_by_username(username):
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('SELECT id, username, password, must_change_password FROM users WHERE username=?', (username,))
        row = c.fetchone()
        conn.close()
        if row:
            mcp = bool(row[3]) if len(row) > 3 and row[3] is not None else False
            return User(id=row[0], username=row[1], password_hash=row[2], must_change_password=mcp)
        return None
    except Exception as e:
        print(f"Error get_user_by_username: {e}")
        return None


def get_user_by_id(user_id):
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('SELECT id, username, password, must_change_password FROM users WHERE id=?', (user_id,))
        row = c.fetchone()
        conn.close()
        if row:
            mcp = bool(row[3]) if len(row) > 3 and row[3] is not None else False
            return User(id=row[0], username=row[1], password_hash=row[2], must_change_password=mcp)
        return None
    except Exception as e:
        print(f"Error get_user_by_id: {e}")
        return None


def change_password(user_id, new_password):
    """Schimbă parola și marchează must_change_password=False."""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        hashed = generate_password_hash(new_password)
        c.execute('UPDATE users SET password=?, must_change_password=0 WHERE id=?',
                  (hashed, user_id))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"Error change_password: {e}")
        return False
