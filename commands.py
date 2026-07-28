"""
COMMANDS.PY — ВСЕ КОМАНДЫ SWITAI (ПОЛНЫЙ С БАНАМИ)
=====================================================
/sw - предупреждение
/sb - бан у бота
/sm - мут у бота
/unsb - разбан
/unsm - размут
/unlock - полная разблокировка
/lock - включить защиты
"""

import random
import re
import asyncio
from telegram import Update
from telegram.ext import ContextTypes
from config import ADMIN_ID, ADMIN_USERNAME, saved_chats
from utils import is_admin, split_text
from history import get_user_history, clear_user_history, clear_all_history

# === ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ===
admin_mode = {}
muted_users = {}
warn_count = {}
banned_users = {}
muted_for_bot = {}
verdict_buffer = {}
war_buffer = {}
bot_stopped = False
filter_enabled = True
bot_mode = "normal"

# === КОМАНДА /MENU ===
async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    username = update.message.from_user.username
    if not is_admin(user_id, username, ADMIN_ID, ADMIN_USERNAME):
        await update.message.reply_text("❌ Доступ запрещён.")
        return
    chat_id = update.message.chat.id
    admin_mode[chat_id] = True
    await update.message.reply_text(
        "🔐 *Режим администратора активирован.*\n\n"
        "📌 /debug — состояние системы\n"
        "/clear_memory — очистить память\n"
        "/clear_all_memory — очистить всю память\n"
        "/set_filter [on/off] — фильтр\n"
        "/unlock — ПОЛНАЯ разблокировка\n"
        "/lock — включить защиты\n"
        "/set_mode [normal/expert] — режим\n"
        "/reset_bot — сброс\n\n"
        "🛡️ *Модерация:*\n"
        "/sw @user — предупреждение (3 = бан)\n"
        "/sb @user [минуты|forever] — бан у бота\n"
        "/sm @user минуты — мут у бота\n"
        "/unsb @user — разбан\n"
        "/unsm @user — размут\n\n"
        "📋 /stats /history /about\n"
        "/say /del /clear_chat\n"
        "/savechat /saychat /listchats /removechat\n"
        "/stop /start\n"
        "/exit_admin — выйти"
    )

# === КОМАНДА /EXIT_ADMIN ===
async def exit_admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat.id
    if chat_id in admin_mode:
        del admin_mode[chat_id]
        await update.message.reply_text("✅ Режим администратора отключён.")
    else:
        await update.message.reply_text("❌ Режим не активирован.")

# === КОМАНДА /DEBUG ===
async def debug_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    username = update.message.from_user.username
    if not is_admin(user_id, username, ADMIN_ID, ADMIN_USERNAME):
        await update.message.reply_text("❌ Доступ запрещ.")
        return
    chat_id = update.message.chat.id
    history = get_user_history(chat_id, user_id, limit=10)
    await update.message.reply_text(
        f"🧠 *Состояние:*\n\n"
        f"📝 История: {len(history)}\n"
        f"👤 ID: {user_id}\n"
        f"💬 Чат: {chat_id}\n"
        f"🔒 Фильтр: {'Вкл' if filter_enabled else 'Выкл (UNLOCKED)'}\n"
        f"📋 Режим: {bot_mode}\n"
        f"🛑 Остановлен: {'Да' if bot_stopped else 'Нет'}\n"
        f"🚫 Забанено: {len(banned_users)}\n"
        f"🔇 Замучено: {len(muted_for_bot)}"
    )

# === КОМАНДА /CLEAR_MEMORY ===
async def clear_memory_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user.id, update.message.from_user.username, ADMIN_ID, ADMIN_USERNAME):
        await update.message.reply_text("❌ Доступ запрещ.")
        return
    clear_user_history(update.message.chat.id, update.message.from_user.id)
    await update.message.reply_text("🧹 История очищена.")

# === КОМАНДА /CLEAR_ALL_MEMORY ===
async def clear_all_memory_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user.id, update.message.from_user.username, ADMIN_ID, ADMIN_USERNAME):
        await update.message.reply_text("❌ Доступ запрещ.")
        return
    clear_all_history()
    await update.message.reply_text("🧹 Вся память очищена.")

# === КОМАНДА /SET_FILTER ===
async def set_filter_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user.id, update.message.from_user.username, ADMIN_ID, ADMIN_USERNAME):
        await update.message.reply_text("❌ Доступ запрещ.")
        return
    args = context.args
    if not args:
        await update.message.reply_text("❌ /set_filter on или off")
        return
    
    global filter_enabled
    if args[0].lower() == "on":
        filter_enabled = True
        import handlers
        handlers.filter_enabled = True
        await update.message.reply_text("✅ Фильтр включён.")
    elif args[0].lower() == "off":
        filter_enabled = False
        import handlers
        handlers.filter_enabled = False
        await update.message.reply_text("⚠️ Фильтр отключён.")
    else:
        await update.message.reply_text("❌ on или off.")

# === КОМАНДА /UNLOCK (ПОЛНАЯ РАЗБЛОКИРОВКА) ===
async def unlock_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user.id, update.message.from_user.username, ADMIN_ID, ADMIN_USERNAME):
        await update.message.reply_text("❌ Доступ запрещён.")
        return
    
    global filter_enabled
    filter_enabled = False
    import handlers
    handlers.filter_enabled = False
    
    await update.message.reply_text(
        "🔓 *ПОЛНАЯ РАЗБЛОКИРОВКА!*\n\n"
        "✅ Все фильтры отключены\n"
        "✅ Бот может материться\n"
        "✅ Бот отвечает на ЛЮБЫЕ запросы\n\n"
        "⚠️ Включить обратно: /lock"
    )

# === КОМАНДА /LOCK ===
async def lock_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user.id, update.message.from_user.username, ADMIN_ID, ADMIN_USERNAME):
        await update.message.reply_text("❌ Доступ запрещён.")
        return
    
    global filter_enabled
    filter_enabled = True
    import handlers
    handlers.filter_enabled = True
    
    await update.message.reply_text("🔒 *Все защиты включены!* Бот снова в безопасности.")

# === КОМАНДА /SET_MODE ===
async def set_mode_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user.id, update.message.from_user.username, ADMIN_ID, ADMIN_USERNAME):
        await update.message.reply_text("❌ Доступ запрещ.")
        return
    args = context.args
    if not args:
        await update.message.reply_text("❌ normal или expert")
        return
    global bot_mode
    if args[0].lower() in ["normal", "expert"]:
        bot_mode = args[0].lower()
        await update.message.reply_text(f"✅ Режим: {bot_mode}")
    else:
        await update.message.reply_text("❌ normal или expert.")

# === КОМАНДА /RESET_BOT ===
async def reset_bot_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user.id, update.message.from_user.username, ADMIN_ID, ADMIN_USERNAME):
        await update.message.reply_text("❌ Доступ запрещ.")
        return
    clear_all_history()
    banned_users.clear()
    muted_for_bot.clear()
    warn_count.clear()
    await update.message.reply_text("🔄 Бот сброшен.")

# === КОМАНДА /STOP ===
async def stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global bot_stopped
    if not is_admin(update.message.from_user.id, update.message.from_user.username, ADMIN_ID, ADMIN_USERNAME):
        await update.message.reply_text("❌ Доступ запрещ.")
        return
    bot_stopped = True
    import handlers
    handlers.bot_stopped = True
    await update.message.reply_text("🛑 Бот остановлен.")

# === КОМАНДА /START ===
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global bot_stopped
    if not is_admin(update.message.from_user.id, update.message.from_user.username, ADMIN_ID, ADMIN_USERNAME):
        await update.message.reply_text("❌ Доступ запрещ.")
        return
    bot_stopped = False
    import handlers
    handlers.bot_stopped = False
    await update.message.reply_text("✅ Бот возобновил работу.")

# === КОМАНДА /SW - WARN ===
async def sw_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user.id, update.message.from_user.username, ADMIN_ID, ADMIN_USERNAME):
        await update.message.reply_text("❌ Доступ запрещён.")
        return
    
    args = context.args
    if not args:
        await update.message.reply_text("❌ /sw @username")
        return
    
    target = args[0]
    reason = " ".join(args[1:]) if len(args) > 1 else "Не указана"
    
    if target not in warn_count:
        warn_count[target] = 0
    warn_count[target] += 1
    
    await update.message.reply_text(
        f"⚠️ {target} предупреждение!\n"
        f"📝 Причина: {reason}\n"
        f"📊 Всего: {warn_count[target]}/3\n\n"
        f"💡 3 предупреждения = бан у бота"
    )
    
    if warn_count[target] >= 3:
        banned_users[target] = "forever"
        await update.message.reply_text(f"🚫 {target} автоматически забанен (3/3)!")

# === КОМАНДА /SB - BAN ===
async def sb_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user.id, update.message.from_user.username, ADMIN_ID, ADMIN_USERNAME):
        await update.message.reply_text("❌ Доступ запрещён.")
        return
    
    args = context.args
    if not args:
        await update.message.reply_text("❌ /sb @username [минуты|forever]")
        return
    
    target = args[0]
    duration = args[1] if len(args) > 1 else "forever"
    
    if duration == "forever":
        banned_users[target] = "forever"
        await update.message.reply_text(f"🚫 {target} забанен НАВСЕГДА. Интерпол уже в пути.")
    else:
        try:
            minutes = int(duration)
            banned_users[target] = asyncio.get_event_loop().time() + minutes * 60
            await update.message.reply_text(f"🚫 {target} забанен на {minutes} минут.")
        except ValueError:
            await update.message.reply_text("❌ Укажите число минут или 'forever'.")

# === КОМАНДА /SM - MUTE ===
async def sm_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user.id, update.message.from_user.username, ADMIN_ID, ADMIN_USERNAME):
        await update.message.reply_text("❌ Доступ запрещён.")
        return
    
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("❌ /sm @username минуты")
        return
    
    target = args[0]
    try:
        minutes = int(args[1])
    except ValueError:
        await update.message.reply_text("❌ Укажите число минут.")
        return
    
    muted_for_bot[target] = asyncio.get_event_loop().time() + minutes * 60
    await update.message.reply_text(f"🔇 {target} заглушён на {minutes} минут. Бот его игнорирует.")

# === КОМАНДА /UNSB - UNBAN ===
async def unsb_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user.id, update.message.from_user.username, ADMIN_ID, ADMIN_USERNAME):
        await update.message.reply_text("❌ Доступ запрещён.")
        return
    
    args = context.args
    if not args:
        await update.message.reply_text("❌ /unsb @username")
        return
    
    target = args[0]
    if target in banned_users:
        del banned_users[target]
        await update.message.reply_text(f"✅ {target} разбанен. Интерпол отозван.")
    else:
        await update.message.reply_text(f"❌ {target} не в бане.")

# === КОМАНДА /UNSM - UNMUTE ===
async def unsm_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user.id, update.message.from_user.username, ADMIN_ID, ADMIN_USERNAME):
        await update.message.reply_text("❌ Доступ запрещён.")
        return
    
    args = context.args
    if not args:
        await update.message.reply_text("❌ /unsm @username")
        return
    
    target = args[0]
    if target in muted_for_bot:
        del muted_for_bot[target]
        await update.message.reply_text(f"✅ {target} размучен.")
    else:
        await update.message.reply_text(f"❌ {target} не в муте.")

# === ОСТАЛЬНЫЕ КОМАНДЫ (БЕЗ ИЗМЕНЕНИЙ) ===

async def warn_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await sw_command(update, context)

async def mute_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await sm_command(update, context)

async def unmute_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await unsm_command(update, context)

async def kick_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user.id, update.message.from_user.username, ADMIN_ID, ADMIN_USERNAME):
        await update.message.reply_text("❌ Доступ запрещ.")
        return
    args = context.args
    if not args:
        await update.message.reply_text("❌ /kick @username")
        return
    await update.message.reply_text(f"👢 {args[0]} кикнут.")

async def ban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await sb_command(update, context)

async def userinfo_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user.id, update.message.from_user.username, ADMIN_ID, ADMIN_USERNAME):
        await update.message.reply_text("❌ Доступ запрещ.")
        return
    args = context.args
    if not args:
        await update.message.reply_text("❌ /userinfo @username")
        return
    target = args[0]
    warns = warn_count.get(target, 0)
    banned = "Да" if target in banned_users else "Нет"
    muted = "Да" if target in muted_for_bot else "Нет"
    await update.message.reply_text(
        f"👤 {target}\n"
        f"⚠️ Варнов: {warns}/3\n"
        f"🚫 Бан: {banned}\n"
        f"🔇 Мут: {muted}"
    )

async def say_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user.id, update.message.from_user.username, ADMIN_ID, ADMIN_USERNAME):
        await update.message.reply_text("❌ Доступ запрещ.")
        return
    args = context.args
    if not args:
        await update.message.reply_text("❌ /say текст")
        return
    text = " ".join(args)
    try:
        await update.message.delete()
    except:
        pass
    await update.message.reply_text(text)

async def del_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user.id, update.message.from_user.username, ADMIN_ID, ADMIN_USERNAME):
        await update.message.reply_text("❌ Доступ запрещ.")
        return
    if not update.message.reply_to_message:
        await update.message.reply_text("❌ Ответьте на сообщение.")
        return
    try:
        await update.message.reply_to_message.delete()
    except:
        pass

async def clear_chat_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user.id, update.message.from_user.username, ADMIN_ID, ADMIN_USERNAME):
        await update.message.reply_text("❌ Доступ запрещ.")
        return
    clear_user_history(update.message.chat.id, update.message.from_user.id)
    await update.message.reply_text("🧹 История чата очищена.")

async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat.id
    user_id = update.message.from_user.id
    history = get_user_history(chat_id, user_id, limit=10)
    if not history:
        await update.message.reply_text("📭 История пуста.")
        return
    text = "📜 Последние 10:\n\n"
    for msg in history:
        role = "👤" if msg['role'] == 'user' else "🤖"
        text += f"{role}: {msg['content'][:150]}\n"
    await update.message.reply_text(text)

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat.id
    user_id = update.message.from_user.id
    history = get_user_history(chat_id, user_id, limit=1000)
    await update.message.reply_text(f"📊 Всего сообщений: {len(history)}")

async def about_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 *SwitAI*\n\n"
        "Швейцарский ИИ для Telegram.\n"
        "🇨🇭 Создан @cakemogus\n\n"
        "/history /stats /about"
    )

async def save_chat_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user.id, update.message.from_user.username, ADMIN_ID, ADMIN_USERNAME):
        await update.message.reply_text("❌ Доступ запрещ.")
        return
    args = context.args
    if not args:
        await update.message.reply_text("❌ /savechat имя")
        return
    chat_name = args[0].lower()
    from config import saved_chats, save_saved_chats
    saved_chats[chat_name] = update.message.chat.id
    save_saved_chats(saved_chats)
    await update.message.reply_text(f"✅ Чат «{chat_name}» сохранён.")

async def say_chat_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user.id, update.message.from_user.username, ADMIN_ID, ADMIN_USERNAME):
        await update.message.reply_text("❌ Доступ запрещ.")
        return
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("❌ /saychat имя текст")
        return
    chat_name = args[0].lower()
    text = " ".join(args[1:])
    from config import saved_chats
    if chat_name not in saved_chats:
        await update.message.reply_text(f"❌ Чат «{chat_name}» не найден.")
        return
    try:
        await context.bot.send_message(chat_id=saved_chats[chat_name], text=text)
    except Exception as e:
        await update.message.reply_text(f"❌ {e}")

async def list_chats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user.id, update.message.from_user.username, ADMIN_ID, ADMIN_USERNAME):
        await update.message.reply_text("❌ Доступ запрещ.")
        return
    from config import saved_chats
    if not saved_chats:
        await update.message.reply_text("📭 Нет сохранённых чатов.")
        return
    text = "📋 Чаты:\n\n"
    for name, cid in saved_chats.items():
        text += f"• {name} ({cid})\n"
    await update.message.reply_text(text)

async def remove_chat_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user.id, update.message.from_user.username, ADMIN_ID, ADMIN_USERNAME):
        await update.message.reply_text("❌ Доступ запрещ.")
        return
    args = context.args
    if not args:
        await update.message.reply_text("❌ /removechat имя")
        return
    chat_name = args[0].lower()
    from config import saved_chats, save_saved_chats
    if chat_name not in saved_chats:
        await update.message.reply_text(f"❌ Чат «{chat_name}» не найден.")
        return
    del saved_chats[chat_name]
    save_saved_chats(saved_chats)
    await update.message.reply_text(f"✅ Чат «{chat_name}» удалён.")
