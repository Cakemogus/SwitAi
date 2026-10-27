"""
BOT.PY — SWITAI (ТОЧКА ВХОДА)
=========================================
Запуск Telegram-бота и Flask для Health Check.
"""

import logging
import os
from threading import Thread
from flask import Flask
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters

from config import BOT_TOKEN
from handlers import handle_message
from commands import (
    menu_command, exit_admin_command, debug_command,
    clear_memory_command, clear_all_memory_command,
    set_filter_command, set_mode_command, reset_bot_command,
    stop_command, start_command,
    sw_command, sb_command, sm_command,
    unsb_command, unsm_command,
    warn_command, mute_command, unmute_command,
    kick_command, ban_command, userinfo_command,
    say_command, del_command,
    clear_chat_command, history_command, stats_command, about_command,
    save_chat_command, say_chat_command, list_chats_command, remove_chat_command,
    unlock_command, lock_command
)

# =====================================================================
# ЛОГИРОВАНИЕ (Чтобы видеть ошибки в консоли хостинга)
# =====================================================================
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", 
    level=logging.INFO
)
# Отключаем спам от библиотеки httpx (чтобы логи не забивались запросами к API)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

# =====================================================================
# FLASK ДЛЯ HEALTH CHECK (Чтобы хостинг не усыплял бота)
# =====================================================================
app_web = Flask(__name__)

@app_web.route('/')
@app_web.route('/health')
def health_check():
    return "✅ SwitAI жив и здоров!", 200

def run_web():
    port = int(os.environ.get("PORT", "10000"))
    # Отключаем логи Flask, чтобы не засорять консоль
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)
    app_web.run(host='0.0.0.0', port=port)

# =====================================================================
# ЗАПУСК БОТА
# =====================================================================
def main():
    if not BOT_TOKEN:
        logger.error("❌ Не установлен BOT_TOKEN в переменных окружения!")
        return

    # Запускаем Flask в отдельном потоке для Health Check
    thread = Thread(target=run_web)
    thread.daemon = True
    thread.start()
    logger.info(f"✅ Flask Health Check запущен на порту {os.environ.get('PORT', '10000')}")

    # Инициализация Telegram Бота
    app = Application.builder().token(BOT_TOKEN).build()

    # === ПОДКЛЮЧЕНИЕ ОБРАБОТЧИКОВ ===
    
    # Обработчик обычных сообщений (текст)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Публичные команды
    app.add_handler(CommandHandler("history", history_command))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("about", about_command))

    # Админские команды
    app.add_handler(CommandHandler("menu", menu_command))
    app.add_handler(CommandHandler("exit_admin", exit_admin_command))
    app.add_handler(CommandHandler("debug", debug_command))
    app.add_handler(CommandHandler("clear_memory", clear_memory_command))
    app.add_handler(CommandHandler("clear_all_memory", clear_all_memory_command))
    app.add_handler(CommandHandler("set_filter", set_filter_command))
    app.add_handler(CommandHandler("unlock", unlock_command))
    app.add_handler(CommandHandler("lock", lock_command))
    app.add_handler(CommandHandler("set_mode", set_mode_command))
    app.add_handler(CommandHandler("reset_bot", reset_bot_command))
    app.add_handler(CommandHandler("stop", stop_command))
    app.add_handler(CommandHandler("start", start_command))
    
    # Модерация (старые команды)
    app.add_handler(CommandHandler("warn", warn_command))
    app.add_handler(CommandHandler("mute", mute_command))
    app.add_handler(CommandHandler("unmute", unmute_command))
    app.add_handler(CommandHandler("kick", kick_command))
    app.add_handler(CommandHandler("ban", ban_command))
    app.add_handler(CommandHandler("userinfo", userinfo_command))
    
    # Модерация (новые префиксы /s)
    app.add_handler(CommandHandler("sw", sw_command))
    app.add_handler(CommandHandler("sb", sb_command))
    app.add_handler(CommandHandler("sm", sm_command))
    app.add_handler(CommandHandler("unsb", unsb_command))
    app.add_handler(CommandHandler("unsm", unsm_command))
    
    # Утилиты
    app.add_handler(CommandHandler("say", say_command))
    app.add_handler(CommandHandler("del", del_command))
    app.add_handler(CommandHandler("clear_chat", clear_chat_command))
    app.add_handler(CommandHandler("savechat", save_chat_command))
    app.add_handler(CommandHandler("saychat", say_chat_command))
    app.add_handler(CommandHandler("listchats", list_chats_command))
    app.add_handler(CommandHandler("removechat", remove_chat_command))

    logger.info("✅ SwitAI запущен с модерацией и новой системой ключей!")
    
    # Запуск бота
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
