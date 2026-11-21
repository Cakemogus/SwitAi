# SwitAI 2.0

Запуск: `pip install -r requirements.txt`, переменные окружения — см. `.env.example`, затем `python bot.py`.

Проверка админа осталась прежней: по ID **или** по нику (`ADMIN_ID`, `ADMIN_USERNAME` в config.py / env).

Данные пишутся в `DATA_DIR` (по умолчанию рядом с ботом): `history.json`, `state.json`, `saved_chats.json`.
На Render диск временный — для сохранения банов/памяти между деплоями подключи Persistent Disk и поставь `DATA_DIR`.
