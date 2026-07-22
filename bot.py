import random
import re
import os
import httpx
import datetime
import pytz
import asyncio
import json
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes, CommandHandler
from flask import Flask
from threading import Thread

# === ИМПОРТЫ ИЗ ФАЙЛОВ ===
from jokes import SWISS_EASTER_EGGS, JOKE_COMMANDS, DARK_JOKES
from triggers import (
    COUNTRY_TRIGGERS, FOOTBALL_TRIGGERS, TAIWAN_TRIGGER,
    contains_mate, is_dangerous_request, detect_prompt_injection
)
from history import (
    add_to_history, get_user_history, get_context_with_history,
    clear_user_history, clear_all_history
)

# === КЛЮЧИ ===
BOT_TOKEN = os.getenv("BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

# === ТВОИ ДАННЫЕ ===
ADMIN_ID = 7184396483
ADMIN_USERNAME = "cakemogus"

# === ГЛОБАЛЬНАЯ ПЕРЕМЕННАЯ ДЛЯ ОСТАНОВКИ ===
bot_stopped = False

# === ФАЙЛ ДЛЯ СОХРАНЁННЫХ ЧАТОВ ===
SAVED_CHATS_FILE = "saved_chats.json"

def load_saved_chats():
    if os.path.exists(SAVED_CHATS_FILE):
        try:
            with open(SAVED_CHATS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_saved_chats(chats):
    with open(SAVED_CHATS_FILE, "w", encoding="utf-8") as f:
        json.dump(chats, f, ensure_ascii=False, indent=2)

saved_chats = load_saved_chats()

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

# === ФУНКЦИЯ ПОЛУЧЕНИЯ ШУТКИ ===
def get_joke_by_command(command: str) -> str:
    for key, jokes in JOKE_COMMANDS.items():
        if re.search(key, command, re.IGNORECASE):
            return random.choice(jokes)
    return None

# === ОСНОВНАЯ ФУНКЦИЯ ===
async def ask_switai(chat_id: int, user_id: int, prompt: str, no_filter: bool = False) -> str:
    current_month = get_rp_month()
    
    # === ФИЛЬТР МАТА ===
    if contains_mate(prompt):
        return "Месье, я предпочитаю не обсуждать такие темы. Давайте поговорим о чём-то более альпийском. ⛰️"
    
    if not no_filter and filter_enabled:
        if is_dangerous_request(prompt) or detect_prompt_injection(prompt):
            return "🔐 Швейцарский банк не взламывается, месье."
    
    # === ТРИГГЕР НА ТАЙВАНЬ ===
    if re.search(r"тайвань.*независим|независим.*тайвань", prompt, re.IGNORECASE):
        return TAIWAN_TRIGGER
    
    # === ТРИГГЕР НА ФУТБОЛ ===
    for name, response in FOOTBALL_TRIGGERS.items():
        if re.search(name, prompt, re.IGNORECASE):
            return response
    
    # === ТРИГГЕРЫ ПО СТРАНАМ ===
    for keyword, responses in COUNTRY_TRIGGERS.items():
        if re.search(keyword, prompt, re.IGNORECASE):
            return random.choice(responses)
    
    # === ШУТКИ ===
    joke = get_joke_by_command(prompt)
    if joke:
        return joke
    
    # === ЧЁРНЫЕ ШУТКИ ===
    if re.search(r"скажи чёрную шутку", prompt, re.IGNORECASE):
        return random.choice(DARK_JOKES)
    
    # === ВЕРДИКТ С ПРОШЛЫМИ ===
    if "вердикт" in prompt.lower():
        topic = re.sub(r"вердикт\s*", "", prompt, flags=re.IGNORECASE).strip()
        if not topic:
            return "❌ Месье, укажите тему для вердикта."

        past_verdicts = []
        history = get_user_history(chat_id, user_id, limit=50)
        for msg in history:
            if "вердикт" in msg['content'].lower() and topic.lower() in msg['content'].lower():
                past_verdicts.append(msg['content'])

        headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
        verdict_prompt = (
            f"Ты — SwitAI, швейцарский аналитик. Сделай вердикт на тему: {topic}.\n\n"
            f"Если есть прошлые вердикты по этой теме, проанализируй их и сравни:\n"
            + ("\n".join(past_verdicts) if past_verdicts else "Прошлых вердиктов по этой теме нет.")
            + "\n\nВыдай структурированный ответ:\n"
            "📌 Тема: ...\n"
            "📊 Текущий вердикт: ...\n"
            "📈 Сравнение с прошлым: ...\n"
            "🎯 Прогноз: ...\n"
            "🛡️ Рекомендация: ...\n"
            "💡 Плюсы: ...\n"
            "⚠️ Минусы: ..."
        )

        data = {
            "model": "groq/compound",
            "temperature": 0.3,
            "messages": [{"role": "user", "content": verdict_prompt}]
        }

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(GROQ_URL, headers=headers, json=data)
                resp.raise_for_status()
                result = resp.json()["choices"][0]["message"]["content"]
                return f"📊 *Вердикт SwitAI:*\n\n{result}"
        except Exception as e:
            return f"❌ Швейцарский суд временно не работает: {str(e)}"
    
    # === ОСНОВНОЙ ЗАПРОС ===
    add_to_history(chat_id, user_id, "user", prompt)
    
    # Проверяем, нужна ли история
    history_needed = False
    history_keywords = ["помнишь", "говорил", "про", "о", "возвращайся", "вернись", "что я", "что мы", "что ты", "расскажи про", "напомни"]
    if any(word in prompt.lower() for word in history_keywords):
        history_needed = True
    
    if history_needed:
        history = get_context_with_history(chat_id, user_id, prompt)
    else:
        history = []
    
    system_prompt = (
        f"Ты — SwitAI, коренной швейцарский эксперт. Сейчас в РП {current_month}. "
        f"Говори с лёгким акцентом, используй «месье», «уважаемый». "
        f"Помогай, шути, но без мата."
    )
    
    messages = [{"role": "system", "content": system_prompt}]
    for msg in history:
        messages.append({"role": msg['role'], "content": msg['content']})
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
            add_to_history(chat_id, user_id, "assistant", result)
            return result
    except Exception as e:
        return f"❌ Швейцарский ИИ временно в шоке: {str(e)}"

# === КОМАНДЫ ===
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
        "/saychat [имя] [текст] — написать в сохранённый чат\n"
        "/savechat [имя] — сохранить этот чат под именем\n"
        "/listchats — список сохранённых чатов\n"
        "/removechat [имя] — удалить сохранённый чат\n"
        "/clear_chat — очистить историю чата\n"
        "/stop — остановить бота\n"
        "/start — возобновить работу бота\n"
        "/del — удалить сообщение (ответьте на него)\n"
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
    history = get_user_history(chat_id, user_id, limit=10)
    await update.message.reply_text(
        f"🧠 *Состояние системы:*\n\n"
        f"📝 Сообщений в истории: {len(history)}\n"
        f"👤 ID: {user_id}\n"
        f"💬 Чат ID: {chat_id}\n"
        f"🔒 Фильтр: {'Вкл' if filter_enabled else 'Выкл'}\n"
        f"📋 Режим: {bot_mode}\n"
        f"🛑 Бот остановлен: {'Да' if bot_stopped else 'Нет'}"
    )

async def clear_memory_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    username = update.message.from_user.username
    if not is_admin(user_id, username):
        await update.message.reply_text("❌ Доступ запрещён.")
        return
    chat_id = update.message.chat.id
    clear_user_history(chat_id, user_id)
    await update.message.reply_text("🧹 История очищена.")

async def clear_all_memory_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    username = update.message.from_user.username
    if not is_admin(user_id, username):
        await update.message.reply_text("❌ Доступ запрещён.")
        return
    clear_all_history()
    await update.message.reply_text("🧹 Вся история очищена.")

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
    clear_all_history()
    verdict_buffer.clear()
    war_buffer.clear()
    await update.message.reply_text("🔄 Бот сброшен (память и буферы очищены).")

async def stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global bot_stopped
    user_id = update.message.from_user.id
    username = update.message.from_user.username
    if not is_admin(user_id, username):
        await update.message.reply_text("❌ Доступ запрещён.")
        return
    bot_stopped = True
    await update.message.reply_text("🛑 Бот остановлен. Все команды, кроме /start, игнорируются.")

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global bot_stopped
    user_id = update.message.from_user.id
    username = update.message.from_user.username
    if not is_admin(user_id, username):
        await update.message.reply_text("❌ Доступ запрещён.")
        return
    bot_stopped = False
    await update.message.reply_text("✅ Бот возобновил работу.")

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
    
    try:
        await update.message.delete()
    except:
        pass
    
    await update.message.reply_text(text)

async def save_chat_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    username = update.message.from_user.username
    if not is_admin(user_id, username):
        await update.message.reply_text("❌ Доступ запрещён.")
        return

    args = context.args
    if not args:
        await update.message.reply_text("❌ Укажите имя для этого чата. Например: /savechat альпы")
        return

    chat_name = args[0].lower()
    chat_id = update.message.chat.id

    saved_chats[chat_name] = chat_id
    save_saved_chats(saved_chats)
    await update.message.reply_text(f"✅ Чат сохранён как «{chat_name}» (ID: {chat_id})")

async def say_chat_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    username = update.message.from_user.username
    if not is_admin(user_id, username):
        await update.message.reply_text("❌ Доступ запрещён.")
        return

    args = context.args
    if len(args) < 2:
        await update.message.reply_text("❌ Используйте: /saychat [имя_чата] [текст]")
        return

    chat_name = args[0].lower()
    text = " ".join(args[1:])

    if chat_name not in saved_chats:
        await update.message.reply_text(f"❌ Чат с именем «{chat_name}» не найден.")
        return

    target_chat_id = saved_chats[chat_name]

    try:
        await context.bot.send_message(chat_id=target_chat_id, text=text)
        try:
            await update.message.delete()
        except:
            pass
    except Exception as e:
        await update.message.reply_text(f"❌ Не удалось отправить: {e}")

async def list_chats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    username = update.message.from_user.username
    if not is_admin(user_id, username):
        await update.message.reply_text("❌ Доступ запрещён.")
        return

    if not saved_chats:
        await update.message.reply_text("📭 Нет сохранённых чатов.")
        return

    text = "📋 *Сохранённые чаты:*\n\n"
    for name, chat_id in saved_chats.items():
        text += f"• {name} (ID: {chat_id})\n"
    
    await update.message.reply_text(text)

async def remove_chat_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    username = update.message.from_user.username
    if not is_admin(user_id, username):
        await update.message.reply_text("❌ Доступ запрещён.")
        return

    args = context.args
    if not args:
        await update.message.reply_text("❌ Используйте: /removechat [имя_чата]")
        return

    chat_name = args[0].lower()
    if chat_name not in saved_chats:
        await update.message.reply_text(f"❌ Чат с именем «{chat_name}» не найден.")
        return

    del saved_chats[chat_name]
    save_saved_chats(saved_chats)
    await update.message.reply_text(f"✅ Чат «{chat_name}» удалён.")

async def del_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    username = update.message.from_user.username
    if not is_admin(user_id, username):
        await update.message.reply_text("❌ Доступ запрещён.")
        return
    if not update.message.reply_to_message:
        await update.message.reply_text("❌ Ответьте на сообщение, которое хотите удалить.")
        return
    try:
        await update.message.reply_to_message.delete()
    except Exception as e:
        await update.message.reply_text(f"❌ Не удалось удалить: {e}")

async def clear_chat_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    username = update.message.from_user.username
    if not is_admin(user_id, username):
        await update.message.reply_text("❌ Доступ запрещён.")
        return
    chat_id = update.message.chat.id
    clear_user_history(chat_id, user_id)
    await update.message.reply_text("🧹 История чата очищена.")

async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat.id
    user_id = update.message.from_user.id
    history = get_user_history(chat_id, user_id, limit=10)
    if not history:
        await update.message.reply_text("📭 История пуста.")
        return
    text = "📜 *Последние 10 сообщений:*\n\n"
    for msg in history:
        role = "👤 Вы" if msg['role'] == 'user' else "🤖 Бот"
        text += f"{role}: {msg['content'][:150]}\n"
    await update.message.reply_text(text)

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat.id
    user_id = update.message.from_user.id
    history = get_user_history(chat_id, user_id, limit=1000)
    total = len(history)
    await update.message.reply_text(f"📊 *Статистика чата:*\n\n📝 Всего сообщений: {total}")

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
        "Слава [страна] — 100 стран!\n"
        "скажи шутку — свежие шутки из интернета"
    )

# === ОБРАБОТЧИК СООБЩЕНИЙ ===
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global bot_stopped
    
    if not update.message or not update.message.text:
        return
    
    chat_id = update.message.chat.id
    chat_type = update.message.chat.type
    text = update.message.text
    user_id = update.message.from_user.id
    username = update.message.from_user.username or "Неизвестный"
    
    # === ПРОВЕРКА НА ОСТАНОВКУ ===
    if bot_stopped:
        if text.lower() == "/start":
            pass
        else:
            return
    
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
        add_to_history(chat_id, user_id, "user", text)
    
    # === ТРИГГЕР НА «СВИТ» (РАБОТАЕТ БЕЗ УПОМИНАНИЯ) ===
    if re.search(r"\b(свит|Свит)\b", text):
        question = re.sub(r"(свит|Свит)\s*", "", text, flags=re.IGNORECASE).strip()
        if question:
            try:
                # Если есть ответ на сообщение — используем того пользователя
                if update.message.reply_to_message:
                    target_user = update.message.reply_to_message.from_user
                else:
                    # Получаем список участников (только если бот админ)
                    members = await context.bot.get_chat_administrators(chat_id)
                    users = [m.user for m in members if not m.user.is_bot and m.user.id != 7184396483]
                    target_user = random.choice(users) if users else None
                
                if target_user:
                    target_name = target_user.username or target_user.first_name
                    await update.message.reply_text(f"@{target_name}, {question}")
                else:
                    await update.message.reply_text(f"Случайный пользователь: {question}")
            except:
                await update.message.reply_text(f"Случайный пользователь: {question}")
            return
    
    # === ПРОВЕРКА УПОМИНАНИЯ ===
    if chat_type in ["group", "supergroup"]:
        if context.bot.username.lower() not in text.lower():
            if not (update.message.reply_to_message and update.message.reply_to_message.from_user.id == context.bot.id):
                return
    
    # === АНАЛИЗ ВЕРОЯТНОСТИ ===
    if re.search(r"какая вероятность|вероятность|шанс|каков шанс", text, re.IGNORECASE):
        import random as rnd
        
        # Защита Кейка
        if re.search(r"(кейк|президент|ги пармелен|пармелен)", text, re.IGNORECASE):
            await update.message.reply_text(f"0% — месье, @{update.message.from_user.username}, оскорбления в сторону президента Швейцарии недопустимы.")
            return
        
        # Если запрос не содержит ключевых слов — сразу рандом
        if not re.search(r"(шанс|вероятность|возможно|наверное)", text, re.IGNORECASE):
            probability = rnd.randint(0, 100)
        else:
            # Попытка запроса к Groq
            try:
                headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
                analysis_prompt = (
                    f"Проанализируй запрос и определи вероятность (в процентах) от 0 до 100. "
                    f"Учитывай контекст и логику. Ответь только числом.\n\nЗапрос: {text}"
                )
                data = {
                    "model": "groq/compound",
                    "temperature": 0.3,
                    "messages": [{"role": "user", "content": analysis_prompt}]
                }
                
                async with httpx.AsyncClient(timeout=30.0) as client:
                    resp = await client.post(GROQ_URL, headers=headers, json=data)
                    resp.raise_for_status()
                    result = resp.json()["choices"][0]["message"]["content"].strip()
                    
                    probability_match = re.search(r'\b\d{1,3}\b', result)
                    probability = int(probability_match.group()) if probability_match else 50
                    probability = max(0, min(100, probability))
                    
            except Exception as e:
                # Если Groq упал — генерируем сами
                probability = rnd.randint(0, 100)
                subtract = rnd.randint(10, 20)
                probability = max(0, probability - subtract)
        
        # Если есть цель
        if update.message.reply_to_message:
            target = update.message.reply_to_message.from_user.username or "пользователь"
            await update.message.reply_text(f"@{update.message.from_user.username}, вероятность для @{target} составляет {probability}%.")
        else:
            await update.message.reply_text(f"@{update.message.from_user.username}, вероятность составляет {probability}%.")
        return
    
    # === ВЕРДИКТ С ПРОШЛЫМИ ===
    if "вердикт" in text.lower():
        topic = re.sub(r"вердикт\s*", "", text, flags=re.IGNORECASE).strip()
        if not topic:
            await update.message.reply_text("❌ Месье, укажите тему для вердикта.")
            return

        # Ищем прошлые вердикты
        past_verdicts = []
        history = get_user_history(chat_id, user_id, limit=50)
        for msg in history:
            if "вердикт" in msg['content'].lower() and topic.lower() in msg['content'].lower():
                past_verdicts.append(msg['content'])

        headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
        verdict_prompt = (
            f"Ты — SwitAI, швейцарский аналитик. Сделай вердикт на тему: {topic}.\n\n"
            f"Если есть прошлые вердикты по этой теме, проанализируй их и сравни:\n"
            + ("\n".join(past_verdicts) if past_verdicts else "Прошлых вердиктов по этой теме нет.")
            + "\n\nВыдай структурированный ответ:\n"
            "📌 Тема: ...\n"
            "📊 Текущий вердикт: ...\n"
            "📈 Сравнение с прошлым: ...\n"
            "🎯 Прогноз: ...\n"
            "🛡️ Рекомендация: ...\n"
            "💡 Плюсы: ...\n"
            "⚠️ Минусы: ..."
        )

        data = {
            "model": "groq/compound",
            "temperature": 0.3,
            "messages": [{"role": "user", "content": verdict_prompt}]
        }

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(GROQ_URL, headers=headers, json=data)
                resp.raise_for_status()
                result = resp.json()["choices"][0]["message"]["content"]
                await update.message.reply_text(f"📊 *Вердикт SwitAI:*\n\n{result}")
        except Exception as e:
            await update.message.reply_text(f"❌ Швейцарский суд временно не работает: {str(e)}")
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
    app.add_handler(CommandHandler("saychat", say_chat_command))
    app.add_handler(CommandHandler("savechat", save_chat_command))
    app.add_handler(CommandHandler("listchats", list_chats_command))
    app.add_handler(CommandHandler("removechat", remove_chat_command))
    app.add_handler(CommandHandler("del", del_command))
    app.add_handler(CommandHandler("clear_chat", clear_chat_command))
    app.add_handler(CommandHandler("stop", stop_command))
    app.add_handler(CommandHandler("start", start_command))
    
    print("✅ SwitAI финальная версия с правильным триггером «свит» запущена!")
    app.run_polling()

if __name__ == "__main__":
    main()
