"""
COMMANDS.PY — ВСЕ КОМАНДЫ SWITAI 2.0
====================================
Модерация теперь работает по-настоящему:
  • цель — это ответ на сообщение, @ник, или числовой ID;
  • бан/мут ставятся и по ID, и по нику (смена ника не спасает, если бот уже видел человека);
  • срок: 30 / 30m / 2h / 1d / forever;
  • всё хранится в state.py и переживает перезапуск.

Проверка админа — как и раньше: по ID ИЛИ по нику.
"""

import logging
import time
from functools import wraps

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

import history as hist
from config import ADMIN_ID, ADMIN_USERNAME, saved_chats, save_saved_chats
from state import S
from utils import human_duration, is_admin, parse_duration

log = logging.getLogger(__name__)

WARN_LIMIT = 3


# =====================================================================
# ВСПОМОГАТЕЛЬНОЕ
# =====================================================================

def admin_only(fn):
    @wraps(fn)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        msg = update.effective_message
        if not user or not msg:
            return
        if not is_admin(user.id, user.username, ADMIN_ID, ADMIN_USERNAME):
            await msg.reply_text("❌ Доступ запрещён.")
            return
        return await fn(update, context)
    return wrapper


async def html(update: Update, text: str):
    await update.effective_message.reply_text(text, parse_mode=ParseMode.HTML)


def resolve_target(msg, args):
    """
    Возвращает (keys, label, user_id, остальные_аргументы) или None.
    Приоритет: ответ на сообщение > @ник > числовой ID.
    """
    r = msg.reply_to_message
    if r and r.from_user:
        u = r.from_user
        label = f"@{u.username}" if u.username else u.full_name
        return S.user_keys(u), label, u.id, list(args)
    if args:
        a, rest = args[0], list(args[1:])
        if a.startswith("@") and len(a) > 1:
            name = a[1:].lower()
            uid = S.known_users.get(name)
            keys = ([f"id:{uid}"] if uid else []) + ["@" + name]
            return keys, a, uid, rest
        if a.lstrip("-").isdigit():
            uid = int(a)
            return [f"id:{uid}"], a, uid, rest
    return None


def _is_admin_target(keys, uid) -> bool:
    if uid == ADMIN_ID:
        return True
    return ("@" + ADMIN_USERNAME.lower()) in keys


async def _need_target(update: Update, usage: str):
    await update.effective_message.reply_text(
        f"❌ Укажи цель: ответом на сообщение, @ником или ID.\nПример: {usage}"
    )


# =====================================================================
# ПУБЛИЧНЫЕ КОМАНДЫ
# =====================================================================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    msg = update.effective_message
    if user and is_admin(user.id, user.username, ADMIN_ID, ADMIN_USERNAME) and S.bot_stopped:
        S.bot_stopped = False
        S.save()
        await msg.reply_text("✅ Бот возобновил работу.")
        return
    await html(
        update,
        "🇨🇭 <b>Привет! Я SwitAI — швейцарский ИИ.</b>\n\n"
        "• В личке просто пиши мне.\n"
        "• В группе обращайся: <code>Свит, ...</code> или ответь на моё сообщение.\n"
        "• Картинку: <code>Свит нарисуй кота в шляпе</code>\n"
        "• Отправь фото — я опишу, что на нём.\n"
        "• Актуальное: <code>Свит, курс доллара</code>, <code>новости</code>, <code>погода</code>\n"
        "• <code>Свит вердикт тема</code> · <code>Свит скажи шутку</code>\n\n"
        "Все команды: /help",
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await html(
        update,
        "📖 <b>Команды</b>\n\n"
        "/help — это сообщение\n"
        "/ping — проверка, жив ли бот\n"
        "/history — последние 10 сообщений из памяти\n"
        "/stats — статистика\n"
        "/forgetme — забыть наш диалог\n"
        "/about — о боте",
    )


async def ping_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    t0 = time.perf_counter()
    m = await update.effective_message.reply_text("🏓 Понг!")
    ms = (time.perf_counter() - t0) * 1000
    await m.edit_text(f"🏓 Понг! {ms:.0f} мс")


async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    items = hist.get_user_history(msg.chat.id, update.effective_user.id, limit=10)
    if not items:
        await msg.reply_text("📭 История пуста.")
        return
    lines = ["📜 Последние сообщения:\n"]
    for m in items:
        lines.append(f"{'👤' if m['role'] == 'user' else '🤖'}: {m['content'][:150]}")
    await msg.reply_text("\n".join(lines))


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    items = hist.get_all_user_data(msg.chat.id, update.effective_user.id)
    mine = sum(1 for m in items if m["role"] == "user")
    uptime = int(time.time() - S.started_at)
    h, rem = divmod(uptime, 3600)
    await msg.reply_text(
        f"📊 Статистика\n\n"
        f"💬 Твоих сообщений боту: {mine}\n"
        f"🧠 Записей в памяти: {len(items)}\n"
        f"👥 Людей в памяти этого чата: {hist.count_users_in_chat(msg.chat.id)}\n"
        f"⏱ Аптайм: {h} ч {rem // 60} мин"
    )


async def forgetme_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    hist.clear_user_history(msg.chat.id, update.effective_user.id)
    await msg.reply_text("🧹 Забыл всё, о чём мы говорили.")


async def about_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(
        "🤖 SwitAI 2.0\n\nШвейцарский ИИ для Telegram.\n🇨🇭 Создан @cakemogus\n\n/help — все команды"
    )


# =====================================================================
# АДМИН: МЕНЮ, РЕЖИМЫ, СИСТЕМА
# =====================================================================

@admin_only
async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    S.admin_mode.add(update.effective_message.chat.id)
    await html(
        update,
        "🔐 <b>Режим администратора активирован.</b>\n"
        "Твои сообщения в этом чате идут без фильтров и без обращения «Свит».\n\n"
        "⚙️ <b>Система</b>\n"
        "/debug — состояние\n"
        "/set_filter on|off · /unlock · /lock\n"
        "/set_mode normal|expert\n"
        "/stop · /start — пауза / возобновление\n"
        "/reset_bot — сброс банов, варнов и памяти\n\n"
        "🛡️ <b>Модерация</b> (ответом на сообщение, @ником или ID)\n"
        "/sw — варн (3 = бан) · /unsw — снять варн\n"
        "/sb [срок] — бан у бота · /unsb\n"
        "/sm срок — мут у бота · /unsm\n"
        "/kick — кик из чата · /userinfo\n"
        "Срок: <code>30</code> · <code>2h</code> · <code>1d</code> · <code>forever</code>\n\n"
        "🧠 <b>Память</b>\n"
        "/clear_memory · /clear_chat · /clear_all_memory\n\n"
        "📣 <b>Утилиты</b>\n"
        "/say · /del · /interpol\n"
        "/savechat · /saychat · /listchats · /removechat\n"
        "/stoppvp · /startpvp\n"
        "/exit_admin — выйти",
    )


async def exit_admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    chat_id = msg.chat.id
    if chat_id in S.admin_mode:
        S.admin_mode.discard(chat_id)
        await msg.reply_text("✅ Режим администратора отключён.")
    else:
        await msg.reply_text("❌ Режим не активирован.")


@admin_only
async def debug_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    items = hist.get_user_history(msg.chat.id, update.effective_user.id, limit=10)
    uptime = int(time.time() - S.started_at)
    await msg.reply_text(
        f"🧠 Состояние:\n\n"
        f"📝 История (посл.): {len(items)}\n"
        f"👤 ID: {update.effective_user.id}\n"
        f"💬 Чат: {msg.chat.id}\n"
        f"🔒 Фильтр: {'Вкл' if S.filter_enabled else 'Выкл (UNLOCKED)'}\n"
        f"📋 Режим: {S.bot_mode}\n"
        f"🛑 Остановлен: {'Да' if S.bot_stopped else 'Нет'}\n"
        f"🚫 Банов: {len(S.bans)} · 🔇 Мутов: {len(S.mutes)} · ⚠️ Варнов: {len(S.warns)}\n"
        f"🕵️ В списке Интерпола: {len(S.interpol)}\n"
        f"⏱ Аптайм: {uptime // 3600} ч {(uptime % 3600) // 60} мин"
    )


@admin_only
async def clear_memory_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    hist.clear_user_history(msg.chat.id, update.effective_user.id)
    await msg.reply_text("🧹 Твоя история очищена.")


@admin_only
async def clear_all_memory_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    hist.clear_all_history()
    await update.effective_message.reply_text("🧹 Вся память очищена.")


@admin_only
async def clear_chat_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    n = hist.clear_chat_history(update.effective_message.chat.id)
    await update.effective_message.reply_text(f"🧹 Память этого чата очищена (записей: {n}).")


@admin_only
async def set_filter_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    arg = (context.args[0].lower() if context.args else "")
    if arg == "on":
        S.filter_enabled = True
        S.save()
        await msg.reply_text("✅ Фильтр включён.")
    elif arg == "off":
        S.filter_enabled = False
        S.save()
        await msg.reply_text("⚠️ Фильтр отключён.")
    else:
        await msg.reply_text("❌ /set_filter on или off")


@admin_only
async def unlock_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    S.filter_enabled = False
    S.save()
    await update.effective_message.reply_text(
        "🔓 ПОЛНАЯ РАЗБЛОКИРОВКА!\n\n"
        "✅ Фильтры текста отключены\n✅ Бот может материться\n\n"
        "⚠️ Включить обратно: /lock"
    )


@admin_only
async def lock_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    S.filter_enabled = True
    S.save()
    await update.effective_message.reply_text("🔒 Все защиты включены! Бот снова в безопасности.")


@admin_only
async def set_mode_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    arg = (context.args[0].lower() if context.args else "")
    if arg in ("normal", "expert"):
        S.bot_mode = arg
        S.save()
        await msg.reply_text(
            f"✅ Режим: {arg}" + (" (подробные ответы)" if arg == "expert" else " (короткие ответы)")
        )
    else:
        await msg.reply_text("❌ /set_mode normal или expert")


@admin_only
async def reset_bot_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    hist.clear_all_history()
    S.bans.clear()
    S.mutes.clear()
    S.warns.clear()
    S.save()
    await update.effective_message.reply_text("🔄 Бот сброшен: память, баны, муты и варны очищены.")


@admin_only
async def stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    S.bot_stopped = True
    S.save()
    await update.effective_message.reply_text("🛑 Бот остановлен. Вернуть: /start")


# =====================================================================
# АДМИН: МОДЕРАЦИЯ
# =====================================================================

@admin_only
async def sw_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    t = resolve_target(msg, context.args)
    if not t:
        return await _need_target(update, "/sw @user причина")
    keys, label, uid, rest = t
    if _is_admin_target(keys, uid):
        return await msg.reply_text("😏 Админа предупреждать нельзя.")
    reason = " ".join(rest) or "Не указана"
    primary = keys[0]
    S.warns[primary] = S.warns.get(primary, 0) + 1
    count = S.warns[primary]
    text = f"⚠️ {label}, предупреждение!\n📝 Причина: {reason}\n📊 Всего: {count}/{WARN_LIMIT}"
    if count >= WARN_LIMIT:
        for k in keys:
            S.bans[k] = "forever"
        S.warns.pop(primary, None)
        text += f"\n\n🚫 {label} автоматически забанен у бота ({WARN_LIMIT}/{WARN_LIMIT})!"
    else:
        text += f"\n💡 {WARN_LIMIT} предупреждения = бан у бота"
    S.save()
    await msg.reply_text(text)


@admin_only
async def unsw_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    t = resolve_target(msg, context.args)
    if not t:
        return await _need_target(update, "/unsw @user")
    keys, label, _, _ = t
    primary = keys[0]
    if S.warns.get(primary, 0) > 0:
        S.warns[primary] -= 1
        if S.warns[primary] == 0:
            del S.warns[primary]
        S.save()
        await msg.reply_text(f"✅ С {label} снят один варн. Осталось: {S.warns.get(primary, 0)}/{WARN_LIMIT}")
    else:
        await msg.reply_text(f"❌ У {label} нет варнов.")


@admin_only
async def sb_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    t = resolve_target(msg, context.args)
    if not t:
        return await _need_target(update, "/sb @user 30m  (или forever)")
    keys, label, uid, rest = t
    if _is_admin_target(keys, uid):
        return await msg.reply_text("😏 Админа банить нельзя.")
    dur = parse_duration(rest[0]) if rest else "forever"
    if dur is None:
        return await msg.reply_text("❌ Срок: число минут, 2h, 1d или forever.")
    until = "forever" if dur == "forever" else time.time() + dur
    for k in keys:
        S.bans[k] = until
    S.save()
    await msg.reply_text(f"🚫 {label} забанен у бота: {human_duration(dur)}.")


@admin_only
async def sm_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    t = resolve_target(msg, context.args)
    if not t:
        return await _need_target(update, "/sm @user 30m")
    keys, label, uid, rest = t
    if _is_admin_target(keys, uid):
        return await msg.reply_text("😏 Админа мутить нельзя.")
    dur = parse_duration(rest[0]) if rest else None
    if dur is None or dur == "forever":
        return await msg.reply_text("❌ Укажи срок: число минут, 2h или 1d. Пример: /sm @user 30m")
    for k in keys:
        S.mutes[k] = time.time() + dur
    S.save()
    await msg.reply_text(f"🔇 {label} заглушён на {human_duration(dur)}. Бот его игнорирует.")


@admin_only
async def unsb_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    t = resolve_target(msg, context.args)
    if not t:
        return await _need_target(update, "/unsb @user")
    keys, label, _, _ = t
    removed = [k for k in keys if S.bans.pop(k, None) is not None]
    S.warns.pop(keys[0], None)
    S.save()
    await msg.reply_text(f"✅ {label} разбанен." if removed else f"❌ {label} не в бане.")


@admin_only
async def unsm_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    t = resolve_target(msg, context.args)
    if not t:
        return await _need_target(update, "/unsm @user")
    keys, label, _, _ = t
    removed = [k for k in keys if S.mutes.pop(k, None) is not None]
    S.save()
    await msg.reply_text(f"✅ {label} размучен." if removed else f"❌ {label} не в муте.")


@admin_only
async def kick_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    t = resolve_target(msg, context.args)
    if not t:
        return await _need_target(update, "/kick @user")
    keys, label, uid, _ = t
    if _is_admin_target(keys, uid):
        return await msg.reply_text("😏 Админа кикать нельзя.")
    if uid is None:
        return await msg.reply_text("❌ Не знаю ID этого пользователя. Ответь командой на его сообщение.")
    if msg.chat.type == "private":
        return await msg.reply_text("❌ Кикать можно только в группах.")
    try:
        await context.bot.ban_chat_member(msg.chat.id, uid)
        await context.bot.unban_chat_member(msg.chat.id, uid, only_if_banned=True)
        await msg.reply_text(f"👢 {label} кикнут.")
    except Exception as e:
        await msg.reply_text(f"❌ Не получилось: {str(e)[:120]}\n(Нужны права админа у бота в этом чате.)")


@admin_only
async def userinfo_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    t = resolve_target(msg, context.args)
    if not t:
        return await _need_target(update, "/userinfo @user")
    keys, label, uid, _ = t
    banned = S.keys_active(S.bans, keys)
    muted = S.keys_active(S.mutes, keys)
    interpol = S.interpol.get(str(uid), {}).get("count", 0) if uid else 0
    await msg.reply_text(
        f"👤 {label}\n"
        f"🆔 ID: {uid if uid else 'неизвестен (бот его ещё не видел)'}\n"
        f"⚠️ Варнов: {S.warns.get(keys[0], 0)}/{WARN_LIMIT}\n"
        f"🚫 Бан: {'Да' if banned else 'Нет'}\n"
        f"🔇 Мут: {'Да' if muted else 'Нет'}\n"
        f"🕵️ Интерпол: {interpol}"
    )


@admin_only
async def interpol_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if context.args and context.args[0].lower() == "clear":
        S.interpol.clear()
        S.save()
        return await msg.reply_text("🕵️ Список Интерпола очищен.")
    from handlers import interpol_report
    await msg.reply_text(interpol_report() + "\n\nОчистить: /interpol clear")


# =====================================================================
# АДМИН: УТИЛИТЫ
# =====================================================================

@admin_only
async def say_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if not context.args:
        return await msg.reply_text("❌ /say текст")
    text = " ".join(context.args)
    try:
        await msg.delete()
    except Exception:
        pass
    target = msg.reply_to_message
    if target:
        await target.reply_text(text)
    else:
        await context.bot.send_message(chat_id=msg.chat.id, text=text)


@admin_only
async def del_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if not msg.reply_to_message:
        return await msg.reply_text("❌ Ответь на сообщение, которое нужно удалить.")
    for m in (msg.reply_to_message, msg):
        try:
            await m.delete()
        except Exception:
            pass


@admin_only
async def save_chat_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if not context.args:
        return await msg.reply_text("❌ /savechat имя")
    name = context.args[0].lower()
    saved_chats[name] = msg.chat.id
    save_saved_chats(saved_chats)
    await msg.reply_text(f"✅ Чат «{name}» сохранён.")


@admin_only
async def say_chat_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if len(context.args) < 2:
        return await msg.reply_text("❌ /saychat имя текст")
    name = context.args[0].lower()
    if name not in saved_chats:
        return await msg.reply_text(f"❌ Чат «{name}» не найден.")
    try:
        await context.bot.send_message(chat_id=saved_chats[name], text=" ".join(context.args[1:]))
        await msg.reply_text("✅ Отправлено.")
    except Exception as e:
        await msg.reply_text(f"❌ {str(e)[:150]}")


@admin_only
async def list_chats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if not saved_chats:
        return await msg.reply_text("📭 Нет сохранённых чатов.")
    await msg.reply_text("📋 Чаты:\n\n" + "\n".join(f"• {n} ({cid})" for n, cid in saved_chats.items()))


@admin_only
async def remove_chat_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if not context.args:
        return await msg.reply_text("❌ /removechat имя")
    name = context.args[0].lower()
    if name not in saved_chats:
        return await msg.reply_text(f"❌ Чат «{name}» не найден.")
    del saved_chats[name]
    save_saved_chats(saved_chats)
    await msg.reply_text(f"✅ Чат «{name}» удалён.")


@admin_only
async def stop_pvp_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    S.pvp_disabled.add(update.effective_message.chat.id)
    S.save()
    await update.effective_message.reply_text("🛑 Пинг-понг с ботами отключён.")


@admin_only
async def start_pvp_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    S.pvp_disabled.discard(update.effective_message.chat.id)
    S.save()
    await update.effective_message.reply_text("✅ Пинг-понг с ботами разрешён.")


# Алиасы со старыми именами
warn_command = sw_command
mute_command = sm_command
unmute_command = unsm_command
ban_command = sb_command
unban_command = unsb_command
