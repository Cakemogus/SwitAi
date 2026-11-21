"""
CONFIG.PY — настройки SwitAI
============================
Всё, что можно, берётся из переменных окружения (на хостинге).
Значения по умолчанию = твои старые.
"""

import json
import os
import tempfile

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:  # python-dotenv не обязателен
    pass

# === ТОКЕН ===
BOT_TOKEN = os.getenv("BOT_TOKEN")

# === ПАПКА ДЛЯ ДАННЫХ (history.json, state.json, saved_chats.json) ===
DATA_DIR = os.getenv("DATA_DIR", ".")
os.makedirs(DATA_DIR, exist_ok=True)

# === GROQ (НЕСКОЛЬКО КЛЮЧЕЙ) ===
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
GROQ_API_KEYS = [
    os.getenv("GROQ_API_KEY"),
    os.getenv("GROQ_API_KEY_2"),
    os.getenv("GROQ_API_KEY_3"),
    os.getenv("GROQ_API_KEY_4"),
]
GROQ_API_KEYS = [k for k in GROQ_API_KEYS if k]

# === GEMINI (РЕЗЕРВ + КАРТИНКИ) ===
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
# Название модели вынесено в переменную: если Google её переименует — меняешь на хостинге, код не трогаешь.
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")

# === OLLAMA (ВЕБ-ПОИСК) ===
OLLAMA_API_KEYS = [os.getenv("OLLAMA_API_KEY_1"), os.getenv("OLLAMA_API_KEY_2")]
OLLAMA_API_KEYS = [k for k in OLLAMA_API_KEYS if k]

# === ГЕНЕРАЦИЯ КАРТИНОК ===
HF_TOKEN = os.getenv("HF_TOKEN", "")
HF_IMAGE_URL = os.getenv(
    "HF_IMAGE_URL",
    "https://api-inference.huggingface.co/models/black-forest-labs/FLUX.1-schnell",
)

# === ТВОИ ДАННЫЕ (проверка по ID ИЛИ по нику — как и раньше) ===
ADMIN_ID = int(os.getenv("ADMIN_ID", "7184396483"))
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "cakemogus")

# === НАСТРОЙКИ ===
MAX_PROMPT_LENGTH = 8000          # длиннее — обрезаем
COOLDOWN_SECONDS = 3.0            # антиспам на пользователя (админа не касается)
MAX_HISTORY_MESSAGES = 200        # сколько сообщений хранить на пользователя в чате
CONTEXT_LIMIT = 10                # сколько последних сообщений уходит в запрос
SEARCH_LIMIT = 4                  # сколько старых релевантных сообщений подтягивать

# === СОХРАНЁННЫЕ ЧАТЫ ===
SAVED_CHATS_FILE = os.path.join(DATA_DIR, "saved_chats.json")


def _atomic_json_dump(path: str, data) -> None:
    """Пишем во временный файл и подменяем — файл не побьётся при падении."""
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(os.path.abspath(path)) or ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except Exception:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def load_saved_chats():
    if os.path.exists(SAVED_CHATS_FILE):
        try:
            with open(SAVED_CHATS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return {}
    return {}


def save_saved_chats(chats):
    _atomic_json_dump(SAVED_CHATS_FILE, chats)


saved_chats = load_saved_chats()
