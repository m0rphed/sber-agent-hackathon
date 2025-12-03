"""
- пайплайн парсинга данных для RAG

Оркестрирует процесс парсинга:
1. Парсинг жизненных ситуаций (life_situations)
2. Извлечение ссылок на услуги
3. Дедупликация URL
4. Парсинг страниц услуг (service_pages)

Пример использования:
    pipeline = ParsingPipeline()
    result = pipeline.run()  # Полный парсинг

    # Или пошагово:
    step1 = pipeline.parse_life_situations()
    step2 = pipeline.extract_service_urls(step1)
    step3 = pipeline.parse_services(step2.service_urls)
"""

from dataclasses import dataclass, field
from datetime import datetime
import re
from typing import Any

from app.logging_config import get_logger
from app.rag.models import ParsedDocument, ParserResult  # , SourceType
from app.rag.parsers.life_situations import LifeSituationsParser
from app.rag.parsers.service_pages import ServicePageParser

logger = get_logger(__name__)


@dataclass
class PipelineStep:
    """
    Результат шага пайплайна
    """

    name: str
    status: str  # 'pending', 'running', 'completed', 'failed'
    started_at: datetime | None = None
    completed_at: datetime | None = None
    documents_count: int = 0
    errors_count: int = 0
    details: dict[str, Any] = field(default_factory=dict)

    @property
    def duration_seconds(self) -> float | None:
        """
        Длительность шага в секундах
        """
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None

    def to_dict(self) -> dict[str, Any]:
        """
        Сериализует в словарь
        """
        return {
            'name': self.name,
            'status': self.status,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'duration_seconds': self.duration_seconds,
            'documents_count': self.documents_count,
            'errors_count': self.errors_count,
            'details': self.details,
        }


@dataclass
class LifeSituationsStepResult:
    """
    Результат шага парсинга жизненных ситуаций
    """

    step: PipelineStep
    result: ParserResult
    service_urls: list[str] = field(default_factory=list)


@dataclass
class ServicePagesStepResult:
    """
    Результат шага парсинга страниц услуг
    """

    step: PipelineStep
    result: ParserResult


@dataclass
class PipelineResult:
    """
    Итоговый результат пайплайна парсинга
    """

    steps: list[PipelineStep] = field(default_factory=list)
    life_situations: ParserResult = field(default_factory=ParserResult)
    service_pages: ParserResult = field(default_factory=ParserResult)

    @property
    def total_documents(self) -> int:
        """
        Общее количество документов
        """
        return self.life_situations.success_count + self.service_pages.success_count

    @property
    def total_errors(self) -> int:
        """
        Общее количество ошибок
        """
        return self.life_situations.error_count + self.service_pages.error_count

    @property
    def all_documents(self) -> list[ParsedDocument]:
        """
        Все документы из всех шагов
        """
        return self.life_situations.documents + self.service_pages.documents

    def to_dict(self) -> dict[str, Any]:
        """
        Сериализует в словарь
        """
        return {
            'steps': [s.to_dict() for s in self.steps],
            'total_documents': self.total_documents,
            'total_errors': self.total_errors,
            'life_situations': {
                'documents': self.life_situations.success_count,
                'errors': self.life_situations.error_count,
            },
            'service_pages': {
                'documents': self.service_pages.success_count,
                'errors': self.service_pages.error_count,
            },
        }


class ParsingPipeline:
    """
    Оркестратор парсинга данных для RAG.

    Управляет процессом парсинга:
    1. life_situations → извлекает категории + droppanel секции
    2. Из контента извлекает URL услуг
    3. service_pages → парсит страницы услуг (с дедупликацией URL)

    Attributes:
        life_parser: Парсер жизненных ситуаций
        service_parser: Парсер страниц услуг
    """

    # паттерн для извлечения URL услуг из контента
    SERVICE_URL_PATTERN = re.compile(r'https://gu\.spb\.ru/(\d+)/')

    def __init__(
        self,
        request_delay: float = 0.5,
        request_timeout: int = 30,
    ):
        """
        Args:
            request_delay: Задержка между запросами (секунды)
            request_timeout: Таймаут запроса (секунды)
        """
        self.life_parser = LifeSituationsParser(
            delay=request_delay,
            timeout=request_timeout,
        )
        self.service_parser = ServicePageParser(
            delay=request_delay,
            timeout=request_timeout,
        )
        self._result = PipelineResult()

    def run(
        self,
        parse_services: bool = True,
        max_services: int | None = None,
    ) -> PipelineResult:
        """
        Запускает полный пайплайн парсинга.

        Args:
            parse_services: Парсить ли страницы услуг
            max_services: Максимальное количество услуг для парсинга (None = все)

        Returns:
            PipelineResult с результатами всех шагов
        """
        logger.info('Starting parsing pipeline')
        self._result = PipelineResult()

        # (шаг 1) Парсим жизненные ситуации
        life_step = self.parse_life_situations()
        self._result.steps.append(life_step.step)
        self._result.life_situations = life_step.result

        if not parse_services:
            logger.info('Skipping service pages parsing')
            return self._result

        # (шаг 2) Извлекаем URL услуг
        service_urls = life_step.service_urls
        if max_services:
            service_urls = service_urls[:max_services]

        logger.info(f'Found {len(service_urls)} unique service URLs')

        # (шаг 3) Парсим страницы услуг
        if service_urls:
            service_step = self.parse_services(service_urls)
            self._result.steps.append(service_step.step)
            self._result.service_pages = service_step.result

        logger.info(
            f'Pipeline completed: {self._result.total_documents} documents, '
            f'{self._result.total_errors} errors'
        )

        return self._result

    def parse_life_situations(self) -> LifeSituationsStepResult:
        """
        Шаг 1: Парсит все жизненные ситуации.

        Returns:
            LifeSituationsStepResult с документами и извлечёнными URL услуг
        """
        step = PipelineStep(
            name='parse_life_situations',
            status='running',
            started_at=datetime.now(),
        )

        logger.info('Step 1: Parsing life situations...')

        try:
            result = self.life_parser.parse()

            # извлекаем URL услуг из контента всех документов
            service_urls = self._extract_service_urls(result.documents)

            step.status = 'completed'
            step.completed_at = datetime.now()
            step.documents_count = result.success_count
            step.errors_count = result.error_count
            step.details = {
                'categories_parsed': result.success_count,
                'service_urls_found': len(service_urls),
            }

            logger.info(
                f'Step 1 completed: {result.success_count} categories, '
                f'{len(service_urls)} service URLs extracted'
            )

            return LifeSituationsStepResult(
                step=step,
                result=result,
                service_urls=service_urls,
            )

        except Exception as e:
            step.status = 'failed'
            step.completed_at = datetime.now()
            step.details = {'error': str(e)}
            logger.error(f'Step 1 failed: {e}')

            return LifeSituationsStepResult(
                step=step,
                result=ParserResult(),
                service_urls=[],
            )

    def parse_services(self, urls: list[str]) -> ServicePagesStepResult:
        """
        Шаг 2: Парсит страницы услуг.

        Args:
            urls: Список URL услуг для парсинга

        Returns:
            ServicePagesStepResult с документами услуг
        """
        step = PipelineStep(
            name='parse_service_pages',
            status='running',
            started_at=datetime.now(),
            details={'urls_to_parse': len(urls)},
        )

        logger.info(f'Step 2: Parsing {len(urls)} service pages...')

        try:
            result = self.service_parser.parse(urls=urls)

            step.status = 'completed'
            step.completed_at = datetime.now()
            step.documents_count = result.success_count
            step.errors_count = result.error_count
            step.details.update(
                {
                    'pages_parsed': result.success_count,
                    'pages_failed': result.error_count,
                }
            )

            logger.info(
                f'Step 2 completed: {result.success_count} pages parsed, '
                f'{result.error_count} errors'
            )

            return ServicePagesStepResult(step=step, result=result)

        except Exception as e:
            step.status = 'failed'
            step.completed_at = datetime.now()
            step.details['error'] = str(e)
            logger.error(f'Step 2 failed: {e}')

            return ServicePagesStepResult(step=step, result=ParserResult())

    def _extract_service_urls(
        self,
        documents: list[ParsedDocument],
    ) -> list[str]:
        """
        Извлекает уникальные URL услуг из контента документов.

        Args:
            documents: Список документов жизненных ситуаций

        Returns:
            Список уникальных URL услуг (без дубликатов)
        """
        seen: set[str] = set()
        urls: list[str] = []

        for doc in documents:
            # ищем все URL услуг в контенте
            matches = self.SERVICE_URL_PATTERN.findall(doc.content)

            for service_id in matches:
                url = f'https://gu.spb.ru/{service_id}/'
                if url not in seen:
                    seen.add(url)
                    urls.append(url)

        logger.debug(f'Extracted {len(urls)} unique service URLs from {len(documents)} documents')
        return urls

    @property
    def result(self) -> PipelineResult:
        """
        Текущий результат пайплайна
        """
        return self._result


# CLI для тестирования
if __name__ == '__main__':
    import argparse
    import json

    # Логгинг уже настроен через app.logging_config

    parser = argparse.ArgumentParser(description='Запуск пайплайна парсинга')
    parser.add_argument(
        '--max-services',
        type=int,
        default=None,
        help='Максимальное количество услуг для парсинга',
    )
    parser.add_argument(
        '--skip-services',
        action='store_true',
        help='Пропустить парсинг страниц услуг',
    )
    parser.add_argument(
        '--output',
        type=str,
        default='data/parsed_docs/pipeline_result.json',
        help='Файл для сохранения результата',
    )

    args = parser.parse_args()

    pipeline = ParsingPipeline()
    result = pipeline.run(
        parse_services=not args.skip_services,
        max_services=args.max_services,
    )

    # выводим статистику
    print('\n' + '=' * 50)
    print('PIPELINE RESULT')
    print('=' * 50)

    for step in result.steps:
        duration = f'{step.duration_seconds:.1f}s' if step.duration_seconds else 'N/A'
        print(f'\n{step.name}:')
        print(f'  Status: {step.status}')
        print(f'  Duration: {duration}')
        print(f'  Documents: {step.documents_count}')
        print(f'  Errors: {step.errors_count}')
        if step.details:
            for k, v in step.details.items():
                print(f'  {k}: {v}')

    print('\nTOTAL:')
    print(f'  Documents: {result.total_documents}')
    print(f'  Errors: {result.total_errors}')

    # сохраняем результат
    from pathlib import Path

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # сохраняем метаданные
    output_path.write_text(
        json.dumps(result.to_dict(), ensure_ascii=False, indent=2),
        encoding='utf-8',
    )
    print(f'\nResult saved to: {output_path}')

    # сохраняем документы
    docs_path = output_path.parent / 'all_documents.json'
    docs_data = [doc.to_dict() for doc in result.all_documents]
    docs_path.write_text(
        json.dumps(docs_data, ensure_ascii=False, indent=2),
        encoding='utf-8',
    )
    print(f'Documents saved to: {docs_path}')
