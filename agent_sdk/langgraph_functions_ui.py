"""
Функции для работы с LangGraph Server из Streamlit UI.
Синхронные обёртки и генераторы для использования со Streamlit.
"""

from collections.abc import Generator
import functools
from typing import Any

from langgraph_sdk import get_sync_client

from agent_sdk.config import LANGGRAPH_URL, LOG_LEVEL, GraphType, supported_graphs
from agent_sdk.langgraph_functions import _user_id_to_uuid


# кешированный клиент (создаётся один раз)
@functools.lru_cache(maxsize=1)
def get_client():
    """
    Возвращает синхронный клиент LangGraph SDK (кешированный)
    """
    return get_sync_client(url=LANGGRAPH_URL)


def check_server_available() -> bool:
    """
    Проверяет доступность LangGraph Server.

    Returns:
        True если сервер доступен
    """
    try:
        client = get_client()
        # пробуем получить список assistants
        client.assistants.search()
        return True
    except Exception:
        return False


def _get_assistant_id(
    client,
    agent_graph_id: GraphType,
) -> str:
    """
    Получает assistant_id для указанного графа.
    """
    assistants = client.assistants.search()

    # ищем указанный граф
    for assistant in assistants:
        graph_id = assistant.get('graph_id', '')
        if graph_id == agent_graph_id:
            return assistant['assistant_id']

    # fallback: первый подходящий
    for assistant in assistants:
        graph_id = assistant.get('graph_id', '')
        if graph_id in supported_graphs:
            return assistant['assistant_id']

    raise ValueError(
        f'No suitable assistant found. Available: {[a.get("graph_id") for a in assistants]}'
    )


def _ensure_thread(client, thread_id: str) -> str:
    """
    Создаёт thread если не существует, возвращает thread_id.
    """
    try:
        thread = client.threads.get(thread_id)
        return thread['thread_id']
    except Exception:
        thread = client.threads.create(thread_id=thread_id)
        return thread['thread_id']


def chat_sync(
    user_chat_id: str,
    message: str,
    agent_graph_id: GraphType = 'supervisor',
) -> str:
    """
    Синхронная версия chat — для простого использования в Streamlit.

    Args:
        user_chat_id: ID пользователя
        message: Сообщение пользователя
        agent_graph_id: Тип графа

    Returns:
        Ответ агента
    """
    client = get_sync_client(url=LANGGRAPH_URL)
    thread_id = _user_id_to_uuid(user_chat_id)

    assistant_id = _get_assistant_id(client, agent_graph_id)
    thread_id = _ensure_thread(client, thread_id)

    input_state = {'messages': [{'type': 'human', 'content': message}]}

    # синхронный wait
    result = client.runs.wait(
        thread_id=thread_id,
        assistant_id=assistant_id,
        input=input_state,
    )

    # извлекаем ответ
    if isinstance(result, dict):
        final_response = result.get('final_response')
        if final_response:
            return final_response

        messages = result.get('messages', [])
        if messages:
            last_message = messages[-1]
            if isinstance(last_message, dict):
                return last_message.get('content', 'Нет ответа')
            else:
                return getattr(last_message, 'content', 'Нет ответа')

    return 'Ошибка: пустой ответ'


def stream_chat(
    user_chat_id: str,
    message: str,
    agent_graph_id: GraphType = 'supervisor',
) -> Generator[str, None, None]:
    """
    Streaming версия для Streamlit — синхронный генератор.

    Использует sync client для совместимости со Streamlit.

    Args:
        user_chat_id: ID пользователя
        message: Сообщение пользователя
        agent_graph_id: Тип графа

    Yields:
        str: Части ответа (токены) по мере генерации
    """
    client = get_sync_client(url=LANGGRAPH_URL)
    thread_id = _user_id_to_uuid(user_chat_id)

    assistant_id = _get_assistant_id(client, agent_graph_id)
    thread_id = _ensure_thread(client, thread_id)

    input_state = {'messages': [{'type': 'human', 'content': message}]}

    # синхронный streaming
    for event in client.runs.stream(
        thread_id=thread_id,
        assistant_id=assistant_id,
        input=input_state,
        stream_mode='messages',
    ):
        if LOG_LEVEL == 'DEBUG':
            print(f'[Stream event: {event.event}]')

        if event.event == 'messages/partial':
            data = event.data
            if isinstance(data, dict):
                content = data.get('content', '')
                if content:
                    yield content
            elif isinstance(data, list) and data:
                for chunk in data:
                    if isinstance(chunk, dict):
                        content = chunk.get('content', '')
                        if content:
                            yield content

        elif event.event == 'error':
            error_msg = event.data if isinstance(event.data, str) else str(event.data)
            yield f'\n\n❌ Ошибка: {error_msg}'
            break


def stream_chat_with_status(
    user_chat_id: str,
    message: str,
    agent_graph_id: GraphType = 'supervisor',
) -> Generator[dict[str, Any], None, None]:
    """
    Streaming с информацией о статусе — для продвинутого UI.

    Yields:
        dict: {'type': 'token'|'status'|'error'|'complete', 'content': str}
    """
    client = get_sync_client(url=LANGGRAPH_URL)
    thread_id = _user_id_to_uuid(user_chat_id)

    try:
        assistant_id = _get_assistant_id(client, agent_graph_id)
        thread_id = _ensure_thread(client, thread_id)
    except Exception as e:
        yield {'type': 'error', 'content': f'Ошибка подключения: {e}'}
        return

    yield {'type': 'status', 'content': 'Отправка запроса...'}

    input_state = {'messages': [{'type': 'human', 'content': message}]}

    full_response = []
    got_tokens = False

    try:
        # Используем оба режима: messages для токенов, values для финального состояния
        for event in client.runs.stream(
            thread_id=thread_id,
            assistant_id=assistant_id,
            input=input_state,
            stream_mode=['messages', 'values'],  # оба режима
        ):
            if LOG_LEVEL == 'DEBUG':
                print(f'[Stream event: {event.event}]')

            if event.event == 'messages/partial':
                # Токены от LLM
                data = event.data
                if isinstance(data, dict):
                    content = data.get('content', '')
                    if content:
                        got_tokens = True
                        full_response.append(content)
                        yield {'type': 'token', 'content': content}
                elif isinstance(data, list) and data:
                    for chunk in data:
                        if isinstance(chunk, dict):
                            content = chunk.get('content', '')
                            if content:
                                got_tokens = True
                                full_response.append(content)
                                yield {'type': 'token', 'content': content}

            elif event.event == 'messages/complete':
                # Полное сообщение — используем если не было partial токенов
                if not got_tokens:
                    data = event.data
                    if isinstance(data, dict):
                        content = data.get('content', '')
                        if content:
                            full_response.append(content)
                            yield {'type': 'token', 'content': content}
                    elif isinstance(data, list) and data:
                        # Последний элемент — AI ответ
                        last_msg = data[-1] if data else None
                        if isinstance(last_msg, dict):
                            content = last_msg.get('content', '')
                            if content:
                                full_response.append(content)
                                yield {'type': 'token', 'content': content}

            elif event.event == 'values':
                # Финальный state — fallback если messages не сработали
                if not full_response:
                    data = event.data
                    if isinstance(data, dict):
                        # Пробуем final_response
                        final_resp = data.get('final_response', '')
                        if final_resp:
                            full_response.append(final_resp)
                            yield {'type': 'token', 'content': final_resp}
                        else:
                            # Последнее сообщение из messages
                            messages = data.get('messages', [])
                            if messages:
                                last_msg = messages[-1]
                                if isinstance(last_msg, dict):
                                    content = last_msg.get('content', '')
                                    if content and last_msg.get('type') != 'human':
                                        full_response.append(content)
                                        yield {'type': 'token', 'content': content}

            elif event.event == 'error':
                error_msg = event.data if isinstance(event.data, str) else str(event.data)
                yield {'type': 'error', 'content': error_msg}
                return

        yield {'type': 'complete', 'content': ''.join(full_response)}

    except Exception as e:
        yield {'type': 'error', 'content': f'Ошибка streaming: {e}'}


# =======
# Функции для работы с историей и потоками (threads)
# =======


def get_thread_history(user_chat_id: str) -> list[dict[str, str]]:
    """
    Получает историю сообщений из thread на сервере.

    Args:
        user_chat_id: ID пользователя/чата

    Returns:
        Список сообщений в формате [{'role': 'user'|'assistant', 'content': str}]
    """
    client = get_client()
    thread_id = _user_id_to_uuid(user_chat_id)

    try:
        # получаем state потока
        state = client.threads.get_state(thread_id)

        if not state or 'values' not in state:
            return []

        values = state.get('values', {})
        messages = values.get('messages', [])

        # конвертируем в формат UI
        ui_messages = []
        for msg in messages:
            if isinstance(msg, dict):
                msg_type = msg.get('type', '')
                content = msg.get('content', '')

                if msg_type == 'human':
                    ui_messages.append({'role': 'user', 'content': content})
                elif msg_type == 'ai':
                    ui_messages.append({'role': 'assistant', 'content': content})
                # tool messages пропускаем

        return ui_messages

    except Exception as e:
        if LOG_LEVEL == 'DEBUG':
            print(f'[get_thread_history error: {e}]')
        return []


def clear_thread_history(user_chat_id: str) -> bool:
    """
    Очищает историю thread (удаляет thread).

    Args:
        user_chat_id: ID пользователя/чата

    Returns:
        True если успешно
    """
    client = get_client()
    thread_id = _user_id_to_uuid(user_chat_id)

    try:
        client.threads.delete(thread_id)
        return True
    except Exception as e:
        if LOG_LEVEL == 'DEBUG':
            print(f'[clear_thread_history error: {e}]')
        return False


def list_threads() -> list[dict[str, Any]]:
    """
    Получает список всех threads на сервере.

    Returns:
        Список threads
    """
    client = get_client()
    try:
        threads = client.threads.search()
        return list(threads)
    except Exception as e:
        if LOG_LEVEL == 'DEBUG':
            print(f'[list_threads error: {e}]')
        return []


def get_available_graphs() -> list[str]:
    """
    Получает список доступных графов на сервере.

    Returns:
        Список graph_id
    """
    client = get_client()
    try:
        assistants = client.assistants.search()
        return [a.get('graph_id', '') for a in assistants if a.get('graph_id')]
    except Exception:
        return []
