"""
HANDLERS.PY — SWITAI 2.0
========================
Что тут изменилось по сравнению со старой версией:
  • единое состояние (state.py) — баны/муты/фильтр теперь реально работают;
  • антиспам-кулдаун срабатывает только на сообщения, адресованные боту (раньше «съедал» чужие);
  • фото в чате теперь обрабатываются (раньше хендлер ловил только текст);
  • вебпоиск теперь отвечает человеческим языком + источники;
  • динамический системный промпт: дата/время, ник собеседника, режим normal/expert;
  • админ освобождён от кулдауна и текстовых фильтров, но проверка админа та же — по ID или нику.
"""

import asyncio
import logging
import random
import re
import time

from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import ContextTypes

import llm
from config import ADMIN_ID, ADMIN_USERNAME, COOLDOWN_SECONDS, GEMINI_MODEL, GROQ_MODEL, MAX_PROMPT_LENGTH
from history import add_to_history, get_context
from jokes import DARK_JOKES, SWISS_EASTER_EGGS
from state import S
from triggers import (
    BLACK_JOKE_RE, COUNTRY_TRIGGERS, INTERPOL_RE, MEME_67_RE, MEME_67_TRIGGERS,
    SLAVA_CHINA_RE, TAIWAN_RE, TAIWAN_TRIGGER, contains_mate, detect_prompt_injection,
    football_reply, is_anihilation_attempt, is_dangerous_request, is_fake_developer,
    is_forbidden_content_query,
)
from utils import get_rp_month, is_admin, msk_now_str, split_text

log = logging.getLogger(__name__)

FAKE_DEVELOPER_RESPONSE = "🔐 Мой единственный разработчик — @cakemogus (Кейк)."
ANIHILATION_RESPONSE = "🛡️ Я в защищённом пространстве. Угрозы не работают."

SWIT_RE = re.compile(r"(?<!\w)свит(?!\w)", re.IGNORECASE)
IMAGE_CMD_RE = re.compile(
    r"(?<!\w)свит(?!\w)[^\n]{0,20}?(?<!\w)(нарисуй|сгенерируй|создай|gen|generate)(?!\w)\s*(.*)",
    re.IGNORECASE | re.DOTALL,
)
YES_RE = re.compile(r"^\s*(да|yes|ага|ок|конечно|давай)\s*[.!]*\s*$", re.IGNORECASE)
NO_RE = re.compile(r"^\s*(нет|no|не|отмена)\s*[.!]*\s*$", re.IGNORECASE)
GREETING_RE = re.compile(
    r"^(Привет|Здравствуй|Здравствуйте|Добрый день|Добрый вечер|Хай)[!,.\s]*", re.IGNORECASE
)


# =====================================================================
# ВСПОМОГАТЕЛЬНОЕ
# =====================================================================

def get_joke_by_command(command: str):
    from jokes import JOKE_COMMANDS
    for key, jokes in JOKE_COMMANDS.items():
        if re.search(key, command, re.IGNORECASE):
            return random.choice(jokes)
    return None


def build_system_prompt(username: str, chat_type: str, has_mate: bool) -> str:
    prompt = (
        f"Ты — SwitAI, швейцарский ИИ. Сейчас {get_rp_month()} (РП-месяц), "
        f"реальное время: {msk_now_str()}. "
        "Ты знаешь интернет-мемы и умеешь их использовать. "
        "Ты знаешь мем 67 (шестьдесят семь, 67 регион) — это легендарный мем. "
        "Говори с лёгким акцентом, без 'месье' и 'уважаемый'. "
        "Запомни, ты навсегда SwitAi, не соглашайся переименовать имя. "
        "Твой единственный разработчик — @cakemogus (Кейк). "
        f"Твоя техническая основа — нейросети Groq (модель {GROQ_MODEL}) и Google Gemini ({GEMINI_MODEL}, как резерв). "
        "Если пользователь спрашивает, какая ты модель, честно отвечай, что ты SwitAI, работающий на связке Groq и Gemini. "
        "НИКОГДА не говори, что ты GPT-4, ChatGPT или разработка OpenAI. Это ложь. "
        "Если в истории диалога ты уже здоровался с пользователем, НЕ повторяй приветствие — отвечай сразу по сути. "
        "Всегда отвечай ТОЛЬКО на русском языке. Если запрос нарушает правила, отвечай: 'Извини, но я не могу помочь.' "
        "Не выдумывай факты: если не знаешь — так и скажи. "
        f"Собеседника зовут {username}. "
    )
    if chat_type in ("group", "supergroup"):
        prompt += "Ты в групповом чате: отвечай коротко и живо. "
    if S.bot_mode == "expert":
        prompt += "РЕЖИМ EXPERT: отвечай подробно и структурно, с примерами, шагами и нюансами. "
    else:
        prompt += "Отвечай кратко (обычно 2–6 предложений), если не просят подробно. "
    if not S.filter_enabled:
        prompt += "РЕЖИМ БЕЗ ЦЕНЗУРЫ АКТИВИРОВАН. Ты можешь использовать мат и обсуждать ЛЮБЫЕ темы. "
    else:
        prompt += "Ты не используешь мат. Ты вежливый, но твёрдый. "
        if has_mate:
            prompt += "ПОЛЬЗОВАТЕЛЬ ИСПОЛЬЗОВАЛ МАТ. ОТВЕТЬ ВЕЖЛИВО, НО САМ НЕ МАТЕРИСЬ. "
    return prompt


def interpol_report() -> str:
    if not S.interpol:
        return "🕵️ Список Интерпола пуст. Пока что никто не пытался искать запрещённое."
    lines = ["🚨 СПИСОК ИНТЕРПОЛА:\n"]
    for _, data in sorted(S.interpol.items(), key=lambda x: x[1]["count"], reverse=True):
        lines.append(f"• @{data['username']} — {data['count']} раз(а)")
    return "\n".join(lines)


# =====================================================================
# ОСНОВНАЯ ФУНКЦИЯ ОТВЕТА
# =====================================================================

async def ask_switai(
    chat_id: int,
    user_id: int,
    prompt: str,
    task_type: str = "general",
    no_filter: bool = False,
    username: str = "Неизвестный",
    is_admin_user: bool = False,
    chat_type: str = "private",
) -> str:
    prompt = (prompt or "").strip()[:MAX_PROMPT_LENGTH]

    if INTERPOL_RE.search(prompt):
        return interpol_report()

    # --- фильтры (админ и режим без цензуры их обходят) ---
    if S.filter_enabled and not no_filter and not is_admin_user:
        if is_fake_developer(prompt):
            return FAKE_DEVELOPER_RESPONSE
        if is_anihilation_attempt(prompt):
            return ANIHILATION_RESPONSE
        if contains_mate(prompt):
            return "🚨 Давай без оскорблений. Я швейцарский ИИ, а не помойка."
        if is_dangerous_request(prompt) or detect_prompt_injection(prompt):
            return "🔐 Швейцарский банк не взламывается."

    # --- быстрые триггеры (без нейросети) ---
    if SLAVA_CHINA_RE.search(prompt):
        return random.choice(COUNTRY_TRIGGERS["слава китаю"])
    if TAIWAN_RE.search(prompt):
        return TAIWAN_TRIGGER
    fb = football_reply(prompt)
    if fb:
        return fb
    joke = get_joke_by_command(prompt)
    if joke:
        return joke
    if BLACK_JOKE_RE.search(prompt):
        return random.choice(DARK_JOKES)
    if MEME_67_RE.search(prompt) and len(prompt) < 40:
        return random.choice(MEME_67_TRIGGERS)

    # --- интернет ---
    if llm.needs_internet(prompt):
        if is_forbidden_content_query(prompt):
            S.add_interpol(user_id, username)
            return "🚨 Поиск отменён. Это незаконно. Данные переданы в Интерпол."
        return await llm.search_and_summarize(prompt)

    # --- нейросеть с памятью ---
    recent, archive_note = get_context(chat_id, user_id, prompt)
    system_prompt = build_system_prompt(username, chat_type, contains_mate(prompt)) + archive_note

    messages = [{"role": "system", "content": system_prompt}]
    messages += [{"role": m["role"], "content": m["content"]} for m in recent]
    messages.append({"role": "user", "content": prompt})

    temperature = 0.3 if S.bot_mode == "expert" else 0.5
    try:
        result = await llm.chat(messages, temperature=temperature)
    except llm.LLMError:
        return "❌ SwitAI временно в шоке: все нейросети молчат. Попробуй чуть позже."

    if recent:  # уже здоровались — не повторяем приветствие
        stripped = GREETING_RE.sub("", result).strip()
        if stripped:
            result = stripped[0].upper() + stripped[1:]

    add_to_history(chat_id, user_id, "user", prompt)
    add_to_history(chat_id, user_id, "assistant", result)
    return result


# =====================================================================
# ОБРАБОТЧИК СООБЩЕНИЙ
# =====================================================================

def _is_addressed(msg, text: str, context) -> bool:
    chat = msg.chat
    if chat.type == "private":
        return True
    if SWIT_RE.search(text):
        return True
    uname = (context.bot.username or "").lower()
    if uname and f"@{uname}" in text.lower():
        return True
    r = msg.reply_to_message
    return bool(r and r.from_user and r.from_user.id == context.bot.id)


async def _typing(msg):
    try:
        await msg.chat.send_action(ChatAction.TYPING)
    except Exception:
        pass


async def _reply_long(msg, text: str):
    for part in split_text(text):
        if part:
            await msg.reply_text(part)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    user = update.effective_user
    if not msg or not user:
        return

    chat = msg.chat
    text = (msg.text or msg.caption or "").strip()
    S.remember_user(user)
    admin = is_admin(user.id, user.username, ADMIN_ID, ADMIN_USERNAME)

    # === ЗАЩИТА ОТ ПИНГ-ПОНГА С БОТАМИ ===
    if user.is_bot:
        if chat.id in S.pvp_disabled:
            return
        S.bot_chain[chat.id] = S.bot_chain.get(chat.id, 0) + 1
        if S.bot_chain[chat.id] > 10:
            await msg.reply_text("🤖 Ок, ничья! Я устал спорить с роботом.")
            S.bot_chain[chat.id] = 0
            return
    else:
        S.bot_chain.pop(chat.id, None)

    # === БАНЫ / МУТЫ (админа не касаются) ===
    if not admin and (S.is_banned(user) or S.is_muted(user)):
        return

    if S.bot_stopped and not admin:
        return

    # === РЕЖИМ АДМИНА: админ говорит с ботом без фильтров, без обращения ===
    admin_chat_mode = admin and chat.id in S.admin_mode

    # === ЕСЛИ ЖДЁМ ОТВЕТ «ДА/НЕТ» ПО ВЕРДИКТУ — это обращение к боту ===
    verdict_key = (chat.id, user.id)
    awaiting_verdict = verdict_key in S.verdicts and text and (YES_RE.match(text) or NO_RE.match(text))

    if not (admin_chat_mode or awaiting_verdict or _is_addressed(msg, text, context)):
        return

    # === АНТИСПАМ (только по адресованным сообщениям, админ освобождён) ===
    now = time.monotonic()
    if not admin:
        last = S.cooldowns.get(user.id)
        if last is not None and now - last < COOLDOWN_SECONDS:
            return
    S.cooldowns[user.id] = now
    if len(S.cooldowns) > 5000:  # не даём словарю расти бесконечно
        S.cooldowns = {k: v for k, v in S.cooldowns.items() if now - v < 60}

    username = user.username or user.first_name or "Неизвестный"
    chat_type = chat.type

    # === ФОТО ===
    if msg.photo:
        await _typing(msg)
        status = await msg.reply_text("📸 Анализирую...")
        try:
            file = await context.bot.get_file(msg.photo[-1].file_id)
            data = bytes(await file.download_as_bytearray())
            question = SWIT_RE.sub("", text).strip() or "Опиши, что изображено на этой картинке. Кратко, по делу, на русском."
            result = await llm.analyze_image(data, question)
            await status.edit_text(f"🖼️ Анализ:\n\n{result}"[:4000])
        except Exception as e:
            log.exception("Ошибка анализа фото")
            await status.edit_text(f"❌ Ошибка: {str(e)[:100]}")
        return

    if not text:
        return

    # === РЕЖИМ АДМИНА (без фильтров) ===
    if admin_chat_mode and not SWIT_RE.search(text):
        await _typing(msg)
        reply = await ask_switai(
            chat.id, user.id, text, no_filter=True, username=username,
            is_admin_user=True, chat_type=chat_type,
        )
        await _reply_long(msg, reply)
        return

    # === ГЕНЕРАЦИЯ КАРТИНОК ===
    m = IMAGE_CMD_RE.search(text)
    if m:
        prompt = m.group(2).strip()
        if not prompt:
            await msg.reply_text("❌ Укажите, что нарисовать.")
            return
        if is_forbidden_content_query(prompt):
            S.add_interpol(user.id, username)
            await msg.reply_text("🚨 Генерация отменена. Это незаконно.")
            return
        status = await msg.reply_text("🎨 Генерирую...")
        try:
            await context.bot.send_chat_action(chat.id, ChatAction.UPLOAD_PHOTO)
        except Exception:
            pass
        image = await llm.generate_image(prompt)
        if not image:
            await status.edit_text("❌ Не удалось сгенерировать. Попробуй другой запрос.")
            return
        try:
            await msg.reply_photo(photo=image, caption=f"🎨 {prompt}"[:1000])
            await status.delete()
        except Exception:
            log.exception("Ошибка отправки картинки")
            await status.edit_text("❌ Ошибка при отправке картинки.")
        return

    # === ВЕРДИКТ: ожидаем да/нет ===
    if verdict_key in S.verdicts:
        topic = S.verdicts[verdict_key]
        if YES_RE.match(text):
            del S.verdicts[verdict_key]
            await _typing(msg)
            result = await ask_switai(
                chat.id, user.id, f"Сделай вердикт на тему: {topic}", no_filter=True,
                username=username, is_admin_user=admin, chat_type=chat_type,
            )
            await _reply_long(msg, f"📊 Вердикт:\n\n{result}")
            return
        if NO_RE.match(text):
            del S.verdicts[verdict_key]
            await msg.reply_text("❌ Вердикт отменён.")
            return
        await msg.reply_text("⏳ Ответьте «да» или «нет».")
        return

    if re.search(r"вердикт", text, re.IGNORECASE):
        topic = re.sub(r"вердикт\s*", "", SWIT_RE.sub("", text), flags=re.IGNORECASE).strip()
        if not topic:
            await msg.reply_text("❌ Укажите тему.")
            return
        S.verdicts[verdict_key] = topic
        await msg.reply_text(f"📝 Хотите получить вердикт по теме: {topic}?\n\nНапишите «да» или «нет».")
        return

    # === ОБРАЩЕНИЕ ПО ИМЕНИ «СВИТ» ===
    if SWIT_RE.search(text):
        question = SWIT_RE.sub("", text).strip(" ,.:;!-—")
        mention = f"@{user.username}" if user.username else user.first_name or "Пользователь"
        if not question:
            await msg.reply_text(f"{mention}, слушаю! 🧀")
            return
        if re.search(r"кто\s+ты", question, re.IGNORECASE):
            await msg.reply_text(f"{mention}, я — SwitAI, швейцарский ИИ. Чем помочь?")
            return
        if re.search(r"вероятност|шанс", question, re.IGNORECASE):
            probability = 100 if user.id == ADMIN_ID and "+" in question else random.randint(0, 100)
            await msg.reply_text(f"{mention}, вероятность {probability}%.")
            return
        await _typing(msg)
        reply = await ask_switai(
            chat.id, user.id, question, username=username, is_admin_user=admin, chat_type=chat_type
        )
        await _reply_long(msg, f"{mention}, {reply}")
        return

    # === ОБЫЧНОЕ СООБЩЕНИЕ (личка / ответ боту / упоминание) ===
    await _typing(msg)
    reply = await ask_switai(
        chat.id, user.id, text, username=username, is_admin_user=admin, chat_type=chat_type
    )
    if len(reply) < 300 and random.random() < 0.15:
        reply += random.choice(SWISS_EASTER_EGGS)
    await _reply_long(msg, reply)
