import json
import os
import re
from datetime import datetime, timedelta

# === НАСТРОЙКИ ===
HISTORY_FILE = "history.json"
MAX_HISTORY_LENGTH = 1000  # максимальное количество сообщений на пользователя
CONTEXT_LIMIT = 10  # сколько последних сообщений отправляем в запрос
SEARCH_LIMIT = 5  # сколько релевантных сообщений подтягиваем из архива

# === ЗАГРУЗКА / СОХРАНЕНИЕ ===
def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_history(history):
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

# === РАБОТА С ПОЛЬЗОВАТЕЛЕМ ===
def get_user_key(chat_id, user_id):
    return f"{chat_id}_{user_id}"

def get_user_history(chat_id, user_id, limit=CONTEXT_LIMIT):
    history = load_history()
    key = get_user_key(chat_id, user_id)
    if key not in history:
        return []
    return history[key][-limit:]

def add_to_history(chat_id, user_id, role, content, timestamp=None):
    if timestamp is None:
        timestamp = datetime.now().isoformat()
    
    history = load_history()
    key = get_user_key(chat_id, user_id)
    if key not in history:
        history[key] = []
    
    history[key].append({
        "role": role,
        "content": content,
        "timestamp": timestamp
    })
    
    # Ограничиваем длину
    if len(history[key]) > MAX_HISTORY_LENGTH:
        history[key] = history[key][-MAX_HISTORY_LENGTH:]
    
    save_history(history)

def clear_user_history(chat_id, user_id):
    history = load_history()
    key = get_user_key(chat_id, user_id)
    if key in history:
        del history[key]
        save_history(history)

def clear_all_history():
    save_history({})

def get_all_user_data(chat_id, user_id):
    history = load_history()
    key = get_user_key(chat_id, user_id)
    return history.get(key, [])

# === ПОИСК ПО КЛЮЧЕВЫМ СЛОВАМ ===
def search_history(chat_id, user_id, keyword, limit=SEARCH_LIMIT):
    """Ищет сообщения в истории по ключевому слову."""
    history = load_history()
    key = get_user_key(chat_id, user_id)
    if key not in history:
        return []
    
    results = []
    for msg in reversed(history[key]):
        if keyword.lower() in msg['content'].lower():
            results.append(msg)
            if len(results) >= limit:
                break
    return results

def search_history_multiple(chat_id, user_id, keywords, limit=SEARCH_LIMIT):
    """Ищет сообщения по нескольким ключевым словам."""
    if not keywords:
        return []
    
    history = load_history()
    key = get_user_key(chat_id, user_id)
    if key not in history:
        return []
    
    results = []
    for msg in reversed(history[key]):
        for kw in keywords:
            if kw.lower() in msg['content'].lower():
                results.append(msg)
                break
        if len(results) >= limit:
            break
    return results

# === РЕЛЕВАНТНЫЙ КОНТЕКСТ ===
def extract_keywords(text, min_len=4, max_words=5):
    """Извлекает ключевые слова из текста для поиска."""
    words = re.findall(r'[\w]+', text.lower())
    # Убираем стоп-слова
    stop_words = {'что', 'как', 'для', 'это', 'так', 'вот', 'если', 'то', 'на', 'с', 'по', 'из', 'у', 'о', 'об', 'без', 'до', 'за', 'при', 'через', 'между', 'среди', 'про'}
    keywords = [w for w in words if w not in stop_words and len(w) >= min_len]
    return list(set(keywords))[:max_words]

def find_relevant_history(chat_id, user_id, prompt, limit=SEARCH_LIMIT):
    """Находит в истории сообщения, связанные с текущим запросом."""
    keywords = extract_keywords(prompt)
    if not keywords:
        return []
    
    history = load_history()
    key = get_user_key(chat_id, user_id)
    if key not in history:
        return []
    
    results = []
    # Идём с конца, чтобы взять самые свежие
    for msg in reversed(history[key]):
        content_lower = msg['content'].lower()
        for kw in keywords:
            if kw in content_lower:
                results.append(msg)
                break
        if len(results) >= limit:
            break
    
    return results

# === ПОИСК ПО ДАТЕ ===
def search_history_by_date(chat_id, user_id, date_str, limit=SEARCH_LIMIT):
    """Ищет сообщения за конкретную дату (YYYY-MM-DD)."""
    history = load_history()
    key = get_user_key(chat_id, user_id)
    if key not in history:
        return []
    
    results = []
    for msg in reversed(history[key]):
        if date_str in msg.get('timestamp', ''):
            results.append(msg)
            if len(results) >= limit:
                break
    return results

def search_history_last_days(chat_id, user_id, days, limit=SEARCH_LIMIT):
    """Ищет сообщения за последние N дней."""
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    history = load_history()
    key = get_user_key(chat_id, user_id)
    if key not in history:
        return []
    
    results = []
    for msg in reversed(history[key]):
        if msg.get('timestamp', '') >= cutoff:
            results.append(msg)
            if len(results) >= limit:
                break
    return results

# === ФОРМАТИРОВАНИЕ ДЛЯ КОНТЕКСТА ===
def format_history_for_context(messages, max_messages=SEARCH_LIMIT):
    """Форматирует историю для вставки в контекст запроса."""
    if not messages:
        return ""
    
    text = "\n[Из архива сообщений]\n"
    for msg in messages[:max_messages]:
        role = "Вы" if msg['role'] == 'user' else "Бот"
        text += f"{role}: {msg['content'][:500]}\n"
    text += "\n[/конец архива]\n"
    return text

def get_context_with_history(chat_id, user_id, prompt):
    """Получает историю + релевантные сообщения для контекста."""
    # Берём последние сообщения
    recent = get_user_history(chat_id, user_id, limit=CONTEXT_LIMIT)
    
    # Ищем релевантные старые сообщения
    relevant = find_relevant_history(chat_id, user_id, prompt, limit=SEARCH_LIMIT)
    
    # Объединяем, убирая дубли
    combined = []
    seen = set()
    for msg in recent + relevant:
        # Используем содержимое для проверки дублей
        content_hash = msg['content'][:100]
        if content_hash not in seen:
            seen.add(content_hash)
            combined.append(msg)
    
    return combined[-CONTEXT_LIMIT:]  # оставляем не больше лимита
