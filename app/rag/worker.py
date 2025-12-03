"""
- worker для периодического парсинга и индексации

Использование:
    python -m app.rag.worker parse        # парсинг всех источников
    python -m app.rag.worker parse --source life_situations
    python -m app.rag.worker index        # индексация в векторную БД
    python -m app.rag.worker full         # парсинг + индексация
    python -m app.rag.worker schedule     # запуск по расписанию

TODO: для production рекомендуется использовать:
- Celery для распределённых задач
- cron / systemd timer для простого расписания
- APScheduler для Python-native планировщика
"""

import argparse
from datetime import datetime
import json
from pathlib import Path

from app.logging_config import get_logger
from app.rag.config import get_rag_config
from app.rag.models import ParserResult, SourceType
from app.rag.parsers import LifeSituationsParser

logger = get_logger(__name__)


def parse_source(source: str, incremental: bool = False) -> ParserResult:
    """
    Парсит указанный источник данных.

    Args:
        source: Тип источника (life_situations, knowledge_base, etc.)
        incremental: Парсить только изменённые документы

    Returns:
        ParserResult с документами
    """
    config = get_rag_config()

    if source == 'life_situations':
        parser = LifeSituationsParser(
            delay=config.parser.delay,
            timeout=config.parser.timeout,
            max_depth=config.parser.max_depth,
        )
    # TODO: добавить другие парсеры
    # elif source == 'knowledge_base':
    #     parser = KnowledgeBaseParser(...)
    else:
        raise ValueError(f'Unknown source: {source}')

    logger.info(f'Starting parsing: {source} (incremental={incremental})')
    result = parser.parse(incremental=incremental)
    logger.info(f'Parsing complete: {result.success_count} docs, {result.error_count} errors')

    return result


def save_parsed_docs(result: ParserResult, source: str) -> Path:
    """
    Сохраняет прошедшие парсинг документы в JSON.

    Args:
        result: Результат парсинга
        source: Тип источника

    Returns:
        Путь к сохранённому файлу
    """
    config = get_rag_config()
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f'{source}_{timestamp}.json'
    filepath = config.index.parsed_docs_dir / filename

    data = {
        'source': source,
        'parsed_at': datetime.now().isoformat(),
        'stats': result.stats,
        'documents': [doc.to_dict() for doc in result.documents],
        'errors': result.errors,
    }

    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    logger.info(f'Saved {len(result.documents)} documents to {filepath}')
    return filepath


def parse_all_sources(incremental: bool = False) -> dict[str, ParserResult]:
    """
    Парсит все доступные источники.

    Returns:
        Словарь {source: ParserResult}
    """
    sources = ['life_situations']  # TODO: добавить другие
    results = {}

    for source in sources:
        try:
            result = parse_source(source, incremental)
            save_parsed_docs(result, source)
            results[source] = result
        except Exception as e:
            logger.error(f'Error parsing {source}: {e}')
            results[source] = ParserResult(errors=[{'source': source, 'error': str(e)}])

    return results


def index_documents(docs_path: Path | None = None) -> int:
    """
    Индексирует документы в векторную БД.

    Args:
        docs_path: Путь к JSON с документами (или None для последнего)

    Returns:
        Количество проиндексированных документов
    """
    # TODO: реализовать индексацию
    # 1. Загрузить документы из JSON
    # 2. Разбить на чанки
    # 3. Создать embeddings
    # 4. Добавить в ChromaDB

    logger.info('Indexing not implemented yet')
    return 0


def run_full_pipeline(incremental: bool = False) -> dict:
    """
    Запускает полный пайплайн: парсинг + индексация.

    Returns:
        Статистика выполнения
    """
    stats = {
        'start_time': datetime.now().isoformat(),
        'parse_results': {},
        'index_count': 0,
    }

    # 1) парсинг
    parse_results = parse_all_sources(incremental)
    stats['parse_results'] = {
        source: {
            'documents': result.success_count,
            'errors': result.error_count,
        }
        for source, result in parse_results.items()
    }

    # 2) индексация
    # TODO: index_documents(...)

    stats['end_time'] = datetime.now().isoformat()
    return stats


def setup_schedule():
    """
    Настраивает периодический запуск.

    Использует APScheduler для простоты.
    TODO: для production лучше использовать Celery + Redis
    """
    try:
        from apscheduler.schedulers.blocking import BlockingScheduler
        from apscheduler.triggers.cron import CronTrigger
    except ImportError:
        logger.error('APScheduler not installed. Run: pip install apscheduler')
        return

    scheduler = BlockingScheduler()

    # парсинг каждую ночь в 3:00
    scheduler.add_job(
        lambda: run_full_pipeline(incremental=True),
        trigger=CronTrigger(hour=3, minute=0),
        id='nightly_parse',
        name='Nightly parsing and indexing',
    )

    # полный парсинг раз в неделю (воскресенье 4:00)
    scheduler.add_job(
        lambda: run_full_pipeline(incremental=False),
        trigger=CronTrigger(day_of_week='sun', hour=4, minute=0),
        id='weekly_full_parse',
        name='Weekly full parsing',
    )

    logger.info('Scheduler started. Press Ctrl+C to stop.')
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info('Scheduler stopped.')


def main():
    """
    CLI для worker'а
    """
    parser = argparse.ArgumentParser(description='RAG parsing and indexing worker')

    subparsers = parser.add_subparsers(dest='command', help='Command to run')

    # parse command
    parse_parser = subparsers.add_parser('parse', help='Parse data sources')
    parse_parser.add_argument(
        '--source',
        type=str,
        default='all',
        help='Source to parse (life_situations, knowledge_base, all)',
    )
    parse_parser.add_argument(
        '--incremental',
        action='store_true',
        help='Parse only changed documents',
    )

    # index command
    index_parser = subparsers.add_parser('index', help='Index documents')
    index_parser.add_argument(
        '--docs-path',
        type=Path,
        help='Path to parsed documents JSON',
    )

    # full command
    full_parser = subparsers.add_parser('full', help='Run full pipeline')
    full_parser.add_argument(
        '--incremental',
        action='store_true',
        help='Incremental update',
    )

    # schedule command
    subparsers.add_parser('schedule', help='Run scheduled tasks')

    args = parser.parse_args()

    if args.command == 'parse':
        if args.source == 'all':
            parse_all_sources(args.incremental)
        else:
            result = parse_source(args.source, args.incremental)
            save_parsed_docs(result, args.source)

    elif args.command == 'index':
        index_documents(args.docs_path)

    elif args.command == 'full':
        stats = run_full_pipeline(args.incremental)
        print(json.dumps(stats, indent=2, ensure_ascii=False))

    elif args.command == 'schedule':
        setup_schedule()

    else:
        parser.print_help()


if __name__ == '__main__':
    main()
