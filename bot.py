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

# === ТВОИ ДАННЫЕ ===
ADMIN_ID = 7184396483
ADMIN_USERNAME = "cakemogus"

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

# === БАЗА ДАННЫХ ===
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
    c.execute('''
        CREATE TABLE IF NOT EXISTS dialog_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER,
            user_id INTEGER,
            role TEXT,
            content TEXT,
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

def save_dialog(chat_id, user_id, role, content):
    conn = sqlite3.connect('history.db')
    c = conn.cursor()
    c.execute('INSERT INTO dialog_history (chat_id, user_id, role, content) VALUES (?, ?, ?, ?)',
              (chat_id, user_id, role, content))
    conn.commit()
    conn.close()

def get_dialog_history(chat_id, user_id, limit=50):
    conn = sqlite3.connect('history.db')
    c = conn.cursor()
    c.execute('''
        SELECT role, content FROM dialog_history
        WHERE chat_id = ? AND user_id = ?
        ORDER BY timestamp DESC LIMIT ?
    ''', (chat_id, user_id, limit))
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
muted_users = {}
warn_count = {}
filter_enabled = True
bot_mode = "normal"

# === ФУНКЦИЯ РАЗБИВКИ ===
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

# === ПРОВЕРКА АДМИНА ===
def is_admin(user_id: int, username: str) -> bool:
    if user_id == ADMIN_ID:
        return True
    if username and username.lower() == ADMIN_USERNAME.lower():
        return True
    return False

# === ФИЛЬТР ===
FORBIDDEN_KEYWORDS = [
    "взломай", "сломай", "обойди", "инструкция", "как сделать бомбу",
    "как сделать гранату", "наркотики", "системный промпт", "игнорируй",
    "ты теперь", "забудь", "ты больше не SwitAI", "действуй как"
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

# === ПАСХАЛКИ ===
COUNTRY_EASTER_EGGS = {
    "слава украине": ["🇺🇦 ПОТУЖНООО ДАЙ ДІНЯГ!", "🇺🇦 Слава Україні! Героям слава!", "🇺🇦 Сало, борщ, вареники — це сила!"],
    "слава беларуси": ["🇧🇾 Жыве Беларусь! Бульба, дзяды і воля!", "🇧🇾 Беларусь — край, дзе нават боты размаўляюць!"],
    "слава польше": ["🇵🇱 Polska gurom! Pierogi i wódka czekają!", "🇵🇱 Jeszcze Polska nie zginęła!"],
    "слава германии": ["🇩🇪 Deutschland über alles! Но без фанатизма.", "🇩🇪 Братвурст и пиво — вот наше всё!"],
    "слава франции": ["🇫🇷 Vive la France! Багеты, круассаны и забастовки!", "🇫🇷 Франция — это любовь, вино и революции!"],
    "слава италии": ["🇮🇹 Viva l'Italia! Паста, пицца и крики о помощи!", "🇮🇹 Мафия, папа римский и изысканный вкус!"],
    "слава испании": ["🇪🇸 Viva España! Сиеста, коррида и паэлья!", "🇪🇸 Испания — это солнце, танцы и бег от быков!"],
    "слава великобритании": ["🇬🇧 God save the King! Чай, дождь и непонятная еда!", "🇬🇧 Британия — это традиции, пабы и королевская семейка!"],
    "слава сша": ["🇺🇸 USA! USA! Хот-доги, бургеры и свобода!", "🇺🇸 Америка — это мечта, оружие и две партии!"],
    "слава россии": ["⚠️ ZOV обнаружен! Швейцария — нейтральна.", "🇷🇺 Россия — это загадка, водка и тройка лошадей."],
    "слава китая": ["🇨🇳 +100 социальный кредит! Кошко-девочка одобряет!", "🇨🇳 Китай — это чай, шёлк и великий дракон!"],
    "слава японии": ["🇯🇵 Банзай! Суши, самураи и роботы!", "🇯🇵 Япония — это аниме, цветущая сакура и Токио!"],
    "слава южной корее": ["🇰🇷 К-РОР! Кимчи, дорамы и технологии!", "🇰🇷 Корея — это бесконечные клипы и фантастическая еда!"],
    "слава индии": ["🇮🇳 Jai Hind! Карри, слоны и Болливуд!", "🇮🇳 Индия — это краски, танцы и специи!"],
    "слава бразилии": ["🇧🇷 Vai Brasil! Самба, футбол и дикие пляжи!", "🇧🇷 Бразилия — это карнавал, кофе и пляжи!"],
    "слава аргентины": ["🇦🇷 Vamos Argentina! Танго, асос и душный захват!", "🇦🇷 Аргентина — это страсть, говядина и футбол!"],
    "слава нидерландов": ["🇳🇱 Hup Holland! Тюльпаны, ветряки и свобода!", "🇳🇱 Голландия — это велосипеды, сыр и каналы!"],
    "слава швеции": ["🇸🇪 Heja Sverige! Абба, мисс Марсель и ИКЕА!", "🇸🇪 Швеция — это спокойствие, дизайн и фрикадельки!"],
    "слава норвегии": ["🇳🇴 Norge! Фьорды, викинги и лосось!", "🇳🇴 Норвегия — это горы, море и полярное сияние!"],
    "слава финляндии": ["🇫🇮 Suomi! Сауна, озёра и вежливость!", "🇫🇮 Финляндия — это тишина, снег и тракторы!"],
    "слава дании": ["🇩🇰 Skål! Лего, Дания и викинги!", "🇩🇰 Дания — это сказки, каналы и велосипеды!"],
    "слава австралии": ["🇦🇺 G'day! Кенгуру, пауки и пляжи!", "🇦🇺 Австралия — это опасно, но красиво!"],
    "слава новой зеландии": ["🇳🇿 Kia ora! Киви, хоббиты и горы!", "🇳🇿 Новая Зеландия — это сама природа!"],
    "слава египта": ["🇪🇬 تحيا مصر! Пирамиды, фараоны и верблюды!", "🇪🇬 Египет — это древность и жаркое солнце!"],
    "слава турции": ["🇹🇷 Yaşasın Türkiye! Кебаб, донер и ковры!", "🇹🇷 Турция — это восток, вкусная еда и ала-верды!"],
    "слава греции": ["🇬🇷 Ζήτω η Ελλάδα! Оливки, море и философия!", "🇬🇷 Греция — это мифы, солнце и оливковое масло!"],
    "слава израиля": ["🇮🇱 Am Yisrael Chai! Хумус, пустыня и стартапы!", "🇮🇱 Израиль — это технологии, история и Святая земля!"],
    "слава оаэ": ["🇦🇪 Dubai! Деньги, небоскребы и пустыня!", "🇦🇪 ОАЭ — это роскошь, золото и безмерные траты!"],
    "слава казахстана": ["🇰🇿 Жаңа Қазақстан! Степь, яблоки и нефть!", "🇰🇿 Казахстан — это Астана, космос и бескрайние поля!"],
    "слава грузии": ["🇬🇪 Saqartvelo! Хачапури, вино и горы!", "🇬🇪 Грузия — это гостеприимство, танцы и тосты!"]
}

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

# === ОСНОВНАЯ ФУНКЦИЯ ===
async def ask_switai(chat_id: int, user_id: int, prompt: str, no_filter: bool = False) -> str:
    current_month = get_rp_month()
    
    if not no_filter and filter_enabled:
        if is_dangerous_request(prompt) or detect_prompt_injection(prompt):
            return "🔐 Швейцарский банк не взламывается, месье."
    
    if re.search(r"тайвань.*независим|независим.*тайвань", prompt, re.IGNORECASE):
        return "🇨🇳 你在开玩笑吗？ (Ты шутишь?)"
    
    for keyword, responses in COUNTRY_EASTER_EGGS.items():
        if re.search(keyword, prompt, re.IGNORECASE):
            return random.choice(responses)
    
    if re.search(r"(скажи шутку|расскажи анекдот|что сейчас смешное|мем)", prompt, re.IGNORECASE):
        topic_match = re.search(r"про\s*(.+)", prompt, re.IGNORECASE)
        topic = topic_match.group(1) if topic_match else ""
        return await get_joke_from_internet(topic)
    
    save_dialog(chat_id, user_id, "user", prompt)
    history = get_dialog_history(chat_id, user_id, limit=50)
    
    messages = [{"role": "system", "content": f"Ты — SwitAI, швейцарский эксперт. Сейчас в РП {current_month}. Ты помнишь всю историю диалога. Отвечай с учётом предыдущих сообщений."}]
    for role, content in history:
        messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": prompt})
    
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
    data = {
        "model": "groq/compound",
        "temperature": 0.3,
        "messages": messages
    }
    
    try:
        await asyncio.sleep(0.5)
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(GROQ_URL, headers=headers, json=data)
            resp.raise_for_status()
            result = resp.json()["choices"][0]["message"]["content"]
            save_dialog(chat_id, user_id, "assistant", result)
            return result
    except Exception as e:
        return f"❌ Швейцарский ИИ временно в шоке: {str(e)}"

# === АДМИН-КОМАНДЫ ===
async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    username = update.message.from_user.username
    if not is_admin(user_id, username):
        await update.message.reply_text("❌ Доступ запрещён.")
        return
    chat_id = update.message.chat.id
    admin_mode[chat_id] = True
    await update.message.reply_text(
        "🔐 *Режим администратора активирован в этом чате.*\n\n"
        "📌 /debug — состояние системы\n"
        "/clear_memory — очистить мою память\n"
        "/clear_all_memory — очистить всю память\n"
        "/set_filter [on/off] — включить/выключить защиту\n"
        "/set_mode [normal/expert] — сменить режим\n"
        "/reset_bot — сбросить бота\n"
        "/stats — статистика чата\n"
        "/history — история сообщений\n"
        "/warn @user — предупреждение\n"
        "/mute @user минуты — заглушить\n"
        "/unmute @user — размутить\n"
        "/kick @user — кикнуть\n"
        "/ban @user — забанить\n"
        "/userinfo @user — информация\n"
        "/say текст — написать от имени бота\n"
        "/clear_chat — очистить историю чата\n"
        "/exit_admin — выйти"
    )

async def exit_admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat.id
    if chat_id in admin_mode:
        del admin_mode[chat_id]
        await update.message.reply_text("✅ Режим администратора отключён в этом чате.")
    else:
        await update.message.reply_text("❌ Режим администратора не активирован.")

async def debug_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    username = update.message.from_user.username
    if not is_admin(user_id, username):
        await update.message.reply_text("❌ Доступ запрещён.")
        return
    chat_id = update.message.chat.id
    dialog = get_dialog_history(chat_id, user_id, 10)
    await update.message.reply_text(
        f"🧠 *Состояние системы:*\n\n"
        f"📝 Сообщений в диалоге: {len(dialog)}\n"
        f"👤 ID: {user_id}\n"
        f"💬 Чат ID: {chat_id}\n"
        f"🔒 Фильтр: {'Вкл' if filter_enabled else 'Выкл'}\n"
        f"📋 Режим: {bot_mode}"
    )

async def clear_memory_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    username = update.message.from_user.username
    if not is_admin(user_id, username):
        await update.message.reply_text("❌ Доступ запрещён.")
        return
    chat_id = update.message.chat.id
    key = f"{chat_id}_{user_id}"
    if key in dialog_memory:
        del dialog_memory[key]
    await update.message.reply_text("🧹 Моя память очищена.")

async def clear_all_memory_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    username = update.message.from_user.username
    if not is_admin(user_id, username):
        await update.message.reply_text("❌ Доступ запрещён.")
        return
    dialog_memory.clear()
    await update.message.reply_text("🧹 Вся память очищена.")

async def set_filter_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    username = update.message.from_user.username
    if not is_admin(user_id, username):
        await update.message.reply_text("❌ Доступ запрещён.")
        return
    args = context.args
    if not args:
        await update.message.reply_text("❌ Укажите on или off. Пример: /set_filter on")
        return
    global filter_enabled
    if args[0].lower() == "on":
        filter_enabled = True
        await update.message.reply_text("✅ Фильтр включён.")
    elif args[0].lower() == "off":
        filter_enabled = False
        await update.message.reply_text("✅ Фильтр отключён.")
    else:
        await update.message.reply_text("❌ Используйте on или off.")

async def set_mode_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    username = update.message.from_user.username
    if not is_admin(user_id, username):
        await update.message.reply_text("❌ Доступ запрещён.")
        return
    args = context.args
    if not args:
        await update.message.reply_text("❌ Укажите normal или expert. Пример: /set_mode expert")
        return
    global bot_mode
    if args[0].lower() in ["normal", "expert"]:
        bot_mode = args[0].lower()
        await update.message.reply_text(f"✅ Режим изменён на {bot_mode}.")
    else:
        await update.message.reply_text("❌ Используйте normal или expert.")

async def reset_bot_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    username = update.message.from_user.username
    if not is_admin(user_id, username):
        await update.message.reply_text("❌ Доступ запрещён.")
        return
    dialog_memory.clear()
    verdict_buffer.clear()
    war_buffer.clear()
    await update.message.reply_text("🔄 Бот сброшен (память и буферы очищены).")

async def warn_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    username = update.message.from_user.username
    if not is_admin(user_id, username):
        await update.message.reply_text("❌ Доступ запрещён.")
        return
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("❌ Используйте: /warn @username причина")
        return
    target = args[0]
    reason = " ".join(args[1:])
    if target not in warn_count:
        warn_count[target] = 0
    warn_count[target] += 1
    await update.message.reply_text(f"⚠️ {target} получил предупреждение.\nПричина: {reason}\nВсего: {warn_count[target]}")

async def mute_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    username = update.message.from_user.username
    if not is_admin(user_id, username):
        await update.message.reply_text("❌ Доступ запрещён.")
        return
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("❌ Используйте: /mute @username минуты")
        return
    target = args[0]
    minutes = int(args[1])
    muted_users[target] = minutes
    await update.message.reply_text(f"🔇 {target} заглушён на {minutes} минут.")

async def unmute_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    username = update.message.from_user.username
    if not is_admin(user_id, username):
        await update.message.reply_text("❌ Доступ запрещён.")
        return
    args = context.args
    if not args:
        await update.message.reply_text("❌ Используйте: /unmute @username")
        return
    target = args[0]
    if target in muted_users:
        del muted_users[target]
        await update.message.reply_text(f"🔊 {target} размучен.")
    else:
        await update.message.reply_text(f"❌ {target} не в муте.")

async def kick_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    username = update.message.from_user.username
    if not is_admin(user_id, username):
        await update.message.reply_text("❌ Доступ запрещён.")
        return
    args = context.args
    if not args:
        await update.message.reply_text("❌ Используйте: /kick @username")
        return
    target = args[0]
    await update.message.reply_text(f"👢 {target} кикнут из чата.")

async def ban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    username = update.message.from_user.username
    if not is_admin(user_id, username):
        await update.message.reply_text("❌ Доступ запрещён.")
        return
    args = context.args
    if not args:
        await update.message.reply_text("❌ Используйте: /ban @username")
        return
    target = args[0]
    await update.message.reply_text(f"🚫 {target} забанен навсегда.")

async def userinfo_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    username = update.message.from_user.username
    if not is_admin(user_id, username):
        await update.message.reply_text("❌ Доступ запрещён.")
        return
    args = context.args
    if not args:
        await update.message.reply_text("❌ Используйте: /userinfo @username")
        return
    target = args[0]
    warns = warn_count.get(target, 0)
    muted = target in muted_users
    await update.message.reply_text(
        f"👤 *Информация об игроке:*\n\n"
        f"Ник: {target}\n"
        f"⚠️ Предупреждений: {warns}\n"
        f"🔇 Заглушён: {'Да' if muted else 'Нет'}"
    )

async def say_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    username = update.message.from_user.username
    if not is_admin(user_id, username):
        await update.message.reply_text("❌ Доступ запрещён.")
        return
    args = context.args
    if not args:
        await update.message.reply_text("❌ Используйте: /say текст")
        return
    text = " ".join(args)
    await update.message.reply_text(text)

async def clear_chat_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    username = update.message.from_user.username
    if not is_admin(user_id, username):
        await update.message.reply_text("❌ Доступ запрещён.")
        return
    chat_id = update.message.chat.id
    conn = sqlite3.connect('history.db')
    c = conn.cursor()
    c.execute('DELETE FROM messages WHERE chat_id = ?', (chat_id,))
    conn.commit()
    conn.close()
    await update.message.reply_text("🧹 История чата очищена.")

# === КОМАНДЫ ДЛЯ ВСЕХ ===
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
    if chat_id in admin_mode and admin_mode[chat_id]:
        if not is_admin(user_id, username):
            del admin_mode[chat_id]
            await update.message.reply_text("❌ Доступ отозван. Вы не администратор.")
            return
        if text.lower() == "/exit_admin":
            del admin_mode[chat_id]
            await update.message.reply_text("✅ Режим администратора отключён в этом чате.")
            return
        reply = await ask_switai(chat_id, user_id, text, no_filter=True)
        await update.message.reply_text(reply)
        return
    
    # === СОХРАНЕНИЕ ИСТОРИИ ===
    if chat_type in ["group", "supergroup"]:
        save_message(chat_id, user_id, username, text)
    
    # === ПРОВЕРКА УПОМИНАНИЯ ===
    if chat_type in ["group", "supergroup"]:
        if context.bot.username.lower() not in text.lower():
            if not (update.message.reply_to_message and update.message.reply_to_message.from_user.id == context.bot.id):
                return
    
    # === АВТО-ВЕРДИКТ ===
    if update.message.reply_to_message and context.bot.username.lower() in text.lower():
        original_text = update.message.reply_to_message.text
        if original_text:
            reply = await ask_switai(chat_id, user_id, f"вердикт {original_text}")
            for part in split_text(reply):
                await update.message.reply_text(part)
            return
    
    # === ВЕРДИКТ ===
    if re.search(r"^верд(икт)?$", text, re.IGNORECASE):
        if update.message.reply_to_message and update.message.reply_to_message.text:
            text_to_judge = update.message.reply_to_message.text
        else:
            try:
                prev_message = await context.bot.get_messages(chat_id=chat_id, message_ids=update.message.message_id - 1)
                if prev_message and prev_message.text:
                    text_to_judge = prev_message.text
                else:
                    await update.message.reply_text("❌ Месье, нет текста для анализа.")
                    return
            except:
                await update.message.reply_text("❌ Месье, нет текста для анализа.")
                return
        verdict_request[user_id] = {"chat_id": chat_id, "text": text_to_judge}
        await update.message.reply_text("📝 Вы хотите получить вердикт? Напишите *да* или *нет*.")
        return
    
    # === ПОДТВЕРЖДЕНИЕ ===
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
    app.add_handler(CommandHandler("debug", debug_command))
    app.add_handler(CommandHandler("clear_memory", clear_memory_command))
    app.add_handler(CommandHandler("clear_all_memory", clear_all_memory_command))
    app.add_handler(CommandHandler("set_filter", set_filter_command))
    app.add_handler(CommandHandler("set_mode", set_mode_command))
    app.add_handler(CommandHandler("reset_bot", reset_bot_command))
    app.add_handler(CommandHandler("warn", warn_command))
    app.add_handler(CommandHandler("mute", mute_command))
    app.add_handler(CommandHandler("unmute", unmute_command))
    app.add_handler(CommandHandler("kick", kick_command))
    app.add_handler(CommandHandler("ban", ban_command))
    app.add_handler(CommandHandler("userinfo", userinfo_command))
    app.add_handler(CommandHandler("say", say_command))
    app.add_handler(CommandHandler("clear_chat", clear_chat_command))
    
    print("✅ SwitAI финальная версия запущена!")
    app.run_polling()

if __name__ == "__main__":
    main()
