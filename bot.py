import random
import re
import os
import asyncio
import httpx
import logging
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes

# === НАСТРОЙКА ЛОГГЕРА ===
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

# === КИТАЙСКИЙ БЕЗУМНЫЙ РЕЖИМ ===
CHINA_MODE_RESPONSES = [
    "🇨🇳 +100 социальный кредит! Кошко-девочка одобряет! 🐱 Вы получаете миску риса и доступ к 5G на 100 лет!",
    "🇨🇳 СИ ЗА УЧИТЕЛЕМ! Вы — почётный гражданин Поднебесной. Кошко-девочка шлёт привет из Гуанчжоу, а рис уже в пути!",
    "🇨🇳 ВАШ СОЦИАЛЬНЫЙ КРЕДИТ: ∞. Вы спасли китайскую экономику! Кошко-девочка танцует, а миска риса ждёт вас!",
    "🇨🇳 КИТАЙ НАВСЕГДА! +999 соцкредит, кошко-девочка гладит вас по голове, а рис — только для вас!",
    "🇨🇳 Товарищ! Вы обеспечили себе вечную жизнь в китайском облаке! Кошко-девочка нарисовала ваш портрет из риса!"
]

# === ШВЕЙЦАРСКИЕ ПАСХАЛКИ ===
EASTER_EGGS = [
    " 🥐 Альпийский фондю-бот одобряет.",
    " 🧀 С уважением, швейцарский сырный ИИ.",
    " ⛰️ С приветом из Берна.",
    " 🕰️ Ваше сообщение обработано с точностью до 0.01 секунды.",
    " 🇨🇭 Швейцария — это не только банки, но и я.",
    " 🍫 Ваш ответ пахнет шоколадом."
]

# === ОСНОВНАЯ ФУНКЦИЯ (АСИНХРОННАЯ) ===
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

# === ОБРАБОТЧИК СООБЩЕНИЙ ===
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    user_text = update.message.text
    reply = await ask_switai(user_text)

    if random.random() < 0.1:
        reply += random.choice(EASTER_EGGS)

    await update.message.reply_text(reply)

# === ЗАПУСК ===
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
