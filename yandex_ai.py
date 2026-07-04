"""
Асинхронный клиент для Yandex AI Studio (DeepSeek V4 Flash)
С поддержкой повторных попыток при ошибках 429 (rate limit)
"""
import asyncio
import aiohttp
import json
import re
import time
from typing import List, Dict, Optional
from config import (
    YC_API_KEY, YC_FOLDER_ID, YC_IAM_TOKEN,
    YANDEX_MODEL, YANDEX_API_BASE,
    TRIPLET_TEMPERATURE, TRIPLET_MAX_TOKENS
)


class YandexAIClientAsync:
    def __init__(self):
        self.api_key = YC_API_KEY
        self.folder_id = YC_FOLDER_ID
        self.iam_token = YC_IAM_TOKEN
        self.model = YANDEX_MODEL
        self.base_url = YANDEX_API_BASE.rstrip('/')

        if not self.api_key and not self.iam_token:
            raise ValueError("Не указан YC_API_KEY или YC_IAM_TOKEN")

        self.headers = {
            "Content-Type": "application/json",
            "x-folder-id": self.folder_id,
        }
        if self.api_key:
            self.headers["Authorization"] = f"Api-Key {self.api_key}"
        elif self.iam_token:
            self.headers["Authorization"] = f"Bearer {self.iam_token}"

        self.model_uri = f"gpt://{self.folder_id}/{self.model}"
        print(f"🔧 Yandex AI Client (async) initialized")
        print(f"   Model: {self.model_uri}")
        print(f"   Base URL: {self.base_url}")

    async def _call_chat_completions_async(
        self,
        session: aiohttp.ClientSession,
        messages: List[Dict],
        temperature: float = 0.3,
        max_tokens: int = 4000,
        max_retries: int = 5,
        initial_delay: float = 2.0
    ) -> str:
        """
        Отправляет запрос с автоматическими повторными попытками при ошибках 429 и 5xx.
        """
        url = f"{self.base_url}/chat/completions"
        payload = {
            "model": self.model_uri,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        delay = initial_delay
        for attempt in range(max_retries):
            try:
                async with session.post(url, headers=self.headers, json=payload, timeout=120) as resp:
                    if resp.status == 429:
                        # Превышение лимита запросов
                        error_text = await resp.text()
                        print(f"   ⚠️ Ошибка 429 (лимит), попытка {attempt+1}/{max_retries}, ждём {delay:.1f} сек...")
                        await asyncio.sleep(delay)
                        delay *= 2  # экспоненциальная задержка
                        continue
                    elif resp.status >= 500:
                        # Временная ошибка сервера
                        error_text = await resp.text()
                        print(f"   ⚠️ Ошибка сервера {resp.status}, попытка {attempt+1}/{max_retries}, ждём {delay:.1f} сек...")
                        await asyncio.sleep(delay)
                        delay *= 2
                        continue
                    elif resp.status != 200:
                        # Другие ошибки (401, 403, 400 и т.д.) — не повторяем
                        text = await resp.text()
                        raise Exception(f"HTTP {resp.status}: {text[:200]}")
                    # Успешный ответ
                    data = await resp.json()
                    return data["choices"][0]["message"]["content"]
            except asyncio.TimeoutError:
                print(f"   ⚠️ Таймаут, попытка {attempt+1}/{max_retries}, ждём {delay:.1f} сек...")
                await asyncio.sleep(delay)
                delay *= 2
            except Exception as e:
                if attempt == max_retries - 1:
                    raise
                print(f"   ⚠️ Ошибка: {e}, попытка {attempt+1}/{max_retries}, ждём {delay:.1f} сек...")
                await asyncio.sleep(delay)
                delay *= 2

        raise Exception(f"Не удалось выполнить запрос после {max_retries} попыток")

    async def generate_triples_async(
        self,
        session: aiohttp.ClientSession,
        chunk_text: str,
        doc_name: str
    ) -> List[Dict]:
        """
        Генерирует триплеты из текста (может быть большим фрагментом).
        """
        system_prompt = """Ты — эксперт по горно-металлургическим процессам.

Извлеки из текста максимум структурированных фактов в виде JSON-массива триплетов.
Каждый триплет — объект с полями:
- subject: субъект (материал, процесс, оборудование)
- predicate: отношение (HAS_PROPERTY, USES_EQUIPMENT, LEADS_TO, IN_MODE и т.д.)
- object: объект
- value: числовое значение или параметр (если есть)
- mode: режим/условие (температура, давление и т.п.)
- conclusion: вывод или результат
- confidence: число от 0 до 1 (уверенность)

Верни **только** JSON-массив, без пояснений."""

        user_prompt = f"""Фрагмент документа ({doc_name}):

{chunk_text[:50000]}"""  # ограничиваем отправляемый текст

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        try:
            content = await self._call_chat_completions_async(
                session, messages,
                temperature=TRIPLET_TEMPERATURE,
                max_tokens=TRIPLET_MAX_TOKENS
            )
        except Exception as e:
            print(f"   ❌ Ошибка генерации триплетов для {doc_name}: {e}")
            return []

        if not content:
            return []

        content = self._clean_json(content)
        try:
            triples = json.loads(content)
            if isinstance(triples, list):
                return triples
        except json.JSONDecodeError:
            match = re.search(r'\[\s*\{[\s\S]*?\}\s*\]', content, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(0))
                except:
                    pass
        return []

    def _clean_json(self, text: str) -> str:
        """Очищает JSON от маркеров и лишнего текста."""
        text = re.sub(r'```json\s*|\s*```', '', text, flags=re.IGNORECASE | re.DOTALL)
        text = re.sub(r'^```.*?\n', '', text, flags=re.DOTALL)
        start = text.find('[')
        end = text.rfind(']')
        if start != -1 and end != -1 and end > start:
            text = text[start:end+1]
        return text.strip()

    async def generate_answer_async(
        self,
        session: aiohttp.ClientSession,
        query: str,
        context: str
    ) -> str:
        """
        Генерирует структурированный ответ на запрос на основе контекста.
        """
        system_prompt = """Ты — эксперт по горно-металлургическим процессам Норникеля.

На основе предоставленного контекста (факты из Knowledge Graph и веб-поиска) дай структурированный ответ.
В ответе обязательно укажи:
- Найденные решения и эксперименты
- Числовые параметры и условия (концентрации, температуры, скорости)
- Источники и уровень уверенности
- Пробелы в знаниях (если есть)
- Рекомендации

Если данных недостаточно, честно скажи об этом."""

        user_prompt = f"""Вопрос: {query}

Контекст из Knowledge Graph и веб-поиска:
{context[:7000]}"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        try:
            return await self._call_chat_completions_async(
                session, messages,
                temperature=0.2,
                max_tokens=3000
            )
        except Exception as e:
            return f"⚠️ Ошибка генерации ответа: {e}"


# Синглтон
_client = None

def get_yandex_client() -> YandexAIClientAsync:
    global _client
    if _client is None:
        _client = YandexAIClientAsync()
    return _client