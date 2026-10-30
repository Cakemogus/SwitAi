import os
import json

# === ТОКЕНЫ ===
BOT_TOKEN = os.getenv("BOT_TOKEN")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

# === КЛЮЧИ GROQ (ПОДДЕРЖКА НЕСКОЛЬКИХ) ===
# На хостинге добавь GROQ_API_KEY, GROQ_API_KEY_2 (если есть) и т.д.
GROQ_API_KEYS = [
    os.getenv("GROQ_API_KEY"),
    os.getenv("GROQ_API_KEY_2"),
    os.getenv("GROQ_API_KEY_3"),
]
# Убираем пустые значения, если какие-то ключи не заданы
GROQ_API_KEYS = [k for k in GROQ_API_KEYS if k]

# === КЛЮЧ GEMINI ===
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# === КЛЮЧИ OLLAMA ===
OLLAMA_API_KEYS = [
    os.getenv("OLLAMA_API_KEY_1"),
    os.getenv("OLLAMA_API_KEY_2")
]

# === ТВОИ ДАННЫЕ ===
ADMIN_ID = 7184396483
ADMIN_USERNAME = "cakemogus"

# === НАСТРОЙКИ ===
MAX_PROMPT_LENGTH = 8000
MAX_HISTORY_MESSAGES = 50

# === СОХРАНЁННЫЕ ЧАТЫ ===
SAVED_CHATS_FILE = "saved_chats.json"

def load_saved_chats():
    if os.path.exists(SAVED_CHATS_FILE):
        try:
            with open(SAVED_CHATS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_saved_chats(chats):
    with open(SAVED_CHATS_FILE, "w", encoding="utf-8") as f:
        json.dump(chats, f, ensure_ascii=False, indent=2)

saved_chats = load_saved_chats()
