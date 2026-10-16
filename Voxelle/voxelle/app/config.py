import os
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return default


TZ = ZoneInfo(os.getenv("APP_TZ", "Asia/Kolkata"))

DATA_DIR = Path(os.getenv("DATA_DIR", BASE_DIR / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = Path(os.getenv("DB_PATH", DATA_DIR / "voxelle.db"))
TTS_CACHE_DIR = DATA_DIR / "tts_cache"
TTS_CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Gnani (Vachana) APIs
GNANI_API_KEY = os.getenv("GNANI_API_KEY", "").strip()
STT_URL = "https://api.vachana.ai/stt/v3"
TTS_URL = "https://api.vachana.ai/api/v1/tts/inference"
STT_LANGUAGE = os.getenv("STT_LANGUAGE", "hi-IN")
TTS_MODEL = os.getenv("TTS_MODEL", "timbre-v2.5")
TTS_VOICE = os.getenv("TTS_VOICE", "Poorvi")
TTS_LANGUAGE = os.getenv("TTS_LANGUAGE", "hi-en")
try:
    TTS_SPEED = float(os.getenv("TTS_SPEED", "0.95"))
except ValueError:
    TTS_SPEED = 0.95

# Web push
VAPID_PUBLIC_KEY = os.getenv("VAPID_PUBLIC_KEY", "").strip()
_vapid_file = os.getenv("VAPID_PRIVATE_KEY_FILE", "data/vapid_private.pem")
VAPID_PRIVATE_KEY_FILE = Path(_vapid_file) if Path(_vapid_file).is_absolute() else BASE_DIR / _vapid_file
VAPID_SUBJECT = os.getenv("VAPID_SUBJECT", "mailto:you@example.com")

# On hosts without a persistent disk, the private key can be passed as an environment variable.
_pem = os.getenv("VAPID_PRIVATE_KEY_PEM", "").replace("\\n", "\n").strip()
if _pem and not VAPID_PRIVATE_KEY_FILE.exists():
    VAPID_PRIVATE_KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
    VAPID_PRIVATE_KEY_FILE.write_text(_pem + "\n")

# Reminder timing
REMIND_EVERY_MIN = _int("REMIND_EVERY_MIN", 10)
MAX_REMINDERS = _int("MAX_REMINDERS", 3)
MISSED_AFTER_MIN = _int("MISSED_AFTER_MIN", 30)
DUE_WINDOW_MIN = _int("DUE_WINDOW_MIN", 90)
SCHEDULER_TICK_SEC = _int("SCHEDULER_TICK_SEC", 15)

STATIC_DIR = BASE_DIR / "static"
