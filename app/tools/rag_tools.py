"""
LangChain Tools для RAG-поиска по базе знаний госуслуг.

Использует LangGraph для структурированного пайплайна.
"""

import os

from langchain_core.tools import tool

from app.logging_config import get_logger

logger = get_logger(__name__)

# ленивая инициализация
_rag_graph = None


def _get_rag_graph():
    """
    Получает singleton RAG Graph
    """
    global _rag_graph
    if _rag_graph is None:
        from app.rag.graph import create_rag_graph

        # можно отключить через переменные окружения
        use_rewriting = os.getenv('RAG_USE_QUERY_REWRITING', 'true').lower() == 'true'
        use_grading = os.getenv('RAG_USE_DOCUMENT_GRADING', 'true').lower() == 'true'

        logger.info(
            'rag_graph_init',
            use_rewriting=use_rewriting,
            use_grading=use_grading,
        )
        _rag_graph = create_rag_graph(
            use_query_rewriting=use_rewriting,
            use_document_grading=use_grading,
        )
    return _rag_graph


def _get_simple_retriever():
    """
    Получает singleton retriever (без улучшений query rewriting/grading).

    Использует кэшированный HybridRetriever из app.rag.retriever.
    """
    from app.rag.retriever import get_retriever

    return get_retriever()


@tool
def search_city_services(query: str) -> str:
    """
    Поиск информации о государственных услугах Санкт-Петербурга.

    Используй этот инструмент, когда пользователь спрашивает:
    - Как получить [документ/услугу]?
    - Какие документы нужны для [услуга]?
    - Где оформить [документ]?
    - Сроки получения [услуга]?
    - Кто может получить [льгота/услуга]?
    - Информация о госуслугах

    Примеры запросов:
    - "как получить загранпаспорт"
    - "документы для регистрации по месту жительства"
    - "субсидии на оплату ЖКХ"
    - "запись ребенка в детский сад"

    Args:
        query: Поисковый запрос пользователя на естественном языке

    Returns:
        Релевантная информация из базы знаний госуслуг с указанием источников
    """
    logger.info('tool_call', tool='search_city_services', query=query)

    try:
        # Используем RAG Graph
        graph = _get_rag_graph()

        # Инициализируем состояние
        initial_state = {
            'query': query,
            'k': 5,
            'min_relevant': 2,
            'rewritten_query': None,
            'retrieved_docs': [],
            'deduplicated_docs': [],
            'graded_docs': [],
            'metadata': {},
        }

        # Выполняем граф
        result = graph.invoke(initial_state)

        results = result.get('graded_docs', [])
        metadata = result.get('metadata', {})

        # логируем метаданные поиска
        logger.info(
            'search_complete',
            original_query=query,
            rewritten_query=metadata.get('rewritten_query'),
            retrieved_count=metadata.get('retrieved_count', 0),
            filtered_count=metadata.get('final_count', 0),
        )

        if not results:
            logger.warning('search_no_results', query=query)
            return 'К сожалению, по вашему запросу ничего не найдено. Попробуйте переформулировать вопрос.'

        # форматируем результаты
        formatted_results = []
        seen_urls = set()  # без дубликатов по URL

        for doc in results:
            url = doc.metadata.get('url', '')

            # пропускаем дубликаты
            if url in seen_urls:
                continue
            seen_urls.add(url)

            title = doc.metadata.get('title', 'Без названия')
            content = doc.page_content.strip()

            # ограничиваем длину контента
            if len(content) > 800:
                content = content[:800] + '...'

            formatted_results.append(f'## {title}\n**Источник:** {url}\n\n{content}')

        logger.info(
            'tool_result',
            tool='search_city_services',
            results_count=len(formatted_results),
        )

        response = '\n\n---\n\n'.join(formatted_results)
        return response

    except Exception as e:
        logger.error('tool_error', tool='search_city_services', error=str(e))
        return f'Произошла ошибка при поиске: {e}'


@tool
def search_city_services_simple(query: str) -> str:
    """
    Простой поиск информации о госуслугах (без улучшений).

    Используется как fallback или для сравнения с улучшенным поиском.

    Args:
        query: Поисковый запрос

    Returns:
        Информация из базы знаний
    """
    logger.info('tool_call', tool='search_city_services_simple', query=query)

    try:
        retriever = _get_simple_retriever()
        results = retriever.search(query, k=5)

        if not results:
            return 'Ничего не найдено.'

        formatted = []
        for doc in results[:3]:
            title = doc.metadata.get('title', 'N/A')
            url = doc.metadata.get('url', '')
            content = doc.page_content[:500]
            formatted.append(f'## {title}\n{url}\n\n{content}...')

        return '\n\n---\n\n'.join(formatted)

    except Exception as e:
        logger.error('tool_error', tool='search_city_services_simple', error=str(e))
        return f'Ошибка: {e}'


# список RAG-инструментов (основной + простой для сравнения)
RAG_TOOLS = [
    search_city_services,
]

# все RAG инструменты включая debug
RAG_TOOLS_ALL = [
    search_city_services,
    search_city_services_simple,
]
