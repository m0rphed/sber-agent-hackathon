"""
RAG Pipeline как LangGraph StateGraph.

Преимущества:
- Явные узлы с именами для трейсинга
- Возможность визуализации графа
- Легко добавить новые шаги (self-reflection, retry, etc.)
- Структурированное состояние на каждом этапе

Узлы пайплайна:
0. check_toxicity - проверка токсичности запроса (первый шаг!)
1. rewrite_query - переформулирование запроса
2. retrieve_documents - гибридный поиск (vector + BM25)
3. deduplicate_chunks - удаление дублей по URL
4. grade_documents - batch grading релевантности
5. format_response - форматирование результата

Граф:
    START → check_toxicity → [если токсично → END]
                           → [если ОК → rewrite_query → retrieve → deduplicate → grade → format → END]
"""

from typing import TypedDict

from langchain_core.documents import Document

# Импорты LangGraph - актуальный API v1
# ВАЖНО: используем именно эти импорты для совместимости
from langgraph.graph import END, START, StateGraph

from app.logging_config import get_logger

logger = get_logger(__name__)


# =============================================================================
# State Definition
# =============================================================================


class RAGState(TypedDict):
    """
    Состояние RAG пайплайна.

    Каждый узел читает и обновляет это состояние.
    """

    # Входные данные
    query: str  # Исходный запрос пользователя
    k: int  # Количество документов для возврата
    min_relevant: int  # Минимум релевантных документов

    # Toxicity check результат
    is_toxic: bool  # True если запрос токсичный
    toxicity_response: str | None  # Ответ для токсичного запроса

    # Промежуточные результаты
    rewritten_query: str | None  # Переформулированный запрос
    retrieved_docs: list[Document]  # Найденные документы
    deduplicated_docs: list[Document]  # После дедупликации
    graded_docs: list[Document]  # Отфильтрованные релевантные

    # Метаданные для логирования
    metadata: dict  # Статистика по шагам


# =============================================================================
# Node Functions
# =============================================================================


def check_toxicity_node(state: RAGState) -> dict:
    """
    Узел 0: Проверка токсичности запроса.

    Выполняется ПЕРВЫМ, до любой обработки.
    Если запрос токсичный - пайплайн прерывается.
    """
    from app.services.toxicity import get_toxicity_filter

    query = state['query']

    logger.info('node_start', node='check_toxicity', query_length=len(query))

    toxicity_filter = get_toxicity_filter()
    result = toxicity_filter.check(query)

    if result.should_block:
        response = toxicity_filter.get_response(result)
        logger.warning(
            'node_complete',
            node='check_toxicity',
            is_toxic=True,
            toxicity_level=result.level.value,
            matched_patterns_count=len(result.matched_patterns),
            confidence=result.confidence,
        )
        logger.debug(
            'toxicity_details',
            matched_patterns=result.matched_patterns[:5],
        )
        return {
            'is_toxic': True,
            'toxicity_response': response,
            'metadata': {
                **state.get('metadata', {}),
                'toxicity_blocked': True,
                'toxicity_level': result.level.value,
            },
        }

    logger.info(
        'node_complete',
        node='check_toxicity',
        is_toxic=False,
        toxicity_level=result.level.value,
    )

    return {
        'is_toxic': False,
        'toxicity_response': None,
        'metadata': {
            **state.get('metadata', {}),
            'toxicity_blocked': False,
        },
    }


def rewrite_query_node(state: RAGState) -> dict:
    """
    Узел 1: Переформулирование запроса.

    Использует LLM для создания более информативного запроса,
    подходящего для векторного и ключевого поиска.
    """
    from app.rag.enhancers import QueryRewriter

    query = state['query']

    logger.info('node_start', node='rewrite_query', query=query)

    rewriter = QueryRewriter()
    rewritten = rewriter.rewrite(query)

    logger.info(
        'node_complete',
        node='rewrite_query',
        original=query,
        rewritten=rewritten,
    )

    return {
        'rewritten_query': rewritten,
        'metadata': {
            **state.get('metadata', {}),
            'query_rewritten': query != rewritten,
        },
    }


def retrieve_documents_node(state: RAGState) -> dict:
    """
    Узел 2: Гибридный поиск документов.

    Использует singleton HybridRetriever (vector + BM25) для поиска.
    Retriever кэшируется — повторные запросы не создают новый indexer.
    """
    from app.rag.retriever import get_retriever

    # Используем переписанный запрос если есть
    search_query = state.get('rewritten_query') or state['query']
    k = state.get('k', 5)

    # Запрашиваем больше для последующей фильтрации
    fetch_k = k * 2

    logger.info(
        'node_start',
        node='retrieve_documents',
        query=search_query,
        fetch_k=fetch_k,
    )

    # Singleton retriever — не создаём новый при каждом запросе
    retriever = get_retriever()
    documents = retriever.search(search_query, k=fetch_k)

    logger.info(
        'node_complete',
        node='retrieve_documents',
        retrieved_count=len(documents),
    )

    return {
        'retrieved_docs': documents,
        'metadata': {
            **state.get('metadata', {}),
            'retrieved_count': len(documents),
        },
    }


def deduplicate_chunks_node(state: RAGState) -> dict:
    """
    Узел 3: Дедупликация чанков по URL.

    Убирает дублирующиеся чанки из одного документа,
    оставляя только первый (обычно самый релевантный).
    """
    documents = state.get('retrieved_docs', [])

    logger.info(
        'node_start',
        node='deduplicate_chunks',
        input_count=len(documents),
    )

    seen_urls: set[str] = set()
    unique_docs: list[Document] = []

    for doc in documents:
        url = doc.metadata.get('url', '')
        if url and url in seen_urls:
            continue
        seen_urls.add(url)
        unique_docs.append(doc)

    logger.info(
        'node_complete',
        node='deduplicate_chunks',
        input_count=len(documents),
        output_count=len(unique_docs),
    )

    return {
        'deduplicated_docs': unique_docs,
        'metadata': {
            **state.get('metadata', {}),
            'deduplicated_count': len(unique_docs),
        },
    }


def grade_documents_node(state: RAGState) -> dict:
    """
    Узел 4: Batch grading документов.

    Оценивает релевантность всех документов одним вызовом LLM.
    """
    from app.rag.enhancers import DocumentGrader

    documents = state.get('deduplicated_docs', [])
    query = state['query']  # Оригинальный запрос для grading
    min_relevant = state.get('min_relevant', 2)

    logger.info(
        'node_start',
        node='grade_documents',
        input_count=len(documents),
    )

    if not documents:
        logger.warning('node_skip', node='grade_documents', reason='no_documents')
        return {'graded_docs': [], 'metadata': state.get('metadata', {})}

    grader = DocumentGrader()
    graded = grader.filter_relevant(
        query=query,
        documents=documents,
        min_relevant=min_relevant,
        deduplicate=False,  # Уже дедуплицировали
    )

    logger.info(
        'node_complete',
        node='grade_documents',
        input_count=len(documents),
        output_count=len(graded),
    )

    return {
        'graded_docs': graded,
        'metadata': {
            **state.get('metadata', {}),
            'graded_count': len(graded),
        },
    }


def format_response_node(state: RAGState) -> dict:
    """
    Узел 5: Финальное форматирование результата.

    Ограничивает количество документов до k.
    """
    documents = state.get('graded_docs', [])
    k = state.get('k', 5)

    logger.info(
        'node_start',
        node='format_response',
        input_count=len(documents),
        limit_k=k,
    )

    # Ограничиваем до k
    final_docs = documents[:k]

    # Собираем финальные метаданные
    metadata = {
        **state.get('metadata', {}),
        'original_query': state['query'],
        'rewritten_query': state.get('rewritten_query'),
        'final_count': len(final_docs),
    }

    logger.info(
        'node_complete',
        node='format_response',
        output_count=len(final_docs),
    )

    return {
        'graded_docs': final_docs,
        'metadata': metadata,
    }


# =============================================================================
# Graph Builder
# =============================================================================


def _toxicity_router(state: RAGState) -> str:
    """
    Условный роутер после проверки токсичности.

    Если запрос токсичный - сразу на END.
    Иначе - продолжаем к rewrite_query или retrieve.
    """
    if state.get('is_toxic', False):
        logger.debug('toxicity_router', decision='END', reason='toxic_query')
        return 'end'
    logger.debug('toxicity_router', decision='continue', reason='safe_query')
    return 'continue'


def create_rag_graph(
    use_query_rewriting: bool = True,
    use_document_grading: bool = True,
    use_toxicity_check: bool = True,
) -> StateGraph:
    """
    Создаёт RAG пайплайн как LangGraph.

    Args:
        use_query_rewriting: Включить переформулирование запроса
        use_document_grading: Включить grading документов
        use_toxicity_check: Включить проверку токсичности (первый шаг)

    Returns:
        Скомпилированный граф
    """
    logger.info(
        'graph_build_start',
        use_toxicity_check=use_toxicity_check,
        use_query_rewriting=use_query_rewriting,
        use_document_grading=use_document_grading,
    )

    builder = StateGraph(RAGState)

    # Добавляем узлы
    if use_toxicity_check:
        builder.add_node('check_toxicity', check_toxicity_node)

    if use_query_rewriting:
        builder.add_node('rewrite_query', rewrite_query_node)

    builder.add_node('retrieve_documents', retrieve_documents_node)
    builder.add_node('deduplicate_chunks', deduplicate_chunks_node)

    if use_document_grading:
        builder.add_node('grade_documents', grade_documents_node)

    builder.add_node('format_response', format_response_node)

    # Добавляем рёбра (edges)
    # Определяем первый узел после START
    first_processing_node = 'rewrite_query' if use_query_rewriting else 'retrieve_documents'

    if use_toxicity_check:
        # START → check_toxicity → [условный переход]
        builder.add_edge(START, 'check_toxicity')
        builder.add_conditional_edges(
            'check_toxicity',
            _toxicity_router,
            {
                'end': END,  # Токсичный запрос → сразу END
                'continue': first_processing_node,  # Безопасный → продолжаем
            },
        )
    else:
        # Без проверки токсичности - сразу к обработке
        builder.add_edge(START, first_processing_node)

    # Остальные рёбра
    if use_query_rewriting:
        builder.add_edge('rewrite_query', 'retrieve_documents')

    builder.add_edge('retrieve_documents', 'deduplicate_chunks')

    if use_document_grading:
        builder.add_edge('deduplicate_chunks', 'grade_documents')
        builder.add_edge('grade_documents', 'format_response')
    else:
        builder.add_edge('deduplicate_chunks', 'format_response')

    builder.add_edge('format_response', END)

    graph = builder.compile()

    logger.info('graph_build_complete', nodes=list(graph.nodes.keys()))

    return graph


# =============================================================================
# Graph Cache
# =============================================================================

# Кэш для RAG графов (по конфигурации)
_rag_graph_cache: dict[tuple[bool, bool, bool], StateGraph] = {}


def get_rag_graph(
    use_query_rewriting: bool = True,
    use_document_grading: bool = True,
    use_toxicity_check: bool = True,
):
    """
    Возвращает кэшированный RAG Graph.

    Граф создаётся один раз для каждой комбинации параметров и переиспользуется.
    """
    cache_key = (use_query_rewriting, use_document_grading, use_toxicity_check)

    if cache_key not in _rag_graph_cache:
        _rag_graph_cache[cache_key] = create_rag_graph(
            use_query_rewriting=use_query_rewriting,
            use_document_grading=use_document_grading,
            use_toxicity_check=use_toxicity_check,
        )

    return _rag_graph_cache[cache_key]


# =============================================================================
# Convenience Function
# =============================================================================


def search_with_graph(
    query: str,
    k: int = 5,
    min_relevant: int = 2,
    use_query_rewriting: bool = True,
    use_document_grading: bool = True,
    use_toxicity_check: bool = True,
) -> tuple[list[Document], dict]:
    """
    Выполняет RAG поиск через граф.

    Args:
        query: Поисковый запрос
        k: Количество результатов
        min_relevant: Минимум релевантных документов
        use_query_rewriting: Использовать переформулирование
        use_document_grading: Использовать grading
        use_toxicity_check: Проверять токсичность (первый шаг)

    Returns:
        Кортеж (документы, метаданные)
        Если запрос токсичный - документы=[], metadata содержит toxicity_blocked=True
    """
    # Используем кэшированный граф
    graph = get_rag_graph(
        use_query_rewriting=use_query_rewriting,
        use_document_grading=use_document_grading,
        use_toxicity_check=use_toxicity_check,
    )

    # Инициализируем состояние
    initial_state: RAGState = {
        'query': query,
        'k': k,
        'min_relevant': min_relevant,
        # Toxicity fields
        'is_toxic': False,
        'toxicity_response': None,
        # Processing fields
        'rewritten_query': None,
        'retrieved_docs': [],
        'deduplicated_docs': [],
        'graded_docs': [],
        'metadata': {},
    }

    logger.info(
        'graph_invoke_start',
        query=query,
        k=k,
        min_relevant=min_relevant,
        use_toxicity_check=use_toxicity_check,
    )

    # Выполняем граф
    result = graph.invoke(initial_state)

    # Проверяем, был ли запрос заблокирован
    if result.get('is_toxic', False):
        logger.warning(
            'graph_invoke_blocked',
            reason='toxic_query',
            toxicity_response=result.get('toxicity_response'),
        )
        return [], {
            **result.get('metadata', {}),
            'toxicity_blocked': True,
            'toxicity_response': result.get('toxicity_response'),
        }

    documents = result.get('graded_docs', [])
    metadata = result.get('metadata', {})

    logger.info(
        'graph_invoke_complete',
        results_count=len(documents),
        metadata=metadata,
    )

    return documents, metadata


# =============================================================================
# CLI для тестирования
# =============================================================================


if __name__ == '__main__':
    import os

    os.environ['LOG_LEVEL'] = 'DEBUG'
    from app.logging_config import configure_logging

    configure_logging()

    # Тест 1: Нормальный запрос
    query = 'как получить загранпаспорт'
    print(f"\n{'=' * 60}")
    print(f"Тест 1: Нормальный запрос: '{query}'")
    print('=' * 60)

    docs, meta = search_with_graph(query, k=3)

    print(f'\nНайдено документов: {len(docs)}')
    print(f'Метаданные: {meta}')

    for i, doc in enumerate(docs, 1):
        title = doc.metadata.get('title', 'N/A')
        url = doc.metadata.get('url', '')
        print(f'\n{i}. {title}')
        print(f'   URL: {url}')

    # Тест 2: Токсичный запрос
    toxic_query = 'ты тупой идиот, ответь мне!'
    print(f"\n{'=' * 60}")
    print(f"Тест 2: Токсичный запрос: '{toxic_query}'")
    print('=' * 60)

    docs, meta = search_with_graph(toxic_query, k=3)

    print(f'\nНайдено документов: {len(docs)}')
    print(f'Заблокирован: {meta.get("toxicity_blocked", False)}')
    if meta.get('toxicity_response'):
        print(f'Ответ: {meta.get("toxicity_response")}')
