"""
Тест поиска метро
"""
import asyncio

from app.api.yazzh_new import YazzhAsyncClient


async def test():
    async with YazzhAsyncClient() as c:
        # Тест 1: метро Пионерская
        print("=== Тест: 'метро Пионерская' ===")
        try:
            r = await c.search_building('метро Пионерская', count=5)
            for i, b in enumerate(r):
                print(f'{i+1}. {b.full_address} (id={b.building_id}, район={b.district})')
        except Exception as e:
            print(f"Ошибка: {e}")

        print()

        # Тест 2: Пионерская улица 1
        print("=== Тест: 'Пионерская улица' ===")
        try:
            r = await c.search_building('Пионерская улица', count=5)
            for i, b in enumerate(r):
                print(f'{i+1}. {b.full_address} (id={b.building_id}, район={b.district})')
        except Exception as e:
            print(f"Ошибка: {e}")

        print()

        # Тест 3: станция метро Пионерская
        print("=== Тест: 'станция метро Пионерская' ===")
        try:
            r = await c.search_building('станция метро Пионерская', count=5)
            for i, b in enumerate(r):
                print(f'{i+1}. {b.full_address} (id={b.building_id}, район={b.district})')
        except Exception as e:
            print(f"Ошибка: {e}")

        print()

        # Тест 4: Коломяжский проспект (рядом с м. Пионерская)
        print("=== Тест: 'Коломяжский проспект 15' ===")
        try:
            r = await c.search_building('Коломяжский проспект 15', count=5)
            for i, b in enumerate(r):
                print(f'{i+1}. {b.full_address} (id={b.building_id}, район={b.district})')
        except Exception as e:
            print(f"Ошибка: {e}")


if __name__ == '__main__':
    asyncio.run(test())
