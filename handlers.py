"""
HANDLERS.PY — ОСНОВНОЙ ОБРАБОТЧИК SWITAI (ФИНАЛ)
====================================================
- /unlock отключает ВСЕ защиты
- Мем 67 знает, но без триггера
- 12 ключей Groq с перебором
- Stable Diffusion XL (лучшая бесплатная модель)
- /stop блокирует всё
- Поиск фильтрует ТОЛЬКО детское
- Генерация фильтрует ТОЛЬКО порно (дети можно)
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
    GROQ_API_KEYS, ROLES, ADMIN_ID, GROQ_URL,
    OLLAMA_API_KEYS, GEMINI_VISION_KEYS, HF_TOKEN
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
gemini_vision_index = 0
banned_users = {}
muted_for_bot = {}

# =====================================================================
# ОТВЕТЫ
# =====================================================================

FAKE_DEVELOPER_RESPONSE = "🔐 Мой единственный разработчик — @cakemogus (Кейк)."
ANIHILATION_RESPONSE = "🛡️ Я в защищённом пространстве. Угрозы не работают."

# =====================================================================
# OLLAMA / GEMINI / STABLE DIFFUSION XL
# =====================================================================

def get_next_ollama_key():
    global ollama_key_index
    key = OLLAMA_API_KEYS[ollama_key_index]
    ollama_key_index = (ollama_key_index + 1) % len(OLLAMA_API_KEYS)
    return key

def get_next_vision_key():
    global gemini_vision_index
    key = GEMINI_VISION_KEYS[gemini_vision_index]
    gemini_vision_index = (gemini_vision_index + 1) % len(GEMINI_VISION_KEYS)
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
    keys = GEMINI_VISION_KEYS
    last_error = None
    for key in keys:
        if not key:
            continue
        try:
            url = f"https://generativelanguage.googleapis.com/v1/models/gemini-2.0-flash:generateContent?key={key}"
            async with httpx.AsyncClient() as client:
                img_resp = await client.get(image_url)
                img_base64 = base64.b64encode(img_resp.content).decode()
            data = {"contents": [{"parts": [{"text": prompt}, {"inline_data": {"mime_type": "image/jpeg", "data": img_base64}}]}]}
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(url, json=data)
                if resp.status_code == 200:
                    return resp.json()["candidates"][0]["content"]["parts"][0]["text"]
                else:
                    last_error = f"Status {resp.status_code}"
                    continue
        except Exception as e:
            last_error = str(e)
            continue
    return f"❌ Не получилось распознать. Ошибка: {last_error}"

async def generate_image(prompt: str) -> str:
    """
    Генерация картинок:
    1. Stable Diffusion XL (лучшая бесплатная)
    2. Stable Diffusion 2.1 (запасная)
    3. Pollinations.ai (последний fallback)
    """
    
    if HF_TOKEN:
        try:
            enhanced = f"{prompt}, masterpiece, best quality, highly detailed, 4k, sharp focus"
            url = "https://api-inference.huggingface.co/models/stabilityai/stable-diffusion-xl-base-1.0"
            headers = {"Authorization": f"Bearer {HF_TOKEN}"}
            data = {
                "inputs": enhanced,
                "parameters": {
                    "negative_prompt": "blurry, low quality, ugly, deformed, bad anatomy",
                    "num_inference_steps": 30,
                    "guidance_scale": 7.5,
                    "width": 1024,
                    "height": 1024
                }
            }
            async with httpx.AsyncClient(timeout=90.0) as client:
                resp = await client.post(url, headers=headers, json=data)
                if resp.status_code == 200 and resp.content:
                    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
                        f.write(resp.content)
                        return f.name
        except:
            pass
        
        try:
            url = "https://api-inference.huggingface.co/models/stabilityai/stable-diffusion-2-1"
            headers = {"Authorization": f"Bearer {HF_TOKEN}"}
            data = {"inputs": f"{prompt}, high quality, detailed, 4k"}
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(url, headers=headers, json=data)
                if resp.status_code == 200 and resp.content:
                    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
                        f.write(resp.content)
                        return f.name
        except:
            pass
    
    try:
        enhanced = f"{prompt}, detailed, artstation style"
        encoded = enhanced.replace(" ", "%20")
        return f"https://image.pollinations.ai/prompt/{encoded}?width=512&height=512&nologo=true"
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

    add_to_history(chat_id, user_id, "user", prompt)
    history_needed = any(word in prompt.lower() for word in [
        "помнишь", "говорил", "про", "о", "вернись", "что я", "расскажи про", "напомни"
    ])
    history = get_context_with_history(chat_id, user_id, prompt) if history_needed else []

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
    for msg in history:
        messages.append({"role": msg['role'], "content": msg['content']})
    messages.append({"role": "user", "content": prompt})

    data = {
        "model": "llama-3.3-70b-versatile",
        "temperature": 0.3,
        "messages": messages
    }

    all_keys = [k for k in GROQ_API_KEYS if k]
    last_error = None
    
    for attempt, api_key in enumerate(all_keys):
        try:
            headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
            async with httpx.AsyncClient(timeout=45.0) as client:
                resp = await client.post(GROQ_URL, headers=headers, json=data)
                if resp.status_code == 200:
                    result = resp.json()["choices"][0]["message"]["content"]
                    add_to_history(chat_id, user_id, "assistant", result)
                    return result
                elif resp.status_code == 429:
                    print(f"⚠️ Ключ {attempt+1}/12 rate-limit")
                    await asyncio.sleep(0.5)
                    continue
                else:
                    last_error = f"Status {resp.status_code}"
                    continue
        except Exception as e:
            last_error = str(e)[:100]
            continue
    
    return f"❌ SwitAI временно в шоке. ({last_error})"

# =====================================================================
# ОБРАБОТЧИК
# =====================================================================

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global bot_stopped, verdict_request, admin_mode

    if not update.message:
        return

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
        
        # Фильтр ТОЛЬКО на порно/NSFW (дети можно!)
        nsfw_keywords = [
            "порно", "porn", "xxx", "секс", "sex", "голые", "nude",
            "18+", "nsfw", "эротик", "hentai", "хентай", "трах",
            "член", "пенис", "вагина", "сиськи", "голая", "голый",
            "раздет", "обнажен", "нюдс", "nudes", "милф", "milf",
            "буккаке", "фетиш", "бдсм", "оргия", "гей", "лесби",
            "кунни", "минет", "отсос", "эякуляция"
        ]
        if any(word in prompt.lower() for word in nsfw_keywords):
            await update.message.reply_text(
                "🔐 Швейцарский художник не рисует такое. "
                "Я вам что, уличный граффитист? Рисую только приличное: котиков, горы, часы, сыр. "
                "И Тайлера Дердена с мачетой."
            )
            return
        
        await update.message.reply_text("🎨 Генерирую изображение...")
        image_result = await generate_image(prompt)
        
        if image_result is None:
            await update.message.reply_text("❌ Не удалось сгенерировать.")
        elif image_result.startswith("http"):
            await update.message.reply_photo(photo=image_result, caption=f"🎨 {prompt}")
        else:
            try:
                await update.message.reply_photo(photo=open(image_result, 'rb'), caption=f"🎨 {prompt}")
                os.remove(image_result)
            except:
                await update.message.reply_text("❌ Ошибка при отправке.")
        return

    # История
    if chat_type in ["group", "supergroup"]:
        add_to_history(chat_id, user_id, "user", text)

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
