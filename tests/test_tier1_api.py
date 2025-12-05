"""
Тест для проверки API методов Tier 1:
- Услуги для пенсионеров
- Памятные даты
- Статистика спортплощадок
"""

import asyncio

from app.api.yazzh_new import (
    YazzhAsyncClient,
    format_memorable_dates_for_chat,
    format_pensioner_services_for_chat,
    format_sportgrounds_count_for_chat,
)


async def demo_test_pensioner_services():
    """
    Тест услуг для пенсионеров
    """
    print('\n=== ТЕСТ: Услуги для пенсионеров ===\n')

    async with YazzhAsyncClient() as client:
        # Получаем категории
        categories = await client.get_pensioner_service_categories()
        print(f'Категории услуг: {categories}')

        # Получаем услуги в Невском районе
        services = await client.get_pensioner_services(
            district='Невский',
            categories=['Здоровье'],
            count=3,
        )
        print(f'\nНайдено услуг: {len(services)}')
        print(format_pensioner_services_for_chat(services))


async def demo_test_memorable_dates():
    """
    Тест памятных дат
    """
    print('\n=== ТЕСТ: Памятные даты ===\n')

    async with YazzhAsyncClient() as client:
        # Получаем даты на сегодня
        dates_today = await client.get_memorable_dates_today()
        print(f'Событий сегодня: {len(dates_today)}')
        print(format_memorable_dates_for_chat(dates_today))

        # Получаем даты на конкретный день (1 января)
        dates_jan1 = await client.get_memorable_dates_by_date(day=1, month=1)
        print(f'\nСобытий 1 января: {len(dates_jan1)}')
        if dates_jan1:
            print(dates_jan1[0].format_for_human())


async def demo_test_sportgrounds():
    """
    Тест спортплощадок
    """
    print('\n=== ТЕСТ: Спортплощадки ===\n')

    async with YazzhAsyncClient() as client:
        # Общее количество
        total = await client.get_sportgrounds_count()
        print(f'Всего площадок: {total}')

        # По районам
        by_district = await client.get_sportgrounds_count_by_district()
        print(f'\nПо районам ({len(by_district)} районов):')
        print(format_sportgrounds_count_for_chat(by_district))

        # Конкретный район
        nevsky = await client.get_sportgrounds_count_by_district('Невский')
        print(f'\nНевский район: {nevsky}')

        # Типы площадок
        types = await client.get_sportgrounds_types()
        print('\nТипы площадок:')
        print(f'  Летние: {len(types.get("summer", []))} видов')
        print(f'  Зимние: {len(types.get("winter", []))} видов')
        print(f'  Все: {len(types.get("all", []))} видов')


async def main():
    await demo_test_pensioner_services()
    await demo_test_memorable_dates()
    await demo_test_sportgrounds()


if __name__ == '__main__':
    asyncio.run(main())
