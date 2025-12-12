"""
Абстракция Retriever для RAG.

Позволяет легко заменять реализацию поиска:
- HybridRetriever (ChromaDB + BM25) - текущая
- OpenSearchRetriever - для production (TODO)

Использование:
    from langgraph_app.rag.retriever import get_retriever

    retriever = get_retriever()  # singleton, lazy init
    docs = retriever.search("запрос", k=5)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from langchain_core.documents import Document

from langgraph_app.logging_config import get_logger
from langgraph_app.rag.config import RAGConfig, get_rag_config

if TYPE_CHECKING:
    from langgraph_app.rag.indexer import HybridIndexer

logger = get_logger(__name__)


# =============================================================================
# Protocol / Interface
# =============================================================================


@runtime_checkable
class RetrieverProtocol(Protocol):
    """
    Протокол для retriever'ов.

    Любой retriever должен реализовать этот интерфейс,
    чтобы быть совместимым с RAG pipeline.
    """

    def search(self, query: str, k: int | None = None) -> list[Document]:
        """
        Выполняет поиск по запросу.

        Args:
            query: Поисковый запрос
            k: Количество результатов (None = default)

        Returns:
            Список релевантных документов
        """
        ...

    def is_ready(self) -> bool:
        """
        Проверяет, готов ли retriever к поиску.

        Returns:
            True если индекс загружен и готов
        """
        ...


class BaseRetriever(ABC):
    """
    Базовый класс для retriever'ов.

    Предоставляет общую логику и требует реализации
    конкретных методов в наследниках.
    """

    @abstractmethod
    def search(self, query: str, k: int | None = None) -> list[Document]:
        """Выполняет поиск."""
        ...

    @abstractmethod
    def is_ready(self) -> bool:
        """Проверяет готовность."""
        ...

    @abstractmethod
    def initialize(self) -> None:
        """Инициализирует retriever (загружает индекс и т.д.)."""
        ...


# =============================================================================
# Hybrid Retriever (ChromaDB + BM25)
# =============================================================================


class HybridRetriever(BaseRetriever):
    """
    Гибридный retriever с векторным и BM25 поиском.

    Обёртка над HybridIndexer с:
    - Ленивой инициализацией
    - Кэшированием подключения к ChromaDB
    - Готовностью к использованию в singleton
    """

    _indexer: HybridIndexer | None
    _config: RAGConfig
    _initialized: bool

    def __init__(self, config: RAGConfig | None = None):
        self._config = config or get_rag_config()
        self._indexer = None
        self._initialized = False

    def initialize(self) -> None:
        """
        Инициализирует indexer и загружает BM25 документы.

        Вызывается автоматически при первом search(),
        но можно вызвать явно для eager loading.
        """
        if self._initialized:
            return

        from langgraph_app.rag.indexer import HybridIndexer

        logger.info('hybrid_retriever_init_start')

        self._indexer = HybridIndexer(config=self._config)
        self._indexer._load_bm25_docs()

        self._initialized = True

        logger.info(
            'hybrid_retriever_init_complete',
            bm25_docs_count=len(self._indexer._bm25_docs),
        )

    def is_ready(self) -> bool:
        """Проверяет, инициализирован ли retriever."""
        return self._initialized and self._indexer is not None

    def search(self, query: str, k: int | None = None) -> list[Document]:
        """
        Выполняет гибридный поиск.

        Args:
            query: Поисковый запрос
            k: Количество результатов (None = из конфига)

        Returns:
            Список документов
        """
        # Lazy initialization
        if not self._initialized:
            self.initialize()

        effective_k = k if k is not None else self._config.search.k
        return self._indexer.search(query, k=effective_k)

    @property
    def indexer(self):
        """
        Доступ к underlying indexer для расширенных операций.

        Например: индексация новых документов.
        """
        if not self._initialized:
            self.initialize()
        return self._indexer


# =============================================================================
# OpenSearch Retriever (TODO: для production)
# =============================================================================


class OpenSearchRetriever(BaseRetriever):
    """
    OpenSearch retriever для production.

    TODO: Реализовать когда будет готов OpenSearch.

    Преимущества:
    - Масштабируемость
    - Встроенный BM25
    - Поддержка kNN для векторов
    """

    def __init__(self, endpoint: str | None = None):
        self._endpoint = endpoint
        self._client = None
        self._initialized = False

    def initialize(self) -> None:
        """Инициализация подключения к OpenSearch."""
        raise NotImplementedError('OpenSearchRetriever not implemented yet')

    def is_ready(self) -> bool:
        return self._initialized and self._client is not None

    def search(self, query: str, k: int | None = None) -> list[Document]:
        raise NotImplementedError('OpenSearchRetriever not implemented yet')


# =============================================================================
# Singleton / Factory
# =============================================================================

# Глобальный кэш retriever'ов
_retriever_cache: dict[str, BaseRetriever] = {}


def get_retriever(
    retriever_type: str = 'hybrid',
    force_new: bool = False,
    config: RAGConfig | None = None,
) -> BaseRetriever:
    """
    Возвращает singleton retriever.

    Args:
        retriever_type: Тип retriever'а ('hybrid' или 'opensearch')
        force_new: Создать новый экземпляр (для тестов)
        config: Конфигурация RAG (None = глобальный)

    Returns:
        Инициализированный retriever

    Raises:
        ValueError: Если тип не поддерживается
    """
    retriever: BaseRetriever

    if force_new or retriever_type not in _retriever_cache:
        if retriever_type == 'hybrid':
            retriever = HybridRetriever(config=config)
        elif retriever_type == 'opensearch':
            retriever = OpenSearchRetriever()
        else:
            raise ValueError(f"Unknown retriever type: {retriever_type}")

        if not force_new:
            _retriever_cache[retriever_type] = retriever

        logger.debug('retriever_created', type=retriever_type, cached=not force_new)
        return retriever
    logger.debug('retriever_reused_cached', type=retriever_type)
    return _retriever_cache[retriever_type]


def get_hybrid_retriever(force_new: bool = False) -> HybridRetriever:
    """
    Сокращение для get_retriever('hybrid').

    Возвращает типизированный HybridRetriever.
    """
    return get_retriever('hybrid', force_new=force_new)  # type: ignore


def clear_retriever_cache() -> None:
    """
    Очищает кэш retriever'ов.

    Используется в тестах или при hot-reload индекса.
    """
    global _retriever_cache
    _retriever_cache.clear()
    logger.info('retriever_cache_cleared')


# =============================================================================
# Quick search function
# =============================================================================


def search(
    query: str,
    k: int | None = None,
    retriever_type: str = 'hybrid',
    config: RAGConfig | None = None,
) -> list[Document]:
    """
    Быстрый поиск через singleton retriever.

    Удобная функция для простых случаев.

    Args:
        query: Поисковый запрос
        k: Количество результатов (None = из конфига)
        retriever_type: Тип retriever'а
        config: Конфигурация RAG

    Returns:
        Список документов
    """
    cfg = config or get_rag_config()
    effective_k = k if k is not None else cfg.search.k
    retriever = get_retriever(retriever_type, config=config)
    return retriever.search(query, k=effective_k)
