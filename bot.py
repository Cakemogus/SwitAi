import random
import re
import os
import asyncio
import httpx
import logging
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes

# Настройка логгера
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# === КЛЮЧИ ===
BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# === ГЛОБАЛЬНЫЙ HTTP КЛИЕНТ ===
http_client = httpx.AsyncClient(timeout=30.0)

# ... CHINA_MODE_RESPONSES и EASTER_EGGS без изменений ...

async def ask_switai(prompt: str) -> str:
    if re.search(r"слава\s*китаю", prompt, re.IGNORECASE):
        return random.choice(CHINA_MODE_RESPONSES)

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }
    
    system_prompt = (
        "Ты — SwitAI, швейцарский искусственный интеллект. "
        "Отвечай с лёгким швейцарским акцентом, используй слова "
        "«месье», «уважаемый», «точно», «альпийский». "
        "Будь вежлив, немногословен и точен. "
        "Если можно, добавляй лёгкий юмор."
    )
    
    data = {
        "model": "deepseek/deepseek-v4-flash:free",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ]
    }
    
    try:
        resp = await http_client.post(OPENROUTER_URL, headers=headers, json=data)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]
    except Exception as e:
        logger.error(f"API error: {e}")
        return f"❌ Швейцарский ИИ временно в шоке: {str(e)}"

# ... handle_message без изменений ...

async def main():
    if not BOT_TOKEN or not OPENROUTER_API_KEY:
        logger.error("❌ Не установлены переменные окружения!")
        return
    
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    logger.info("✅ SwitAI бот с пасхалками успешно запущен!")
    
    try:
        await app.run_polling()
    finally:
        await http_client.aclose()

if __name__ == "__main__":
    asyncio.run(main())
