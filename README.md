# Safeguard Vision

**Safeguard Vision** es un sistema de monitoreo de seguridad industrial basado en visión artificial. Utiliza **YOLOv8** para detectar personas y validar el uso correcto de Equipos de Protección Individual (EPIs), específicamente **cascos** y **chalecos**.

## Características

- **Detección en Tiempo Real**: Identifica personas y verifica el uso de casco y chaleco.
- **Zona Peligrosa**: Define áreas virtuales donde la presencia de personas genera alertas.
- **Sistema de Alertas**:
  - Alertas visuales con bounding boxes (Rojo = Peligro, Verde = Seguro).
  - Registro de incidentes en base de datos.
  - Captura automática de imágenes de infracciones (con intervalo de 30s).
- **Dashboard Web Moderno**:
  - Transmisión de video en vivo con baja latencia.
  - Panel de control con botón **START/STOP** para el monitoreo.
  - Estadísticas en tiempo real y contador de FPS.
  - Historial de alertas con acceso a capturas de pantalla.
- **Seguridad**:
  - Sistema de login protegido.
  - Usuarios y contraseñas gestionados en base de datos.

## Instalación

1. **Clonar/Descargar** el proyecto.
2. Crear un entorno virtual (recomendado):
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```
3. Instalar dependencias:
   ```bash
   pip install -r requirements.txt
   ```

## Uso

1. **Iniciar la aplicación**:
   ```bash
   python app.py
   ```
2. **Acceder al Dashboard**:
   - Abre tu navegador en `http://localhost:5000`.
   - **Usuario**: `admin`
   - **Contraseña**: `admin123`

## Acceso Remoto (Opcional)

Para ver la cámara desde fuera de la red local (ej. celular):

1. Instalar `pyngrok` (ya incluido en requirements).
2. Configurar tu token de ngrok (regístrate en ngrok.com):
   ```bash
   ngrok config add-authtoken <TU_TOKEN>
   ```
3. Ejecutar el script stick de túnel:
   ```bash
   python ngrok_tunnel.py
   ```
   Esto mostrará una URL pública (ej. `https://xyz.ngrok-free.app`) para acceder.

## Estructura del Proyecto

- `app.py`: Servidor web Flask y lógica principal.
- `detector.py`: Lógica de visión artificial (YOLO + Heurística de Color).
- `camera.py`: Gestión de la cámara y fallback a video sintético.
- `database.py`: Gestión de base de datos SQLite (Usuarios e Incidentes).
- `templates/`: Archivos HTML.
- `static/`: Estilos CSS y capturas de pantalla (`captures/`).

## Créditos

Desarrollado para mejorar la seguridad en entornos industriales mediante IA accesible.
