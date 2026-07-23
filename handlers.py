import random
import re
import httpx
import asyncio
from telegram import Update
from telegram.ext import ContextTypes
from config import GROQ_API_KEYS, ROLES, ADMIN_ID
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
verdict_request = {}
filter_enabled = True
bot_mode = "normal"

# === ФУНКЦИЯ ПОЛУЧЕНИЯ КЛЮЧА ПО РОЛИ ===
def get_key_for_task(task_type: str):
    role = ROLES.get(task_type)
    if role is None:
        raise ValueError(f"Неизвестная задача: {task_type}")

    # Если роль — число (один ключ), превращаем в список
    if isinstance(role, int):
        role = [role]

    primary_keys = [GROQ_API_KEYS[i] for i in role if i < len(GROQ_API_KEYS)]
    backup_keys = [GROQ_API_KEYS[i] for i in ROLES.get("backup", []) if i < len(GROQ_API_KEYS)]

    # Сначала пробуем основные
    for key in primary_keys:
        if key:
            return key

    # Потом резервные
    for key in backup_keys:
        if key:
            return key

    # Если ничего нет — падаем
    raise Exception("Нет рабочих ключей для задачи")

# === ШУТКИ ===
def get_joke_by_command(command: str) -> str:
    from jokes import JOKE_COMMANDS
    for key, jokes in JOKE_COMMANDS.items():
        if re.search(key, command, re.IGNORECASE):
            return random.choice(jokes)
    return None

# === ОСНОВНАЯ ФУНКЦИЯ ===
async def ask_switai(chat_id: int, user_id: int, prompt: str, task_type: str = "general", no_filter: bool = False) -> str:
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
    
    # === ВЫБОР КЛЮЧА ПО ЗАДАЧЕ ===
    api_key = get_key_for_task(task_type)
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    data = {
        "model": "groq/compound",
        "temperature": 0.3,
        "messages": messages
    }
    
    try:
        await asyncio.sleep(0.5)
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=data)
            resp.raise_for_status()
            result = resp.json()["choices"][0]["message"]["content"]
            add_to_history(chat_id, user_id, "assistant", result)
            return result
    except Exception as e:
        return f"❌ Швейцарский ИИ временно в шоке: {str(e)}"

# === ОБРАБОТЧИК СООБЩЕНИЙ ===
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global bot_stopped, verdict_request
    
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
        reply = await ask_switai(chat_id, user_id, text, task_type="general", no_filter=True)
        await update.message.reply_text(reply)
        return
    
    # === СОХРАНЕНИЕ ИСТОРИИ ===
    if chat_type in ["group", "supergroup"]:
        add_to_history(chat_id, user_id, "user", text)
    
    # === ПРОВЕРКА УПОМИНАНИЯ (ТОЛЬКО ЕСЛИ НЕТ «СВИТ») ===
    if chat_type in ["group", "supergroup"]:
        if not re.search(r"\b(свит|Свит)\b", text):
            if context.bot.username.lower() not in text.lower():
                if not (update.message.reply_to_message and update.message.reply_to_message.from_user.id == context.bot.id):
                    return
    
    # === ТРИГГЕР НА «СВИТ» ===
    if re.search(r"\b(свит|Свит)\b", text):
        question = re.sub(r"(свит|Свит)\s*", "", text, flags=re.IGNORECASE).strip()
        if question:
            user_mention = f"@{update.message.from_user.username}" if update.message.from_user.username else "Пользователь"
            
            # === 1. Вердикт (в приоритете) ===
            if re.search(r"вердикт", question, re.IGNORECASE):
                topic = re.sub(r"вердикт\s*", "", question, flags=re.IGNORECASE).strip()
                if not topic:
                    await update.message.reply_text(f"{user_mention}, укажите тему для вердикта.")
                    return
                
                verdict_request[user_id] = {"chat_id": chat_id, "topic": topic}
                msg = await update.message.reply_text(
                    f"{user_mention}, вы хотите получить вердикт по теме: *{topic}*?\n\n"
                    "Напишите *да* в течение 15 секунд, чтобы подтвердить.\n"
                    "Напишите *нет* или ничего — чтобы отменить."
                )
                
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
            
            # === 2. Вопрос о боте ===
            if re.search(r"(ты|тебя|твой|свит|бот|SwitAI)", question, re.IGNORECASE):
                reply = f"{user_mention}, я — SwitAI, месье! Чем могу помочь?"
                await update.message.reply_text(reply)
                return
            
            # === 3. Вероятность ===
            if re.search(r"(вероятность|шанс)", question, re.IGNORECASE):
                import random as rnd
                
                if user_id == ADMIN_ID:
                    if "+" in question:
                        probability = 100
                    elif "–" in question or "-" in question:
                        probability = 0
                    else:
                        probability = rnd.randint(0, 100)
                else:
                    try:
                        api_key = get_key_for_task("general")
                        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
                        analysis_prompt = f"Проанализируй запрос и определи вероятность (в процентах) от 0 до 100. Учитывай контекст и логику. Ответь только числом.\n\nЗапрос: {question}"
                        data = {"model": "groq/compound", "temperature": 0.3, "messages": [{"role": "user", "content": analysis_prompt}]}
                        
                        async with httpx.AsyncClient(timeout=30.0) as client:
                            resp = await client.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=data)
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
            
            # === 4. Вопрос с «кто» ===
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
            
            # === 5. Остальное — через Groq ===
            reply = await ask_switai(chat_id, user_id, question, task_type="general")
            await update.message.reply_text(f"{user_mention}, {reply}")
            return
    
    # === ВЕРДИКТ С ТАЙМЕРОМ (без «свит») ===
    if "вердикт" in text.lower():
        topic = re.sub(r"вердикт\s*", "", text, flags=re.IGNORECASE).strip()
        if not topic:
            await update.message.reply_text("❌ Месье, укажите тему для вердикта.")
            return
        
        verdict_request[user_id] = {"chat_id": chat_id, "topic": topic}
        msg = await update.message.reply_text(
            f"📝 Месье, вы хотите получить вердикт по теме: *{topic}*?\n\n"
            "Напишите *да* в течение 15 секунд, чтобы подтвердить.\n"
            "Напишите *нет* или ничего — чтобы отменить."
        )
        
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
    
    # === ОБРАБОТКА ОТВЕТА НА ПОДТВЕРЖДЕНИЕ ВЕРДИКТА ===
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
                "model": "groq/compound",
                "temperature": 0.3,
                "messages": [{"role": "user", "content": verdict_prompt}]
            }

            try:
                async with httpx.AsyncClient(timeout=60.0) as client:
                    resp = await client.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=data)
                    resp.raise_for_status()
                    result = resp.json()["choices"][0]["message"]["content"]
                    await update.message.reply_text(f"📊 *Вердикт SwitAI:*\n\n{result}")
            except Exception as e:
                await update.message.reply_text(f"❌ Швейцарский суд временно не работает: {str(e)}")
            return
        
        elif re.search(r"^(нет|no|не|отмена|не надо)$", text, re.IGNORECASE):
            del verdict_request[user_id]
            await update.message.reply_text("❌ Вердикт отменён.")
            return
        else:
            await update.message.reply_text("⏳ Пожалуйста, ответьте *да* или *нет*.")
            return
    
    # === ОБЫЧНЫЙ ОТВЕТ ===
    reply = await ask_switai(chat_id, user_id, text, task_type="general")
    if random.random() < 0.15:
        reply += random.choice(SWISS_EASTER_EGGS)
    for part in split_text(reply):
        await update.message.reply_text(part)
