"""
- модели данных для RAG модуля

Определяет структуры для:
- Прошедших парсинг документов
- Результатов парсинга
- Чанков (кусочков текста) для индексации
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from langchain_core.documents import Document


class SourceType(str, Enum):
    """
    Тип источника данных
    """

    LIFE_SITUATIONS = 'life_situations' # gu.spb.ru/mfc/life_situations
    SERVICE_PAGES = 'service_pages'     # gu.spb.ru/{service_id}/ - страницы услуг
    KNOWLEDGE_BASE = 'knowledge_base'   # gu.spb.ru/knowledge-base
    GOV_HELPER = 'gov_helper'           # gov.spb.ru/helper
    MFC_SERVICES = 'mfc_services'       # gu.spb.ru/mfc/services
    OTHER = 'other'


@dataclass
class ParsedDocument:
    """
    Распарсенный документ из источника данных.

    Attributes:
        doc_id: Уникальный ID документа (обычно из URL)
        title: Заголовок страницы/документа
        content: Основной текст контента
        url: URL источника
        source_type: Тип источника (life_situations, knowledge_base, etc.)
        category: Категория документа (если есть)
        parent_id: ID родительского документа (для иерархии)
        metadata: Дополнительные метаданные
        parsed_at: Время парсинга
        content_hash: Хеш контента для отслеживания изменений
    """

    doc_id: str
    title: str
    content: str
    url: str
    source_type: SourceType
    category: str = ''
    parent_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    parsed_at: datetime = field(default_factory=datetime.now)
    content_hash: str = ''

    def __post_init__(self):
        """
        Вычисляем хеш контента если не задан
        """
        if not self.content_hash:
            import hashlib

            self.content_hash = hashlib.md5(self.content.encode()).hexdigest()

    def to_langchain_doc(self) -> Document:
        """
        Конвертирует в LangChain Document для индексации.

        Returns:
            Document с контентом и метаданными
        """
        return Document(
            page_content=self.content,
            metadata={
                'doc_id': self.doc_id,
                'title': self.title,
                'url': self.url,
                'source_type': self.source_type.value,
                'category': self.category,
                'parent_id': self.parent_id,
                'parsed_at': self.parsed_at.isoformat(),
                'content_hash': self.content_hash,
                **self.metadata,
            },
        )

    def to_dict(self) -> dict[str, Any]:
        """
        Сериализует в словарь
        """
        return {
            'doc_id': self.doc_id,
            'title': self.title,
            'content': self.content,
            'url': self.url,
            'source_type': self.source_type.value,
            'category': self.category,
            'parent_id': self.parent_id,
            'metadata': self.metadata,
            'parsed_at': self.parsed_at.isoformat(),
            'content_hash': self.content_hash,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> 'ParsedDocument':
        """
        Десериализует из словаря
        """
        return cls(
            doc_id=data['doc_id'],
            title=data['title'],
            content=data['content'],
            url=data['url'],
            source_type=SourceType(data['source_type']),
            category=data.get('category', ''),
            parent_id=data.get('parent_id'),
            metadata=data.get('metadata', {}),
            parsed_at=datetime.fromisoformat(data['parsed_at']),
            content_hash=data.get('content_hash', ''),
        )


@dataclass
class ParserResult:
    """
    Результат работы парсера.

    Attributes:
        documents: Список распарсенных документов
        errors: Список ошибок при парсинге
        stats: Статистика парсинга
    """

    documents: list[ParsedDocument] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)
    stats: dict[str, Any] = field(default_factory=dict)

    def add_document(self, doc: ParsedDocument) -> None:
        """
        Добавляет документ в результат
        """
        self.documents.append(doc)

    def add_error(self, url: str, error: str) -> None:
        """
        Добавляет ошибку в результат
        """
        self.errors.append(
            {
                'url': url,
                'error': error,
                'timestamp': datetime.now().isoformat(),
            }
        )

    def merge(self, other: 'ParserResult') -> 'ParserResult':
        """
        Объединяет с другим результатом
        """
        return ParserResult(
            documents=self.documents + other.documents,
            errors=self.errors + other.errors,
            stats={**self.stats, **other.stats},
        )

    @property
    def success_count(self) -> int:
        """
        Количество успешно прошедших парсинг документов
        """
        return len(self.documents)

    @property
    def error_count(self) -> int:
        """
        Количество ошибок
        """
        return len(self.errors)

    def to_langchain_docs(self) -> list[Document]:
        """
        Конвертирует все документы в LangChain формат
        """
        return [doc.to_langchain_doc() for doc in self.documents]


@dataclass
class ChunkMetadata:
    """
    Метаданные чанка для индексации.

    Attributes:
        chunk_id: Уникальный ID чанка
        doc_id: ID исходного документа
        chunk_index: Индекс чанка в документе
        total_chunks: Общее количество чанков в документе
    """

    chunk_id: str
    doc_id: str
    chunk_index: int
    total_chunks: int
