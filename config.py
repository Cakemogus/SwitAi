import os

# === ТОКЕНЫ ===
BOT_TOKEN = os.getenv("BOT_TOKEN")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

# === ВСЕ 12 API-КЛЮЧЕЙ (по порядку) ===
GROQ_API_KEYS = [
    os.getenv("GROQ_API_KEY_1"),   # 1: следит за историей
    os.getenv("GROQ_API_KEY_2"),   # 2: основные ответы
    os.getenv("GROQ_API_KEY_3"),   # 3: основные ответы
    os.getenv("GROQ_API_KEY_4"),   # 4: основные ответы
    os.getenv("GROQ_API_KEY_5"),   # 5: вердикты
    os.getenv("GROQ_API_KEY_6"),   # 6: вердикты
    os.getenv("GROQ_API_KEY_7"),   # 7: вердикты
    os.getenv("GROQ_API_KEY_8"),   # 8: вердикты
    os.getenv("GROQ_API_KEY_9"),   # 9: сжимает историю
    os.getenv("GROQ_API_KEY_10"),  # 10: шутки и пасхалки
    os.getenv("GROQ_API_KEY_11"),  # 11: резерв
    os.getenv("GROQ_API_KEY_12"),  # 12: резерв
]

# === РОЛИ КЛЮЧЕЙ (по номерам) ===
ROLES = {
    "history_manager": 0,          # ключ 1 (индекс 0)
    "general": [1, 2, 3],          # ключи 2–4 (индексы 1, 2, 3)
    "verdict": [4, 5, 6, 7],       # ключи 5–8 (индексы 4, 5, 6, 7)
    "history_compressor": 8,       # ключ 9 (индекс 8)
    "fun": 9,                      # ключ 10 (индекс 9)
    "backup": [10, 11]             # ключи 11–12 (индексы 10, 11)
}

# === ТВОИ ДАННЫЕ ===
ADMIN_ID = 7184396483
ADMIN_USERNAME = "cakemogus"

# === ДРУГИЕ НАСТРОЙКИ ===
MAX_PROMPT_LENGTH = 2000
MAX_HISTORY_MESSAGES = 10
