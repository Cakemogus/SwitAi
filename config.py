import os
import json

# === ТОКЕНЫ ===
BOT_TOKEN = os.getenv("BOT_TOKEN")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

# === ВСЕ 12 API-КЛЮЧЕЙ GROQ ===
GROQ_API_KEYS = [
    os.getenv("GROQ_API_KEY_1"),
    os.getenv("GROQ_API_KEY_2"),
    os.getenv("GROQ_API_KEY_3"),
    os.getenv("GROQ_API_KEY_4"),
    os.getenv("GROQ_API_KEY_5"),
    os.getenv("GROQ_API_KEY_6"),
    os.getenv("GROQ_API_KEY_7"),
    os.getenv("GROQ_API_KEY_8"),
    os.getenv("GROQ_API_KEY_9"),
    os.getenv("GROQ_API_KEY_10"),
    os.getenv("GROQ_API_KEY_11"),
    os.getenv("GROQ_API_KEY_12"),
]

# === КЛЮЧИ OLLAMA (для интернет-поиска) ===
OLLAMA_API_KEYS = [
    os.getenv("OLLAMA_API_KEY_1"),
    os.getenv("OLLAMA_API_KEY_2")
]

# === РОЛИ КЛЮЧЕЙ GROQ ===
ROLES = {
    "history_manager": 0,
    "general": [1, 2, 3],
    "verdict": [4, 5, 6, 7],
    "history_compressor": 8,
    "fun": 9,
    "backup": [10, 11]
}

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
