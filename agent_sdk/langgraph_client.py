# backend/langgraph_client.py
from collections.abc import Generator
import functools
from typing import Any

from langgraph_sdk import get_sync_client

from agent_sdk.config import LANGGRAPH_URL, LOG_LEVEL, supported_graphs
from agent_sdk.langgraph_functions import _user_id_to_uuid  # если уже есть

# Если _user_id_to_uuid у тебя пока в этом же файле – можно вот так:
# import hashlib
# import uuid
#
# def _user_id_to_uuid(user_id: str) -> str:
#     hash_bytes = hashlib.md5(f'max_{user_id}'.encode()).digest()
#     return str(uuid.UUID(bytes=hash_bytes))


@functools.lru_cache(maxsize=1)
def get_client():
    """
    Кешированный sync-клиент LangGraph.
    """
    return get_sync_client(url=LANGGRAPH_URL)


def check_server_available() -> bool:
    try:
        client = get_client()
        client.assistants.search()
        return True
    except Exception:
        return False


def _get_assistant_id(client, agent_graph_id: str) -> str:
    assistants = client.assistants.search()

    for assistant in assistants:
        graph_id = assistant.get('graph_id', '')
        if graph_id == agent_graph_id:
            return assistant['assistant_id']

    for assistant in assistants:
        graph_id = assistant.get('graph_id', '')
        if graph_id in supported_graphs:
            return assistant['assistant_id']

    raise ValueError(
        f'No suitable assistant found. Available: {[a.get("graph_id") for a in assistants]}'
    )


def _ensure_thread(client, thread_id: str) -> str:
    try:
        thread = client.threads.get(thread_id)
        return thread['thread_id']
    except Exception:
        thread = client.threads.create(thread_id=thread_id)
        return thread['thread_id']


def chat_sync(
    user_chat_id: str,
    message: str,
    agent_graph_id: str = 'supervisor',
) -> str:
    """
    Один запрос → один полный ответ.
    """
    client = get_client()
    thread_id = _user_id_to_uuid(user_chat_id)

    assistant_id = _get_assistant_id(client, agent_graph_id)
    thread_id = _ensure_thread(client, thread_id)

    input_state = {'messages': [{'type': 'human', 'content': message}]}

    result = client.runs.wait(
        thread_id=thread_id,
        assistant_id=assistant_id,
        input=input_state,
    )

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
    agent_graph_id: str = 'supervisor',
) -> Generator[str, None, None]:
    """
    Streaming-генератор токенов (plain text, по кусочкам).
    """
    client = get_client()
    thread_id = _user_id_to_uuid(user_chat_id)

    assistant_id = _get_assistant_id(client, agent_graph_id)
    thread_id = _ensure_thread(client, thread_id)

    input_state = {'messages': [{'type': 'human', 'content': message}]}

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


def get_thread_history(user_chat_id: str) -> list[dict[str, str]]:
    client = get_client()
    thread_id = _user_id_to_uuid(user_chat_id)

    try:
        state = client.threads.get_state(thread_id)

        if not state or 'values' not in state:
            return []

        values = state.get('values', {})
        messages = values.get('messages', [])

        ui_messages: list[dict[str, str]] = []
        for msg in messages:
            if isinstance(msg, dict):
                msg_type = msg.get('type', '')
                content = msg.get('content', '')

                if msg_type == 'human':
                    ui_messages.append({'role': 'user', 'content': content})
                elif msg_type == 'ai':
                    ui_messages.append({'role': 'assistant', 'content': content})

        return ui_messages

    except Exception as e:
        if LOG_LEVEL == 'DEBUG':
            print(f'[get_thread_history error: {e}]')
        return []
