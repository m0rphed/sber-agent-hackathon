"""
Agent SDK — клиентские функции для работы с LangGraph Server.
"""

from agent_sdk.config import LANGGRAPH_URL, GraphType, supported_graphs
from agent_sdk.langgraph_functions import (
    chat_with_agent,
    chat_with_streaming,
    get_final_response_streaming,
)

# UI-специфичные функции (синхронные, для Streamlit)
from agent_sdk.langgraph_functions_ui import (
    check_server_available,
    chat_sync,
    stream_chat,
    stream_chat_with_status,
    get_thread_history,
    clear_thread_history,
    list_threads,
    get_available_graphs,
)

__all__ = [
    # config
    'LANGGRAPH_URL',
    'GraphType',
    'supported_graphs',
    # async functions (для ботов)
    'chat_with_agent',
    'chat_with_streaming',
    'get_final_response_streaming',
    # sync functions (для UI)
    'check_server_available',
    'chat_sync',
    'stream_chat',
    'stream_chat_with_status',
    'get_thread_history',
    'clear_thread_history',
    'list_threads',
    'get_available_graphs',
]
