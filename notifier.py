"""
Notificări externe: Telegram + Email.
Configurare în config.json (gitignored — conține tokeni/credențiale).

Apelat la severity='critical' și la cameră offline > 10 min.
"""
import json
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage
import urllib.request
import urllib.parse

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.json')

_notifier_config = None


def _load_config():
    global _notifier_config
    if _notifier_config is not None:
        return _notifier_config
    try:
        with open(CONFIG_PATH, 'r') as f:
            _notifier_config = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        _notifier_config = {}
    return _notifier_config


def send_telegram(message, image_path=None):
    """Trimite mesaj (și opțional imagine) pe Telegram."""
    cfg = _load_config()
    token = cfg.get('telegram_bot_token')
    chat_id = cfg.get('telegram_chat_id')
    if not token or not chat_id:
        return False

    try:
        # Trimite mesaj text
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        data = urllib.parse.urlencode({
            'chat_id': chat_id,
            'text': message,
            'parse_mode': 'HTML'
        }).encode()
        urllib.request.urlopen(url, data, timeout=10)

        # Trimite imagine dacă există
        if image_path and os.path.exists(image_path):
            url = f"https://api.telegram.org/bot{token}/sendPhoto"
            with open(image_path, 'rb') as img:
                import mimetypes
                mime = mimetypes.guess_type(image_path)[0] or 'image/jpeg'
                boundary = '----Boundary' + os.urandom(8).hex()
                body = (
                    f'--{boundary}\r\n'
                    f'Content-Disposition: form-data; name="chat_id"\r\n\r\n'
                    f'{chat_id}\r\n'
                    f'--{boundary}\r\n'
                    f'Content-Disposition: form-data; name="photo"; filename="{os.path.basename(image_path)}"\r\n'
                    f'Content-Type: {mime}\r\n\r\n'
                ).encode() + img.read() + f'\r\n--{boundary}--\r\n'.encode()
                req = urllib.request.Request(url, data=body, method='POST')
                req.add_header('Content-Type', f'multipart/form-data; boundary={boundary}')
                urllib.request.urlopen(req, timeout=15)
        return True
    except Exception as e:
        print(f"[Notifier] Telegram error: {e}")
        return False


def send_email(subject, body, image_path=None):
    """Trimite email (și opțional imagine atașată)."""
    cfg = _load_config()
    smtp_host = cfg.get('smtp_host')
    smtp_port = cfg.get('smtp_port', 587)
    smtp_user = cfg.get('smtp_user')
    smtp_pass = cfg.get('smtp_pass')
    alert_email = cfg.get('alert_email')
    if not all([smtp_host, smtp_user, smtp_pass, alert_email]):
        return False

    try:
        msg = MIMEMultipart()
        msg['From'] = smtp_user
        msg['To'] = alert_email
        msg['Subject'] = f"[Safeguard Vision] {subject}"
        msg.attach(MIMEText(body, 'plain', 'utf-8'))

        if image_path and os.path.exists(image_path):
            with open(image_path, 'rb') as img:
                msg_img = MIMEImage(img.read())
                msg_img.add_header('Content-Disposition', 'attachment',
                                   filename=os.path.basename(image_path))
                msg.attach(msg_img)

        with smtplib.SMTP(smtp_host, smtp_port, timeout=15) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.send_message(msg)
        return True
    except Exception as e:
        print(f"[Notifier] Email error: {e}")
        return False


def send_alert(title, message, image_path=None, severity='warning'):
    """
    Trimite alertă pe toate canalele configurate.
    severity: 'warning', 'danger', 'critical'
    Doar 'critical' trimite notificări externe (evită spam).
    """
    if severity != 'critical':
        return  # Doar critic trimite extern

    full_msg = f"🚨 SAFEGUARD VISION\n\n📊 Severidad: {severity.upper()}\n📍 {title}\n\n{message}"
    send_telegram(full_msg, image_path)
    send_email(title, message, image_path)
