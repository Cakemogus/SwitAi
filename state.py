"""
STATE.PY — ЕДИНОЕ СОСТОЯНИЕ БОТА
================================
Раньше баны/муты/режимы лежали в двух местах (handlers.py и commands.py) —
поэтому /sb и /sm фактически ничего не банили. Теперь всё здесь, один источник правды,
и это сохраняется на диск (переживает перезапуск).

Баны/муты хранятся по ключам:
  "id:123456"  — по айди (надёжно)
  "@nick"      — по нику (в нижнем регистре)
"""

import json
import os
import threading
import time

from config import DATA_DIR, _atomic_json_dump

STATE_FILE = os.path.join(DATA_DIR, "state.json")

_PERSISTED = (
    "bans", "mutes", "warns", "interpol", "known_users",
    "filter_enabled", "bot_stopped", "bot_mode", "pvp_disabled",
)


class State:
    def __init__(self):
        self._lock = threading.RLock()
        # --- сохраняется на диск ---
        self.bans = {}          # {key: "forever" | unix_time_until}
        self.mutes = {}         # {key: unix_time_until}
        self.warns = {}         # {key: count}
        self.interpol = {}      # {str(user_id): {"username": str, "count": int}}
        self.known_users = {}   # {nick_lower: user_id}
        self.filter_enabled = True
        self.bot_stopped = False
        self.bot_mode = "normal"
        self.pvp_disabled = set()
        # --- только в памяти ---
        self.admin_mode = set()   # chat_id, где админ включил /menu
        self.bot_chain = {}       # {chat_id: счётчик цепочки ботов}
        self.cooldowns = {}       # {user_id: время последнего сообщения}
        self.verdicts = {}        # {(chat_id, user_id): topic}
        self.started_at = time.time()
        self._load()

    # ---------- диск ----------
    def _load(self):
        if not os.path.exists(STATE_FILE):
            return
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            return
        for name in _PERSISTED:
            if name in data:
                value = data[name]
                setattr(self, name, set(value) if name == "pvp_disabled" else value)

    def save(self):
        with self._lock:
            data = {}
            for name in _PERSISTED:
                value = getattr(self, name)
                data[name] = sorted(value) if isinstance(value, set) else value
            try:
                _atomic_json_dump(STATE_FILE, data)
            except OSError:
                pass

    # ---------- пользователи ----------
    def remember_user(self, user):
        """Запоминаем ник -> айди, чтобы банить по @нику и при этом знать айди."""
        if user and user.username:
            key = user.username.lower()
            if self.known_users.get(key) != user.id:
                self.known_users[key] = user.id
                self.save()

    @staticmethod
    def user_keys(user):
        keys = [f"id:{user.id}"]
        if user.username:
            keys.append("@" + user.username.lower())
        return keys

    # ---------- проверка банов/мутов ----------
    def _active(self, table, keys) -> bool:
        now = time.time()
        changed = False
        result = False
        for k in keys:
            v = table.get(k)
            if v is None:
                continue
            if v == "forever" or v > now:
                result = True
            else:
                del table[k]
                changed = True
        if changed:
            self.save()
        return result

    def is_banned(self, user) -> bool:
        return self._active(self.bans, self.user_keys(user))

    def is_muted(self, user) -> bool:
        return self._active(self.mutes, self.user_keys(user))

    def keys_active(self, table, keys) -> bool:
        return self._active(table, keys)

    # ---------- интерпол ----------
    def add_interpol(self, user_id: int, username: str):
        entry = self.interpol.setdefault(str(user_id), {"username": username, "count": 0})
        entry["count"] += 1
        entry["username"] = username
        self.save()


S = State()
