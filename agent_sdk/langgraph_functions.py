import hashlib
import uuid

from langgraph_sdk import get_client
import rich

from agent_sdk.config import LANGGRAPH_URL, LOG_LEVEL, GraphType, supported_graphs


def _user_id_to_uuid(user_id: str) -> str:
    """
    Конвертирует произвольный user_id в валидный UUID.
    """
    # создаём детерминированный UUID на основе user_id
    hash_bytes = hashlib.md5(f'max_{user_id}'.encode()).digest()
    return str(uuid.UUID(bytes=hash_bytes))


async def chat_with_agent(
    user_chat_id: str,
    message: str,
    agent_graph_id: GraphType = 'supervisor',  # граф агента по умолчанию
) -> str:
    """
    Отправить сообщение агенту и получить ответ.

    Args:
        user_chat_id: ID пользователя или чата (используется как thread_id в langgraph)
        message: Сообщение пользователя
        agent_graph_id: Тип графа для агента (например: 'supervisor' или 'hybrid')

    Returns:
        Ответ агента
    """
    # используем асинхронный клиент для async функции
    client = get_client(url=LANGGRAPH_URL)

    # thread_id должен быть в формате UUID
    user_chat_id = _user_id_to_uuid(user_chat_id)

    # получаем список assistants (графов) = "агентов" и выбираем нужный
    assistants = await client.assistants.search()

    # ищем указанный граф
    assistant_id = None
    for assistant in assistants:
        graph_id = assistant.get('graph_id', '')
        if graph_id == agent_graph_id:
            assistant_id = assistant['assistant_id']
            if __debug__:
                rich.print(f'[green]Using assistant: {graph_id}[/green]')
            break

    if assistant_id is None:
        # fallback: ищем любой подходящий граф
        for assistant in assistants:
            graph_id = assistant.get('graph_id', '')
            if graph_id in supported_graphs:
                assistant_id = assistant['assistant_id']
                rich.print(
                    f'[yellow]Graph "{agent_graph_id}" not found, using: {graph_id}[/yellow]'
                )
                break

    if assistant_id is None:
        raise ValueError(
            f'No suitable assistant found. Available: {[a.get("graph_id") for a in assistants]}'
        )

    # создаём или используем существующий thread
    try:
        thread = await client.threads.get(user_chat_id)
    except Exception:
        thread = await client.threads.create(thread_id=user_chat_id)

    # запускаем граф
    # используем формат LangChain для совместимости с MessagesState
    input_state = {'messages': [{'type': 'human', 'content': message}]}

    # ждём завершения run
    result = await client.runs.wait(
        thread_id=thread['thread_id'],
        assistant_id=assistant_id,
        input=input_state,
    )
    if LOG_LEVEL == 'DEBUG':
        rich.print('Run result:', result)

    # result уже содержит финальный state
    # извлекаем ответ из final_response или последнего сообщения
    if isinstance(result, dict):
        # сначала пробуем final_response
        final_response = result.get('final_response')
        if final_response:
            return final_response

        # иначе берём последнее AI сообщение
        messages = result.get('messages', [])
        if messages:
            last_message = messages[-1]
            rich.print('Last message:\n', last_message)
            if isinstance(last_message, dict):
                return last_message.get('content', 'Нет ответа')
            else:
                return getattr(last_message, 'content', 'Нет ответа')

    return 'Ошибка: пустой ответ'


async def chat_with_streaming(
    user_chat_id: str,
    message: str,
    agent_graph_id: GraphType = 'supervisor',
):
    """
    Streaming версия — получаем ответ по частям (токенам).

    Использует stream_mode='messages' для получения LLM токенов.

    Args:
        user_chat_id: ID пользователя или чата
        message: Сообщение пользователя
        agent_graph_id: Тип графа для агента

    Yields:
        str: Части (токены) ответа по мере генерации
    """
    client = get_client(url=LANGGRAPH_URL)
    thread_id = _user_id_to_uuid(user_chat_id)

    # получаем список assistants и выбираем нужный
    assistants = await client.assistants.search()

    assistant_id = None
    for assistant in assistants:
        graph_id = assistant.get('graph_id', '')
        if graph_id == agent_graph_id:
            assistant_id = assistant['assistant_id']
            break

    if assistant_id is None:
        # fallback: первый подходящий
        for assistant in assistants:
            graph_id = assistant.get('graph_id', '')
            if graph_id in supported_graphs:
                assistant_id = assistant['assistant_id']
                break

    if assistant_id is None:
        raise ValueError(
            f'No suitable assistant found. Available: {[a.get("graph_id") for a in assistants]}'
        )

    # создаём или используем существующий thread
    try:
        await client.threads.get(thread_id)
    except Exception:
        await client.threads.create(thread_id=thread_id)

    input_state = {'messages': [{'type': 'human', 'content': message}]}

    # streaming с режимом messages для получения токенов
    async for event in client.runs.stream(
        thread_id=thread_id,
        assistant_id=assistant_id,
        input=input_state,
        stream_mode='messages',
    ):
        # event.event может быть:
        # - 'messages/partial' — частичный токен
        # - 'messages/complete' — полное сообщение
        # - 'metadata' — метаданные
        # - 'error' — ошибка

        if LOG_LEVEL == 'DEBUG':
            rich.print(f'[dim]Stream event: {event.event}[/dim]')

        if event.event == 'messages/partial':
            # частичный токен от LLM
            data = event.data
            if isinstance(data, dict):
                content = data.get('content', '')
                if content:
                    yield content
            elif isinstance(data, list) and data:
                # иногда приходит список чанков
                for chunk in data:
                    if isinstance(chunk, dict):
                        content = chunk.get('content', '')
                        if content:
                            yield content

        elif event.event == 'messages/complete':
            # полное сообщение — можно использовать для финализации
            # но обычно partial уже всё выдали
            pass

        elif event.event == 'error':
            error_msg = event.data if isinstance(event.data, str) else str(event.data)
            rich.print(f'[red]Stream error: {error_msg}[/red]')
            yield f'\n\n❌ Ошибка: {error_msg}'
            break


async def get_final_response_streaming(
    user_chat_id: str,
    message: str,
    agent_graph_id: GraphType = 'supervisor',
) -> str:
    """
    Streaming версия, но возвращает полный ответ (собирает все токены).

    Полезно для тестирования streaming без изменения UI.
    """
    chunks = []
    async for chunk in chat_with_streaming(user_chat_id, message, agent_graph_id):
        chunks.append(chunk)
    return ''.join(chunks)
