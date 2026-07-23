import os
import asyncio
from telegram.ext import Application, CommandHandler, MessageHandler, filters
from flask import Flask
from threading import Thread

# === ИМПОРТЫ ИЗ МОДУЛЕЙ ===
from config import BOT_TOKEN
from handlers import handle_message
from commands import (
    menu_command, exit_admin_command, debug_command,
    clear_memory_command, clear_all_memory_command,
    set_filter_command, set_mode_command, reset_bot_command,
    stop_command, start_command,
    warn_command, mute_command, unmute_command,
    kick_command, ban_command, userinfo_command,
    say_command, del_command,
    clear_chat_command, history_command, stats_command, about_command,
    save_chat_command, say_chat_command, list_chats_command, remove_chat_command
)

# === МИКРО-СЕРВЕР ДЛЯ RENDER ===
app_web = Flask(__name__)

@app_web.route('/')
@app_web.route('/health')
def health_check():
    return "✅ SwitAI жив и здоров, месье!", 200

def run_web():
    app_web.run(host='0.0.0.0', port=10000)

# === ЗАПУСК БОТА ===
def main():
    if not BOT_TOKEN:
        print("❌ Не установлен BOT_TOKEN!")
        return

    # Запускаем микро-сервер для пингов Render
    thread = Thread(target=run_web)
    thread.daemon = True
    thread.start()

    # Создаём приложение Telegram
    app = Application.builder().token(BOT_TOKEN).build()

    # === ОБРАБОТЧИК СООБЩЕНИЙ ===
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # === КОМАНДЫ ДЛЯ ВСЕХ ===
    app.add_handler(CommandHandler("history", history_command))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("about", about_command))

    # === АДМИН-КОМАНДЫ ===
    app.add_handler(CommandHandler("menu", menu_command))
    app.add_handler(CommandHandler("exit_admin", exit_admin_command))
    app.add_handler(CommandHandler("debug", debug_command))
    app.add_handler(CommandHandler("clear_memory", clear_memory_command))
    app.add_handler(CommandHandler("clear_all_memory", clear_all_memory_command))
    app.add_handler(CommandHandler("set_filter", set_filter_command))
    app.add_handler(CommandHandler("set_mode", set_mode_command))
    app.add_handler(CommandHandler("reset_bot", reset_bot_command))
    app.add_handler(CommandHandler("stop", stop_command))
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("warn", warn_command))
    app.add_handler(CommandHandler("mute", mute_command))
    app.add_handler(CommandHandler("unmute", unmute_command))
    app.add_handler(CommandHandler("kick", kick_command))
    app.add_handler(CommandHandler("ban", ban_command))
    app.add_handler(CommandHandler("userinfo", userinfo_command))
    app.add_handler(CommandHandler("say", say_command))
    app.add_handler(CommandHandler("del", del_command))
    app.add_handler(CommandHandler("clear_chat", clear_chat_command))
    app.add_handler(CommandHandler("savechat", save_chat_command))
    app.add_handler(CommandHandler("saychat", say_chat_command))
    app.add_handler(CommandHandler("listchats", list_chats_command))
    app.add_handler(CommandHandler("removechat", remove_chat_command))

    # === ЗАПУСК ===
    print("✅ SwitAI финальная версия запущена!")
    app.run_polling()

if __name__ == "__main__":
    main()
