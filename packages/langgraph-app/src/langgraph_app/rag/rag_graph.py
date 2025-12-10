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
from langgraph_app.logging_config import get_logger

logger = get_logger(__name__)


def create_rag_graph(
    use_query_rewriting: bool = True,
    use_document_grading: bool = True,
    use_toxicity_check: bool = True,
) -> StateGraph:
    raise NotImplementedError()