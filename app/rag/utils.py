from __future__ import annotations

import json
import os
from typing import Any

import requests


class GigaChatClient:
    """
    Минимальный HTTP-клиент для GigaChat под наши задачи.
    Вынесен отдельно, чтобы при желании заменить на официальный SDK.
    """

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str = 'GigaChat', # подставь реальное имя модели
        timeout: int = 30,
    ):
        self.base_url = base_url or os.getenv('GIGACHAT_API_URL', '').rstrip('/')
        self.api_key = api_key or os.getenv('GIGACHAT_API_KEY', '')
        self.model = model
        self.timeout = timeout

        if not self.base_url:
            raise ValueError('GIGACHAT_API_URL не задан')
        if not self.api_key:
            raise ValueError('GIGACHAT_API_KEY не задан')

    def chat(self, messages: list[dict[str, str]], temperature: float = 0.0) -> str:
        """
        Делает один запрос к GigaChat и возвращает content первого ответа как строку.

        messages: [{'role': 'system'|'user'|'assistant', 'content': '...'}, ...]
        """
        payload: dict[str, Any] = {
            'model': self.model,
            'messages': messages,
            'temperature': temperature,
        }

        headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json',
        }

        # TODO: нужно удостовериться что такой endpoint у GigaChat действительно есть
        url = f'{self.base_url}/v1/chat/completions'

        resp = requests.post(
            url,
            headers=headers,
            data=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
            timeout=self.timeout,
        )
        resp.raise_for_status()
        data = resp.json()

        # TODO: требуется проверка формата ответа GigaChat
        # сейчас — "OpenAI-like"
        content = data['choices'][0]['message']['content']
        return content
