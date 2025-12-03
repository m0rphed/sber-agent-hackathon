from typing import Any

from langgraph_sdk import get_client, get_sync_client
import rich

# Подключение к LangGraph Server
client = get_sync_client(url="http://localhost:2024")

async def chat_with_agent(user_id: str, message: str) -> str:
    """
    Отправить сообщение агенту и получить ответ.

    Args:
        user_id: ID пользователя (используется как thread_id)
        message: Сообщение пользователя

    Returns:
        Ответ агента
    """
    # thread_id = user_id для сохранения истории диалога
    thread_id = f"max_{user_id}"

    # Получаем список assistants (графов)
    assistants = client.assistants.search()
    # Берём supervisor или hybrid
    assistant_id = assistants[0]["assistant_id"]

    # Создаём или используем существующий thread
    try:
        thread = client.threads.get(thread_id)
    except Exception:
        thread = client.threads.create(thread_id=thread_id)

    # Запускаем граф
    input_state = {
        "messages": [{"role": "user", "content": message}]
    }

    # Вариант 1: Синхронный вызов (ждём полный ответ)
    result = client.runs.create(
        thread_id=thread["thread_id"],
        assistant_id=assistant_id,
        input=input_state,
    )
    rich.print(result)
    # Извлекаем ответ
    final_state = client.threads.get_state(thread["thread_id"])
    _values: dict[str, Any] | Any = final_state.values
    if not isinstance(_values, dict):
        raise ValueError("Unexpected state values format")

    messages = _values.get("messages", [])
    if messages:
        last_message = messages[-1]
        return last_message.get("content", "Нет ответа")

    return "Ошибка: пустой ответ"


async def chat_with_streaming(user_id: str, message: str):
    """
    Streaming версия — получаем ответ по частям.
    """
    client = get_client(url="http://localhost:2024")
    thread_id = f"max_{user_id}"

    assistants = client.assistants.search()
    assistant_id = (await assistants)[0]["assistant_id"]

    input_state = {
        "messages": [{"role": "user", "content": message}]
    }

    # Streaming
    async for event in client.runs.stream(
        thread_id=thread_id,
        assistant_id=assistant_id,
        input=input_state,
        stream_mode="messages",  # или "values", "updates"
    ):
        if event.event == "messages/complete":
            # Полное сообщение готово
            yield event.data["content"]
