"""
Базовый класс парсера для источников данных.

-> определяет общий интерфейс и утилиты для всех парсеров
"""

from abc import ABC, abstractmethod
import time
from typing import Any
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
import requests

from app.logging_config import get_logger
from app.rag.models import ParsedDocument, ParserResult, SourceType

logger = get_logger(__name__)


class BaseParser(ABC):
    """
    Базовый класс для парсеров источников данных.

    Особенности:
    - Rate limiting для вежливого парсинга
    - Обработка ошибок с логированием
    - Кеширование для инкрементального обновления
    - Унифицированный формат результатов
    """

    # настройки по умолчанию
    DEFAULT_DELAY = 0.5  # секунд между запросами
    DEFAULT_TIMEOUT = 30  # таймаут запроса
    DEFAULT_USER_AGENT = (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/120.0.0.0 Safari/537.36'
    )

    def __init__(
        self,
        base_url: str,
        source_type: SourceType,
        delay: float = DEFAULT_DELAY,
        timeout: int = DEFAULT_TIMEOUT,
    ):
        """
        Args:
            base_url: Базовый URL источника
            source_type: Тип источника данных
            delay: Задержка между запросами (секунды)
            timeout: Таймаут запроса (секунды)
        """
        self.base_url = base_url.rstrip('/')
        self.source_type = source_type
        self.delay = delay
        self.timeout = timeout
        self.session = self._create_session()
        self._last_request_time = 0.0

    def _create_session(self) -> requests.Session:
        """
        Создаёт сессию с настроенными заголовками
        """
        session = requests.Session()
        session.headers.update(
            {
                'User-Agent': self.DEFAULT_USER_AGENT,
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'ru-RU,ru;q=0.9,en;q=0.8',
            }
        )
        return session

    def _rate_limit(self) -> None:
        """
        Ограничивает частоту запросов
        """
        elapsed = time.time() - self._last_request_time
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)
        self._last_request_time = time.time()

    def fetch_page(self, url: str) -> BeautifulSoup | None:
        """
        Загружает и парсит HTML страницу.

        Args:
            url: URL страницы

        Returns:
            BeautifulSoup объект или None при ошибке
        """
        self._rate_limit()

        try:
            logger.debug(f'Fetching: {url}')
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()
            response.encoding = response.apparent_encoding or 'utf-8'
            return BeautifulSoup(response.text, 'html.parser')

        except requests.RequestException as e:
            logger.error(f'Error fetching {url}: {e}')
            return None

    def get_absolute_url(self, relative_url: str) -> str:
        """
        Преобразует относительный URL в абсолютный
        """
        return urljoin(self.base_url, relative_url)

    def extract_id_from_url(self, url: str) -> str:
        """
        Извлекает ID из URL.

        Пример: /mfc/life_situations/190057/ -> 190057
        """
        path = urlparse(url).path.rstrip('/')
        parts = path.split('/')
        # Ищем числовой ID
        for part in reversed(parts):
            if part.isdigit():
                return part
        # Если нет числа, берём последнюю часть
        return parts[-1] if parts else url

    def clean_text(self, text: str) -> str:
        """
        Очищает текст от лишних пробелов и переносов.

        Args:
            text: Исходный текст

        Returns:
            Очищенный текст
        """
        if not text:
            return ''
        # убираем множественные пробелы и переносы
        lines = text.split('\n')
        cleaned_lines = [' '.join(line.split()) for line in lines]
        # убираем пустые строки
        cleaned_lines = [line for line in cleaned_lines if line]
        return '\n'.join(cleaned_lines)

    @abstractmethod
    def parse(self, **kwargs: Any) -> ParserResult:
        """
        Основной метод парсинга.

        Returns:
            ParserResult с документами и статистикой
        """

    @abstractmethod
    def parse_page(self, url: str) -> ParsedDocument | None:
        """
        Парсит отдельную страницу.

        Args:
            url: URL страницы

        Returns:
            ParsedDocument или None при ошибке
        """

    def get_existing_hashes(self) -> dict[str, str]:
        """
        Получает хеши существующих документов для инкрементального обновления.

        Returns:
            Словарь {doc_id: content_hash}

        Note:
            Переопределите для использования с хранилищем
        """
        return {}

    def should_update(self, doc: ParsedDocument) -> bool:
        """
        Проверяет, нужно ли обновлять документ.

        Args:
            doc: документ прошедший парсинг

        Returns:
            True если документ новый или изменился
        """
        existing_hashes = self.get_existing_hashes()
        existing_hash = existing_hashes.get(doc.doc_id)

        if existing_hash is None:
            logger.debug(f'New document: {doc.doc_id}')
            return True

        if existing_hash != doc.content_hash:
            logger.debug(f'Updated document: {doc.doc_id}')
            return True

        logger.debug(f'Unchanged document: {doc.doc_id}')
        return False
