"""
RAG (Retrieval-Augmented Generation) модуль для Городского помощника.

Содержит:
- models.py - модели данных (ParsedDocument, ParserResult)
- parsers/ - парсеры источников данных (gu.spb.ru)
- pipeline.py - оркестратор парсинга
- indexer.py - индексация документов в векторное хранилище
- enhancers.py - улучшения RAG (query rewriting, document grading)
"""

from app.rag.enhancers import DocumentGrader, EnhancedRAGSearch, QueryRewriter
from app.rag.indexer import DocumentChunker, HybridIndexer, load_parsed_documents
from app.rag.models import ParsedDocument, ParserResult, SourceType
from app.rag.parsers import BaseParser, LifeSituationsParser, ServicePageParser
from app.rag.pipeline import ParsingPipeline, PipelineResult

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
    # Indexer
    'DocumentChunker',
    'HybridIndexer',
    'load_parsed_documents',
    # Enhancers
    'QueryRewriter',
    'DocumentGrader',
    'EnhancedRAGSearch',
]
