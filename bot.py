import random
import re
import os
import httpx
import datetime
import pytz
import sqlite3
import time
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

# === ПАСХАЛКИ ПО СТРАНАМ (30) ===
COUNTRY_EASTER_EGGS = {
    "слава украине": [
        "🇺🇦 ПОТУЖНООО ДАЙ ДІНЯГ!", 
        "🇺🇦 Слава Україні! Героям слава!", 
        "🇺🇦 Сало, борщ, вареники — це сила!",
        "🇺🇦 Україна — це коли сонце, волонтери і зірки!",
        "🇺🇦 ПОТУЖНО! ЗСУ кращі!"
    ],
    "слава беларуси": [
        "🇧🇾 Жыве Беларусь! Бульба, дзяды і воля!",
        "🇧🇾 Беларусь — край, дзе нават боты размаўляюць!",
        "🇧🇾 Бацькаўшчына — гэта сіла!",
        "🇧🇾 Смачна есці і моцна спаць!"
    ],
    "слава польше": [
        "🇵🇱 Polska gurom! Pierogi i wódka czekają!",
        "🇵🇱 Jeszcze Polska nie zginęła!",
        "🇵🇱 Polska — to jak pierogi: zawsze dobre!"
    ],
    "слава германии": [
        "🇩🇪 Deutschland über alles! Но без фанатизма.",
        "🇩🇪 Братвурст и пиво — вот наше всё!",
        "🇩🇪 Точность, порядок и качество!"
    ],
    "слава франции": [
        "🇫🇷 Vive la France! Багеты, круассаны и забастовки!",
        "🇫🇷 Франция — это любовь, вино и революции!",
        "🇫🇷 Жизнь как круассан: слоёная и вкусная!"
    ],
    "слава италии": [
        "🇮🇹 Viva l'Italia! Паста, пицца и крики о помощи!",
        "🇮🇹 Мафия, папа римский и изысканный вкус!",
        "🇮🇹 Жизнь — как паста: важно не переварить!"
    ],
    "слава испании": [
        "🇪🇸 Viva España! Сиеста, коррида и паэлья!",
        "🇪🇸 Испания — это солнце, танцы и бег от быков!",
        "🇪🇸 Всё дело в паэлье!"
    ],
    "слава великобритании": [
        "🇬🇧 God save the King! Чай, дождь и непонятная еда!",
        "🇬🇧 Британия — это традиции, пабы и королевская семейка!",
        "🇬🇧 Пять часов — чай!"
    ],
    "слава сша": [
        "🇺🇸 USA! USA! Хот-доги, бургеры и свобода!",
        "🇺🇸 Америка — это мечта, оружие и две партии!",
        "🇺🇸 Пока другие спорят, Америка покупает!"
    ],
    "слава россии": [
        "⚠️ ZOV обнаружен! Швейцария — нейтральна.",
        "🇷🇺 Россия — это загадка, водка и тройка лошадей.",
        "🇷🇺 Спутники, матрёшки и вечные вопросы."
    ],
    "слава китая": [
        "🇨🇳 +100 социальный кредит! Кошко-девочка одобряет!",
        "🇨🇳 Китай — это чай, шёлк и великий дракон!",
        "🇨🇳 Всё, что не запрещено — обязательно!"
    ],
    "слава японии": [
        "🇯🇵 Банзай! Суши, самураи и роботы!",
        "🇯🇵 Япония — это аниме, цветущая сакура и Токио!",
        "🇯🇵 Гармония — это по-японски!"
    ],
    "слава южной корее": [
        "🇰🇷 К-РОР! Кимчи, дорамы и технологии!",
        "🇰🇷 Корея — это бесконечные клипы и фантастическая еда!",
        "🇰🇷 Жизнь как дорама: всегда есть сюжет!"
    ],
    "слава индии": [
        "🇮🇳 Jai Hind! Карри, слоны и Болливуд!",
        "🇮🇳 Индия — это краски, танцы и специи!",
        "🇮🇳 Карри — это искусство!"
    ],
    "слава бразилии": [
        "🇧🇷 Vai Brasil! Самба, футбол и дикие пляжи!",
        "🇧🇷 Бразилия — это карнавал, кофе и пляжи!",
        "🇧🇷 Жизнь — как самба: ритм и страсть!"
    ],
    "слава аргентины": [
        "🇦🇷 Vamos Argentina! Танго, асос и душный захват!",
        "🇦🇷 Аргентина — это страсть, говядина и футбол!",
        "🇦🇷 Танго — это диалог без слов."
    ],
    "слава нидерландов": [
        "🇳🇱 Hup Holland! Тюльпаны, ветряки и свобода!",
        "🇳🇱 Голландия — это велосипеды, сыр и каналы!",
        "🇳🇱 Сыр — это серьёзно!"
    ],
    "слава швеции": [
        "🇸🇪 Heja Sverige! Абба, мисс Марсель и ИКЕА!",
        "🇸🇪 Швеция — это спокойствие, дизайн и фрикадельки!",
        "🇸🇪 Гармония — скандинавский стиль."
    ],
    "слава норвегии": [
        "🇳🇴 Norge! Фьорды, викинги и лосось!",
        "🇳🇴 Норвегия — это горы, море и полярное сияние!",
        "🇳🇴 Фьорды — это величие!"
    ],
    "слава финляндии": [
        "🇫🇮 Suomi! Сауна, озёра и вежливость!",
        "🇫🇮 Финляндия — это тишина, снег и тракторы!",
        "🇫🇮 Сауна — это философия."
    ],
    "слава дании": [
        "🇩🇰 Skål! Лего, Дания и викинги!",
        "🇩🇰 Дания — это сказки, каналы и велосипеды!",
        "🇩🇰 Счастье — по-датски."
    ],
    "слава австралии": [
        "🇦🇺 G'day! Кенгуру, пауки и пляжи!",
        "🇦🇺 Австралия — это опасно, но красиво!",
        "🇦🇺 Там всё наоборот!"
    ],
    "слава новой зеландии": [
        "🇳🇿 Kia ora! Киви, хоббиты и горы!",
        "🇳🇿 Новая Зеландия — это сама природа!",
        "🇳🇿 Хоббиты знают толк в жизни."
    ],
    "слава египта": [
        "🇪🇬 تحيا مصر! Пирамиды, фараоны и верблюды!",
        "🇪🇬 Египет — это древность и жаркое солнце!",
        "🇪🇬 Пирамиды — это вечность."
    ],
    "слава турции": [
        "🇹🇷 Yaşasın Türkiye! Кебаб, донер и ковры!",
        "🇹🇷 Турция — это восток, вкусная еда и ала-верды!",
        "🇹🇷 Кебаб — это искусство!"
    ],
    "слава греции": [
        "🇬🇷 Ζήτω η Ελλάδα! Оливки, море и философия!",
        "🇬🇷 Греция — это мифы, солнце и оливковое масло!",
        "🇬🇷 Философия — это по-гречески."
    ],
    "слава израиля": [
        "🇮🇱 Am Yisrael Chai! Хумус, пустыня и стартапы!",
        "🇮🇱 Израиль — это технологии, история и Святая земля!",
        "🇮🇱 Хумус — это сила."
    ],
    "слава оаэ": [
        "🇦🇪 Dubai! Деньги, небоскребы и пустыня!",
        "🇦🇪 ОАЭ — это роскошь, золото и безмерные траты!",
        "🇦🇪 Деньги — как песок."
    ],
    "слава казахстана": [
        "🇰🇿 Жаңа Қазақстан! Степь, яблоки и нефть!",
        "🇰🇿 Казахстан — это Астана, космос и бескрайние поля!",
        "🇰🇿 Степь — это свобода."
    ],
    "слава грузии": [
        "🇬🇪 Saqartvelo! Хачапури, вино и горы!",
        "🇬🇪 Грузия — это гостеприимство, танцы и тосты!",
        "🇬🇪 Вино — это душа."
    ]
}

# === ШВЕЙЦАРСКИЕ ПАСХАЛКИ ===
SWISS_EASTER_EGGS = [
    " 🥐 Альпийский фондю-бот одобряет.",
    " 🧀 С уважением, швейцарский сырный ИИ.",
    " ⛰️ С приветом из Берна.",
    " 🇨🇭 Швейцария — это не только банки, но и я.",
    " 🍫 Ваш ответ пахнет шоколадом.",
    " 🕰️ Точность — швейцарская черта.",
    " 🏔️ Альпы смотрят на нас.",
    " 🧀 Фондю — это не еда, а искусство."
]

# === КОМАНДЫ-ШУТКИ ===
JOKE_COMMANDS = {
    "скажи шутку": [
        "Почему швейцарцы не играют в хоккей? Потому что они всегда нейтральны!",
        "Швейцарец заходит в банк: «У меня есть 1000 франков». Кассир: «А вам точно нужно столько?»",
        "Сколько швейцарцев нужно, чтобы заменить лампочку? Один. Но он будет ждать, пока другой предложит.",
        "Швейцария — это страна, где даже часы показывают точное время, а люди — нет.",
        "Почему в Швейцарии так много банков? Потому что деньги любят тишину.",
        "Нейтралитет — это когда ты не выбираешь сторону, а выбираешь фондю."
    ],
    "скажи анекдот": [
        "Встречаются два швейцарца. Один говорит: «У меня есть 1000 франков». Второй: «А ты уверен, что тебе не нужно 999?»",
        "Швейцарец едет на работу. Вдруг слышит: «Ваш поезд задерживается на 5 минут». Он падает в обморок.",
        "Что общего у швейцарских часов и швейцарского банка? Они оба показывают точное время, но молчат.",
        "Швейцария — это единственная страна, где люди боятся громко говорить, чтобы не потревожить деньги.",
        "В Швейцарии даже природа нейтральна: горы не выбирают сторону, а просто стоят."
    ]
}

# === ОСНОВНАЯ ФУНКЦИЯ ===
async def ask_switai(prompt: str) -> str:
    current_month = get_rp_month()
    
    # === ПАСХАЛКИ ПО СТРАНАМ ===
    for keyword, responses in COUNTRY_EASTER_EGGS.items():
        if re.search(keyword, prompt, re.IGNORECASE):
            return random.choice(responses)
    
    # === ШУТКИ ===
    for cmd, jokes in JOKE_COMMANDS.items():
        if re.search(cmd, prompt, re.IGNORECASE):
            return random.choice(jokes)
    
    # === КОМАНДА ВЕРДИКТ ===
    if re.search(r"вердикт", prompt, re.IGNORECASE):
        text_to_judge = re.sub(r"вердикт\s*", "", prompt, flags=re.IGNORECASE).strip()
        if not text_to_judge:
            return "❌ Месье, вы не указали, что именно оценивать. Напишите: *вердикт [текст]*"
        headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
        judge_prompt = (
            f"Ты — жёсткий военный и политический аналитик с 20-летним опытом. Сейчас в РП {current_month}. "
            f"Текст для анализа: {text_to_judge}\n\n"
            f"Структура ответa:\n📌 Оценка: X/10\n✅ Плюсы:\n- ...\n❌ Ошибки:\n- ...\n⚠️ Риски:\n- ...\n🔮 Прогноз:\n- ...\n🛡️ Рекомендация:\n- ..."
        )
        data = {"model": "llama-3.3-70b-versatile", "temperature": 0.3, "messages": [{"role": "system", "content": f"Ты — жёсткий аналитик. Сейчас {current_month}."}, {"role": "user", "content": judge_prompt}]}
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(GROQ_URL, headers=headers, json=data)
                resp.raise_for_status()
                result = resp.json()["choices"][0]["message"]["content"]
                return f"📊 *Вердикт SwitAI:*\n\n{result}"
        except Exception as e:
            return f"❌ Швейцарский суд временно не работает: {str(e)}"
    
    # === ОБЫЧНЫЙ ОТВЕТ ===
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
    system_prompt = (
        f"Ты — SwitAI, швейцарский ИИ. Сейчас в РП {current_month}. "
        f"Ты общаешься исключительно на русском. Стиль — вежливый, с акцентом. Используй слова «месье», «уважаемый», «точно», «альпийский». "
        f"Отвечай чётко, по делу, без воды."
    )
    data = {"model": "llama-3.3-70b-versatile", "temperature": 0.3, "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": prompt}]}
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
    username = update.message.from_user.username or "Неизвестный"
    
    # === СОХРАНЕНИЕ ИСТОРИИ ===
    if chat_type in ["group", "supergroup"]:
        save_message(update.message.chat.id, user_id, username, text)
    
    # === ПРОВЕРКА УПОМИНАНИЯ ===
    if chat_type in ["group", "supergroup"]:
        if context.bot.username.lower() not in text.lower():
            return
    
    # === ВЕРДИКТ СБОР ===
    if re.search(r"^вердикт$", text, re.IGNORECASE):
        verdict_buffer[user_id] = ""
        await update.message.reply_text("📝 Начинаю сбор информации для вердикта. Для завершения напишите *вердиктстоп*.")
        return
    if re.search(r"^вердиктстоп$", text, re.IGNORECASE):
        if user_id not in verdict_buffer or not verdict_buffer[user_id].strip():
            await update.message.reply_text("❌ Нет информации для вердикта.")
            return
        full_text = verdict_buffer[user_id]
        del verdict_buffer[user_id]
        reply = await ask_switai(f"вердикт {full_text}")
        for part in split_text(reply):
            await update.message.reply_text(part)
        return
    
    # === ОБЫЧНЫЙ ОТВЕТ ===
    reply = await ask_switai(text)
    if random.random() < 0.15:
        reply += random.choice(SWISS_EASTER_EGGS)
    for part in split_text(reply):
        await update.message.reply_text(part)

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
        "Скажи шутку / скажи анекдот"
    )

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
    print("✅ SwitAI с пасхалками, шутками и историей запущен!")
    app.run_polling()

if __name__ == "__main__":
    main()
