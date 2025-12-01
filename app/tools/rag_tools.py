"""
LangChain Tools для RAG-поиска по базе знаний госуслуг.
"""

import logging
import os

from langchain_core.tools import tool

logger = logging.getLogger(__name__)

# ленивая инициализация enhanced search
_enhanced_search = None
_simple_indexer = None


def _get_enhanced_search():
    """
    Получает singleton EnhancedRAGSearch
    """
    global _enhanced_search
    if _enhanced_search is None:
        from app.rag.enhancers import EnhancedRAGSearch

        # можно отключить через переменные окружения
        use_rewriting = os.getenv('RAG_USE_QUERY_REWRITING', 'true').lower() == 'true'
        use_grading = os.getenv('RAG_USE_DOCUMENT_GRADING', 'true').lower() == 'true'

        logger.info(
            f'Initializing EnhancedRAGSearch '
            f'(rewriting={use_rewriting}, grading={use_grading})...'
        )
        _enhanced_search = EnhancedRAGSearch(
            use_query_rewriting=use_rewriting,
            use_document_grading=use_grading,
        )
    return _enhanced_search


def _get_simple_indexer():
    """
    Получает singleton простого индексатора (без улучшений)
    """
    global _simple_indexer
    if _simple_indexer is None:
        from app.rag.indexer import HybridIndexer

        logger.info('Initializing simple HybridIndexer...')
        _simple_indexer = HybridIndexer()
        _simple_indexer._load_bm25_docs()
    return _simple_indexer


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
    logger.info(f'🔧 [TOOL CALL] search_city_services(query="{query}")')

    try:
        # используем улучшенный поиск
        enhanced_search = _get_enhanced_search()
        results, metadata = enhanced_search.search(query, k=5, min_relevant=2)

        # логируем метаданные поиска
        if metadata.get('rewritten_query'):
            logger.info(f'📝 Query rewritten: "{query}" → "{metadata["rewritten_query"]}"')
        logger.info(
            f'📊 Search stats: retrieved={metadata["retrieved_count"]}, '
            f'filtered={metadata["filtered_count"]}'
        )

        if not results:
            logger.warning(f'⚠️ [TOOL RESULT] Ничего не найдено по запросу: {query}')
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

            formatted_results.append(
                f'## {title}\n'
                f'**Источник:** {url}\n\n'
                f'{content}'
            )

        logger.info(f'✅ [TOOL RESULT] Найдено {len(formatted_results)} результатов')

        response = '\n\n---\n\n'.join(formatted_results)
        return response

    except Exception as e:
        logger.error(f'❌ [TOOL ERROR] {e}')
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
    logger.info(f'🔧 [TOOL CALL] search_city_services_simple(query="{query}")')

    try:
        indexer = _get_simple_indexer()
        results = indexer.search(query, k=5)

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
        logger.error(f'❌ [TOOL ERROR] {e}')
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
