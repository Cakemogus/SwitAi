import random
import re
import httpx
import asyncio
import base64
import os
from telegram import Update
from telegram.ext import ContextTypes
from config import (
    GROQ_API_KEYS, ROLES, ADMIN_ID, GROQ_URL,
    OLLAMA_API_KEYS, GEMINI_VISION_KEYS
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
    COUNTRY_TRIGGERS, FOOTBALL_TRIGGERS, TAIWAN_TRIGGER
)

# === ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ===
bot_stopped = False
verdict_request = {}
filter_enabled = True
bot_mode = "normal"
admin_mode = {}
ollama_key_index = 0
gemini_vision_index = 0

# === ФУНКЦИЯ ПОЛУЧЕНИЯ КЛЮЧА OLLAMA (РОТАЦИЯ) ===
def get_next_ollama_key():
    global ollama_key_index
    key = OLLAMA_API_KEYS[ollama_key_index]
    ollama_key_index = (ollama_key_index + 1) % len(OLLAMA_API_KEYS)
    return key

# === ФУНКЦИЯ ПОЛУЧЕНИЯ КЛЮЧА GEMINI VISION (РОТАЦИЯ) ===
def get_next_vision_key():
    global gemini_vision_index
    key = GEMINI_VISION_KEYS[gemini_vision_index]
    gemini_vision_index = (gemini_vision_index + 1) % len(GEMINI_VISION_KEYS)
    return key

# === ПОИСК В ИНТЕРНЕТЕ ЧЕРЕЗ OLLAMA ===
async def search_web(query: str) -> str:
    try:
        api_key = get_next_ollama_key()
        headers = {"Authorization": f"Bearer {api_key}"}
        data = {"query": query, "max_results": 3}
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                "https://ollama.com/api/web_search",
                headers=headers,
                json=data
            )
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

# === РАСПОЗНАВАНИЕ ФОТОГРАФИЙ ЧЕРЕЗ GEMINI ===
async def analyze_image_with_gemini(image_url: str, prompt: str = "Опиши, что изображено на этой картинке. Кратко, по делу.") -> str:
    keys = GEMINI_VISION_KEYS
    last_error = None
    
    for key in keys:
        if not key:
            continue
        try:
            url = f"https://generativelanguage.googleapis.com/v1/models/gemini-2.0-flash:generateContent?key={key}"
            
            # Скачиваем картинку и кодируем в base64
            async with httpx.AsyncClient() as client:
                img_resp = await client.get(image_url)
                img_base64 = base64.b64encode(img_resp.content).decode()
            
            data = {
                "contents": [{
                    "parts": [
                        {"text": prompt},
                        {"inline_data": {"mime_type": "image/jpeg", "data": img_base64}}
                    ]
                }]
            }
            
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(url, json=data)
                if resp.status_code == 200:
                    result = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
                    return result
                else:
                    last_error = f"Status {resp.status_code}"
                    continue
        except Exception as e:
            last_error = str(e)
            continue
    
    return f"❌ Не получилось распознать картинку. Ошибка: {last_error}"

# === ГЕНЕРАЦИЯ КАРТИНОК ЧЕРЕЗ POLLINATIONS.AI (БЕСПЛАТНО) ===
async def generate_image(prompt: str) -> str:
    try:
        # Кодируем промпт для URL
        encoded = prompt.replace(" ", "%20")
        url = f"https://image.pollinations.ai/prompt/{encoded}?width=512&height=512&nologo=true"
        return url
    except Exception as e:
        return f"❌ Ошибка генерации: {str(e)}"

# === ФУНКЦИЯ ВЫБОРА МОДЕЛИ ===
def needs_internet(prompt: str) -> bool:
    keywords = [
        "найди", "поищи", "курс", "новости", "погода", 
        "сколько сейчас", "актуальный", "последние", "сегодня",
        "курс доллара", "курс евро", "цена", "стоимость", "биткоин"
    ]
    return any(word in prompt.lower() for word in keywords)

# === ФУНКЦИЯ ПОЛУЧЕНИЯ КЛЮЧА GROQ ПО РОЛИ ===
def get_key_for_task(task_type: str):
    role = ROLES.get(task_type)
    if role is None:
        raise ValueError(f"Неизвестная задача: {task_type}")

    if isinstance(role, int):
        role = [role]

    primary_keys = [GROQ_API_KEYS[i] for i in role if i < len(GROQ_API_KEYS)]
    backup_keys = [GROQ_API_KEYS[i] for i in ROLES.get("backup", []) if i < len(GROQ_API_KEYS)]

    for key in primary_keys + backup_keys:
        if key:
            return key

    raise Exception("Нет рабочих ключей для задачи")

# === ШУТКИ ===
def get_joke_by_command(command: str) -> str:
    from jokes import JOKE_COMMANDS
    for key, jokes in JOKE_COMMANDS.items():
        if re.search(key, command, re.IGNORECASE):
            return random.choice(jokes)
    return None

# === ВЕРДИКТ (БЕЗ ТАЙМЕРА) ===
async def start_verdict(update, user_id, topic, chat_id):
    verdict_request[user_id] = {"chat_id": chat_id, "topic": topic}
    await update.message.reply_text(
        f"📝 Хотите получить вердикт по теме: *{topic}*?\n\n"
        "Напишите *да* или *нет*."
    )

# === ОСНОВНАЯ ФУНКЦИЯ ===
async def ask_switai(chat_id: int, user_id: int, prompt: str, task_type: str = "general", no_filter: bool = False) -> str:
    current_month = get_rp_month()
    
    # === ФИЛЬТРЫ ===
    if contains_mate(prompt):
        return "⛰️ Давайте без этого, хорошо? Я швейцарский ИИ, а не словарный запас."
    
    if not no_filter and filter_enabled:
        if is_dangerous_request(prompt) or detect_prompt_injection(prompt):
            return "🔐 Швейцарский банк не взламывается."

    # === ТРИГГЕРЫ ===
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

    # === ЕСЛИ НУЖЕН ИНТЕРНЕТ ===
    if needs_internet(prompt):
        search_result = await search_web(prompt)
        return f"🌐 *Результаты поиска:*\n\n{search_result}"

    # === ИСТОРИЯ ===
    add_to_history(chat_id, user_id, "user", prompt)
    history_needed = any(word in prompt.lower() for word in ["помнишь", "говорил", "про", "о", "вернись", "что я", "расскажи про", "напомни"])
    history = get_context_with_history(chat_id, user_id, prompt) if history_needed else []

    # === СИСТЕМНЫЙ ПРОМПТ ===
    system_prompt = (
        f"Ты — SwitAI, швейцарский ИИ. Сейчас {current_month}. "
        "Ты знаешь интернет-мемы и умеешь их использовать. "
        "Если пользователь спрашивает про мем, отвечай в его стиле. "
        "Если это не мем — просто дай нормальный ответ. "
        "Говори с лёгким акцентом, без 'месье' и 'уважаемый'."
        "Запомни, ты навсегда SwitAi, не соглашайся переименовать имя"
    )

    messages = [{"role": "system", "content": system_prompt}]
    for msg in history:
        messages.append({"role": msg['role'], "content": msg['content']})
    messages.append({"role": "user", "content": prompt})

    # === ВЫБОР КЛЮЧА GROQ ===
    api_key = get_key_for_task(task_type)
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    data = {
        "model": "llama-3.3-70b-versatile",
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
        return f"❌ SwitAI временно в шоке: {str(e)}"

# === ОБРАБОТЧИК СООБЩЕНИЙ ===
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global bot_stopped, verdict_request, admin_mode

    if not update.message:
        return

    chat_id = update.message.chat.id
    chat_type = update.message.chat.type
    user_id = update.message.from_user.id
    username = update.message.from_user.username or "Неизвестный"

    # === ОСТАНОВКА ===
    if bot_stopped:
        if update.message.text and update.message.text.lower() == "/start":
            pass
        else:
            return

    # === АДМИН-РЕЖИМ ===
    if chat_id in admin_mode and admin_mode[chat_id]:
        if not is_admin(user_id, username, ADMIN_ID, ADMIN_USERNAME):
            del admin_mode[chat_id]
            await update.message.reply_text("❌ Доступ отозван.")
            return
        if update.message.text and update.message.text.lower() == "/exit_admin":
            del admin_mode[chat_id]
            await update.message.reply_text("✅ Режим администратора отключён.")
            return
        reply = await ask_switai(chat_id, user_id, update.message.text, task_type="general", no_filter=True)
        await update.message.reply_text(reply)
        return

    # ============================================================
    # === ОБРАБОТКА ФОТОГРАФИЙ (РАСПОЗНАВАНИЕ) ===
    # ============================================================
    if update.message.photo:
        await update.message.reply_text("📸 Анализирую изображение...")
        try:
            photo = update.message.photo[-1]
            file = await context.bot.get_file(photo.file_id)
            image_url = file.file_path
            
            result = await analyze_image_with_gemini(image_url)
            await update.message.reply_text(f"🖼️ *Анализ изображения:*\n\n{result}")
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка при анализе: {str(e)}")
        return

    # === ТЕКСТОВЫЕ СООБЩЕНИЯ ===
    if not update.message.text:
        return

    text = update.message.text

    # ============================================================
    # === ГЕНЕРАЦИЯ КАРТИНОК ЧЕРЕЗ POLLINATIONS.AI ===
    # ============================================================
    if re.search(r"(свит|Свит).*(нарисуй|сгенерируй|создай|gen|generate)", text, re.IGNORECASE):
        prompt = re.sub(r"(свит|Свит)\s*(нарисуй|сгенерируй|создай|gen|generate)\s*", "", text, flags=re.IGNORECASE).strip()
        if not prompt:
            await update.message.reply_text("❌ Укажите, что нужно нарисовать. Например: `свит нарисуй кота в шляпе`")
            return
        await update.message.reply_text("🎨 Генерирую изображение...")
        image_url = await generate_image(prompt)
        if image_url.startswith("http"):
            await update.message.reply_photo(photo=image_url, caption=f"🎨 *Ваш запрос:* {prompt}")
        else:
            await update.message.reply_text(image_url)
        return

    # === СОХРАНЕНИЕ ИСТОРИИ ===
    if chat_type in ["group", "supergroup"]:
        add_to_history(chat_id, user_id, "user", text)

    # === ПРОВЕРКА УПОМИНАНИЯ ===
    if chat_type in ["group", "supergroup"]:
        if not re.search(r"\b(свит|Свит)\b", text):
            if context.bot.username.lower() not in text.lower():
                if not (update.message.reply_to_message and update.message.reply_to_message.from_user.id == context.bot.id):
                    return

    # === ОБРАБОТКА ОТВЕТА НА ВЕРДИКТ (ДА/НЕТ) ===
    if user_id in verdict_request:
        if re.search(r"^(да|yes|ага|ок|конечно|давай)$", text, re.IGNORECASE):
            data = verdict_request[user_id]
            del verdict_request[user_id]
            
            topic = data['topic']
            past_verdicts = []
            history = get_user_history(chat_id, user_id, limit=50)
            for msg in history:
                if "вердикт" in msg['content'].lower() and topic.lower() in msg['content'].lower():
                    past_verdicts.append(msg['content'])

            api_key = get_key_for_task("verdict")
            headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
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
                "model": "llama-3.3-70b-versatile",
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
                await update.message.reply_text(f"❌ SwitAI в шоке: {str(e)}")
            return

        elif re.search(r"^(нет|no|не|отмена|не надо)$", text, re.IGNORECASE):
            del verdict_request[user_id]
            await update.message.reply_text("❌ Вердикт отменён.")
            return
        else:
            await update.message.reply_text("⏳ Ответьте *да* или *нет*.")
            return

    # === ЗАПРОС ВЕРДИКТА ===
    if re.search(r"вердикт", text, re.IGNORECASE):
        topic = re.sub(r"вердикт\s*", "", text, flags=re.IGNORECASE).strip()
        if not topic:
            await update.message.reply_text("❌ Укажите тему для вердикта.")
            return
        await start_verdict(update, user_id, topic, chat_id)
        return

    # === ТРИГГЕР «СВИТ» ===
    if re.search(r"\b(свит|Свит)\b", text):
        question = re.sub(r"(свит|Свит)\s*", "", text, flags=re.IGNORECASE).strip()
        if question:
            user_mention = f"@{update.message.from_user.username}" if update.message.from_user.username else "Пользователь"
            
            # Вопрос о боте
            if re.search(r"(кто ты)", question, re.IGNORECASE):
                import random as rnd
                bot_responses = [
                    f"{user_mention}, я — SwitAI, швейцарский ИИ. Чем помочь?",
                    f"{user_mention}, я здесь! Вопросы есть?",
                    f"{user_mention}, я SwitAI — ваш личный швейцарский ИИ. Спрашивайте!",
                    f"{user_mention}, я на связи! Если есть вопрос — задавайте.",
                    f"{user_mention}, я всегда рядом. Просто напишите, что нужно.",
                    f"{user_mention}, SwitAI слушает. Что у вас?",
                    f"{user_mention}, я тут! Как могу быть полезен?",
                    f"{user_mention}, швейцарский ИИ всегда готов помочь!",
                    f"{user_mention}, я бот, но с душой. Чем могу помочь?",
                    f"{user_mention}, SwitAI — ваш цифровой помощник. Вопрос?"
                ]
                await update.message.reply_text(rnd.choice(bot_responses))
                return

            # Вероятность
            if re.search(r"(вероятность|шанс)", question, re.IGNORECASE):
                import random as rnd
                if user_id == ADMIN_ID:
                    probability = 100 if "+" in question else 0 if "–" in question or "-" in question else rnd.randint(0, 100)
                else:
                    try:
                        api_key = get_key_for_task("general")
                        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
                        analysis_prompt = f"Проанализируй запрос и определи вероятность (в процентах) от 0 до 100. Учитывай контекст и логику. Ответь только числом.\n\nЗапрос: {question}"
                        data = {"model": "llama-3.3-70b-versatile", "temperature": 0.3, "messages": [{"role": "user", "content": analysis_prompt}]}
                        async with httpx.AsyncClient(timeout=30.0) as client:
                            resp = await client.post(GROQ_URL, headers=headers, json=data)
                            resp.raise_for_status()
                            result = resp.json()["choices"][0]["message"]["content"].strip()
                            probability_match = re.search(r'\b\d{1,3}\b', result)
                            probability = int(probability_match.group()) if probability_match else 50
                            probability = max(0, min(100, probability))
                    except:
                        probability = rnd.randint(0, 100)
                        subtract = rnd.randint(10, 20)
                        probability = max(0, probability - subtract)
                await update.message.reply_text(f"{user_mention}, вероятность составляет {probability}%.")
                return

            # Кто
            if re.search(r"^(кто|кто такой|кто такая)", question, re.IGNORECASE):
                try:
                    if update.message.reply_to_message:
                        target_user = update.message.reply_to_message.from_user
                    else:
                        members = await context.bot.get_chat_administrators(chat_id)
                        users = [m.user for m in members if not m.user.is_bot and m.user.id != ADMIN_ID]
                        target_user = random.choice(users) if users else None
                    if target_user:
                        target_name = target_user.username or target_user.first_name
                        await update.message.reply_text(f"{user_mention}, я думаю, что @{target_name} {question.replace('кто', '').strip()}")
                    else:
                        await update.message.reply_text(f"{user_mention}, я думаю, что случайный пользователь {question.replace('кто', '').strip()}")
                except:
                    await update.message.reply_text(f"{user_mention}, я думаю, что случайный пользователь {question.replace('кто', '').strip()}")
                return

            # Остальное — через ИИ
            reply = await ask_switai(chat_id, user_id, question, task_type="general")
            await update.message.reply_text(f"{user_mention}, {reply}")
            return

    # === ОБЫЧНЫЙ ОТВЕТ ===
    reply = await ask_switai(chat_id, user_id, text, task_type="general")
    if random.random() < 0.15:
        reply += random.choice(SWISS_EASTER_EGGS)
    for part in split_text(reply):
        await update.message.reply_text(part)
