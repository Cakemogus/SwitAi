"""
UTILS.PY — вспомогательные функции
"""

import datetime
import html
import re

import pytz


# === ГЕНЕРАТОР МЕСЯЦА ПО МСК (РП-фишка: меняется каждые 2 часа) ===
def get_rp_month():
    tz = pytz.timezone("Europe/Moscow")
    hour = datetime.datetime.now(tz).hour
    months = [
        "январь", "февраль", "март", "апрель", "май", "июнь",
        "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь",
    ]
    return months[(hour // 2) % 12]


def msk_now_str() -> str:
    tz = pytz.timezone("Europe/Moscow")
    return datetime.datetime.now(tz).strftime("%d.%m.%Y %H:%M (МСК)")


# === РАЗБИВКА ДЛИННЫХ СООБЩЕНИЙ (теперь режет и слишком длинные строки) ===
def split_text(text: str, max_len: int = 4000):
    text = text or ""
    if len(text) <= max_len:
        return [text]
    parts, current = [], ""
    for line in text.split("\n"):
        while len(line) > max_len:  # одна огромная строка без переносов
            if current:
                parts.append(current.strip())
                current = ""
            parts.append(line[:max_len])
            line = line[max_len:]
        if len(current) + len(line) + 1 <= max_len:
            current += line + "\n"
        else:
            if current:
                parts.append(current.strip())
            current = line + "\n"
    if current.strip():
        parts.append(current.strip())
    return parts


# === ПРОВЕРКА АДМИНА: по ID ИЛИ по нику (как ты и просил — не убрано) ===
def is_admin(user_id: int, username: str, ADMIN_ID: int, ADMIN_USERNAME: str) -> bool:
    if user_id == ADMIN_ID:
        return True
    if username and username.lower() == ADMIN_USERNAME.lower():
        return True
    return False


def esc(text) -> str:
    """Экранирование для parse_mode=HTML."""
    return html.escape(str(text), quote=False)


# === ВРЕМЯ / ДЛИТЕЛЬНОСТИ ===
def format_timestamp(timestamp):
    try:
        return datetime.datetime.fromisoformat(timestamp).strftime("%d.%m.%Y %H:%M")
    except (TypeError, ValueError):
        return timestamp


def parse_duration(value: str):
    """'forever' -> 'forever'; '30' / '30m' / '2h' / '1d' -> секунды; иначе None."""
    value = (value or "").strip().lower()
    if value in ("forever", "навсегда", "inf"):
        return "forever"
    m = re.fullmatch(r"(\d+)\s*([mhdмчд]?)", value)
    if not m:
        return None
    n, unit = int(m.group(1)), m.group(2)
    mult = {"": 60, "m": 60, "м": 60, "h": 3600, "ч": 3600, "d": 86400, "д": 86400}[unit]
    return n * mult


def human_duration(seconds) -> str:
    if seconds == "forever":
        return "навсегда"
    seconds = int(seconds)
    if seconds >= 86400:
        return f"{seconds // 86400} д."
    if seconds >= 3600:
        return f"{seconds // 3600} ч."
    return f"{max(1, seconds // 60)} мин."
