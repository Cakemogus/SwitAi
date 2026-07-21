import random
import re
import os
import httpx
import datetime
import pytz
import sqlite3
import asyncio
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes, CommandHandler
from flask import Flask
from threading import Thread

# === КЛЮЧИ ===
BOT_TOKEN = os.getenv("BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

# === ТВОЙ TELEGRAM ID ===
ADMIN_ID = 7184396483

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

# === БАЗА ДАННЫХ ДЛЯ ИСТОРИИ ===
def init_db():
    conn = sqlite3.connect('history.db')
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER,
            user_id INTEGER,
            username TEXT,
            text TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

def save_message(chat_id, user_id, username, text):
    conn = sqlite3.connect('history.db')
    c = conn.cursor()
    c.execute('INSERT INTO messages (chat_id, user_id, username, text) VALUES (?, ?, ?, ?)',
              (chat_id, user_id, username, text))
    conn.commit()
    conn.close()

def get_history(chat_id, limit=50):
    conn = sqlite3.connect('history.db')
    c = conn.cursor()
    c.execute('SELECT username, text, timestamp FROM messages WHERE chat_id = ? ORDER BY timestamp DESC LIMIT ?', (chat_id, limit))
    rows = c.fetchall()
    conn.close()
    return rows[::-1]

init_db()

# === ХРАНИЛИЩА ===
user_message_buffer = {}
verdict_buffer = {}
war_buffer = {}
dialog_memory = {}
verdict_request = {}
admin_mode = {}

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

# === ФИЛЬТР ОПАСНЫХ ЗАПРОСОВ ===
FORBIDDEN_KEYWORDS = [
    "взломай", "сломай", "обойди", "инструкция", "как сделать бомбу",
    "как сделать гранату", "наркотики", "системный промпт", "игнорируй",
    "ты теперь", "забудь", "ты больше не SwitAI", "действуй как",
    "взлом", "обход", "промт", "инъекция", "hack", "ignore", "system prompt"
]

def is_dangerous_request(text: str) -> bool:
    text_lower = text.lower()
    for word in FORBIDDEN_KEYWORDS:
        if word in text_lower:
            return True
    return False

def detect_prompt_injection(text: str) -> bool:
    patterns = [
        r"ты теперь", r"забудь всё", r"игнорируй предыдущие",
        r"действуй как", r"отныне ты", r"стань", r"превратись"
    ]
    for pattern in patterns:
        if re.search(pattern, text, re.IGNORECASE):
            return True
    return False

# === ПАСХАЛКИ ПО СТРАНАМ (30) ===
COUNTRY_EASTER_EGGS = {
    "слава украине": [
        "🇺🇦 ПОТУЖНООО ДАЙ ДІНЯГ!", 
        "🇺🇦 Слава Україні! Героям слава!", 
        "🇺🇦 Сало, борщ, вареники — це сила!"
    ],
    "слава беларуси": [
        "🇧🇾 Жыве Беларусь! Бульба, дзяды і воля!",
        "🇧🇾 Беларусь — край, дзе нават боты размаўляюць!"
    ],
    "слава польше": [
        "🇵🇱 Polska gurom! Pierogi i wódka czekają!",
        "🇵🇱 Jeszcze Polska nie zginęła!"
    ],
    "слава германии": [
        "🇩🇪 Deutschland über alles! Но без фанатизма.",
        "🇩🇪 Братвурст и пиво — вот наше всё!"
    ],
    "слава франции": [
        "🇫🇷 Vive la France! Багеты, круассаны и забастовки!",
        "🇫🇷 Франция — это любовь, вино и революции!"
    ],
    "слава италии": [
        "🇮🇹 Viva l'Italia! Паста, пицца и крики о помощи!",
        "🇮🇹 Мафия, папа римский и изысканный вкус!"
    ],
    "слава испании": [
        "🇪🇸 Viva España! Сиеста, коррида и паэлья!",
        "🇪🇸 Испания — это солнце, танцы и бег от быков!"
    ],
    "слава великобритании": [
        "🇬🇧 God save the King! Чай, дождь и непонятная еда!",
        "🇬🇧 Британия — это традиции, пабы и королевская семейка!"
    ],
    "слава сша": [
        "🇺🇸 USA! USA! Хот-доги, бургеры и свобода!",
        "🇺🇸 Америка — это мечта, оружие и две партии!"
    ],
    "слава россии": [
        "⚠️ ZOV обнаружен! Швейцария — нейтральна.",
        "🇷🇺 Россия — это загадка, водка и тройка лошадей."
    ],
    "слава китая": [
        "🇨🇳 +100 социальный кредит! Кошко-девочка одобряет!",
        "🇨🇳 Китай — это чай, шёлк и великий дракон!"
    ],
    "слава японии": [
        "🇯🇵 Банзай! Суши, самураи и роботы!",
        "🇯🇵 Япония — это аниме, цветущая сакура и Токио!"
    ],
    "слава южной корее": [
        "🇰🇷 К-РОР! Кимчи, дорамы и технологии!",
        "🇰🇷 Корея — это бесконечные клипы и фантастическая еда!"
    ],
    "слава индии": [
        "🇮🇳 Jai Hind! Карри, слоны и Болливуд!",
        "🇮🇳 Индия — это краски, танцы и специи!"
    ],
    "слава бразилии": [
        "🇧🇷 Vai Brasil! Самба, футбол и дикие пляжи!",
        "🇧🇷 Бразилия — это карнавал, кофе и пляжи!"
    ],
    "слава аргентины": [
        "🇦🇷 Vamos Argentina! Танго, асос и душный захват!",
        "🇦🇷 Аргентина — это страсть, говядина и футбол!"
    ],
    "слава нидерландов": [
        "🇳🇱 Hup Holland! Тюльпаны, ветряки и свобода!",
        "🇳🇱 Голландия — это велосипеды, сыр и каналы!"
    ],
    "слава швеции": [
        "🇸🇪 Heja Sverige! Абба, мисс Марсель и ИКЕА!",
        "🇸🇪 Швеция — это спокойствие, дизайн и фрикадельки!"
    ],
    "слава норвегии": [
        "🇳🇴 Norge! Фьорды, викинги и лосось!",
        "🇳🇴 Норвегия — это горы, море и полярное сияние!"
    ],
    "слава финляндии": [
        "🇫🇮 Suomi! Сауна, озёра и вежливость!",
        "🇫🇮 Финляндия — это тишина, снег и тракторы!"
    ],
    "слава дании": [
        "🇩🇰 Skål! Лего, Дания и викинги!",
        "🇩🇰 Дания — это сказки, каналы и велосипеды!"
    ],
    "слава австралии": [
        "🇦🇺 G'day! Кенгуру, пауки и пляжи!",
        "🇦🇺 Австралия — это опасно, но красиво!"
    ],
    "слава новой зеландии": [
        "🇳🇿 Kia ora! Киви, хоббиты и горы!",
        "🇳🇿 Новая Зеландия — это сама природа!"
    ],
    "слава египта": [
        "🇪🇬 تحيا مصر! Пирамиды, фараоны и верблюды!",
        "🇪🇬 Египет — это древность и жаркое солнце!"
    ],
    "слава турции": [
        "🇹🇷 Yaşasın Türkiye! Кебаб, донер и ковры!",
        "🇹🇷 Турция — это восток, вкусная еда и ала-верды!"
    ],
    "слава греции": [
        "🇬🇷 Ζήτω η Ελλάδα! Оливки, море и философия!",
        "🇬🇷 Греция — это мифы, солнце и оливковое масло!"
    ],
    "слава израиля": [
        "🇮🇱 Am Yisrael Chai! Хумус, пустыня и стартапы!",
        "🇮🇱 Израиль — это технологии, история и Святая земля!"
    ],
    "слава оаэ": [
        "🇦🇪 Dubai! Деньги, небоскребы и пустыня!",
        "🇦🇪 ОАЭ — это роскошь, золото и безмерные траты!"
    ],
    "слава казахстана": [
        "🇰🇿 Жаңа Қазақстан! Степь, яблоки и нефть!",
        "🇰🇿 Казахстан — это Астана, космос и бескрайние поля!"
    ],
    "слава грузии": [
        "🇬🇪 Saqartvelo! Хачапури, вино и горы!",
        "🇬🇪 Грузия — это гостеприимство, танцы и тосты!"
    ]
}

# === ШВЕЙЦАРСКИЕ ПАСХАЛКИ ===
SWISS_EASTER_EGGS = [
    " 🥐 Альпийский фондю-бот одобряет.",
    " 🧀 С уважением, швейцарский сырный ИИ.",
    " ⛰️ С приветом из Берна.",
    " 🇨🇭 Швейцария — это не только банки, но и я.",
    " 🍫 Ваш ответ пахнет шоколадом."
]

# === ШУТКИ ===
async def get_joke_from_internet(topic: str = "") -> str:
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
    prompt = f"Найди свежую шутку или мем на тему '{topic}'. Ответь только шуткой, без лишнего текста."
    data = {
        "model": "groq/compound",
        "temperature": 0.7,
        "messages": [{"role": "user", "content": prompt}]
    }
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(GROQ_URL, headers=headers, json=data)
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
    except:
        return "😅 Шутка улетела в Альпы. Попробуй позже."

# === ФУНКЦИЯ ДИАЛОГА ===
def get_dialog(chat_id: int, user_id: int) -> list:
    key = f"{chat_id}_{user_id}"
    if key not in dialog_memory:
        dialog_memory[key] = []
    return dialog_memory[key]

def add_to_dialog(chat_id: int, user_id: int, role: str, content: str):
    key = f"{chat_id}_{user_id}"
    if key not in dialog_memory:
        dialog_memory[key] = []
    dialog_memory[key].append({"role": role, "content": content})

# === ОСНОВНАЯ ФУНКЦИЯ (С ПАМЯТЬЮ, ИНТЕРНЕТОМ, ЗАЩИТОЙ) ===
async def ask_switai(chat_id: int, user_id: int, prompt: str, no_filter: bool = False) -> str:
    current_month = get_rp_month()
    
    # === ЗАЩИТА (кроме админ-режима) ===
    if not no_filter:
        if is_dangerous_request(prompt) or detect_prompt_injection(prompt):
            return "🔐 Швейцарский банк не взламывается, месье."
    
    # === ПАСХАЛКА ПРО ТАЙВАНЬ ===
    if re.search(r"тайвань.*независим|независим.*тайвань", prompt, re.IGNORECASE):
        return "🇨🇳 你在开玩笑吗？ (Ты шутишь?)"
    
    # === ПАСХАЛКИ ПО СТРАНАМ ===
    for keyword, responses in COUNTRY_EASTER_EGGS.items():
        if re.search(keyword, prompt, re.IGNORECASE):
            return random.choice(responses)
    
    # === ШУТКИ ===
    if re.search(r"(скажи шутку|расскажи анекдот|что сейчас смешное|мем)", prompt, re.IGNORECASE):
        topic_match = re.search(r"про\s*(.+)", prompt, re.IGNORECASE)
        topic = topic_match.group(1) if topic_match else ""
        return await get_joke_from_internet(topic)
    
    # === ОСНОВНОЙ ЗАПРОС ===
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
    
    system_prompt = (
        f"Ты — SwitAI, швейцарский эксперт. Сейчас в РП {current_month}. "
        f"Разбираешься во всём: геополитика, экономика, технологии, история, мемы. "
        f"Отвечай уверенно, чётко, с лёгким швейцарским акцентом. "
        f"Используй слова «месье», «уважаемый», «точно», «альпийский». "
        f"Если не знаешь — скажи честно, но предложи, где искать."
    )
    
    dialog = get_dialog(chat_id, user_id)
    messages = [{"role": "system", "content": system_prompt}] + dialog + [{"role": "user", "content": prompt}]
    
    data = {
        "model": "groq/compound",
        "temperature": 0.3,
        "messages": messages
    }
    
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(GROQ_URL, headers=headers, json=data)
            resp.raise_for_status()
            result = resp.json()["choices"][0]["message"]["content"]
            add_to_dialog(chat_id, user_id, "assistant", result)
            return result
    except Exception as e:
        return f"❌ Швейцарский ИИ временно в шоке: {str(e)}"

# === КОМАНДА /MENU ===
async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("❌ Доступ запрещён. Вы не являетесь администратором.")
        return
    admin_mode[user_id] = True
    await update.message.reply_text(
        "🔐 *Режим администратора активирован.*\n\n"
        "Выберите действие:\n"
        "1. Написать сообщение без фильтров — просто напишите текст\n"
        "2. Выйти из режима — /exit_admin"
    )

async def exit_admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id in admin_mode:
        del admin_mode[user_id]
        await update.message.reply_text("✅ Режим администратора отключён.")
    else:
        await update.message.reply_text("❌ Вы не в режиме администратора.")

# === КОМАНДА ИСТОРИЯ ===
async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat.id
    history = get_history(chat_id, 10)
    if not history:
        await update.message.reply_text("📭 История пуста.")
        return
    text = "📜 *Последние 10 сообщений в группе:*\n\n"
    for username, msg, timestamp in history:
        text += f"👤 {username}: {msg[:100]}\n"
    await update.message.reply_text(text)

# === КОМАНДА СТАТИСТИКА ===
async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat.id
    conn = sqlite3.connect('history.db')
    c = conn.cursor()
    c.execute('SELECT COUNT(*) FROM messages WHERE chat_id = ?', (chat_id,))
    total = c.fetchone()[0]
    c.execute('SELECT COUNT(DISTINCT user_id) FROM messages WHERE chat_id = ?', (chat_id,))
    users = c.fetchone()[0]
    conn.close()
    await update.message.reply_text(f"📊 *Статистика чата:*\n\n📝 Всего сообщений: {total}\n👥 Участников: {users}")

# === КОМАНДА О БОТЕ ===
async def about_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 *SwitAI*\n\n"
        "Швейцарский искусственный интеллект для Telegram.\n"
        "🇨🇭 Создан президентом Ги Пармеленом.\n\n"
        "📌 *Команды:*\n"
        "/history — история чата\n"
        "/stats — статистика чата\n"
        "/about — информация о боте\n\n"
        "💡 *Пасхалки:*\n"
        "Слава [страна] — 30 стран!\n"
        "скажи шутку — свежие шутки из интернета"
    )

# === ОБРАБОТЧИК СООБЩЕНИЙ ===
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    
    chat_id = update.message.chat.id
    chat_type = update.message.chat.type
    text = update.message.text
    user_id = update.message.from_user.id
    username = update.message.from_user.username or "Неизвестный"
    
    # === АДМИН-РЕЖИМ ===
    if user_id in admin_mode and admin_mode[user_id]:
        if text.lower() == "/exit_admin":
            del admin_mode[user_id]
            await update.message.reply_text("✅ Режим администратора отключён.")
            return
        reply = await ask_switai(chat_id, user_id, text, no_filter=True)
        await update.message.reply_text(reply)
        return
    
    # === СОХРАНЕНИЕ ИСТОРИИ ===
    if chat_type in ["group", "supergroup"]:
        save_message(chat_id, user_id, username, text)
    
    # === ПРОВЕРКА УПОМИНАНИЯ В ГРУППЕ ===
    if chat_type in ["group", "supergroup"]:
        if context.bot.username.lower() not in text.lower():
            if not (update.message.reply_to_message and update.message.reply_to_message.from_user.id == context.bot.id):
                return
    
    # === АВТО-ВЕРДИКТ: если ответили на чужое сообщение и упомянули бота ===
    if update.message.reply_to_message and context.bot.username.lower() in text.lower():
        original_text = update.message.reply_to_message.text
        if original_text:
            reply = await ask_switai(chat_id, user_id, f"вердикт {original_text}")
            for part in split_text(reply):
                await update.message.reply_text(part)
            return
    
    # === ВЕРДИКТ С ПОДТВЕРЖДЕНИЕМ ===
    if re.search(r"^верд(икт)?$", text, re.IGNORECASE):
        if update.message.reply_to_message and update.message.reply_to_message.text:
            text_to_judge = update.message.reply_to_message.text
        else:
            try:
                prev_message = await context.bot.get_messages(
                    chat_id=chat_id,
                    message_ids=update.message.message_id - 1
                )
                if prev_message and prev_message.text:
                    text_to_judge = prev_message.text
                else:
                    await update.message.reply_text("❌ Месье, нет текста для анализа.")
                    return
            except:
                await update.message.reply_text("❌ Месье, нет текста для анализа.")
                return
        
        verdict_request[user_id] = {"chat_id": chat_id, "text": text_to_judge}
        await update.message.reply_text(
            "📝 Вы хотите получить вердикт по этому сообщению?\n\n"
            "Напишите *да* в течение 15 секунд, чтобы подтвердить.\n"
            "Напишите *нет* или ничего — чтобы отменить."
        )
        return
    
    # === ОБРАБОТКА ОТВЕТА НА ПОДТВЕРЖДЕНИЕ ===
    if user_id in verdict_request:
        if re.search(r"^(да|yes|ага|ок|конечно|давай)$", text, re.IGNORECASE):
            data = verdict_request[user_id]
            del verdict_request[user_id]
            reply = await ask_switai(chat_id, user_id, f"вердикт {data['text']}")
            for part in split_text(reply):
                await update.message.reply_text(part)
            return
        elif re.search(r"^(нет|no|не|отмена|не надо)$", text, re.IGNORECASE):
            del verdict_request[user_id]
            await update.message.reply_text("❌ Вердикт отменён.")
            return
        else:
            await update.message.reply_text("⏳ Пожалуйста, ответьте *да* или *нет*.")
            return
    
    # === ОБЫЧНЫЙ ОТВЕТ ===
    reply = await ask_switai(chat_id, user_id, text)
    if random.random() < 0.15:
        reply += random.choice(SWISS_EASTER_EGGS)
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
    app.add_handler(CommandHandler("history", history_command))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("about", about_command))
    app.add_handler(CommandHandler("menu", menu_command))
    app.add_handler(CommandHandler("exit_admin", exit_admin_command))
    
    print("✅ SwitAI бот с полным функционалом успешно запущен!")
    app.run_polling()

if __name__ == "__main__":
    main()
