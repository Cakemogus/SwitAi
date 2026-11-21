"""
HISTORY.PY — ПАМЯТЬ БОТА
========================
Раньше history.json читался и перезаписывался ЦЕЛИКОМ на каждое сообщение
(а лимит был 10000 сообщений на человека). Теперь:
  • история живёт в памяти, на диск пишется атомарно;
  • лимит разумный (MAX_HISTORY_MESSAGES);
  • старые релевантные сообщения подаются отдельной заметкой, а не вперемешку с диалогом.
"""

import os
import re
import threading
from datetime import datetime, timedelta

from config import CONTEXT_LIMIT, DATA_DIR, MAX_HISTORY_MESSAGES, SEARCH_LIMIT, _atomic_json_dump

HISTORY_FILE = os.path.join(DATA_DIR, "history.json")
_lock = threading.RLock()
_cache = None
_dirty = False

_STOP = {
    "что", "как", "для", "это", "так", "вот", "если", "при", "через", "между", "среди",
    "про", "или", "чтоб", "чтобы", "когда", "тогда", "есть", "быть", "было", "меня", "тебя",
}


def _load():
    global _cache
    if _cache is not None:
        return _cache
    import json
    _cache = {}
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                _cache = data
        except (OSError, ValueError):
            pass
    return _cache


def _flush():
    global _dirty
    try:
        _atomic_json_dump(HISTORY_FILE, _cache)
        _dirty = False
    except OSError:
        pass


def _key(chat_id, user_id):
    return f"{chat_id}_{user_id}"


# === ПУБЛИЧНЫЙ API ===
def get_user_history(chat_id, user_id, limit=CONTEXT_LIMIT):
    with _lock:
        return list(_load().get(_key(chat_id, user_id), [])[-limit:])


def get_all_user_data(chat_id, user_id):
    with _lock:
        return list(_load().get(_key(chat_id, user_id), []))


def add_to_history(chat_id, user_id, role, content, timestamp=None):
    with _lock:
        data = _load()
        items = data.setdefault(_key(chat_id, user_id), [])
        items.append({
            "role": role,
            "content": content,
            "timestamp": timestamp or datetime.now().isoformat(timespec="seconds"),
        })
        if len(items) > MAX_HISTORY_MESSAGES:
            del items[: len(items) - MAX_HISTORY_MESSAGES]
        _flush()


def clear_user_history(chat_id, user_id):
    with _lock:
        if _load().pop(_key(chat_id, user_id), None) is not None:
            _flush()


def clear_chat_history(chat_id) -> int:
    """Чистит память ВСЕХ пользователей в этом чате. Возвращает, сколько записей удалено."""
    with _lock:
        data = _load()
        prefix = f"{chat_id}_"
        keys = [k for k in data if k.startswith(prefix)]
        for k in keys:
            del data[k]
        if keys:
            _flush()
        return len(keys)


def clear_all_history():
    global _cache
    with _lock:
        _cache = {}
        _flush()


def count_users_in_chat(chat_id) -> int:
    with _lock:
        prefix = f"{chat_id}_"
        return sum(1 for k in _load() if k.startswith(prefix))


# === ПОИСК ===
def extract_keywords(text, min_len=4, max_words=6):
    words = re.findall(r"\w+", (text or "").lower())
    seen, out = set(), []
    for w in words:
        if len(w) >= min_len and w not in _STOP and w not in seen:
            seen.add(w)
            out.append(w)
    # длинные слова информативнее
    return sorted(out, key=len, reverse=True)[:max_words]


def _stem(word: str) -> str:
    """Грубая основа — чтобы «собаку» находило «собака»."""
    return word[:-2] if len(word) > 6 else word[:-1] if len(word) > 4 else word


def search_history(chat_id, user_id, keyword, limit=SEARCH_LIMIT):
    with _lock:
        items = list(_load().get(_key(chat_id, user_id), []))
    kw = keyword.lower()
    res = []
    for msg in reversed(items):
        if kw in msg["content"].lower():
            res.append(msg)
            if len(res) >= limit:
                break
    return res


def search_history_last_days(chat_id, user_id, days, limit=SEARCH_LIMIT):
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    with _lock:
        items = list(_load().get(_key(chat_id, user_id), []))
    res = [m for m in reversed(items) if m.get("timestamp", "") >= cutoff]
    return res[:limit]


def find_relevant_history(chat_id, user_id, prompt, limit=SEARCH_LIMIT, exclude_last=CONTEXT_LIMIT):
    """Ищет в СТАРОЙ части истории (за пределами последних сообщений) то, что связано с вопросом."""
    stems = [_stem(w) for w in extract_keywords(prompt)]
    if not stems:
        return []
    with _lock:
        items = list(_load().get(_key(chat_id, user_id), []))
    older = items[:-exclude_last] if exclude_last else items
    scored = []
    for idx, msg in enumerate(older):
        low = msg["content"].lower()
        score = sum(1 for s in stems if s in low)
        if score:
            scored.append((score, idx, msg))
    scored.sort(key=lambda t: (t[0], t[1]), reverse=True)  # больше совпадений, потом свежее
    top = sorted(scored[:limit], key=lambda t: t[1])         # возвращаем в хронологии
    return [m for _, _, m in top]


def format_archive_note(messages) -> str:
    if not messages:
        return ""
    lines = []
    for m in messages:
        who = "Пользователь" if m["role"] == "user" else "Ты (SwitAI)"
        lines.append(f"- {who}: {m['content'][:300]}")
    return (
        "\n\nВот что вы обсуждали раньше (используй, только если это относится к вопросу):\n"
        + "\n".join(lines)
    )


def get_context(chat_id, user_id, prompt):
    """(последние сообщения, текст-заметка из архива)."""
    recent = get_user_history(chat_id, user_id, limit=CONTEXT_LIMIT)
    archive = find_relevant_history(chat_id, user_id, prompt)
    return recent, format_archive_note(archive)


def debug_history(chat_id, user_id):
    items = get_all_user_data(chat_id, user_id)
    if not items:
        return "📭 История пуста."
    lines = ["📜 Вся история:\n"]
    for m in items:
        lines.append(f"{'👤' if m['role'] == 'user' else '🤖'} {m['content'][:100]}")
    return "\n".join(lines)
