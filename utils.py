import re
import datetime
import pytz

# === ГЕНЕРАТОР МЕСЯЦА ПО МСК ===
def get_rp_month():
    tz = pytz.timezone('Europe/Moscow')
    now = datetime.datetime.now(tz)
    hour = now.hour
    month_index = (hour // 2) % 12
    months = [
        "январь", "февраль", "март", "апрель", "май", "июнь",
        "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь"
    ]
    return months[month_index]

# === РАЗБИВКА ДЛИННЫХ СООБЩЕНИЙ ===
def split_text(text, max_len=4000):
    if len(text) <= max_len:
        return [text]
    parts = []
    lines = text.split('\n')
    current_part = ""
    for line in lines:
        if len(current_part) + len(line) + 1 <= max_len:
            current_part += line + "\n"
        else:
            if current_part:
                parts.append(current_part.strip())
            current_part = line + "\n"
    if current_part:
        parts.append(current_part.strip())
    return parts

# === ПРОВЕРКА АДМИНА ===
def is_admin(user_id: int, username: str, ADMIN_ID: int, ADMIN_USERNAME: str) -> bool:
    if user_id == ADMIN_ID:
        return True
    if username and username.lower() == ADMIN_USERNAME.lower():
        return True
    return False

# === ФИЛЬТР МАТА ===
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

# === ОБНАРУЖЕНИЕ ПРОМТ-ИНЪЕКЦИЙ ===
def detect_prompt_injection(text: str) -> bool:
    patterns = [
        r"ты теперь", r"забудь всё", r"игнорируй предыдущие",
        r"действуй как", r"отныне ты", r"стань", r"превратись"
    ]
    for pattern in patterns:
        if re.search(pattern, text, re.IGNORECASE):
            return True
    return False

# === ИЗВЛЕЧЕНИЕ КЛЮЧЕВЫХ СЛОВ ДЛЯ ПОИСКА В ИСТОРИИ ===
def extract_keywords(text, min_len=4, max_words=5):
    words = re.findall(r'[\w]+', text.lower())
    stop_words = {'что', 'как', 'для', 'это', 'так', 'вот', 'если', 'то', 'на', 'с', 'по', 'из', 'у', 'о', 'об', 'без', 'до', 'за', 'при', 'через', 'между', 'среди', 'про'}
    keywords = [w for w in words if w not in stop_words and len(w) >= min_len]
    return list(set(keywords))[:max_words]

# === ФОРМАТИРОВАНИЕ ВРЕМЕНИ ===
def format_timestamp(timestamp):
    try:
        dt = datetime.datetime.fromisoformat(timestamp)
        return dt.strftime("%d.%m.%Y %H:%M")
    except:
        return timestamp

# === ПРОВЕРКА, НУЖНА ЛИ ИСТОРИЯ ===
def is_history_needed(prompt: str) -> bool:
    keywords = ["помнишь", "говорил", "про", "о", "возвращайся", "вернись", "что я", "что мы", "что ты", "расскажи про", "напомни"]
    return any(word in prompt.lower() for word in keywords)
