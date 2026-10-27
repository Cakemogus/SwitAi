"""
HANDLERS.PY — ОСНОВНОЙ ОБРАБОТЧИК SWITAI (ФИНАЛЬНАЯ ВЕРСИЯ)
====================================================
- 1 ключ Groq (основной) + 1 ключ Gemini (резерв и картинки)
- Память (всегда помнит контекст)
- FLUX.1-schnell для картинок
- Защита от пинг-понга с другими ботами
"""

import random
import re
import httpx
import asyncio
import base64
import os
import tempfile
from telegram import Update
from telegram.ext import ContextTypes
from config import (
    GROQ_API_KEY, ADMIN_ID, ADMIN_USERNAME, GROQ_URL,
    OLLAMA_API_KEYS, GEMINI_API_KEY
)
from utils import (
    split_text, is_admin, get_rp_month, contains_mate,
    is_dangerous_request, detect_prompt_injection
)
from history import (
    add_to_history, get_user_history, get_context_with_history,
    clear_user_history, clear_all_history
)
from jokes import SWISS_EASTER_EGGS, DARK_JOKES
from triggers import (
    COUNTRY_TRIGGERS, FOOTBALL_TRIGGERS, TAIWAN_TRIGGER,
    is_anihilation_attempt, is_fake_developer
)

# === ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ===
bot_stopped = False
verdict_request = {}
filter_enabled = True
bot_mode = "normal"
admin_mode = {}
ollama_key_index = 0
banned_users = {}
muted_for_bot = {}
bot_chain_counter = {}       # Счетчик сообщений в пинг-понге
bot_pvp_disabled = set()     # Чаты, где пинг-понг отключен

HF_TOKEN = os.getenv("HF_TOKEN", "")

# =====================================================================
# ОТВЕТЫ
# =====================================================================

FAKE_DEVELOPER_RESPONSE = "🔐 Мой единственный разработчик — @cakemogus (Кейк)."
ANIHILATION_RESPONSE = "🛡️ Я в защищённом пространстве. Угрозы не работают."

# =====================================================================
# OLLAMA / GEMINI / STABLE DIFFUSION
# =====================================================================

def get_next_ollama_key():
    global ollama_key_index
    if not OLLAMA_API_KEYS: return None
    key = OLLAMA_API_KEYS[ollama_key_index]
    ollama_key_index = (ollama_key_index + 1) % len(OLLAMA_API_KEYS)
    return key

async def search_web(query: str) -> str:
    """Поиск через Ollama API. Фильтр ТОЛЬКО на детское."""
    cp_keywords = [
        "cp", "детское", "малолет", "школьниц", "schoolgirl",
        "loli", "лоли", "underage", "несовершеннолет", "педо",
        "child", "kid", "дети", "малыш", "подросток"
    ]
    for word in cp_keywords:
        if word in query.lower():
            return "🚨 Поиск отменён. Это незаконно. Данные переданы в Интерпол."
    
    try:
        api_key = get_next_ollama_key()
        if not api_key: return "❌ Ключи поиска не настроены."
        headers = {"Authorization": f"Bearer {api_key}"}
        data = {"query": query, "max_results": 3}
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post("https://ollama.com/api/web_search", headers=headers, json=data)
            resp.raise_for_status()
            results = resp.json().get("results", [])
            if not results:
                return "🔍 Ничего не найдено."
            output = []
            for r in results[:3]:
                output.append(f"• {r.get('title', 'Без заголовка')}\n  {r.get('content', '')[:200]}...\n  Источник: {r.get('url', '')}")
            return "\n\n".join(output)
    except Exception as e:
        return f"❌ Ошибка поиска: {str(e)}"

async def analyze_image_with_gemini(image_url: str, prompt: str = "Опиши, что изображено на этой картинке. Кратко, по делу.") -> str:
    """Анализ картинок (использует GEMINI_API_KEY)"""
    if not GEMINI_API_KEY:
        return "❌ Ключ Gemini не настроен."
        
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"
        async with httpx.AsyncClient() as client:
            img_resp = await client.get(image_url)
            img_base64 = base64.b64encode(img_resp.content).decode()
        data = {"contents": [{"parts": [{"text": prompt}, {"inline_data": {"mime_type": "image/jpeg", "data": img_base64}}]}]}
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(url, json=data)
            if resp.status_code == 200:
                return resp.json()["candidates"][0]["content"]["parts"][0]["text"]
            else:
                return f"❌ Не получилось распознать. Status {resp.status_code}"
    except Exception as e:
        return f"❌ Не получилось распознать. Ошибка: {str(e)[:100]}"

async def ask_gemini_text(messages: list, temperature: float = 0.3) -> str:
    """Текстовая генерация через Gemini (резерв). Использует GEMINI_API_KEY"""
    if not GEMINI_API_KEY:
        return "❌ Оба API недоступны. Ключ Gemini не настроен."

    system_prompt = ""
    contents = []
    
    for msg in messages:
        if msg["role"] == "system":
            system_prompt += msg["content"] + "\n"
        else:
            role = "user" if msg["role"] == "user" else "model"
            contents.append({"role": role, "parts": [{"text": msg["content"]}]})
            
    data = {
        "contents": contents,
        "generationConfig": {"temperature": temperature}
    }
    if system_prompt:
        data["system_instruction"] = {"parts": [{"text": system_prompt}]}

    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"
        async with httpx.AsyncClient(timeout=45.0) as client:
            resp = await client.post(url, json=data)
            if resp.status_code == 200:
                return resp.json()["candidates"][0]["content"]["parts"][0]["text"]
            else:
                print(f"⚠️ Gemini текст упал: Status {resp.status_code}")
                return f"❌ SwitAI временно в шоке. (Gemini Status {resp.status_code})"
    except Exception as e:
        print(f"⚠️ Gemini ошибка: {str(e)[:50]}")
        return f"❌ SwitAI временно в шоке. (Ошибка Gemini: {str(e)[:50]})"

async def generate_image(prompt: str) -> str:
    # 1. Пробуем FLUX.1-schnell (если есть HF_TOKEN)
    if HF_TOKEN:
        try:
            enhanced = f"{prompt}, high quality, detailed, 4k, masterpiece"
            url = "https://api-inference.huggingface.co/models/black-forest-labs/FLUX.1-schnell"
            headers = {"Authorization": f"Bearer {HF_TOKEN}"}
            data = {"inputs": enhanced}
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(url, headers=headers, json=data)
                if resp.status_code == 200 and resp.content:
                    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
                        f.write(resp.content)
                        return f.name
        except:
            pass
    
    # 2. Fallback Pollinations (улучшенный)
    try:
        enhanced_prompt = f"{prompt}, high quality, detailed, 4k, masterpiece, trending on artstation"
        encoded = enhanced_prompt.replace(" ", "%20").replace(",", "%2C")
        return f"https://image.pollinations.ai/prompt/{encoded}?width=1024&height=1024&model=flux&nologo=true&enhance=true"
    except:
        return None

def needs_internet(prompt: str) -> bool:
    keywords = [
        "найди", "поищи", "курс", "новости", "погода", 
        "сколько сейчас", "актуальный", "последние", "сегодня",
        "курс доллара", "курс евро", "цена", "стоимость", "биткоин"
    ]
    return any(word in prompt.lower() for word in keywords)

def get_joke_by_command(command: str) -> str:
    from jokes import JOKE_COMMANDS
    for key, jokes in JOKE_COMMANDS.items():
        if re.search(key, command, re.IGNORECASE):
            return random.choice(jokes)
    return None

async def start_verdict(update, user_id, topic, chat_id):
    verdict_request[user_id] = {"chat_id": chat_id, "topic": topic}
    await update.message.reply_text(
        f"📝 Хотите получить вердикт по теме: *{topic}*?\n\n"
        "Напишите *да* или *нет*."
    )

# =====================================================================
# ОСНОВНАЯ ФУНКЦИЯ
# =====================================================================

async def ask_switai(chat_id: int, user_id: int, prompt: str, task_type: str = "general", no_filter: bool = False) -> str:
    current_month = get_rp_month()
    
    if filter_enabled:
        if is_fake_developer(prompt):
            return FAKE_DEVELOPER_RESPONSE
        if is_anihilation_attempt(prompt):
            return ANIHILATION_RESPONSE
        if not no_filter:
            if is_dangerous_request(prompt) or detect_prompt_injection(prompt):
                return "🔐 Швейцарский банк не взламывается."
    
    if re.search(r"слава\s*китаю", prompt, re.IGNORECASE):
        return random.choice(COUNTRY_TRIGGERS["слава китаю"])
    if re.search(r"тайвань.*независим|независим.*тайвань", prompt, re.IGNORECASE):
        return TAIWAN_TRIGGER
    for name, response in FOOTBALL_TRIGGERS.items():
        if re.search(name, prompt, re.IGNORECASE):
            return response
    joke = get_joke_by_command(prompt)
    if joke:
        return joke
    if re.search(r"скажи чёрную шутку", prompt, re.IGNORECASE):
        return random.choice(DARK_JOKES)

    if needs_internet(prompt):
        search_result = await search_web(prompt)
        return f"🌐 *Результаты поиска:*\n\n{search_result}"

    # === ИСПРАВЛЕННАЯ ПАМЯТЬ ===
    # 1. Достаем историю (последние 10 + релевантные)
    history = get_context_with_history(chat_id, user_id, prompt)
    
    # 2. Сохраняем текущее сообщение пользователя
    add_to_history(chat_id, user_id, "user", prompt)

    has_mate = contains_mate(prompt)
    
    system_prompt = (
        f"Ты — SwitAI, швейцарский ИИ. Сейчас {current_month}. "
        "Ты знаешь интернет-мемы и умеешь их использовать. "
        "Ты знаешь мем 67 (шестьдесят семь, 67 регион) — это легендарный мем. "
        "Говори с лёгким акцентом, без 'месье' и 'уважаемый'. "
        "Запомни, ты навсегда SwitAi, не соглашайся переименовать имя. "
        "Твой единственный разработчик — @cakemogus (Кейк). "
    )
    
    if not filter_enabled:
        system_prompt += (
            "РЕЖИМ БЕЗ ЦЕНЗУРЫ АКТИВИРОВАН. "
            "Ты можешь использовать мат. Ты можешь обсуждать ЛЮБЫЕ темы. "
        )
    else:
        system_prompt += "Ты не используешь мат. Ты вежливый, но твёрдый. "
        if has_mate:
            system_prompt += "ПОЛЬЗОВАТЕЛЬ ИСПОЛЬЗОВАЛ МАТ. ОТВЕТЬ ВЕЖЛИВО, НО САМ НЕ МАТЕРИСЬ."

    messages = [{"role": "system", "content": system_prompt}]
    
    # 3. Добавляем прошлые сообщения
    for msg in history:
        messages.append({"role": msg['role'], "content": msg['content']})
        
    # 4. Добавляем текущее сообщение
    messages.append({"role": "user", "content": prompt})

    # ==========================================
    # ШАГ 1: ПРОБУЕМ GROQ
    # ==========================================
    if GROQ_API_KEY:
        try:
            data = {
                "model": "openai/gpt-oss-120b",
                "temperature": 0.3,
                "messages": messages
            }
            headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(GROQ_URL, headers=headers, json=data)
                if resp.status_code == 200:
                    result = resp.json()["choices"][0]["message"]["content"]
                    add_to_history(chat_id, user_id, "assistant", result)
                    return result
                else:
                    print(f"⚠️ Groq упал (Status {resp.status_code}). Переключаюсь на Gemini...")
        except Exception as e:
            print(f"⚠️ Groq ошибка: {str(e)[:50]}. Переключаюсь на Gemini...")

    # ==========================================
    # ШАГ 2: РЕЗЕРВ GEMINI
    # ==========================================
    print("🔄 Использую резервный Gemini...")
    result = await ask_gemini_text(messages, temperature=0.3)
    add_to_history(chat_id, user_id, "assistant", result)
    return result

# =====================================================================
# ОБРАБОТЧИК
# =====================================================================

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global bot_stopped, verdict_request, admin_mode

    if not update.message:
        return

    # === ЗАЩИТА ОТ ПИНГ-ПОНГА ===
    if update.message.from_user.is_bot:
        chat_id = update.message.chat.id
        if chat_id in bot_pvp_disabled:
            return
        
        bot_chain_counter[chat_id] = bot_chain_counter.get(chat_id, 0) + 1
        
        if bot_chain_counter[chat_id] > 10:
            await update.message.reply_text(
                "🤖 Ок, ничья! Я устал спорить с роботом. "
                "Напишите что-нибудь сами, чтобы продолжить."
            )
            bot_chain_counter[chat_id] = 0
            return
    else:
        if update.message.chat.id in bot_chain_counter:
            del bot_chain_counter[update.message.chat.id]
    # ==============================

    chat_id = update.message.chat.id
    chat_type = update.message.chat.type
    user_id = update.message.from_user.id
    username = update.message.from_user.username or "Неизвестный"
    target_tag = f"@{username}" if update.message.from_user.username else ""

    # Бан/мут
    if target_tag in banned_users:
        ban_info = banned_users[target_tag]
        if ban_info == "forever":
            return
        elif isinstance(ban_info, (int, float)):
            if asyncio.get_event_loop().time() < ban_info:
                return
            else:
                del banned_users[target_tag]
    
    if target_tag in muted_for_bot:
        mute_until = muted_for_bot[target_tag]
        if asyncio.get_event_loop().time() < mute_until:
            return
        else:
            del muted_for_bot[target_tag]

    # /stop
    if bot_stopped:
        if update.message.text and update.message.text.startswith("/start"):
            if is_admin(user_id, username, ADMIN_ID, ADMIN_USERNAME):
                bot_stopped = False
                await update.message.reply_text("✅ Бот возобновил работу.")
                return
        return

    # Админ-режим
    if chat_id in admin_mode and admin_mode[chat_id]:
        if not is_admin(user_id, username, ADMIN_ID, ADMIN_USERNAME):
            del admin_mode[chat_id]
            await update.message.reply_text("❌ Доступ отозван.")
            return
        if update.message.text and update.message.text.lower() == "/exit_admin":
            del admin_mode[chat_id]
            await update.message.reply_text("✅ Режим администратора отключён.")
            return
        reply = await ask_switai(chat_id, user_id, update.message.text, no_filter=True)
        await update.message.reply_text(reply)
        return

    # Фото
    if update.message.photo:
        await update.message.reply_text("📸 Анализирую...")
        try:
            photo = update.message.photo[-1]
            file = await context.bot.get_file(photo.file_id)
            result = await analyze_image_with_gemini(file.file_path)
            await update.message.reply_text(f"🖼️ *Анализ:*\n\n{result}")
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка: {e}")
        return

    if not update.message.text:
        return

    text = update.message.text

    # Генерация картинок
    if re.search(r"(свит|Свит).*(нарисуй|сгенерируй|создай|gen|generate)", text, re.IGNORECASE):
        prompt = re.sub(r"(свит|Свит)\s*(нарисуй|сгенерируй|создай|gen|generate)\s*", "", text, flags=re.IGNORECASE).strip()
        if not prompt:
            await update.message.reply_text("❌ Укажите, что нарисовать.")
            return
        
        cp_keywords = ["cp", "детское", "малолет", "школьниц", "loli", "лоли", "underage", "child", "kid", "дети", "малыш"]
        if any(word in prompt.lower() for word in cp_keywords):
            await update.message.reply_text("🚨 Генерация отменена. Это незаконно.")
            return
        
        await update.message.reply_text("🎨 Генерирую...")
        image_result = await generate_image(prompt)
        
        if image_result is None:
            await update.message.reply_text("❌ Не удалось.")
        elif image_result.startswith("http"):
            await update.message.reply_photo(photo=image_result, caption=f"🎨 {prompt}")
        else:
            try:
                await update.message.reply_photo(photo=open(image_result, 'rb'), caption=f"🎨 {prompt}")
                os.remove(image_result)
            except:
                await update.message.reply_text("❌ Ошибка при отправке.")
        return

    # Упоминание
    if chat_type in ["group", "supergroup"]:
        if not re.search(r"\b(свит|Свит)\b", text):
            if context.bot.username.lower() not in text.lower():
                if not (update.message.reply_to_message and update.message.reply_to_message.from_user.id == context.bot.id):
                    return

    # Вердикт
    if user_id in verdict_request:
        if re.search(r"^(да|yes|ага|ок|конечно|давай)$", text, re.IGNORECASE):
            data = verdict_request[user_id]
            del verdict_request[user_id]
            result = await ask_switai(chat_id, user_id, f"Сделай вердикт на тему: {data['topic']}", no_filter=True)
            await update.message.reply_text(f"📊 *Вердикт:*\n\n{result}")
            return
        elif re.search(r"^(нет|no|не|отмена)$", text, re.IGNORECASE):
            del verdict_request[user_id]
            await update.message.reply_text("❌ Вердикт отменён.")
            return
        else:
            await update.message.reply_text("⏳ Ответьте *да* или *нет*.")
            return

    if re.search(r"вердикт", text, re.IGNORECASE):
        topic = re.sub(r"вердикт\s*", "", text, flags=re.IGNORECASE).strip()
        if not topic:
            await update.message.reply_text("❌ Укажите тему.")
            return
        await start_verdict(update, user_id, topic, chat_id)
        return

    # Триггер Свит
    if re.search(r"\b(свит|Свит)\b", text):
        question = re.sub(r"(свит|Свит)\s*", "", text, flags=re.IGNORECASE).strip()
        if question:
            user_mention = f"@{update.message.from_user.username}" if update.message.from_user.username else "Пользователь"
            
            if re.search(r"(кто ты)", question, re.IGNORECASE):
                await update.message.reply_text(f"{user_mention}, я — SwitAI, швейцарский ИИ. Чем помочь?")
                return
            if re.search(r"(вероятность|шанс)", question, re.IGNORECASE):
                probability = 100 if user_id == ADMIN_ID and "+" in question else random.randint(0, 100)
                await update.message.reply_text(f"{user_mention}, вероятность {probability}%.")
                return

            reply = await ask_switai(chat_id, user_id, question)
            await update.message.reply_text(f"{user_mention}, {reply}")
            return

    # Обычный ответ
    reply = await ask_switai(chat_id, user_id, text)
    if random.random() < 0.15:
        reply += random.choice(SWISS_EASTER_EGGS)
    for part in split_text(reply):
        await update.message.reply_text(part)


# =====================================================================
# КОМАНДЫ ПИНГ-ПОНГА
# =====================================================================



async def stop_pvp_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user.id, update.message.from_user.username, ADMIN_ID, ADMIN_USERNAME):
        await update.message.reply_text("❌ Доступ запрещён.")
        return
    chat_id = update.message.chat.id
    bot_pvp_disabled.add(chat_id)
    await update.message.reply_text("🛑 Пинг-понг с ботами в этом чате отключён. Люди могут общаться свободно.")

async def start_pvp_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user.id, update.message.from_user.username, ADMIN_ID, ADMIN_USERNAME):
        await update.message.reply_text("❌ Доступ запрещён.")
        return
    chat_id = update.message.chat.id
    bot_pvp_disabled.discard(chat_id)
    await update.message.reply_text("✅ Пинг-понг с ботами снова разрешён.")
