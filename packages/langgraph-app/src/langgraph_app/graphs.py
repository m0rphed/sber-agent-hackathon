"""
Экспорт LangGraph графов для Agent Server.

Этот модуль предоставляет точки входа для langgraph.json.
Каждая функция возвращает скомпилированный граф, опционально
принимая конфигурацию для runtime настройки.

Графы:
    - supervisor: Основной агент с intent routing
    - hybrid: Агент с ReAct для API tools
    - rag: RAG-пайплайн для поиска по базе знаний

Использование в langgraph.json:
    {
        "graphs": {
            "supervisor": "./app/graphs.py:supervisor",
            "hybrid": "./app/graphs.py:hybrid",
            "rag": "./app/graphs.py:rag"
        }
    }
"""

from langchain_core.runnables import RunnableConfig
from langgraph.graph.state import CompiledStateGraph

from langgraph_app.logging_config import get_logger

logger = get_logger(__name__)


# =============================================================================
# Graph Factory Functions
# =============================================================================


def hybrid(config: RunnableConfig | None = None) -> CompiledStateGraph:
    """
    Создаёт Hybrid Graph — агент с ReAct для сложных API запросов.

    Отличия от Supervisor:
        - Использует полноценный ReAct агент для API tools
        - Может делать цепочки tool calls
        - Более гибкий, но дороже по API вызовам

    Args:
        config: Runtime конфигурация

    Returns:
        Скомпилированный StateGraph
    """
    from langgraph_app.agent.hybrid import create_hybrid_v2_graph

    logger.info(
        'graph_factory_hybrid',
        config_present=config is not None,
    )

    graph = create_hybrid_v2_graph(checkpointer=None)

    return graph


def rag(config: RunnableConfig | None = None) -> CompiledStateGraph:
    """
    Создаёт RAG Graph — пайплайн для поиска по базе знаний.

    Архитектура:
        START → rewrite_query → retrieve → deduplicate → grade → END

    Опциональные улучшения (включены по умолчанию):
        - Query rewriting для улучшения поиска
        - Document grading для фильтрации нерелевантных

    Args:
        config: Runtime конфигурация

    Returns:
        Скомпилированный StateGraph
    """
    from langgraph_app.rag.graph import create_rag_graph

    logger.info(
        'graph_factory_rag',
        config_present=config is not None,
    )

    graph = create_rag_graph(
        use_query_rewriting=True,
        use_document_grading=True,
    )

    return graph


# =============================================================================
# Pre-built Graph Instances (for simple use cases)
# =============================================================================

# Для случаев, когда нужен готовый экземпляр без фабрики
# Примечание: эти экземпляры создаются при первом доступе

_cached_graphs: dict[str, CompiledStateGraph] = {}


def get_hybrid() -> CompiledStateGraph:
    """
    Возвращает кэшированный Hybrid Graph
    """
    if 'hybrid' not in _cached_graphs:
        _cached_graphs['hybrid'] = hybrid()
    return _cached_graphs['hybrid']


def get_rag() -> CompiledStateGraph:
    """
    Возвращает кэшированный RAG Graph
    """
    if 'rag' not in _cached_graphs:
        _cached_graphs['rag'] = rag()
    return _cached_graphs['rag']


# =============================================================================
# Exports for langgraph.json
# =============================================================================

# Эти имена используются в langgraph.json:
#   "./app/graphs.py:supervisor"   → supervisor function
#   "./app/graphs.py:hybrid"       → hybrid function
#   "./app/graphs.py:rag"          → rag function

__all__ = [
    'hybrid',
    'rag',
    'get_hybrid',
    'get_rag',
]
