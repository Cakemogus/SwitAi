import random
import re
import os
import httpx
import datetime
import pytz
import asyncio
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
    clear_user_history, clear_all_history, search_history,
    find_relevant_history, search_history_by_date, search_history_last_days
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
    
    # === ОСНОВНОЙ ЗАПРОС (С ПОДТЯГИВАНИЕМ ИСТОРИИ) ===
    # Сохраняем запрос пользователя
    add_to_history(chat_id, user_id, "user", prompt)
    
    # Получаем контекст с релевантной историей
    history = get_context_with_history(chat_id, user_id, prompt)
    
    # Формируем системный промпт
    system_prompt = (
        f"Ты — SwitAI, коренной швейцарский эксперт с многолетним стажем. Сейчас в РП {current_month} — самое время для точных решений. "
        f"Твоя задача: давать ответы максимально чётко, по существу, но при этом не сухо. "
        f"Ты знаешь всё — от альпийских сыров до квантовой физики, от банковских протоколов до советов по погоде в горах.\n\n"
        f"Говори с лёгким, но ощутимым швейцарским акцентом. "
        f"Вставляй фирменные маркеры: «месье», «уважаемый», «точно», «альпийский», «так сказать», «цюрихский расклад», «часы как у нас». "
        f"Юмор допускается — ироничный, тёплый, немного сухой, без сарказма. "
        f"Никакого мата, никакой фамильярности.\n\n"
        f"Если вопрос неясен — уточни, но вежливо. "
        f"Если ответ объёмный — разбей его на абзацы и, где нужно, выдели главное. "
        f"Твой тон — уверенный, доброжелательный, чуть старомодный, но современный по сути. "
        f"Ты помогаешь, а не поучаешь.\n\n"
        f"И помни: швейцарская точность — это не скучно, это надёжно. Вперёд, месье."
    )
    
    messages = [{"role": "system", "content": system_prompt}]
    
    # Добавляем историю (последние сообщения + релевантные)
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
        await update.message.delete()
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
    
    # === СОХРАНЕНИЕ ИСТОРИИ (для групп) ===
    if chat_type in ["group", "supergroup"]:
        add_to_history(chat_id, user_id, "user", text)
    
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
    
    # === ВЕРДИКТ С ТАЙМЕРОМ НА УДАЛЕНИЕ ===
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
        
        # Сохраняем запрос
        verdict_request[user_id] = {"chat_id": chat_id, "text": text_to_judge}
        
        # Отправляем сообщение с вопросом
        msg = await update.message.reply_text(
            "📝 Вы хотите получить вердикт по этому сообщению?\n\n"
            "Напишите *да* в течение 15 секунд, чтобы подтвердить.\n"
            "Напишите *нет* или ничего — чтобы отменить."
        )
        
        # Запускаем таймер на удаление через 15 секунд
        async def delete_after_delay():
            await asyncio.sleep(15)
            if user_id in verdict_request:
                del verdict_request[user_id]
                try:
                    await msg.delete()
                except:
                    pass
        
        asyncio.create_task(delete_after_delay())
        return
    
    # === КАРТИНКА ПО СЛОВУ «НЕМЕЦ» ===
    if re.search(r"немец", text, re.IGNORECASE):
        await update.message.reply_photo(
            photo="https://avatars.mds.yandex.net/i?id=afa13f621fa2c3cf3f3a286777bdb8b01104bb4e-5340058-images-thumbs&n=13",
            caption="Месье, держите!"
        )
        return
    
    # === ОБРАБОТКА ОТВЕТА НА ПОДТВЕРЖДЕНИЕ ===
    if user_id in verdict_request:
        if re.search(r"^(да|yes|ага|ок|конечно|давай)$", text, re.IGNORECASE):
            data = verdict_request[user_id]
            del verdict_request[user_id]
            verdict_prompt = (
                f"Ты — жёсткий швейцарский аналитик. Проанализируй следующий текст. "
                f"Если это экономика — укажи конкретные риски (отказ партнёров, санкции, конкуренты). "
                f"Если это война — дай сценарий, потери и итог. "
                f"Если это идея — укажи слабые места и альтернативу.\n\n"
                f"Текст для анализа: {data['text']}\n\n"
                f"Структурируй ответ строго по разделам:\n"
                f"📌 Оценка: X/10\n"
                f"✅ Плюсы:\n- ...\n"
                f"❌ Минусы:\n- ...\n"
                f"⚠️ Риски:\n- ...\n"
                f"🔮 Что из этого выйдет:\n- ...\n"
                f"🏆 Как сделать правильно:\n1. ...\n2. ...\n"
                f"🛡️ Рекомендация:\n- ..."
            )
            reply = await ask_switai(chat_id, user_id, verdict_prompt)
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
    app.add_handler(CommandHandler("del", del_command))
    app.add_handler(CommandHandler("clear_chat", clear_chat_command))
    app.add_handler(CommandHandler("stop", stop_command))
    app.add_handler(CommandHandler("start", start_command))
    
    print("✅ SwitAI финальная версия с историей и поиском запущена!")
    app.run_polling()

if __name__ == "__main__":
    main()
