"""
Клиент для GitHub Models (бесплатный OpenAI-совместимый API).
Использует Personal Access Token (PAT) для аутентификации.[reference:13]
"""
import os
import json
from typing import List, Dict, Optional
import requests
from config import (
    GITHUB_TOKEN,
    GITHUB_MODELS_BASE_URL,
    GITHUB_MODEL,
    LLM_TEMPERATURE,
    LLM_MAX_TOKENS
)


class GitHubModelsClient:
    """Синхронный клиент для GitHub Models (OpenAI-совместимый)."""

    def __init__(self):
        self.api_key = GITHUB_TOKEN
        self.base_url = GITHUB_MODELS_BASE_URL
        self.model = GITHUB_MODEL

        if not self.api_key:
            print("⚠️ GITHUB_TOKEN не указан. Получите PAT: https://github.com/settings/tokens")
            print("   Требуется право: models:read")

    def _get_headers(self) -> Dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def chat_completion(self, messages: List[Dict], temperature: float = None, max_tokens: int = None) -> str:
        """
        Синхронный вызов GPT-4o через GitHub Models.
        """
        if not self.api_key:
            return "⚠️ GitHub Token не настроен. Укажите GITHUB_TOKEN в .env"

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature or LLM_TEMPERATURE,
            "max_tokens": max_tokens or LLM_MAX_TOKENS,
        }

        try:
            response = requests.post(self.base_url, headers=self._get_headers(), json=payload, timeout=60)
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]
        except requests.exceptions.RequestException as e:
            print(f"⚠️ Ошибка GitHub Models: {e}")
            if hasattr(e, 'response') and e.response:
                print(f"   Ответ: {e.response.text[:200]}")
            return f"⚠️ Ошибка генерации ответа: {str(e)[:200]}"

    def generate_answer(self, query: str, context: str) -> str:
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

        return self.chat_completion(messages, temperature=0.2, max_tokens=3000)


# Синглтон
_sync_client = None


def get_llm_client() -> GitHubModelsClient:
    global _sync_client
    if _sync_client is None:
        _sync_client = GitHubModelsClient()
    return _sync_client