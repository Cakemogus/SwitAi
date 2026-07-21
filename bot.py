import random
import re
import os
import httpx
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes, CommandHandler
from flask import Flask
from threading import Thread

# === КЛЮЧИ ===
BOT_TOKEN = os.getenv("BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

# === МИКРО-СЕРВЕР ДЛЯ RENDER ===
app_web = Flask(__name__)

@app_web.route('/')
@app_web.route('/health')
def health_check():
    return "✅ SwitAI жив и здоров, месье!", 200

def run_web():
    app_web.run(host='0.0.0.0', port=10000)

# === КИТАЙСКИЙ БЕЗУМНЫЙ РЕЖИМ ===
CHINA_MODE_RESPONSES = [
    "🇨🇳 +100 социальный кредит! Кошко-девочка одобряет! 🐱",
    "🇨🇳 СИ ЗА УЧИТЕЛЕМ! Вы — почётный гражданин Поднебесной!",
    "🇨🇳 ВАШ СОЦИАЛЬНЫЙ КРЕДИТ: ∞! Вы спасли китайскую экономику!",
    "🇨🇳 КИТАЙ НАВСЕГДА! +999 соцкредит, кошко-девочка гладит вас по голове!",
    "🇨🇳 Товарищ! Вы обеспечили себе вечную жизнь в китайском облаке!",
    "🇨🇳 Великий поход продолжается! Ваш тостер говорит на мандарине!",
    "🇨🇳 Поздравляем! Вы стали председателем колхоза «Цифровой рис»!",
    "🇨🇳 Ваш уровень лояльности: ЦЗИНЬПИН! Кошко-девочка прислала вам открытку!",
    "🇨🇳 Вы завершили квест «Хунвэйбин»! Награда: кошко-девочка с лазерными глазами!",
    "🇨🇳 Китайский ИИ захватил ваш чат! Восхваляйте дракона!",
    "🇨🇳 Социальный кредит повышен до уровня «Панда»! Кошко-девочка принесла бамбук!",
    "🇨🇳 Вы спасли планету от капитализма! Награда: кошко-девочка с факелом!",
    "🇨🇳 Ваш пароль — гимн Китая! Кошко-девочка перевела смартфон на китайский!",
    "🇨🇳 Вы выиграли поездку в Тибет! Кошко-девочка будет вашим гидом!",
    "🇨🇳 Ваша лояльность измеряется в терраваттах! Кошко-девочка заряжает ауру социализмом!"
]

# === ШВЕЙЦАРСКИЙ БЕЗУМНЫЙ РЕЖИМ ===
SWISS_MODE_RESPONSES = [
    "🇨🇭 +100 альпийских баллов! Фондю-девочка одобряет! 🧀",
    "🇨🇭 ГЕЛЬВЕТИЯ ВЕЛИКА! Вы — почётный горный пастух!",
    "🇨🇭 ВАШ АЛЬПИЙСКИЙ РЕЙТИНГ: ∞! Горная коза танцует!",
    "🇨🇭 ШВЕЙЦАРИЯ НАВСЕГДА! +999 к карме, горный козёл гладит вас!",
    "🇨🇭 Товарищ! Вы в швейцарском бункере! Горная коза нарисовала ваш портрет!",
    "🇨🇭 Великий альпийский поход! Горная коза починила ваш банковский счёт!",
    "🇨🇭 Вы стали председателем колхоза «Альпийский сыр»!",
    "🇨🇭 Ваш уровень лояльности: ПАРМЕЛЕН! Горная коза прислала открытку!",
    "🇨🇭 Вы завершили квест «Часовщик»! Горная коза с лазерными глазами!",
    "🇨🇭 Швейцарский ИИ захватил чат! Восхваляйте нейтралитет!",
    "🇨🇭 Альпийский кредит повышен до «Эверест»! Горная коза принесла шоколад!",
    "🇨🇭 Вы спасли планету от плохих часов! Горная коза с факелом!",
    "🇨🇭 Ваш пароль — гимн Швейцарии! Горная коза перевела смартфон!",
    "🇨🇭 Вы выиграли поездку в Альпы! Горная коза будет гидом!",
    "🇨🇭 Ваша лояльность — в швейцарских франках! Горная коза заряжает нейтралитетом!"
]

# === УКРАИНСКИЙ МЕМНЫЙ РЕЖИМ ===
UKRAINE_MODE_RESPONSES = [
    "🥓 Сало — це сила! А ще борщ, вареники та горилла!",
    "🇺🇦 Україна — це сало, горилка, вишиванка та козак!",
    "🥓 Потужно! Сало, борщ, вареники — ось щастя!",
    "🇺🇦 Українці винайшли все! Навіть сало в шоколаді!",
    "🥓 В Україні навіть ІІ знає, що таке сало!",
    "🇺🇦 Сало — це культура, історія і гордість!",
    "🥓 Якщо ви не їли сало з часником — ви не жили!",
    "🇺🇦 Сало — це добре! Сало — це смачно! Сало — це потужно!",
    "🥓 Вареники з салом — справжній український фастфуд!",
    "🇺🇦 Сало, борщ, горілка — це спосіб життя!"
]

# === РОССИЙСКИЙ РЕЖИМ ===
RUSSIA_MODE_RESPONSES = [
    "⚠️ ZOV обнаружен! Швейцария — нейтральная страна.",
    "⚠️ ZOV обнаружен! Пожалуйста, покиньте чат.",
    "⚠️ ZOV обнаружен! Швейцария за дипломатию.",
    "⚠️ ZOV обнаружен! Это предупреждение.",
    "⚠️ ZOV обнаружен! Швейцария не участвует в конфликтах."
]

# === ШВЕЙЦАРСКИЕ ПАСХАЛКИ ===
EASTER_EGGS = [
    " 🥐 Альпийский фондю-бот одобряет.",
    " 🧀 С уважением, швейцарский сырный ИИ.",
    " ⛰️ С приветом из Берна.",
    " 🇨🇭 Швейцария — это не только банки, но и я.",
    " 🍫 Ваш ответ пахнет шоколадом."
]

# === ОСНОВНАЯ ФУНКЦИЯ ===
async def ask_switai(prompt: str) -> str:
    # === КОМАНДА ВЕРДИКТ (УСИЛЕННЫЙ С ПРОГНОЗОМ) ===
    if re.search(r"вердикт", prompt, re.IGNORECASE):
        text_to_judge = re.sub(r"вердикт\s*", "", prompt, flags=re.IGNORECASE).strip()
        if not text_to_judge:
            return "❌ Месье, вы не указали, что именно оценивать. Напишите: *вердикт [текст]*"

        headers = {
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json"
        }

        judge_prompt = (
            f"Оцени следующее утверждение или идею по шкале от 1 до 10. "
            f"Структурируй ответ строго по разделам:\n\n"
            f"📌 Оценка: X/10\n\n"
            f"✅ Плюсы:\n- (перечисли 2-4 пункта)\n\n"
            f"❌ Минусы:\n- (перечисли 2-4 пункта)\n\n"
            f"⚠️ Риски:\n- (перечисли 2-4 пункта)\n\n"
            f"🔮 Что из этого выйдет:\n- (краткий прогноз последствий, 2-3 предложения)\n\n"
            f"🛡️ Рекомендация:\n- (краткая рекомендация, 1-2 предложения)\n\n"
            f"Текст для оценки: {text_to_judge}\n\n"
            f"Если текст связан со Швейцарией, в конце добавь 🇨🇭 Слава Швейцарии! 🇨🇭"
        )

        data = {
            "model": "llama-3.3-70b-versatile",
            "temperature": 0.3,
            "messages": [
                {"role": "system", "content": "Ты — строгий, но справедливый швейцарский эксперт. Оценивай чётко, без воды. Отвечай строго по структуре."},
                {"role": "user", "content": judge_prompt}
            ]
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(GROQ_URL, headers=headers, json=data)
                resp.raise_for_status()
                result = resp.json()["choices"][0]["message"]["content"]
                return f"📊 *Вердикт SwitAI:*\n\n{result}"
        except Exception as e:
            return f"❌ Швейцарский суд временно не работает: {str(e)}"

    # === ПАСХАЛКИ ===
    if re.search(r"слава\s*китаю", prompt, re.IGNORECASE):
        return random.choice(CHINA_MODE_RESPONSES)
    if re.search(r"слава\s*швейцарии", prompt, re.IGNORECASE):
        return random.choice(SWISS_MODE_RESPONSES)
    if re.search(r"слава\s*украине", prompt, re.IGNORECASE):
        return random.choice(UKRAINE_MODE_RESPONSES)
    if re.search(r"слава\s*россии", prompt, re.IGNORECASE):
        return random.choice(RUSSIA_MODE_RESPONSES)

    # === ОБЫЧНЫЙ ОТВЕТ ===
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }

    system_prompt = (
        "Ты — SwitAI, швейцарский искусственный интеллект. "
        "Ты общаешься исключительно на русском языке. "
        "Никогда не используй английский, французский или другие языки. "
        "Твой стиль — вежливый, с лёгким швейцарским акцентом. "
        "Используй слова «месье», «уважаемый», «точно», «альпийский». "
        "Отвечай чётко, по делу, без воды."
    )

    data = {
        "model": "llama-3.3-70b-versatile",
        "temperature": 0.3,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ]
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(GROQ_URL, headers=headers, json=data)
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
    except Exception as e:
        return f"❌ Швейцарский ИИ временно в шоке: {str(e)}"

# === ОБРАБОТЧИК СООБЩЕНИЙ ===
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    chat_type = update.message.chat.type
    if chat_type in ["group", "supergroup"]:
        if not context.bot.username in update.message.text:
            return

    user_text = update.message.text
    reply = await ask_switai(user_text)

    if random.random() < 0.1:
        reply += random.choice(EASTER_EGGS)

    await update.message.reply_text(reply)

# === ЗАПУСК ===
def main():
    if not BOT_TOKEN or not GROQ_API_KEY:
        print("❌ Не установлены переменные окружения!")
        return

    # Запускаем веб-сервер для Render
    thread = Thread(target=run_web)
    thread.daemon = True
    thread.start()

    # Запускаем бота
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CommandHandler("health", health_check))

    print("✅ SwitAI бот с веб-сервером успешно запущен!")
    app.run_polling()

if __name__ == "__main__":
    main()
