"""
BOT.PY — SWITAI 2.0 (ТОЧКА ВХОДА)
=================================
Запуск Telegram-бота + Flask для health check (чтобы Render не усыплял).
"""

import logging
import os
from threading import Thread

from flask import Flask
from telegram import BotCommand, Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters

import commands as c
import llm
from config import BOT_TOKEN, GROQ_API_KEYS, GEMINI_API_KEY
from handlers import handle_message

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

# =====================================================================
# FLASK HEALTH CHECK
# =====================================================================
app_web = Flask(__name__)


@app_web.route("/")
@app_web.route("/health")
def health_check():
    return "✅ SwitAI жив и здоров!", 200


def run_web():
    port = int(os.environ.get("PORT", "10000"))
    logging.getLogger("werkzeug").setLevel(logging.ERROR)
    app_web.run(host="0.0.0.0", port=port)


# =====================================================================
# ХУКИ
# =====================================================================
async def post_init(app: Application):
    await app.bot.set_my_commands([
        BotCommand("help", "Список команд"),
        BotCommand("ping", "Проверка связи"),
        BotCommand("history", "Моя история"),
        BotCommand("stats", "Статистика"),
        BotCommand("forgetme", "Забыть наш диалог"),
        BotCommand("about", "О боте"),
    ])


async def post_shutdown(app: Application):
    await llm.close_client()


async def on_error(update, context):
    logger.error("Ошибка в обработчике", exc_info=context.error)


# =====================================================================
# ЗАПУСК
# =====================================================================
COMMANDS = {
    # публичные
    "start": c.start_command, "help": c.help_command, "ping": c.ping_command,
    "history": c.history_command, "stats": c.stats_command,
    "forgetme": c.forgetme_command, "about": c.about_command,
    # админ: система
    "menu": c.menu_command, "exit_admin": c.exit_admin_command, "debug": c.debug_command,
    "clear_memory": c.clear_memory_command, "clear_all_memory": c.clear_all_memory_command,
    "clear_chat": c.clear_chat_command, "set_filter": c.set_filter_command,
    "unlock": c.unlock_command, "lock": c.lock_command, "set_mode": c.set_mode_command,
    "reset_bot": c.reset_bot_command, "stop": c.stop_command,
    # админ: модерация
    "sw": c.sw_command, "warn": c.sw_command, "unsw": c.unsw_command,
    "sb": c.sb_command, "ban": c.sb_command, "unsb": c.unsb_command, "unban": c.unsb_command,
    "sm": c.sm_command, "mute": c.sm_command, "unsm": c.unsm_command, "unmute": c.unsm_command,
    "kick": c.kick_command, "userinfo": c.userinfo_command, "interpol": c.interpol_command,
    # админ: утилиты
    "say": c.say_command, "del": c.del_command,
    "savechat": c.save_chat_command, "saychat": c.say_chat_command,
    "listchats": c.list_chats_command, "removechat": c.remove_chat_command,
    "stoppvp": c.stop_pvp_command, "startpvp": c.start_pvp_command,
}


def main():
    if not BOT_TOKEN:
        logger.error("❌ Не установлен BOT_TOKEN в переменных окружения!")
        return
    if not GROQ_API_KEYS and not GEMINI_API_KEY:
        logger.warning("⚠️ Нет ни GROQ_API_KEY, ни GEMINI_API_KEY — бот не сможет отвечать нейросетью.")

    Thread(target=run_web, daemon=True).start()
    logger.info("✅ Flask Health Check запущен на порту %s", os.environ.get("PORT", "10000"))

    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .concurrent_updates(True)   # пока один человек ждёт нейросеть, остальные не стоят в очереди
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    for name, fn in COMMANDS.items():
        app.add_handler(CommandHandler(name, fn))

    # текст и фото (раньше фото сюда не доходили)
    app.add_handler(MessageHandler((filters.TEXT | filters.PHOTO) & ~filters.COMMAND, handle_message))
    app.add_error_handler(on_error)

    logger.info("✅ SwitAI 2.0 запущен. Ключей Groq: %d, Gemini: %s", len(GROQ_API_KEYS), "да" if GEMINI_API_KEY else "нет")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == "__main__":
    main()
