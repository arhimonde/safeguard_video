"""
Logging structurat cu rotare fișiere.
Înlocuiește print() cu logger.info/warning/error.

Fișiere:
  logs/safeguard.log      — fișier curent (max 5MB)
  logs/safeguard.log.1    — rotație 1
  logs/safeguard.log.2    — rotație 2
"""
import logging
import os
from logging.handlers import RotatingFileHandler

LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
os.makedirs(LOG_DIR, exist_ok=True)
LOG_PATH = os.path.join(LOG_DIR, 'safeguard.log')

_FORMAT = '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
_DATEFMT = '%Y-%m-%d %H:%M:%S'

# Configurare root logger
_handler = RotatingFileHandler(
    LOG_PATH, maxBytes=5*1024*1024, backupCount=3, encoding='utf-8')
_handler.setFormatter(logging.Formatter(_FORMAT, _DATEFMT))

# Păstrăm și output pe consolă pentru depanare
_console = logging.StreamHandler()
_console.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s', _DATEFMT))

_root = logging.getLogger()
_root.setLevel(logging.INFO)
_root.addHandler(_handler)
_root.addHandler(_console)


def get_logger(name='safeguard'):
    """Returnează un logger cu numele modulului."""
    return logging.getLogger(name)
