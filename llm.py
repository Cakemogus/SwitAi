"""
LLM.PY — ВСЁ ОБЩЕНИЕ С НЕЙРОСЕТЯМИ
==================================
• Groq с ротацией ключей (каждый запрос начинает со следующего ключа — нагрузка делится ровно)
• Gemini как резерв + распознавание картинок
• Веб-поиск (Ollama) с краткой выжимкой от нейросети
• Генерация картинок (HF FLUX -> Pollinations), возвращает байты — без временных файлов
"""

import asyncio
import base64
import logging
import re
from urllib.parse import quote

import httpx

from config import (
    GEMINI_API_KEY, GEMINI_MODEL, GROQ_API_KEYS, GROQ_MODEL, GROQ_URL,
    HF_IMAGE_URL, HF_TOKEN, OLLAMA_API_KEYS,
)

log = logging.getLogger(__name__)

_client = None
_groq_idx = 0
_ollama_idx = 0

REFUSAL_PREFIXES = ("i'm sorry", "i cannot", "i can't", "i apologize", "sorry, but")
REFUSAL_TEXT = "Извини, но я не могу помочь с этим запросом. Давай сменим тему. 🤷‍♂️"


class LLMError(Exception):
    """Ни один из провайдеров не ответил."""


def client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(timeout=httpx.Timeout(45.0, connect=10.0), follow_redirects=True)
    return _client


async def close_client():
    if _client is not None and not _client.is_closed:
        await _client.aclose()


def _clean(text: str) -> str:
    text = re.sub(r"<think>.*?</think>", "", text or "", flags=re.DOTALL).strip()
    if text.lower().startswith(REFUSAL_PREFIXES):
        return REFUSAL_TEXT
    return text


# =====================================================================
# ТЕКСТОВЫЙ ЧАТ
# =====================================================================

async def _ask_groq(messages, temperature):
    global _groq_idx
    if not GROQ_API_KEYS:
        return None
    start = _groq_idx
    _groq_idx = (start + 1) % len(GROQ_API_KEYS)
    for i in range(len(GROQ_API_KEYS)):
        key = GROQ_API_KEYS[(start + i) % len(GROQ_API_KEYS)]
        try:
            resp = await client().post(
                GROQ_URL,
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={"model": GROQ_MODEL, "temperature": temperature, "messages": messages},
            )
            if resp.status_code == 200:
                content = resp.json()["choices"][0]["message"].get("content")
                if content and content.strip():
                    return _clean(content)
                log.warning("Groq вернул пустой ответ, пробую следующий ключ")
            else:
                log.warning("Groq ключ #%d: статус %s", (start + i) % len(GROQ_API_KEYS) + 1, resp.status_code)
        except (httpx.HTTPError, KeyError, IndexError, ValueError) as e:
            log.warning("Groq ошибка: %s", str(e)[:80])
    return None


def _to_gemini(messages):
    system, contents = [], []
    for m in messages:
        if m["role"] == "system":
            system.append(m["content"])
            continue
        role = "user" if m["role"] == "user" else "model"
        if contents and contents[-1]["role"] == role:      # Gemini любит чередование ролей
            contents[-1]["parts"][0]["text"] += "\n" + m["content"]
        else:
            contents.append({"role": role, "parts": [{"text": m["content"]}]})
    if contents and contents[0]["role"] != "user":
        contents.insert(0, {"role": "user", "parts": [{"text": "(начало диалога)"}]})
    return "\n".join(system), contents


def _gemini_url():
    return f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"


async def _ask_gemini(messages, temperature):
    if not GEMINI_API_KEY:
        return None
    system, contents = _to_gemini(messages)
    body = {"contents": contents, "generationConfig": {"temperature": temperature}}
    if system:
        body["system_instruction"] = {"parts": [{"text": system}]}
    try:
        resp = await client().post(_gemini_url(), params={"key": GEMINI_API_KEY}, json=body)
        if resp.status_code == 200:
            parts = resp.json()["candidates"][0]["content"]["parts"]
            text = "".join(p.get("text", "") for p in parts)
            if text.strip():
                return _clean(text)
        else:
            log.warning("Gemini статус %s", resp.status_code)
    except (httpx.HTTPError, KeyError, IndexError, ValueError) as e:
        log.warning("Gemini ошибка: %s", str(e)[:80])
    return None


async def chat(messages, temperature: float = 0.4) -> str:
    """Groq (все ключи по кругу) -> Gemini. Бросает LLMError, если все упали."""
    result = await _ask_groq(messages, temperature)
    if result:
        return result
    log.info("Groq недоступен, иду в Gemini")
    result = await _ask_gemini(messages, temperature)
    if result:
        return result
    raise LLMError("все провайдеры недоступны")


# =====================================================================
# КАРТИНКИ: РАСПОЗНАВАНИЕ
# =====================================================================

async def analyze_image(image_bytes: bytes, prompt: str, mime: str = "image/jpeg") -> str:
    if not GEMINI_API_KEY:
        return "❌ Ключ Gemini не настроен."
    body = {
        "contents": [{
            "parts": [
                {"text": prompt},
                {"inline_data": {"mime_type": mime, "data": base64.b64encode(image_bytes).decode()}},
            ]
        }]
    }
    try:
        resp = await client().post(
            _gemini_url(), params={"key": GEMINI_API_KEY}, json=body, timeout=httpx.Timeout(60.0, connect=10.0)
        )
        if resp.status_code == 200:
            parts = resp.json()["candidates"][0]["content"]["parts"]
            return "".join(p.get("text", "") for p in parts).strip() or "🤔 Ничего не смог разглядеть."
        return f"❌ Не получилось распознать (статус {resp.status_code})."
    except (httpx.HTTPError, KeyError, IndexError, ValueError) as e:
        return f"❌ Ошибка распознавания: {str(e)[:80]}"


# =====================================================================
# КАРТИНКИ: ГЕНЕРАЦИЯ
# =====================================================================

async def generate_image(prompt: str):
    """Возвращает bytes картинки или None."""
    enhanced = f"{prompt}, high quality, detailed, 4k"
    if HF_TOKEN:
        try:
            resp = await client().post(
                HF_IMAGE_URL,
                headers={"Authorization": f"Bearer {HF_TOKEN}"},
                json={"inputs": enhanced},
                timeout=httpx.Timeout(60.0, connect=10.0),
            )
            if resp.status_code == 200 and resp.headers.get("content-type", "").startswith("image"):
                return resp.content
        except httpx.HTTPError as e:
            log.warning("HF ошибка: %s", str(e)[:80])
    try:
        url = (
            f"https://image.pollinations.ai/prompt/{quote(enhanced)}"
            "?width=1024&height=1024&model=flux&nologo=true"
        )
        resp = await client().get(url, timeout=httpx.Timeout(90.0, connect=10.0))
        if resp.status_code == 200 and resp.headers.get("content-type", "").startswith("image"):
            return resp.content
    except httpx.HTTPError as e:
        log.warning("Pollinations ошибка: %s", str(e)[:80])
    return None


# =====================================================================
# ВЕБ-ПОИСК
# =====================================================================

_SEARCH_RE = re.compile(
    r"(?<!\w)(?:найди|поищи|погугли|загугли|новости|новость|погода|погоду|курс|"
    r"сколько\s+стоит|цена\s+на|биткоин\w*|сколько\s+сейчас)(?!\w)",
    re.IGNORECASE,
)


def needs_internet(prompt: str) -> bool:
    return bool(_SEARCH_RE.search(prompt or ""))


async def search_web(query: str):
    """Список {title, content, url} или строка с ошибкой."""
    global _ollama_idx
    if not OLLAMA_API_KEYS:
        return "❌ Ключи поиска не настроены."
    key = OLLAMA_API_KEYS[_ollama_idx % len(OLLAMA_API_KEYS)]
    _ollama_idx += 1
    try:
        resp = await client().post(
            "https://ollama.com/api/web_search",
            headers={"Authorization": f"Bearer {key}"},
            json={"query": query, "max_results": 4},
            timeout=httpx.Timeout(30.0, connect=10.0),
        )
        resp.raise_for_status()
        return resp.json().get("results", [])
    except (httpx.HTTPError, ValueError) as e:
        return f"❌ Ошибка поиска: {str(e)[:80]}"


def _raw_results(results) -> str:
    out = []
    for r in results[:3]:
        out.append(f"• {r.get('title', 'Без заголовка')}\n  {r.get('content', '')[:200]}...\n  {r.get('url', '')}")
    return "\n\n".join(out)


async def search_and_summarize(query: str) -> str:
    results = await search_web(query)
    if isinstance(results, str):
        return results
    if not results:
        return "🔍 Ничего не найдено."
    context = "\n\n".join(
        f"[{i}] {r.get('title', '')}\n{r.get('content', '')[:700]}\nИсточник: {r.get('url', '')}"
        for i, r in enumerate(results[:4], 1)
    )
    try:
        answer = await chat(
            [
                {"role": "system", "content": (
                    "Ты — SwitAI, швейцарский ИИ. Ответь на вопрос пользователя по-русски, кратко и по делу, "
                    "используя ТОЛЬКО результаты поиска ниже. Если данных мало — так и скажи. Не выдумывай цифры."
                )},
                {"role": "user", "content": f"Вопрос: {query}\n\nРезультаты поиска:\n{context}"},
            ],
            temperature=0.2,
        )
        sources = "\n".join(f"🔗 {r.get('url', '')}" for r in results[:3] if r.get("url"))
        return f"🌐 {answer}\n\n{sources}".strip()
    except LLMError:
        return f"🌐 Результаты поиска:\n\n{_raw_results(results)}"
