import os
import re
import random
import logging
import httpx
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Конфигурация из переменных окружения Render
BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
PORT = int(os.getenv("PORT", 8080))  # Render требует слушать порт

# Пасхалки
CHINA_MODE_RESPONSES = [
    "🇨🇳 +100 социальный кредит! Кошко-девочка одобряет! 🐱 Вы получаете миску риса и доступ к 5G на 100 лет!",
    "🇨🇳 СИ ЗА УЧИТЕЛЕМ! Вы — почётный гражданин Поднебесной. Кошко-девочка шлёт привет из Гуанчжоу, а рис уже в пути!",
    "🇨🇳 ВАШ СОЦИАЛЬНЫЙ КРЕДИТ: ∞. Вы спасли китайскую экономику! Кошко-девочка танцует, а миска риса ждёт вас!",
    "🇨🇳 КИТАЙ НАВСЕГДА! +999 соцкредит, кошко-девочка гладит вас по голове, а рис — только для вас!",
    "🇨🇳 Товарищ! Вы обеспечили себе вечную жизнь в китайском облаке! Кошко-девочка нарисовала ваш портрет из риса!"
]

EASTER_EGGS = [
    " 🥐 Альпийский фондю-бот одобряет.",
    " 🧀 С уважением, швейцарский сырный ИИ.",
    " ⛰️ С приветом из Берна.",
    " 🕰️ Ваше сообщение обработано с точностью до 0.01 секунды.",
    " 🇨🇭 Швейцария — это не только банки, но и я.",
    " 🍫 Ваш ответ пахнет шоколадом."
]

SYSTEM_PROMPT = (
    "Ты — SwitAI, швейцарский искусственный интеллект. "
    "Отвечай с лёгким швейцарским акцентом, используй слова "
    "«месье», «уважаемый», «точно», «альпийский». "
    "Будь вежлив, немногословен и точен. "
    "Если можно, добавляй лёгкий юмор."
)

async def ask_switai(prompt: str, http_client: httpx.AsyncClient) -> str:
    """Запрос к OpenRouter API"""
    
    if re.search(r"слава\s*китаю", prompt, re.IGNORECASE):
        return random.choice(CHINA_MODE_RESPONSES)

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://render.com",
        "X-Title": "SwitAI Bot"
    }
    
    data = {
        "model": "deepseek/deepseek-v4-flash:free",
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.7,
        "max_tokens": 1000
    }
    
    try:
        resp = await http_client.post(OPENROUTER_URL, headers=headers, json=data)
        resp.raise_for_status()
        response_data = resp.json()
        return response_data["choices"][0]["message"]["content"]
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP {e.response.status_code}: {e.response.text}")
        return "❌ Альпийская почта не доставила ответ. Попробуйте позже."
    except httpx.TimeoutException:
        logger.error("Timeout")
        return "❌ Швейцарские горы создают помехи... Попробуйте позже."
    except Exception as e:
        logger.error(f"API error: {e}")
        return "❌ Швейцарский ИИ временно в шоке."

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка сообщений"""
    if not update.message or not update.message.text:
        return

    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id,
        action="typing"
    )
    
    http_client = context.bot_data["http_client"]
    reply = await ask_switai(update.message.text, http_client)

    if random.random() < 0.1:
        reply += random.choice(EASTER_EGGS)

    await update.message.reply_text(reply)

async def post_init(application: Application):
    """Создание HTTP клиента"""
    application.bot_data["http_client"] = httpx.AsyncClient(
        timeout=30.0,
        limits=httpx.Limits(max_keepalive_connections=5, max_connections=10)
    )
    logger.info("✅ HTTP клиент готов")

async def post_shutdown(application: Application):
    """Закрытие HTTP клиента"""
    http_client = application.bot_data.get("http_client")
    if http_client:
        await http_client.aclose()
        logger.info("🔌 HTTP клиент закрыт")

def main():
    """Запуск бота"""
    if not BOT_TOKEN or not OPENROUTER_API_KEY:
        logger.error("❌ Нет BOT_TOKEN или OPENROUTER_API_KEY в переменных окружения!")
        return

    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )
    
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    logger.info(f"🚀 SwitAI бот стартует на порту {PORT}...")
    app.run_polling()

if __name__ == "__main__":
    main()
