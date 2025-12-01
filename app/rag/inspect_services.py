"""
Скрипт для инспекции парсинга страниц услуг.

Извлекает ссылки на услуги из life_situations и парсит их.
"""

import argparse
from datetime import datetime
import json
import logging
from pathlib import Path

from app.rag.parsers.life_situations import LifeSituationsParser
from app.rag.parsers.service_pages import ServicePageParser

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger(__name__)


def extract_service_urls_from_content(content: str) -> list[str]:
    """
    Извлекает URL услуг из контента документа
    """
    import re

    # паттерн для URL услуг: https://gu.spb.ru/123456/
    pattern = re.compile(r'https://gu\.spb\.ru/(\d+)/')
    matches = pattern.findall(content)

    # убираем дубликаты, сохраняя порядок
    seen = set()
    urls = []
    for service_id in matches:
        url = f'https://gu.spb.ru/{service_id}/'
        if url not in seen:
            seen.add(url)
            urls.append(url)

    return urls


def main():
    parser = argparse.ArgumentParser(description='Инспекция парсинга страниц услуг')
    parser.add_argument(
        '--life-situation',
        type=str,
        help='URL конкретной жизненной ситуации для извлечения услуг',
    )
    parser.add_argument(
        '--services',
        type=int,
        default=3,
        help='Количество услуг для парсинга (default: 3)',
    )
    parser.add_argument(
        '--output',
        type=str,
        default='data/parsed_docs/services_inspection',
        help='Директория для сохранения результатов',
    )

    args = parser.parse_args()

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    logger.info(f'Output directory: {output_dir}')

    # 1. парсим жизненную ситуацию для получения списка услуг
    if args.life_situation:
        life_url = args.life_situation
    else:
        life_url = 'https://gu.spb.ru/mfc/life_situations/190057/'  # Рождение ребёнка

    logger.info(f'Parsing life situation: {life_url}')

    life_parser = LifeSituationsParser()
    life_doc = life_parser.parse_page(life_url)

    if not life_doc:
        logger.error('Failed to parse life situation')
        return

    logger.info(f'Life situation: {life_doc.title}')
    logger.info(f'Content length: {len(life_doc.content)} chars')

    # 2. извлекаем URL услуг из контента
    service_urls = extract_service_urls_from_content(life_doc.content)
    logger.info(f'Found {len(service_urls)} service URLs')

    for i, url in enumerate(service_urls[:10], 1):
        logger.info(f'  {i}. {url}')

    # 3. парсим первые N услуг
    urls_to_parse = service_urls[: args.services]
    logger.info(f'\nParsing {len(urls_to_parse)} services...')

    service_parser = ServicePageParser()
    result = service_parser.parse(urls=urls_to_parse)

    # 4. сохраняем результаты
    logger.info('\nSaving results...')

    # сохраняем каждый документ
    for doc in result.documents:
        filename = f'{doc.doc_id}.md'
        filepath = output_dir / filename

        md_content = f"""# {doc.title}

**URL:** {doc.url}
**Doc ID:** {doc.doc_id}
**Content Length:** {len(doc.content)} chars

---

## Content

{doc.content}

---

## Metadata

```json
{json.dumps(doc.metadata, ensure_ascii=False, indent=2)}
```
"""
        filepath.write_text(md_content, encoding='utf-8')
        logger.info(f'  Saved: {filename} ({len(doc.content)} chars)')

    # Сохраняем индекс
    index_content = f"""# Инспекция парсинга услуг

**Дата:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
**Источник:** {life_doc.title}
**URL источника:** {life_url}

## Найденные услуги

Всего найдено: {len(service_urls)} URLs

| # | URL | Статус |
|---|-----|--------|
"""
    for i, url in enumerate(service_urls, 1):
        if i <= args.services:
            # Найдём соответствующий документ
            doc = next((d for d in result.documents if d.url == url), None)
            if doc:
                status = f'✅ {len(doc.content)} chars'
                name = f'[{doc.title[:40]}...]({doc.doc_id}.md)'
            else:
                status = '❌ failed'
                name = url
        else:
            status = '⏭️ skipped'
            name = url

        index_content += f'| {i} | {name} | {status} |\n'

    index_content += f"""

## Статистика

- **Успешно распарсено:** {result.success_count}
- **Ошибок:** {result.error_count}
- **Общий объём контента:** {sum(len(d.content) for d in result.documents)} chars
"""

    index_path = output_dir / 'INDEX.md'
    index_path.write_text(index_content, encoding='utf-8')
    logger.info(f'Index saved: {index_path}')

    # Сохраняем summary.json
    summary = {
        'source': {
            'title': life_doc.title,
            'url': life_url,
        },
        'service_urls_found': len(service_urls),
        'services_parsed': result.success_count,
        'services_failed': result.error_count,
        'total_content_chars': sum(len(d.content) for d in result.documents),
        'documents': [
            {
                'doc_id': d.doc_id,
                'title': d.title,
                'url': d.url,
                'content_length': len(d.content),
            }
            for d in result.documents
        ],
    }
    summary_path = output_dir / 'summary.json'
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    logger.info(f'Summary saved: {summary_path}')

    logger.info(f'\nDone! Check {output_dir}')


if __name__ == '__main__':
    main()
