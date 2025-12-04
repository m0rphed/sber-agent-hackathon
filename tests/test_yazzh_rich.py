"""
Интерактивные тесты для YAZZH API с красивым выводом через rich.

Запуск всех тестов:
    python -m tests.test_yazzh_rich all

Запуск конкретных тестов:
    python -m tests.test_yazzh_rich demo --dou
    python -m tests.test_yazzh_rich demo --schools --polyclinics

Fuzz-тестирование:
    python -m tests.test_yazzh_rich fuzz schools
    python -m tests.test_yazzh_rich fuzz all --raw
"""

import asyncio
from enum import Enum
import json
from typing import Annotated

from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
import typer

app = typer.Typer(
    name='yazzh-test',
    help='🧪 Интерактивные тесты YAZZH API с красивым выводом',
    rich_markup_mode='rich',
    no_args_is_help=True,
)
console = Console()


# ============================================================================
# Вспомогательные функции
# ============================================================================


def print_input(name: str, **kwargs) -> None:
    """
    Печатает входные параметры теста
    """
    table = Table(title=f'📥 ВХОД: {name}', show_header=True, header_style='bold cyan')
    table.add_column('Параметр', style='dim')
    table.add_column('Значение', style='green')

    for key, value in kwargs.items():
        table.add_row(key, repr(value))

    console.print(table)
    console.print()


def print_output(name: str, result, raw: bool = False) -> None:
    """
    Печатает результат теста
    """
    if raw:
        # Сырой JSON вывод
        if hasattr(result, 'model_dump'):
            data = result.model_dump(exclude_none=True)
        elif isinstance(result, list) and result and hasattr(result[0], 'model_dump'):
            data = [r.model_dump(exclude_none=True) for r in result]
        else:
            data = result

        json_str = json.dumps(data, ensure_ascii=False, indent=2, default=str)
        syntax = Syntax(json_str, 'json', theme='monokai', line_numbers=True)
        console.print(Panel(syntax, title=f'📤 ВЫХОД: {name}', border_style='green'))
    else:
        # Красивый форматированный вывод
        if hasattr(result, 'format_for_human'):
            text = result.format_for_human()
        elif isinstance(result, list):
            if result and hasattr(result[0], 'format_for_human'):
                text = '\n\n'.join(r.format_for_human() for r in result)
            else:
                text = json.dumps(result, ensure_ascii=False, indent=2, default=str)
        elif isinstance(result, str):
            text = result
        else:
            text = (
                json.dumps(result, ensure_ascii=False, indent=2, default=str) if result else 'None'
            )

        console.print(Panel(text, title=f'📤 ВЫХОД: {name}', border_style='green'))

    console.print()


def print_error(name: str, error: Exception) -> None:
    """
    Печатает ошибку
    """
    console.print(
        Panel(
            f'[bold red]❌ Ошибка:[/bold red] {error}', title=f'ОШИБКА: {name}', border_style='red'
        )
    )
    console.print()


def print_separator(title: str) -> None:
    """
    Печатает разделитель между тестами
    """
    console.print()
    console.rule(f'[bold blue]{title}[/bold blue]')
    console.print()


# ============================================================================
# Тестовые данные для fuzz-тестирования
# ============================================================================

# Добавляйте сюда адреса для тестирования разных функций
FUZZ_ADDRESSES = {
    # Адреса для поиска зданий (проверяем building_id, coords)
    'buildings': [
        'Невский проспект 1',
        'Невский проспект 10',
        'Большевиков 68',
        'Лиговский проспект 50',
        'Московский проспект 100',
        '4-я линия В.О., дом 5',
        'Садовая 55',
        'Большая Морская 1',
    ],
    'schools': [
        'Невский проспект 10',
        '4ая линия В.О. 5',
        'Большая Морская 1',
        'Садовая 50',
        'Большевиков 68',
    ],
    'polyclinics': [
        'Невский проспект 10',
        'Московский проспект 100',
        'Лиговский проспект 50',
        'Большевиков 68',
    ],
    'mfc': [
        'Невский проспект 10',
        'Садовая 55',
        'Большевиков 68',
        'Московский проспект 100',
    ],
    'management_company': [
        'Большевиков 68',
        'Московский проспект 100',
        'Лиговский проспект 50',
    ],
    'kindergartens': [
        # (район, возраст_лет, возраст_месяцев)
        ('Невский', 3, 0),
        ('Центральный', 1, 6),
        ('Василеостровский', 2, 0),
        ('Приморский', 4, 0),
    ],
    # Адреса для полного интеграционного теста (адрес → все сервисы)
    'integration': [
        'Невский проспект 10',
        'Большевиков 68',
        'Московский проспект 100',
    ],
}

# Невалидный адрес для проверки обработки ошибок
INVALID_ADDRESS = 'АбраКадабра 999999'


# ============================================================================
# Тесты поиска зданий (Building Search) — КРИТИЧЕСКИ ВАЖНО!
# Это база для всех остальных API (school, polyclinic, mfc используют building_id)
# ============================================================================


async def demo_building_search(raw: bool = False) -> None:
    """
    Тесты поиска зданий — проверяем что building_id приходит корректно
    """
    from app.api.yazzh_new import YazzhAsyncClient, AddressNotFoundError

    print_separator('🏠 ТЕСТЫ ПОИСКА ЗДАНИЙ (Building Search)')

    async with YazzhAsyncClient() as client:
        # Тест 1: Поиск по точному адресу
        address = 'Невский проспект 10'
        print_input('search_building', query=address)

        try:
            results = await client.search_building(address)
            print_output('search_building', results, raw=raw)

            if results:
                console.print(f'[green]✅ Найдено зданий: {len(results)}[/green]')
                first = results[0]
                # Проверяем критически важные поля
                console.print(f'[cyan]   📋 id: {first.id}[/cyan]')
                console.print(f'[cyan]   🏠 building_id: {first.building_id}[/cyan]')
                console.print(f'[cyan]   📍 full_address: {first.full_address}[/cyan]')
                console.print(f'[cyan]   🌐 coords: {first.coords}[/cyan]')

                if not first.building_id:
                    console.print('[red]❌ ПРОБЛЕМА: building_id пустой![/red]')
                if not first.coords:
                    console.print('[yellow]⚠️ Координаты отсутствуют[/yellow]')
            else:
                console.print('[red]❌ Результатов нет![/red]')
        except Exception as e:
            print_error('search_building', e)

        # Тест 2: search_building_first
        address = 'Большевиков 68'
        print_input('search_building_first', query=address)

        try:
            result = await client.search_building_first(address)
            print_output('search_building_first', result, raw=raw)

            console.print(f'[cyan]   📋 id: {result.id}[/cyan]')
            console.print(f'[cyan]   🏠 building_id: {result.building_id}[/cyan]')
            console.print(f'[cyan]   📍 full_address: {result.full_address}[/cyan]')
            console.print(f'[cyan]   🌐 coords: {result.coords}[/cyan]')

            if result.building_id:
                console.print('[green]✅ building_id получен[/green]')
            else:
                console.print('[red]❌ ПРОБЛЕМА: building_id пустой![/red]')
        except Exception as e:
            print_error('search_building_first', e)

        # Тест 3: Ограничение count
        print_input('search_building (count=3)', query='Невский', count=3)

        try:
            results = await client.search_building('Невский', count=3)
            console.print(f'[cyan]Получено результатов: {len(results)} (ожидали <= 3)[/cyan]')
            if len(results) <= 3:
                console.print('[green]✅ Ограничение count работает[/green]')
            else:
                console.print('[yellow]⚠️ Получили больше чем запрашивали[/yellow]')
        except Exception as e:
            print_error('search_building', e)

        # Тест 4: Невалидный адрес (должен выбросить AddressNotFoundError)
        print_input('search_building (invalid)', query=INVALID_ADDRESS)

        try:
            results = await client.search_building(INVALID_ADDRESS)
            console.print(f'[red]❌ ПРОБЛЕМА: Ожидали ошибку, но получили {len(results)} результатов[/red]')
        except AddressNotFoundError as e:
            console.print(f'[green]✅ Корректно выбросил AddressNotFoundError: {e}[/green]')
        except Exception as e:
            console.print(f'[yellow]⚠️ Другая ошибка: {type(e).__name__}: {e}[/yellow]')


# ============================================================================
# Тесты районов (Districts)
# ============================================================================


async def demo_districts(raw: bool = False) -> None:
    """
    Тесты получения списка районов СПб
    """
    from app.api.yazzh_new import YazzhAsyncClient

    print_separator('🗺️ ТЕСТЫ РАЙОНОВ (Districts)')

    async with YazzhAsyncClient() as client:
        print_input('get_districts')

        try:
            districts = await client.get_districts()
            print_output('get_districts', districts, raw=raw)

            if districts:
                console.print(f'[green]✅ Найдено районов: {len(districts)}[/green]')
                # В СПб 18 районов
                if len(districts) >= 18:
                    console.print('[green]✅ Количество районов корректно (>= 18)[/green]')
                else:
                    console.print(f'[yellow]⚠️ Ожидали >= 18 районов, получили {len(districts)}[/yellow]')

                # Проверяем известные районы
                names = [d.name for d in districts]
                known = ['Невский', 'Центральный', 'Василеостровский', 'Приморский']
                for name in known:
                    if any(name in n for n in names):
                        console.print(f'[green]   ✓ {name} найден[/green]')
                    else:
                        console.print(f'[red]   ✗ {name} НЕ найден![/red]')
        except Exception as e:
            print_error('get_districts', e)


# ============================================================================
# Тесты УК (Управляющих компаний)
# ============================================================================


async def demo_management_company(raw: bool = False) -> None:
    """
    Тесты получения информации об управляющей компании
    """
    from app.api.yazzh_new import YazzhAsyncClient

    print_separator('🏢 ТЕСТЫ УК (Управляющие компании)')

    async with YazzhAsyncClient() as client:
        # УК обычно есть для жилых домов
        address = 'Большевиков 68'
        print_input('get_management_company_by_address', address=address)

        try:
            uk = await client.get_management_company_by_address(address)
            print_output('get_management_company_by_address', uk, raw=raw)

            if uk:
                console.print('[green]✅ УК найдена[/green]')
                if uk.name:
                    console.print(f'[cyan]   📋 Название: {uk.name}[/cyan]')
                if uk.address:
                    console.print(f'[cyan]   📍 Адрес: {uk.address}[/cyan]')
            else:
                console.print('[yellow]⚠️ УК не найдена (возможно, нежилое здание)[/yellow]')
        except Exception as e:
            print_error('get_management_company_by_address', e)


# ============================================================================
# Интеграционный тест: Адрес → Building → Все сервисы
# ============================================================================


async def demo_integration(raw: bool = False) -> None:
    """
    Полный интеграционный тест: адрес → building_id → все сервисы
    Проверяем что цепочка работает
    """
    from app.api.yazzh_new import YazzhAsyncClient

    print_separator('🔗 ИНТЕГРАЦИОННЫЙ ТЕСТ (Адрес → Все сервисы)')

    async with YazzhAsyncClient() as client:
        address = 'Московский проспект 100'
        console.print(f'[bold cyan]📍 Тестируем адрес: {address}[/bold cyan]\n')

        # Шаг 1: Поиск здания
        print_input('Шаг 1: search_building_first', query=address)

        try:
            building = await client.search_building_first(address)
            console.print(f'[green]✅ Здание найдено[/green]')
            console.print(f'[cyan]   id: {building.id}[/cyan]')
            console.print(f'[cyan]   building_id: {building.building_id}[/cyan]')
            console.print(f'[cyan]   address: {building.full_address}[/cyan]')

            if not building.building_id:
                console.print('[red]❌ КРИТИЧЕСКАЯ ПРОБЛЕМА: building_id отсутствует![/red]')
                console.print('[red]   Остальные API не смогут работать![/red]')
                return

            bid = building.building_id

            # Шаг 2: МФЦ
            console.print()
            print_input('Шаг 2: get_mfc_by_building', building_id=bid)

            mfc = await client.get_mfc_by_building(bid)
            if mfc:
                console.print(f'[green]✅ МФЦ найден: {mfc.name}[/green]')
            else:
                console.print('[yellow]⚠️ МФЦ не привязан к этому адресу[/yellow]')

            # Шаг 3: Поликлиники
            console.print()
            print_input('Шаг 3: get_polyclinics_by_building', building_id=bid)

            clinics = await client.get_polyclinics_by_building(bid)
            if clinics:
                console.print(f'[green]✅ Найдено поликлиник: {len(clinics)}[/green]')
                for c in clinics[:2]:  # Показываем первые 2
                    console.print(f'[cyan]   • {c.name or c.full_name}[/cyan]')
            else:
                console.print('[yellow]⚠️ Поликлиники не привязаны[/yellow]')

            # Шаг 4: Школы
            console.print()
            print_input('Шаг 4: get_linked_schools', building_id=bid)

            schools = await client.get_linked_schools(bid)
            if schools:
                console.print(f'[green]✅ Найдено школ: {len(schools)}[/green]')
                for s in schools[:2]:
                    console.print(f'[cyan]   • {s.name or s.full_name}[/cyan]')
            else:
                console.print('[yellow]⚠️ Школы не привязаны[/yellow]')

            # Шаг 5: Районная информация
            console.print()
            print_input('Шаг 5: get_district_info_by_building', building_id=bid)

            try:
                info = await client.get_district_info_by_building(bid)
                if info:
                    console.print(f'[green]✅ Районная информация получена (тип: {type(info).__name__})[/green]')
                else:
                    console.print('[yellow]⚠️ Районная информация пуста[/yellow]')
            except Exception as e:
                console.print(f'[yellow]⚠️ Ошибка районной информации: {e}[/yellow]')

            # Итог
            console.print()
            found = sum([1 if mfc else 0, len(clinics) if clinics else 0, len(schools) if schools else 0])
            if found > 0:
                console.print(f'[bold green]✅ Интеграция работает! Найдено сервисов: {found}[/bold green]')
            else:
                console.print('[bold yellow]⚠️ Сервисы не привязаны к этому адресу[/bold yellow]')

        except Exception as e:
            print_error('integration', e)


# ============================================================================
# Тесты для функций поиска детских садов (ДОУ)
# ============================================================================


async def demo_kindergartens(raw: bool = False) -> None:
    """
    Тесты для функций поиска детских садов
    """
    from app.api.yazzh_new import YazzhAsyncClient  #, format_kindergartens_for_chat

    print_separator('🏒 ТЕСТЫ ДЕТСКИХ САДОВ (ДОУ)')

    async with YazzhAsyncClient() as client:
        # Тест 1: Получение детских садов в Невском районе для ребёнка 3 лет
        params = {'district': 'Невский', 'age_year': 3, 'age_month': 0, 'count': 5}
        print_input('get_kindergartens (Невский район, 3 года)', **params)

        try:
            result = await client.get_kindergartens(**params)
            print_output('get_kindergartens', result, raw=raw)

            if not raw and result:
                console.print(f'[green]✅ Найдено детских садов: {len(result)}[/green]')
        except Exception as e:
            print_error('get_kindergartens', e)

        # Тест 2: Получение списка районов
        print_input('get_kindergarten_districts')

        try:
            districts = await client.get_kindergarten_districts()
            print_output('get_kindergarten_districts', districts, raw=raw)

            if not raw and districts:
                console.print(f'[green]✅ Найдено районов: {len(districts)}[/green]')
        except Exception as e:
            print_error('get_kindergarten_districts', e)

        # Тест 3: Детсады для малыша 1.5 года
        params = {'district': 'Центральный', 'age_year': 1, 'age_month': 6, 'count': 3}
        print_input('get_kindergartens (Центральный, 1.5 года)', **params)

        try:
            result = await client.get_kindergartens(**params)
            print_output('get_kindergartens', result, raw=raw)
        except Exception as e:
            print_error('get_kindergartens', e)


# ============================================================================
# Тесты для афиши (мероприятий)
# ============================================================================


async def demo_events(raw: bool = False) -> None:
    """
    Тесты для афиши
    """
    import pendulum

    from app.api.yazzh_new import YazzhAsyncClient  #, format_events_for_chat

    print_separator('🎭 ТЕСТЫ АФИШИ (МЕРОПРИЯТИЯ)')
    async with YazzhAsyncClient() as client:
        now = pendulum.now('Europe/Moscow')
        start_date = now.format('YYYY-MM-DDTHH:mm:ss')
        end_date = now.add(days=7).format('YYYY-MM-DDTHH:mm:ss')

        # Тест 1: Все мероприятия на неделю
        params = {'start_date': start_date, 'end_date': end_date, 'count': 5}
        print_input('get_events (все на 7 дней)', **params)

        try:
            result = await client.get_events(**params)
            print_output('get_events', result, raw=raw)

            if not raw and result:
                console.print(f'[green]✅ Найдено мероприятий: {len(result)}[/green]')
        except Exception as e:
            print_error('get_events', e)

        # Тест 2: Бесплатные мероприятия
        params = {'start_date': start_date, 'end_date': end_date, 'free': True, 'count': 5}
        print_input('get_events (бесплатные)', **params)

        try:
            result = await client.get_events(**params)
            print_output('get_events (free)', result, raw=raw)
        except Exception as e:
            print_error('get_events (free)', e)

        # Тест 3: Для детей
        params = {'start_date': start_date, 'end_date': end_date, 'kids': True, 'count': 5}
        print_input('get_events (для детей)', **params)

        try:
            result = await client.get_events(**params)
            print_output('get_events (kids)', result, raw=raw)
        except Exception as e:
            print_error('get_events (kids)', e)

        # Тест 4: Категории мероприятий
        print_input('get_event_categories')

        try:
            categories = await client.get_event_categories()
            print_output('get_event_categories', categories, raw=raw)

            if not raw and categories:
                console.print(f'[green]✅ Найдено категорий: {len(categories)}[/green]')
        except Exception as e:
            print_error('get_event_categories', e)


# ============================================================================
# Тесты для МФЦ
# ============================================================================


async def demo_mfc(raw: bool = False) -> None:
    """
    Тесты для МФЦ
    """
    from app.api.yazzh_new import YazzhAsyncClient  #, format_mfc_for_chat

    print_separator('🏢 ТЕСТЫ МФЦ')

    async with YazzhAsyncClient() as client:
        # Тест 1: Ближайший МФЦ по адресу
        address = 'Невский проспект 10'
        print_input('get_nearest_mfc_by_address', address=address)

        try:
            result = await client.get_nearest_mfc_by_address(address)
            print_output('get_nearest_mfc_by_address', result, raw=raw)
        except Exception as e:
            print_error('get_nearest_mfc_by_address', e)

        # Тест 2: МФЦ по району
        district = 'Центральный'
        print_input('get_mfc_by_district', district=district)

        try:
            result = await client.get_mfc_by_district(district)
            print_output('get_mfc_by_district', result, raw=raw)

            if not raw and result:
                console.print(f'[green]✅ Найдено МФЦ: {len(result)}[/green]')
        except Exception as e:
            print_error('get_mfc_by_district', e)

        # Тест 3: Все МФЦ
        print_input('get_all_mfc')

        try:
            result = await client.get_all_mfc()
            # Показываем только первые 3
            print_output('get_all_mfc (первые 3)', result[:3] if result else [], raw=raw)

            if not raw and result:
                console.print(f'[green]✅ Всего МФЦ: {len(result)}[/green]')
        except Exception as e:
            print_error('get_all_mfc', e)


# ============================================================================
# Тесты для школ
# ============================================================================


async def demo_schools(raw: bool = False) -> None:
    """
    Тесты для школ
    """
    from app.api.yazzh_new import YazzhAsyncClient  #, format_schools_for_chat

    print_separator('🏫 ТЕСТЫ ШКОЛ')

    async with YazzhAsyncClient() as client:
        # Тест: Школы по адресу (Невский 10 имеет привязку к школе)
        address = 'Невский проспект 10'
        print_input('get_linked_schools_by_address', address=address)

        try:
            result = await client.get_linked_schools_by_address(address)
            print_output('get_linked_schools_by_address', result, raw=raw)

            if not raw and result:
                console.print(f'[green]✅ Найдено школ: {len(result)}[/green]')
        except Exception as e:
            print_error('get_linked_schools_by_address', e)


async def fuzz_schools(raw: bool = False) -> None:
    """
    Fuzz-тест школ по всем адресам из FUZZ_ADDRESSES['schools']
    """
    from app.api.yazzh_new import YazzhAsyncClient

    print_separator('🏫 FUZZ-ТЕСТ ШКОЛ')
    addresses = FUZZ_ADDRESSES.get('schools', [])
    console.print(f'[cyan]📋 Тестируем {len(addresses)} адресов...[/cyan]\n')

    async with YazzhAsyncClient() as client:
        for i, address in enumerate(addresses, 1):
            console.print(f'[dim]━━━ Адрес {i}/{len(addresses)} ━━━[/dim]')
            print_input('get_linked_schools_by_address', address=address)

            try:
                result = await client.get_linked_schools_by_address(address)
                print_output('get_linked_schools_by_address', result, raw=raw)

                if result:
                    console.print(f'[green]✅ Найдено школ: {len(result)}[/green]')
                else:
                    console.print('[yellow]⚠️ Школ не найдено[/yellow]')
            except Exception as e:
                print_error('get_linked_schools_by_address', e)


async def fuzz_polyclinics(raw: bool = False) -> None:
    """
    Fuzz-тест поликлиник по всем адресам из FUZZ_ADDRESSES['polyclinics']
    """
    from app.api.yazzh_new import YazzhAsyncClient

    print_separator('🏥 FUZZ-ТЕСТ ПОЛИКЛИНИК')
    addresses = FUZZ_ADDRESSES.get('polyclinics', [])
    console.print(f'[cyan]📋 Тестируем {len(addresses)} адресов...[/cyan]\n')

    async with YazzhAsyncClient() as client:
        for i, address in enumerate(addresses, 1):
            console.print(f'[dim]━━━ Адрес {i}/{len(addresses)} ━━━[/dim]')
            print_input('get_polyclinics_by_address', address=address)

            try:
                result = await client.get_polyclinics_by_address(address)
                print_output('get_polyclinics_by_address', result, raw=raw)

                if result:
                    console.print(f'[green]✅ Найдено поликлиник: {len(result)}[/green]')
                else:
                    console.print('[yellow]⚠️ Поликлиник не найдено[/yellow]')
            except Exception as e:
                print_error('get_polyclinics_by_address', e)


async def fuzz_mfc(raw: bool = False) -> None:
    """
    Fuzz-тест МФЦ по всем адресам из FUZZ_ADDRESSES['mfc']
    """
    from app.api.yazzh_new import YazzhAsyncClient

    print_separator('🏢 FUZZ-ТЕСТ МФЦ')
    addresses = FUZZ_ADDRESSES.get('mfc', [])
    console.print(f'[cyan]📋 Тестируем {len(addresses)} адресов...[/cyan]\n')

    async with YazzhAsyncClient() as client:
        for i, address in enumerate(addresses, 1):
            console.print(f'[dim]━━━ Адрес {i}/{len(addresses)} ━━━[/dim]')
            print_input('get_nearest_mfc_by_address', address=address)

            try:
                result = await client.get_nearest_mfc_by_address(address)
                print_output('get_nearest_mfc_by_address', result, raw=raw)

                if result:
                    console.print('[green]✅ Найден МФЦ[/green]')
                else:
                    console.print('[yellow]⚠️ МФЦ не найден[/yellow]')
            except Exception as e:
                print_error('get_nearest_mfc_by_address', e)


async def fuzz_kindergartens(raw: bool = False) -> None:
    """
    Fuzz-тест детских садов по всем параметрам из FUZZ_ADDRESSES['kindergartens']
    """
    from app.api.yazzh_new import YazzhAsyncClient

    print_separator('🏒 FUZZ-ТЕСТ ДЕТСКИХ САДОВ')
    params_list = FUZZ_ADDRESSES.get('kindergartens', [])
    console.print(f'[cyan]📋 Тестируем {len(params_list)} вариантов...[/cyan]\n')

    async with YazzhAsyncClient() as client:
        for i, (district, age_year, age_month) in enumerate(params_list, 1):
            console.print(f'[dim]━━━ Вариант {i}/{len(params_list)} ━━━[/dim]')
            params = {
                'district': district,
                'age_year': age_year,
                'age_month': age_month,
                'count': 3,
            }
            print_input('get_kindergartens', **params)

            try:
                result = await client.get_kindergartens(**params)
                print_output('get_kindergartens', result, raw=raw)

                if result:
                    console.print(f'[green]✅ Найдено детсадов: {len(result)}[/green]')
                else:
                    console.print('[yellow]⚠️ Детсадов не найдено[/yellow]')
            except Exception as e:
                print_error('get_kindergartens', e)


async def fuzz_buildings(raw: bool = False) -> None:
    """
    Fuzz-тест поиска зданий — проверяем building_id для всех адресов
    """
    from app.api.yazzh_new import YazzhAsyncClient

    print_separator('🏠 FUZZ-ТЕСТ ПОИСКА ЗДАНИЙ')
    addresses = FUZZ_ADDRESSES.get('buildings', [])
    console.print(f'[cyan]📋 Тестируем {len(addresses)} адресов...[/cyan]\n')

    success = 0
    failed = 0
    no_building_id = 0

    async with YazzhAsyncClient() as client:
        for i, address in enumerate(addresses, 1):
            console.print(f'[dim]━━━ Адрес {i}/{len(addresses)} ━━━[/dim]')
            print_input('search_building_first', query=address)

            try:
                result = await client.search_building_first(address)

                console.print(f'[cyan]   id: {result.id}[/cyan]')
                console.print(f'[cyan]   building_id: {result.building_id}[/cyan]')
                console.print(f'[cyan]   address: {result.full_address}[/cyan]')
                console.print(f'[cyan]   coords: {result.coords}[/cyan]')

                if result.building_id:
                    console.print('[green]✅ building_id получен[/green]')
                    success += 1
                else:
                    console.print('[red]❌ building_id ПУСТОЙ![/red]')
                    no_building_id += 1
            except Exception as e:
                print_error('search_building_first', e)
                failed += 1

    # Итоги
    console.print()
    console.print(f'[bold]📊 ИТОГИ:[/bold]')
    console.print(f'[green]   ✅ Успешно с building_id: {success}[/green]')
    if no_building_id:
        console.print(f'[red]   ❌ Без building_id: {no_building_id}[/red]')
    if failed:
        console.print(f'[red]   ❌ Ошибки: {failed}[/red]')


async def fuzz_integration(raw: bool = False) -> None:
    """
    Fuzz-тест интеграции: адрес → building_id → все сервисы
    """
    from app.api.yazzh_new import YazzhAsyncClient

    print_separator('🔗 FUZZ-ТЕСТ ИНТЕГРАЦИИ')
    addresses = FUZZ_ADDRESSES.get('integration', [])
    console.print(f'[cyan]📋 Тестируем {len(addresses)} адресов...[/cyan]\n')

    async with YazzhAsyncClient() as client:
        for i, address in enumerate(addresses, 1):
            console.print(f'[bold dim]━━━ Адрес {i}/{len(addresses)}: {address} ━━━[/bold dim]')

            try:
                # Шаг 1: Поиск здания
                building = await client.search_building_first(address)
                console.print(f'[cyan]🏠 building_id: {building.building_id}[/cyan]')

                if not building.building_id:
                    console.print('[red]❌ Нет building_id — пропускаем[/red]\n')
                    continue

                bid = building.building_id
                services_found = []

                # Шаг 2: МФЦ
                try:
                    mfc = await client.get_mfc_by_building(bid)
                    if mfc:
                        services_found.append(f'МФЦ: {mfc.name}')
                except Exception:
                    pass

                # Шаг 3: Поликлиники
                try:
                    clinics = await client.get_polyclinics_by_building(bid)
                    if clinics:
                        services_found.append(f'Поликлиник: {len(clinics)}')
                except Exception:
                    pass

                # Шаг 4: Школы
                try:
                    schools = await client.get_linked_schools(bid)
                    if schools:
                        services_found.append(f'Школ: {len(schools)}')
                except Exception:
                    pass

                if services_found:
                    console.print(f'[green]✅ Найдено: {", ".join(services_found)}[/green]')
                else:
                    console.print('[yellow]⚠️ Сервисов не найдено[/yellow]')

            except Exception as e:
                console.print(f'[red]❌ Ошибка: {e}[/red]')

            console.print()


async def fuzz_management_company(raw: bool = False) -> None:
    """
    Fuzz-тест управляющих компаний
    """
    from app.api.yazzh_new import YazzhAsyncClient

    print_separator('🏢 FUZZ-ТЕСТ УК')
    addresses = FUZZ_ADDRESSES.get('management_company', [])
    console.print(f'[cyan]📋 Тестируем {len(addresses)} адресов...[/cyan]\n')

    async with YazzhAsyncClient() as client:
        for i, address in enumerate(addresses, 1):
            console.print(f'[dim]━━━ Адрес {i}/{len(addresses)} ━━━[/dim]')
            print_input('get_management_company_by_address', address=address)

            try:
                uk = await client.get_management_company_by_address(address)
                print_output('get_management_company_by_address', uk, raw=raw)

                if uk:
                    console.print('[green]✅ УК найдена[/green]')
                else:
                    console.print('[yellow]⚠️ УК не найдена[/yellow]')
            except Exception as e:
                print_error('get_management_company_by_address', e)


# ============================================================================
# Тесты для поликлиник
# ============================================================================


async def demo_polyclinics(raw: bool = False) -> None:
    """
    Тесты для поликлиник
    """
    from app.api.yazzh_new import YazzhAsyncClient  #, format_polyclinics_for_chat

    print_separator('🏥 ТЕСТЫ ПОЛИКЛИНИК')

    async with YazzhAsyncClient() as client:
        # Тест: Поликлиники по адресу (Невский 10 имеет привязку)
        address = 'Невский проспект 10'
        print_input('get_polyclinics_by_address', address=address)

        try:
            result = await client.get_polyclinics_by_address(address)
            print_output('get_polyclinics_by_address', result, raw=raw)

            if not raw and result:
                console.print(f'[green]✅ Найдено поликлиник: {len(result)}[/green]')
        except Exception as e:
            print_error('get_polyclinics_by_address', e)


# ============================================================================
# Тесты для LangChain tools
# ============================================================================


def demo_tools(raw: bool = False) -> None:
    """
    Тесты для LangChain tools
    """
    from app.tools.city_tools_v2 import (
        get_city_events_v2,
        get_event_categories_v2,
        get_kindergartens_v2,
    )

    print_separator('🔧 ТЕСТЫ LANGCHAIN TOOLS')

    # Тест 1: Детские сады через tool
    params = {'district': 'Невский', 'age_years': 3, 'age_months': 0}
    print_input('get_kindergartens_v2 (tool)', **params)

    try:
        result = get_kindergartens_v2.invoke(params)
        console.print(Panel(result, title='📤 ВЫХОД: get_kindergartens_v2', border_style='green'))
    except Exception as e:
        print_error('get_kindergartens_v2', e)

    # Тест 2: Мероприятия через tool
    params = {'days_ahead': 7, 'category': '', 'free_only': False, 'for_kids': False}
    print_input('get_city_events_v2 (tool)', **params)

    try:
        result = get_city_events_v2.invoke(params)
        console.print(Panel(result, title='📤 ВЫХОД: get_city_events_v2', border_style='green'))
    except Exception as e:
        print_error('get_city_events_v2', e)

    # Тест 3: Категории через tool
    print_input('get_event_categories_v2 (tool)')

    try:
        result = get_event_categories_v2.invoke({})
        console.print(
            Panel(result, title='📤 ВЫХОД: get_event_categories_v2', border_style='green')
        )
    except Exception as e:
        print_error('get_event_categories_v2', e)


# ============================================================================
# Typer команды
# ============================================================================


class FuzzTarget(str, Enum):
    """
    Цели для fuzz-тестирования
    """

    buildings = 'buildings'
    schools = 'schools'
    polyclinics = 'polyclinics'
    mfc = 'mfc'
    dou = 'dou'
    uk = 'uk'
    integration = 'integration'
    all = 'all'


def _print_header():
    """
    Печатает заголовок
    """
    console.print(
        Panel.fit(
            '[bold blue]🧪 YAZZH API Тесты с Rich[/bold blue]\n'
            '[dim]Интерактивное тестирование API городских сервисов[/dim]',
            border_style='blue',
        )
    )


def _print_done(fuzz: bool = False):
    """
    Печатает завершение
    """
    console.print()
    msg = '✅ Fuzz-тесты завершены' if fuzz else '✅ Тесты завершены'
    console.print(Panel.fit(f'[bold green]{msg}[/bold green]', border_style='green'))


@app.command()
def demo(
    buildings: Annotated[bool, typer.Option('--buildings', '-b', help='Тесты поиска зданий')] = False,
    districts: Annotated[bool, typer.Option('--districts', help='Тесты районов')] = False,
    dou: Annotated[bool, typer.Option('--dou', '-d', help='Тесты детских садов')] = False,
    afisha: Annotated[bool, typer.Option('--afisha', '-a', help='Тесты афиши')] = False,
    mfc: Annotated[bool, typer.Option('--mfc', '-m', help='Тесты МФЦ')] = False,
    schools: Annotated[bool, typer.Option('--schools', '-s', help='Тесты школ')] = False,
    polyclinics: Annotated[
        bool, typer.Option('--polyclinics', '-p', help='Тесты поликлиник')
    ] = False,
    uk: Annotated[bool, typer.Option('--uk', '-u', help='Тесты УК')] = False,
    integration: Annotated[bool, typer.Option('--integration', '-i', help='Интеграционный тест')] = False,
    tools: Annotated[bool, typer.Option('--tools', '-t', help='Тесты LangChain tools')] = False,
    raw: Annotated[bool, typer.Option('--raw', '-r', help='Сырой JSON вывод')] = False,
):
    """
    🔬 Запуск демо-тестов для отдельных API.

    Примеры:
        python -m tests.test_yazzh_rich demo --buildings
        python -m tests.test_yazzh_rich demo --schools --polyclinics
        python -m tests.test_yazzh_rich demo -b -s -p -i --raw
    """
    if not any([buildings, districts, dou, afisha, mfc, schools, polyclinics, uk, integration, tools]):
        console.print('[yellow]⚠️ Укажите хотя бы один флаг теста[/yellow]')
        console.print('[dim]Используйте --help для справки[/dim]')
        raise typer.Exit(1)

    async def run():
        _print_header()
        if buildings:
            await demo_building_search(raw=raw)
        if districts:
            await demo_districts(raw=raw)
        if dou:
            await demo_kindergartens(raw=raw)
        if afisha:
            await demo_events(raw=raw)
        if mfc:
            await demo_mfc(raw=raw)
        if schools:
            await demo_schools(raw=raw)
        if polyclinics:
            await demo_polyclinics(raw=raw)
        if uk:
            await demo_management_company(raw=raw)
        if integration:
            await demo_integration(raw=raw)
        if tools:
            demo_tools(raw=raw)
        _print_done()

    asyncio.run(run())


@app.command('all')
def run_all(
    raw: Annotated[bool, typer.Option('--raw', '-r', help='Сырой JSON вывод')] = False,
):
    """
    🚀 Запуск ВСЕХ демо-тестов.

    Примеры:
        python -m tests.test_yazzh_rich all
        python -m tests.test_yazzh_rich all --raw
    """

    async def run():
        _print_header()
        await demo_building_search(raw=raw)
        await demo_districts(raw=raw)
        await demo_kindergartens(raw=raw)
        await demo_events(raw=raw)
        await demo_mfc(raw=raw)
        await demo_schools(raw=raw)
        await demo_polyclinics(raw=raw)
        await demo_management_company(raw=raw)
        await demo_integration(raw=raw)
        demo_tools(raw=raw)
        _print_done()

    asyncio.run(run())


@app.command()
def fuzz(
    targets: Annotated[
        list[FuzzTarget], typer.Argument(help='Цели: buildings, schools, polyclinics, mfc, dou, uk, integration, all')
    ],
    raw: Annotated[bool, typer.Option('--raw', '-r', help='Сырой JSON вывод')] = False,
):
    """
    🔥 Fuzz-тестирование по адресам из FUZZ_ADDRESSES.

    Добавляйте адреса в словарь FUZZ_ADDRESSES в начале файла.

    Примеры:
        python -m tests.test_yazzh_rich fuzz buildings
        python -m tests.test_yazzh_rich fuzz schools polyclinics
        python -m tests.test_yazzh_rich fuzz integration --raw
        python -m tests.test_yazzh_rich fuzz all
    """

    async def run():
        _print_header()
        for target in targets:
            if target == FuzzTarget.buildings:
                await fuzz_buildings(raw=raw)
            elif target == FuzzTarget.schools:
                await fuzz_schools(raw=raw)
            elif target == FuzzTarget.polyclinics:
                await fuzz_polyclinics(raw=raw)
            elif target == FuzzTarget.mfc:
                await fuzz_mfc(raw=raw)
            elif target == FuzzTarget.dou:
                await fuzz_kindergartens(raw=raw)
            elif target == FuzzTarget.uk:
                await fuzz_management_company(raw=raw)
            elif target == FuzzTarget.integration:
                await fuzz_integration(raw=raw)
            elif target == FuzzTarget.all:
                await fuzz_buildings(raw=raw)
                await fuzz_schools(raw=raw)
                await fuzz_polyclinics(raw=raw)
                await fuzz_mfc(raw=raw)
                await fuzz_kindergartens(raw=raw)
                await fuzz_management_company(raw=raw)
                await fuzz_integration(raw=raw)
        _print_done(fuzz=True)

    asyncio.run(run())


if __name__ == '__main__':
    app()
