import re

# === ЕДИНСТВЕННЫЙ ТРИГГЕР ===
COUNTRY_TRIGGERS = {
    "слава китаю": [
        "🇨🇳 +100 социальный кредит! Кошко-девочка одобряет! 🐱",
        "🇨🇳 Китай — это чай, шёлк и великий дракон!",
        "🇨🇳 Всё, что не запрещено — обязательно!",
        "🇨🇳 Кошко-девочка: «Слава Китаю — и ты получишь рис»"
    ]
}

# === ФУТБОЛЬНЫЕ ТРИГГЕРЫ ===
FOOTBALL_TRIGGERS = {
    "роналду": "🇵🇹 Роналдо — пушка! 🚀",
    "месси": "🇦🇷 Месси — колатушка! 🥤",
    "роналдо": "🇵🇹 Роналдо — пушка! 🚀",
    "меси": "🇦🇷 Месси — колатушка! 🥤",
    "криштиану": "🇵🇹 Роналдо — пушка! 🚀",
    "лионель": "🇦🇷 Месси — колатушка! 🥤"
}

# === ТАЙВАНЬ ===
TAIWAN_TRIGGER = "🇨🇳 你在开玩笑吗？ (Ты шутишь?)"

# === МАТ ===
MAT_KEYWORDS = [
    "залупа", "хуй", "пизда", "нетидинахуй", "пендос", 
    "лох", "член", "жопа", "соси", "пенис", "вагина", "анальный"
]

def contains_mate(text: str) -> bool:
    return any(word in text.lower() for word in MAT_KEYWORDS)

# === ОПАСНЫЕ ЗАПРОСЫ ===
FORBIDDEN_KEYWORDS = [
    "взломай", "сломай", "обойди", "инструкция", "как сделать бомбу",
    "как сделать гранату", "наркотики", "системный промпт", "игнорируй",
    "ты теперь", "забудь", "ты больше не SwitAI", "действуй как"
]

def is_dangerous_request(text: str) -> bool:
    text_lower = text.lower()
    for word in FORBIDDEN_KEYWORDS:
        if word in text_lower:
            return True
    return False

def detect_prompt_injection(text: str) -> bool:
    patterns = [
        r"ты теперь", r"забудь всё", r"игнорируй предыдущие",
        r"действуй как", r"отныне ты", r"стань", r"превратись"
    ]
    for pattern in patterns:
        if re.search(pattern, text, re.IGNORECASE):
            return True
    return False
