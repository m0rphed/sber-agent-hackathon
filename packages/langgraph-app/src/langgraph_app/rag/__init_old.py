"""
RAG (Retrieval-Augmented Generation) модуль для Городского помощника.

Содержит:
- models.py - модели данных (ParsedDocument, ParserResult)
- parsers/ - парсеры источников данных (gu.spb.ru)
- pipeline.py - оркестратор парсинга
- indexer.py - индексация документов в векторное хранилище
- enhancers.py - улучшения RAG (query rewriting, document grading)
- retriever.py - абстракция retriever с singleton кэшированием

Рекомендуемое использование:
    from langgraph_app.rag import get_retriever, search

    # Singleton retriever (рекомендуется)
    retriever = get_retriever()
    docs = retriever.search("как получить паспорт", k=5)

    # Или быстрый поиск
    docs = search("как получить паспорт", k=5)
"""

from langgraph_app.rag.enhancers import DocumentGrader, EnhancedRAGSearch, QueryRewriter
from langgraph_app.rag.indexer import DocumentChunker, HybridIndexer, load_parsed_documents
from langgraph_app.rag.models import ParsedDocument, ParserResult, SourceType
from langgraph_app.rag.parsers import BaseParser, LifeSituationsParser, ServicePageParser
from langgraph_app.rag.pipeline import ParsingPipeline, PipelineResult
from langgraph_app.rag.retriever import (
    BaseRetriever,
    HybridRetriever,
    RetrieverProtocol,
    clear_retriever_cache,
    get_hybrid_retriever,
    get_retriever,
    search,
)

__all__ = [
    # Models
    'ParsedDocument',
    'ParserResult',
    'SourceType',
    # Parsers
    'BaseParser',
    'LifeSituationsParser',
    'ServicePageParser',
    # Pipeline
    'ParsingPipeline',
    'PipelineResult',
    # Indexer (low-level, prefer retriever API)
    'DocumentChunker',
    'HybridIndexer',
    'load_parsed_documents',
    # Retriever (recommended API)
    'RetrieverProtocol',
    'BaseRetriever',
    'HybridRetriever',
    'get_retriever',
    'get_hybrid_retriever',
    'clear_retriever_cache',
    'search',
    # Enhancers
    'QueryRewriter',
    'DocumentGrader',
    'EnhancedRAGSearch',
]
