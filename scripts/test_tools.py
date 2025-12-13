"""
Tool Test Runner - автоматические тесты tools (happy path).

Использует Typer для CLI. Запускает предопределённые тест-кейсы
с проверкой ожидаемых строк в ответе.

Usage:
    python scripts/test_tools.py                    # все тесты
    python scripts/test_tools.py --category pets   # только pets
    python scripts/test_tools.py --verbose         # с выводом результатов
    python scripts/test_tools.py --list            # показать категории
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
import sys

from rich.console import Console
from rich.table import Table
import typer

# путь к src langgraph_app
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / 'packages' / 'langgraph-app' / 'src'))

app = typer.Typer(
    name='test-tools',
    help='🧪 Автоматические тесты tools агента (happy path)',
    add_completion=False,
)

console = Console()


class Category(str, Enum):
    """
    Категории тестов
    """

    ALL = 'all'
    ADDRESS = 'address'
    PETS = 'pets'
    EVENTS = 'events'
    RECYCLING = 'recycling'
    MFC = 'mfc'
    POLYCLINICS = 'polyclinics'
    SCHOOLS = 'schools'
    KINDERGARTENS = 'kindergartens'
    SPORT = 'sport'
    TOURISM = 'tourism'


@dataclass
class TestCase:
    """
    Один тест-кейс
    """

    name: str
    tool_name: str
    args: dict
    expect_contains: list[str]
    expect_not_contains: list[str] | None = None


@dataclass
class TestResult:
    """
    Результат теста
    """

    test: TestCase
    passed: bool
    output: str
    error: str | None = None
    duration: float = 0


def get_test_cases() -> dict[str, list[TestCase]]:
    """
    Определение всех тест-кейсов
    """
    return {
        'address': [
            TestCase(
                name='resolve_location - метро Чернышевская',
                tool_name='resolve_location',
                args={'query': 'метро Чернышевская'},
                expect_contains=['Чернышевская'],
            ),
            TestCase(
                name='resolve_location - точный адрес',
                tool_name='resolve_location',
                args={'query': 'Невский проспект 10'},
                expect_contains=['Невский'],
            ),
            TestCase(
                name='search_address - Большевиков 68',
                tool_name='search_address',
                args={'query': 'Большевиков 68'},
                expect_contains=['Большевиков'],
            ),
        ],
        'pets': [
            TestCase(
                name='get_pet_parks_near - метро Чернышевская',
                tool_name='get_pet_parks_near',
                args={'location': 'метро Чернышевская', 'radius_km': 5.0},
                expect_contains=['Поиск от'],
            ),
            TestCase(
                name='get_vet_clinics_near - Невский проспект',
                tool_name='get_vet_clinics_near',
                args={'location': 'Невский проспект 100', 'radius_km': 10.0},
                expect_contains=['Поиск от'],
            ),
            TestCase(
                name='get_pet_shelters_near - метро Купчино',
                tool_name='get_pet_shelters_near',
                args={'location': 'метро Купчино', 'radius_km': 15.0},
                expect_contains=['Поиск от'],
            ),
        ],
        'events': [
            TestCase(
                name='get_city_events_near - метро Невский',
                tool_name='get_city_events_near',
                args={'location': 'метро Невский проспект', 'radius_km': 10.0},
                expect_contains=['Поиск от'],
            ),
            TestCase(
                name='get_sport_events - Невский район',
                tool_name='get_sport_events',
                args={'district': 'Невский', 'count': 5},
                expect_contains=[],  # может быть пусто
            ),
        ],
        'recycling': [
            TestCase(
                name='get_recycling_points_near - метро',
                tool_name='get_recycling_points_near',
                args={'location': 'метро Площадь Восстания', 'count': 5},
                expect_contains=['Поиск от'],
            ),
        ],
        'mfc': [
            TestCase(
                name='find_nearest_mfc - Невский проспект',
                tool_name='find_nearest_mfc',
                args={'address': 'Невский проспект 100'},
                expect_contains=['МФЦ'],
            ),
            TestCase(
                name='get_mfc_by_district - Невский',
                tool_name='get_mfc_by_district',
                args={'district': 'Невский'},
                expect_contains=['МФЦ'],
            ),
        ],
        'polyclinics': [
            TestCase(
                name='get_polyclinics_by_address - Большевиков',
                tool_name='get_polyclinics_by_address',
                args={'address': 'Большевиков 68'},
                expect_contains=[],  # проверяем что нет ошибки
            ),
        ],
        'schools': [
            TestCase(
                name='get_schools_by_address - Невский',
                tool_name='get_schools_by_address',
                args={'address': 'Невский проспект 100'},
                expect_contains=[],
            ),
            TestCase(
                name='get_schools_in_district - Невский',
                tool_name='get_schools_in_district',
                args={'district': 'Невский'},
                expect_contains=[],
            ),
        ],
        'kindergartens': [
            TestCase(
                name='get_kindergartens_by_district - Невский',
                tool_name='get_kindergartens_by_district',
                args={'district': 'Невский'},
                expect_contains=[],
            ),
        ],
        'sport': [
            TestCase(
                name='get_sportgrounds - Невский',
                tool_name='get_sportgrounds',
                args={'district': 'Невский'},
                expect_contains=[],
            ),
        ],
        'tourism': [
            TestCase(
                name='get_beautiful_places - Центральный',
                tool_name='get_beautiful_places',
                args={'district': 'Центральный'},
                expect_contains=[],
            ),
        ],
    }


def get_tool(tool_name: str):
    """
    Динамически загрузить tool по имени
    """
    from langgraph_app.tools import city_tools_v3

    return getattr(city_tools_v3, tool_name)


async def run_test(test: TestCase) -> TestResult:
    """
    Запустить один тест
    """
    start = datetime.now()

    try:
        tool = get_tool(test.tool_name)
        result = await tool.ainvoke(test.args)
        duration = (datetime.now() - start).total_seconds()

        # проверяем ожидаемые строки
        result_lower = result.lower()
        missing = [s for s in test.expect_contains if s.lower() not in result_lower]

        # проверяем что НЕ должно быть
        forbidden = []
        if test.expect_not_contains:
            forbidden = [s for s in test.expect_not_contains if s.lower() in result_lower]

        if missing:
            return TestResult(
                test=test,
                passed=False,
                output=result,
                error=f'Missing: {missing}',
                duration=duration,
            )

        if forbidden:
            return TestResult(
                test=test,
                passed=False,
                output=result,
                error=f'Found forbidden: {forbidden}',
                duration=duration,
            )

        return TestResult(test=test, passed=True, output=result, duration=duration)

    except Exception as e:
        duration = (datetime.now() - start).total_seconds()
        return TestResult(
            test=test,
            passed=False,
            output='',
            error=str(e),
            duration=duration,
        )


async def run_category(category: str, test_cases: dict, verbose: bool = False) -> list[TestResult]:
    """
    Запустить все тесты категории
    """
    tests = test_cases.get(category, [])
    results = []

    console.print(f'\n[bold cyan]{"=" * 60}[/]')
    console.print(f'[bold cyan]  Category: {category.upper()}[/]')
    console.print(f'[bold cyan]{"=" * 60}[/]')

    for test in tests:
        result = await run_test(test)
        results.append(result)

        status = '[green]✅ PASS[/]' if result.passed else '[red]❌ FAIL[/]'
        console.print(f'  {status} {test.name} [dim]({result.duration:.2f}s)[/]')

        if not result.passed and result.error:
            console.print(f'       [red]Error: {result.error}[/]')

        if verbose and result.output:
            preview = result.output[:300].replace('\n', ' ')
            console.print(f'       [dim]Output: {preview}...[/]')

    return results


def print_summary(results: list[TestResult]):
    """
    Вывести итоговую таблицу
    """
    passed = sum(1 for r in results if r.passed)
    failed = sum(1 for r in results if not r.passed)
    total = len(results)

    console.print(f'\n[bold]{"=" * 60}[/]')
    console.print('[bold]  SUMMARY[/]')
    console.print(f'[bold]{"=" * 60}[/]')

    table = Table(show_header=False, box=None)
    table.add_column('Metric', style='bold')
    table.add_column('Value')

    table.add_row('Total', str(total))
    table.add_row('Passed', f'[green]{passed} ✅[/]')
    table.add_row('Failed', f'[red]{failed} ❌[/]' if failed else f'[green]{failed}[/]')

    console.print(table)
    console.print(f'[bold]{"=" * 60}[/]')

    # список провалившихся тестов
    if failed > 0:
        console.print('\n[bold red]Failed tests:[/]')
        for r in results:
            if not r.passed:
                console.print(f'  - {r.test.name}: {r.error}')


@app.command()
def run(
    category: Category = typer.Option(
        Category.ALL,
        '--category',
        '-c',
        help='Категория тестов для запуска',
    ),
    verbose: bool = typer.Option(
        False,
        '--verbose',
        '-v',
        help='Показывать вывод каждого теста',
    ),
    list_categories: bool = typer.Option(
        False,
        '--list',
        '-l',
        help='Показать доступные категории',
    ),
):
    """
    Запустить тесты tools (happy path)
    """

    if list_categories:
        console.print('[bold]Доступные категории:[/]')
        for cat in Category:
            if cat != Category.ALL:
                console.print(f'  - {cat.value}')
        return

    console.print("[bold cyan]{'=' * 60}[/]")
    console.print('[bold cyan]  TOOLS TEST SUITE - Happy Path[/]')
    console.print("[bold cyan]{'=' * 60}[/]")

    test_cases = get_test_cases()

    categories = list(test_cases.keys()) if category == Category.ALL else [category.value]

    async def run_all():
        all_results = []
        for cat in categories:
            if cat in test_cases:
                results = await run_category(cat, test_cases, verbose)
                all_results.extend(results)
        return all_results

    results = asyncio.run(run_all())
    print_summary(results)

    # exit code
    failed = sum(1 for r in results if not r.passed)
    raise typer.Exit(code=0 if failed == 0 else 1)


@app.command('smoke')
def smoke_test(
    verbose: bool = typer.Option(
        False,
        '--verbose',
        '-v',
        help='Показывать полный вывод каждого теста',
    ),
):
    """
    Быстрый smoke-тест основных tools (по одному из каждой категории)
    """

    console.print('[bold yellow]🔥 SMOKE TEST[/]')

    smoke_cases = [
        TestCase(
            'resolve_location', 'resolve_location', {'query': 'метро Невский проспект'}, ['Невский']
        ),
        TestCase(
            'pet_parks_near',
            'get_pet_parks_near',
            {'location': 'метро Чернышевская', 'radius_km': 5.0},
            ['Поиск от'],
        ),
        TestCase('mfc_nearest', 'find_nearest_mfc', {'address': 'Невский проспект 100'}, ['МФЦ']),
        TestCase('districts', 'get_districts_list', {}, ['район']),
    ]

    async def run_smoke():
        results = []
        for test in smoke_cases:
            result = await run_test(test)
            results.append(result)
            status = '[green]✅[/]' if result.passed else '[red]❌[/]'
            console.print(f'  {status} {test.name} [dim]({result.duration:.2f}s)[/]')
            if not result.passed:
                console.print(f'       [red]{result.error}[/]')
            if verbose and result.output:
                console.print(f'[dim]{"─" * 60}[/]')
                # показываем первые 500 символов или весь вывод
                preview = result.output[:500] if len(result.output) > 500 else result.output
                console.print(f'[cyan]{preview}[/]')
                if len(result.output) > 500:
                    console.print(f'[dim]... (ещё {len(result.output) - 500} символов)[/]')
                console.print(f'[dim]{"─" * 60}[/]')
        return results

    results = asyncio.run(run_smoke())
    passed = sum(1 for r in results if r.passed)
    total = len(results)

    console.print()
    if passed == total:
        console.print(f'[bold green]✅ Smoke test passed: {passed}/{total}[/]')
        raise typer.Exit(code=0)

    console.print(f'[bold red]❌ Smoke test failed: {passed}/{total}[/]')
    raise typer.Exit(code=1)


if __name__ == '__main__':
    app()
