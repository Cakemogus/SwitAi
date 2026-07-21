import random
import re
import os
import httpx
import datetime
import pytz
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

# === ГЕНЕРАТОР МЕСЯЦА ПО МСК ===
def get_rp_month():
    tz = pytz.timezone('Europe/Moscow')
    now = datetime.datetime.now(tz)
    hour = now.hour
    month_index = (hour // 2) % 12
    months = [
        "январь", "февраль", "март", "апрель", "май", "июнь",
        "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь"
    ]
    return months[month_index]

# === ХРАНИЛИЩА ===
user_message_buffer = {}
verdict_buffer = {}
war_buffer = {}

# === ФУНКЦИЯ РАЗБИВКИ ДЛИННЫХ СООБЩЕНИЙ ===
def split_text(text, max_len=4000):
    if len(text) <= max_len:
        return [text]
    
    parts = []
    lines = text.split('\n')
    current_part = ""
    
    for line in lines:
        if len(current_part) + len(line) + 1 <= max_len:
            current_part += line + "\n"
        else:
            if current_part:
                parts.append(current_part.strip())
            current_part = line + "\n"
    
    if current_part:
        parts.append(current_part.strip())
    
    return parts

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
    current_month = get_rp_month()
    
    # === КОМАНДА ВЕРДИКТ ===
    if re.search(r"вердикт", prompt, re.IGNORECASE):
        text_to_judge = re.sub(r"вердикт\s*", "", prompt, flags=re.IGNORECASE).strip()
        if not text_to_judge:
            return "❌ Месье, вы не указали, что именно оценивать. Напишите: *вердикт [текст]*"

        headers = {
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json"
        }

        judge_prompt = (
            f"Ты — жёсткий военный и политический аналитик с 20-летним опытом. "
            f"Твоя задача — дать максимально детальный, профессиональный и критический разбор ситуации. "
            f"Ты не боишься указывать на ошибки, заниженные цифры и устаревшие тактики. "
            f"Сейчас в РП {current_month}. Учитывай это.\n\n"
            f"Текст для анализа: {text_to_judge}\n\n"
            f"Структурируй ответ строго по разделам. Будь максимально конкретным. Используй сравнения с реальными конфликтами (XXI век).\n\n"
            f"📌 *Оценка:* X/10\n"
            f"(кратко — почему такая оценка)\n\n"
            f"✅ *Плюсы:*\n"
            f"- (перечисли 2-4 сильных стороны плана)\n\n"
            f"❌ *Ошибки и слабые места:*\n"
            f"- (перечисли 3-5 конкретных ошибок: географические, тактические, демографические, логистические)\n"
            f"- (сравни с реальными конфликтами: Нагорный Карабах, Донбасс, Сирия)\n\n"
            f"⚠️ *Риски:*\n"
            f"- (перечисли 2-4 фактора, которые могут разрушить план)\n\n"
            f"🔮 *Что из этого выйдет:*\n"
            f"- (краткий прогноз последствий, 2-3 предложения)\n\n"
            f"📊 *Реалистичный прогноз:*\n"
            f"- (раздели на 3 сценария: лучший, средний, худший)\n\n"
            f"🛡️ *Рекомендация:*\n"
            f"- (1-2 предложения, что делать дальше)\n\n"
            f"💡 *Если бы это делал SwitAI (исправленная версия):*\n"
            f"- (краткий альтернативный план, 2-4 шага)"
        )

        data = {
            "model": "llama-3.3-70b-versatile",
            "temperature": 0.3,
            "messages": [
                {"role": "system", "content": f"Ты — жёсткий аналитик. Сейчас {current_month}. Не бойся критиковать. Отвечай чётко, без воды."},
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

    # === ВОЕННЫЙ АНАЛИЗ С ПОИСКОМ ===
    if re.search(r"война", prompt, re.IGNORECASE):
        text_to_analyze = re.sub(r"война\s*", "", prompt, flags=re.IGNORECASE).strip()
        if not text_to_analyze:
            return "❌ Месье, вы не указали данные для военного анализа."

        headers = {
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json"
        }

        war_prompt = (
            f"Ты — военный аналитик с 20-летним опытом. Сейчас в РП {current_month}. "
            f"Проанализируй военную ситуацию. Если не знаешь сил противника — используй веб-поиск через Groq Compound, чтобы найти актуальную информацию о вооружении, численности и тактике врага.\n\n"
            f"Данные от пользователя: {text_to_analyze}\n\n"
            f"Структурируй ответ:\n"
            f"🌍 Условия:\n- Местность, погода, время суток\n"
            f"⚔️ Анализ сил сторон:\n- ... (если данных нет — найди в интернете)\n"
            f"🗺️ Сценарий боевых действий:\n- ...\n"
            f"🎲 Шансы на победу:\n- Сторона А: X%\n- Сторона Б: Y%\n"
            f"💀 Прогноз потерь:\n- Сторона А: ...\n- Сторона Б: ...\n- Гражданские: ...\n"
            f"⏳ Продолжительность:\n- ...\n"
            f"🏁 Итог войны:\n- ...\n"
            f"⚠️ Риски:\n- ...\n"
            f"🛡️ Рекомендация:\n- ..."
        )

        data = {
            "model": "groq/compound",
            "temperature": 0.3,
            "messages": [
                {"role": "system", "content": f"Ты — военный аналитик. Сейчас {current_month}. Если не знаешь данных о враге — используй встроенный веб-поиск Groq для получения актуальной информации."},
                {"role": "user", "content": war_prompt}
            ]
        }

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(GROQ_URL, headers=headers, json=data)
                resp.raise_for_status()
                result = resp.json()["choices"][0]["message"]["content"]
                return f"⚔️ *Военный анализ SwitAI:*\n\n{result}"
        except Exception as e:
            return f"❌ Военный аналитик временно не доступен: {str(e)}"

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
        f"Ты — SwitAI, швейцарский искусственный интеллект. Сейчас в РП {current_month}. Учитывай это в ответах. "
        f"Ты общаешься исключительно на русском языке. "
        f"Никогда не используй английский, французский или другие языки. "
        f"Твой стиль — вежливый, с лёгким швейцарским акцентом. "
        f"Используй слова «месье», «уважаемый», «точно», «альпийский». "
        f"Отвечай чётко, по делу, без воды."
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
    text = update.message.text
    user_id = update.message.from_user.id

    # === ПРОВЕРКА УПОМИНАНИЯ В ГРУППЕ ===
    if chat_type in ["group", "supergroup"]:
        # Проверяем, есть ли упоминание бота в тексте
        if context.bot.username in text:
            pass  # упоминание есть
        else:
            # Проверяем через entities
            if not update.message.entities:
                return
            bot_mentioned = False
            for entity in update.message.entities:
                if entity.type == "mention" and text[entity.offset:entity.offset+entity.length] == f"@{context.bot.username}":
                    bot_mentioned = True
                    break
            if not bot_mentioned:
                return

    # === ВЕРДИКТ СБОР ===
    if re.search(r"^вердикт$", text, re.IGNORECASE):
        verdict_buffer[user_id] = ""
        await update.message.reply_text("📝 Начинаю сбор информации для вердикта. Пишите всё, что считаете нужным. Для завершения напишите *вердиктстоп*.")
        return

    if re.search(r"^вердиктстоп$", text, re.IGNORECASE):
        if user_id not in verdict_buffer or not verdict_buffer[user_id].strip():
            await update.message.reply_text("❌ Вы не отправили никакой информации для вердикта.")
            return
        full_text = verdict_buffer[user_id]
        del verdict_buffer[user_id]
        reply = await ask_switai(f"вердикт {full_text}")
        for part in split_text(reply):
            await update.message.reply_text(part)
        return

    # === ВОЙНА СБОР ===
    if re.search(r"^войнастарт$", text, re.IGNORECASE):
        war_buffer[user_id] = ""
        await update.message.reply_text("⚔️ Начинаю сбор данных для военного анализа. Пишите всё, что связано с войной. Для завершения напишите *войнастоп*.")
        return

    if re.search(r"^войнастоп$", text, re.IGNORECASE):
        if user_id not in war_buffer or not war_buffer[user_id].strip():
            await update.message.reply_text("❌ Вы не отправили никаких данных для военного анализа.")
            return
        full_text = war_buffer[user_id]
        del war_buffer[user_id]
        reply = await ask_switai(f"война {full_text}")
        for part in split_text(reply):
            await update.message.reply_text(part)
        return

    # === СОХРАНЕНИЕ В БУФЕРА ===
    if user_id in verdict_buffer:
        verdict_buffer[user_id] += " " + text
        await update.message.reply_text("📌 Информация сохранена. Продолжайте или напишите *вердиктстоп* для завершения.")
        return

    if user_id in war_buffer:
        war_buffer[user_id] += " " + text
        await update.message.reply_text("📌 Данные сохранены. Продолжайте или напишите *войнастоп* для завершения.")
        return

    # === ОБЫЧНЫЙ ОТВЕТ ===
    if len(text) <= 4096:
        reply = await ask_switai(text)
        if random.random() < 0.1:
            reply += random.choice(EASTER_EGGS)
        for part in split_text(reply):
            await update.message.reply_text(part)
        return

    # === ДЛИННЫЙ ТЕКСТ ===
    if user_id not in user_message_buffer:
        user_message_buffer[user_id] = text
        await update.message.reply_text("📄 Текст длинный. Жду продолжение...")
        return

    user_message_buffer[user_id] += " " + text
    full_text = user_message_buffer[user_id]
    del user_message_buffer[user_id]
    reply = await ask_switai(full_text)
    if random.random() < 0.1:
        reply += random.choice(EASTER_EGGS)
    for part in split_text(reply):
        await update.message.reply_text(part)

# === ЗАПУСК ===
def main():
    if not BOT_TOKEN or not GROQ_API_KEY:
        print("❌ Не установлены переменные окружения!")
        return

    thread = Thread(target=run_web)
    thread.daemon = True
    thread.start()

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CommandHandler("health", health_check))

    print("✅ SwitAI бот с авторазбивкой и поиском успешно запущен!")
    app.run_polling()

if __name__ == "__main__":
    main()
