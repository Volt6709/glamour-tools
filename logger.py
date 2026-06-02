import logging
import os
from logging.handlers import RotatingFileHandler

LOG_PATH = os.path.join(os.path.dirname(__file__), 'glamour_tools.log')

logger = logging.getLogger('glamour_tools')
logger.setLevel(logging.INFO)

if not logger.handlers:
    handler = RotatingFileHandler(LOG_PATH, maxBytes=1_000_000, backupCount=3)
    handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))
    logger.addHandler(handler)


def log_api_call(method, url, status_code, intuit_tid=None, error=None):
    msg = f"{method} {url} → {status_code}"
    if intuit_tid:
        msg += f" | intuit_tid={intuit_tid}"
    if error:
        msg += f" | ERROR: {error}"
        logger.error(msg)
    else:
        logger.info(msg)


def log_error(context, error):
    logger.error(f"[{context}] {error}")


def log_info(msg):
    logger.info(msg)
