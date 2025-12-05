"""
Демо-тесты для проверки API методов Tier 2:
- Дорожные работы ГАТИ
- Ветклиники
- Парки для питомцев
- Школы по району

Запуск: python -m tests.test_tier2_api
"""

import asyncio

from app.api.yazzh_new import (
    YazzhAsyncClient,
    format_pet_parks_for_chat,
    format_road_works_for_chat,
    format_schools_by_district_for_chat,
    format_vet_clinics_for_chat,
)


async def demo_test_road_works():
    """Демо-тест дорожных работ ГАТИ"""
    print('\n=== ТЕСТ: Дорожные работы ГАТИ ===\n')

    async with YazzhAsyncClient() as client:
        # Общая статистика
        stats = await client.get_road_works_stats()
        print(f'Всего работ в городе: {stats.count}')
        print(f'Районов с данными: {len(stats.count_district)}')

        # По конкретному району
        works_nevsky = await client.get_road_works_by_district('Невский')
        print(f'\nНевский район: {works_nevsky[0].count} работ')

        # Форматтер
        formatted = format_road_works_for_chat(stats)
        print(f'\nФорматтер (первые 300 символов):\n{formatted[:300]}...')


async def demo_test_vet_clinics():
    """Демо-тест ветклиник"""
    print('\n=== ТЕСТ: Ветклиники ===\n')

    async with YazzhAsyncClient() as client:
        # По координатам (центр города)
        clinics, total = await client.get_vet_clinics(
            latitude=59.9343,
            longitude=30.3351,
            radius=10,  # км
        )
        print(f'Найдено клиник: {total}')
        if clinics:
            print('\nПервые 3 клиники:')
            print(format_vet_clinics_for_chat(clinics[:3]))

        # По адресу
        print('\nПоиск по адресу "Невский проспект 1":')
        clinics2, total2 = await client.get_vet_clinics_by_address(
            'Невский проспект 1',
            radius=5,  # км
        )
        print(f'Найдено рядом: {total2}')


async def demo_test_pet_parks():
    """Демо-тест парков для питомцев"""
    print('\n=== ТЕСТ: Парки для питомцев ===\n')

    async with YazzhAsyncClient() as client:
        # По координатам
        parks, total = await client.get_pet_parks(
            latitude=59.9343,
            longitude=30.3351,
            radius=5,  # км
        )
        print(f'Найдено мест: {total}')
        if parks:
            print(f'\nПервые 5 мест:')
            print(format_pet_parks_for_chat(parks[:5]))


async def demo_test_schools_by_district():
    """Демо-тест школ по району"""
    print('\n=== ТЕСТ: Школы по району ===\n')

    async with YazzhAsyncClient() as client:
        schools = await client.get_schools_by_district('Невский', count=5)
        print(f'Школ в Невском районе (показано): {len(schools)}')
        print(format_schools_by_district_for_chat(schools, 'Невский'))


async def main():
    """Запуск всех демо-тестов Tier 2"""
    print('=' * 60)
    print('ДЕМО-ТЕСТЫ TIER 2')
    print('=' * 60)

    await demo_test_road_works()
    await demo_test_vet_clinics()
    await demo_test_pet_parks()
    await demo_test_schools_by_district()

    print('\n' + '=' * 60)
    print('✅ ВСЕ ДЕМО-ТЕСТЫ TIER 2 ЗАВЕРШЕНЫ')
    print('=' * 60)


if __name__ == '__main__':
    asyncio.run(main())
