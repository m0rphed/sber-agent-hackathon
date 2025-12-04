import hashlib
from typing import Literal
import uuid

from langgraph_sdk import get_client
import rich

# Подключение к LangGraph Server
LANGGRAPH_URL = 'http://localhost:2024'

# Тип графа по умолчанию
DEFAULT_GRAPH = 'supervisor'

# Доступные графы (работают с messages)
GraphType = Literal['supervisor', 'hybrid']


def _user_id_to_uuid(user_id: str) -> str:
    """
    Конвертирует произвольный user_id в валидный UUID.
    """
    # Создаём детерминированный UUID на основе user_id
    hash_bytes = hashlib.md5(f'max_{user_id}'.encode()).digest()
    return str(uuid.UUID(bytes=hash_bytes))


async def chat_with_agent(
    user_id: str,
    message: str,
    graph: GraphType = DEFAULT_GRAPH,
) -> str:
    """
    Отправить сообщение агенту и получить ответ.

    Args:
        user_id: ID пользователя (используется как thread_id)
        message: Сообщение пользователя
        graph: Тип графа ('supervisor' или 'hybrid')

    Returns:
        Ответ агента
    """
    # Используем асинхронный клиент для async функции
    client = get_client(url=LANGGRAPH_URL)

    # thread_id должен быть в формате UUID
    thread_id = _user_id_to_uuid(user_id)

    # Получаем список assistants (графов) и выбираем нужный
    assistants = await client.assistants.search()

    # Ищем указанный граф
    assistant_id = None
    for assistant in assistants:
        graph_id = assistant.get('graph_id', '')
        if graph_id == graph:
            assistant_id = assistant['assistant_id']
            rich.print(f'[green]Using assistant: {graph_id}[/green]')
            break

    if assistant_id is None:
        # Fallback: ищем любой подходящий граф
        for assistant in assistants:
            graph_id = assistant.get('graph_id', '')
            if graph_id in ('supervisor', 'hybrid'):
                assistant_id = assistant['assistant_id']
                rich.print(f'[yellow]Graph "{graph}" not found, using: {graph_id}[/yellow]')
                break

    if assistant_id is None:
        raise ValueError(f'No suitable assistant found. Available: {[a.get("graph_id") for a in assistants]}')

    # Создаём или используем существующий thread
    try:
        thread = await client.threads.get(thread_id)
    except Exception:
        thread = await client.threads.create(thread_id=thread_id)

    # Запускаем граф
    # Используем формат LangChain для совместимости с MessagesState
    input_state = {'messages': [{'type': 'human', 'content': message}]}

    # Ждём завершения run
    result = await client.runs.wait(
        thread_id=thread['thread_id'],
        assistant_id=assistant_id,
        input=input_state,
    )
    rich.print(result)

    # result уже содержит финальный state
    # Извлекаем ответ из final_response или последнего сообщения
    if isinstance(result, dict):
        # Сначала пробуем final_response
        final_response = result.get('final_response')
        if final_response:
            return final_response

        # Иначе берём последнее AI сообщение
        messages = result.get('messages', [])
        if messages:
            last_message = messages[-1]
            rich.print('Last message:\n', last_message)
            if isinstance(last_message, dict):
                return last_message.get('content', 'Нет ответа')
            else:
                return getattr(last_message, 'content', 'Нет ответа')

    return 'Ошибка: пустой ответ'


async def chat_with_streaming(user_id: str, message: str):
    """
    Streaming версия — получаем ответ по частям.
    """
    client = get_client(url=LANGGRAPH_URL)
    thread_id = _user_id_to_uuid(user_id)

    assistants = await client.assistants.search()
    assistant_id = assistants[0]['assistant_id']

    # Создаём или используем существующий thread
    try:
        await client.threads.get(thread_id)
    except Exception:
        await client.threads.create(thread_id=thread_id)

    input_state = {'messages': [{'type': 'human', 'content': message}]}

    # Streaming
    async for event in client.runs.stream(
        thread_id=thread_id,
        assistant_id=assistant_id,
        input=input_state,
        stream_mode='messages',  # или "values", "updates"
    ):
        if event.event == 'messages/complete':
            # Полное сообщение готово
            yield event.data['content']
