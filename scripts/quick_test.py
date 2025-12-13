"""
Quick Tool Tester - CLI для быстрого тестирования отдельных tools.

Использует Typer для удобного CLI интерфейса.

Usage:
    python scripts/quick_test.py resolve-location "метро Чернышевская"
    python scripts/quick_test.py pet-parks-near "Невский 10" --radius 5
    python scripts/quick_test.py mfc-nearest "Садовая 50"
    python scripts/quick_test.py --help
"""

import asyncio
import sys
from pathlib import Path
from typing import Optional

import typer

# Add package path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "packages" / "langgraph-app" / "src"))

app = typer.Typer(
    name="quick-test",
    help="🔧 Быстрое тестирование tools агента",
    add_completion=False,
)


def run_async(coro):
    """Helper для запуска async функций."""
    return asyncio.run(coro)


def print_result(tool_name: str, args: dict, result: str):
    """Красиво вывести результат."""
    typer.echo()
    typer.secho(f"🔧 Tool: {tool_name}", fg=typer.colors.CYAN, bold=True)
    typer.secho(f"📝 Args: {args}", fg=typer.colors.YELLOW)
    typer.echo("-" * 60)
    typer.echo(result)
    typer.echo("-" * 60)


# =============================================================================
# Location / Address Commands
# =============================================================================


@app.command("resolve-location")
def resolve_location_cmd(
    query: str = typer.Argument(..., help="Адрес или станция метро"),
    limit: int = typer.Option(5, "--limit", "-l", help="Максимум кандидатов"),
):
    """Уточнить адрес или метро и получить координаты."""
    from langgraph_app.tools.city_tools_v3 import resolve_location

    async def run():
        return await resolve_location.ainvoke({"query": query, "limit": limit})

    result = run_async(run())
    print_result("resolve_location", {"query": query, "limit": limit}, result)


@app.command("search-address")
def search_address_cmd(
    query: str = typer.Argument(..., help="Поисковый запрос адреса"),
):
    """Найти адрес по текстовому запросу."""
    from langgraph_app.tools.city_tools_v3 import search_address

    async def run():
        return await search_address.ainvoke({"query": query})

    result = run_async(run())
    print_result("search_address", {"query": query}, result)


# =============================================================================
# Pet Commands
# =============================================================================


@app.command("pet-parks-near")
def pet_parks_near_cmd(
    location: str = typer.Argument(..., help="Адрес или метро"),
    radius: float = typer.Option(5.0, "--radius", "-r", help="Радиус поиска в км"),
):
    """Площадки для выгула собак рядом с адресом/метро."""
    from langgraph_app.tools.city_tools_v3 import get_pet_parks_near

    async def run():
        return await get_pet_parks_near.ainvoke({"location": location, "radius_km": radius})

    result = run_async(run())
    print_result("get_pet_parks_near", {"location": location, "radius_km": radius}, result)


@app.command("vet-clinics-near")
def vet_clinics_near_cmd(
    location: str = typer.Argument(..., help="Адрес или метро"),
    radius: float = typer.Option(10.0, "--radius", "-r", help="Радиус поиска в км"),
):
    """Ветеринарные клиники рядом с адресом/метро."""
    from langgraph_app.tools.city_tools_v3 import get_vet_clinics_near

    async def run():
        return await get_vet_clinics_near.ainvoke({"location": location, "radius_km": radius})

    result = run_async(run())
    print_result("get_vet_clinics_near", {"location": location, "radius_km": radius}, result)


@app.command("pet-shelters-near")
def pet_shelters_near_cmd(
    location: str = typer.Argument(..., help="Адрес или метро"),
    radius: float = typer.Option(15.0, "--radius", "-r", help="Радиус поиска в км"),
):
    """Приюты для животных рядом с адресом/метро."""
    from langgraph_app.tools.city_tools_v3 import get_pet_shelters_near

    async def run():
        return await get_pet_shelters_near.ainvoke({"location": location, "radius_km": radius})

    result = run_async(run())
    print_result("get_pet_shelters_near", {"location": location, "radius_km": radius}, result)


# =============================================================================
# Events Commands
# =============================================================================


@app.command("events-near")
def events_near_cmd(
    location: str = typer.Argument(..., help="Адрес или метро"),
    radius: float = typer.Option(10.0, "--radius", "-r", help="Радиус поиска в км"),
    count: int = typer.Option(5, "--count", "-c", help="Количество результатов"),
):
    """Мероприятия рядом с адресом/метро."""
    from langgraph_app.tools.city_tools_v3 import get_city_events_near

    async def run():
        return await get_city_events_near.ainvoke({
            "location": location,
            "radius_km": radius,
            "count": count,
        })

    result = run_async(run())
    print_result("get_city_events_near", {"location": location, "radius_km": radius}, result)


@app.command("sport-events")
def sport_events_cmd(
    district: str = typer.Argument(..., help="Название района"),
    count: int = typer.Option(5, "--count", "-c", help="Количество результатов"),
):
    """Спортивные мероприятия в районе."""
    from langgraph_app.tools.city_tools_v3 import get_sport_events

    async def run():
        return await get_sport_events.ainvoke({"district": district, "count": count})

    result = run_async(run())
    print_result("get_sport_events", {"district": district, "count": count}, result)


# =============================================================================
# Recycling Commands
# =============================================================================


@app.command("recycling-near")
def recycling_near_cmd(
    location: str = typer.Argument(..., help="Адрес или метро"),
    count: int = typer.Option(5, "--count", "-c", help="Количество результатов"),
):
    """Пункты переработки рядом с адресом/метро."""
    from langgraph_app.tools.city_tools_v3 import get_recycling_points_near

    async def run():
        return await get_recycling_points_near.ainvoke({"location": location, "count": count})

    result = run_async(run())
    print_result("get_recycling_points_near", {"location": location, "count": count}, result)


# =============================================================================
# MFC Commands
# =============================================================================


@app.command("mfc-nearest")
def mfc_nearest_cmd(
    address: str = typer.Argument(..., help="Адрес для поиска"),
    limit: int = typer.Option(5, "--limit", "-l", help="Количество результатов"),
):
    """Ближайшие МФЦ по адресу."""
    from langgraph_app.tools.city_tools_v3 import find_nearest_mfc

    async def run():
        return await find_nearest_mfc.ainvoke({"address": address, "limit": limit})

    result = run_async(run())
    print_result("find_nearest_mfc", {"address": address, "limit": limit}, result)


@app.command("mfc-district")
def mfc_district_cmd(
    district: str = typer.Argument(..., help="Название района"),
    limit: int = typer.Option(10, "--limit", "-l", help="Количество результатов"),
):
    """МФЦ в районе."""
    from langgraph_app.tools.city_tools_v3 import get_mfc_by_district

    async def run():
        return await get_mfc_by_district.ainvoke({"district": district, "limit": limit})

    result = run_async(run())
    print_result("get_mfc_by_district", {"district": district, "limit": limit}, result)


# =============================================================================
# Education Commands
# =============================================================================


@app.command("polyclinics")
def polyclinics_cmd(
    address: str = typer.Argument(..., help="Адрес для поиска"),
):
    """Поликлиники по адресу."""
    from langgraph_app.tools.city_tools_v3 import get_polyclinics_by_address

    async def run():
        return await get_polyclinics_by_address.ainvoke({"address": address})

    result = run_async(run())
    print_result("get_polyclinics_by_address", {"address": address}, result)


@app.command("schools")
def schools_cmd(
    address: str = typer.Argument(..., help="Адрес для поиска"),
):
    """Школы по адресу."""
    from langgraph_app.tools.city_tools_v3 import get_schools_by_address

    async def run():
        return await get_schools_by_address.ainvoke({"address": address})

    result = run_async(run())
    print_result("get_schools_by_address", {"address": address}, result)


@app.command("schools-district")
def schools_district_cmd(
    district: str = typer.Argument(..., help="Название района"),
):
    """Школы в районе."""
    from langgraph_app.tools.city_tools_v3 import get_schools_in_district

    async def run():
        return await get_schools_in_district.ainvoke({"district": district})

    result = run_async(run())
    print_result("get_schools_in_district", {"district": district}, result)


@app.command("kindergartens")
def kindergartens_cmd(
    district: str = typer.Argument(..., help="Название района"),
):
    """Детские сады в районе."""
    from langgraph_app.tools.city_tools_v3 import get_kindergartens_by_district

    async def run():
        return await get_kindergartens_by_district.ainvoke({"district": district})

    result = run_async(run())
    print_result("get_kindergartens_by_district", {"district": district}, result)


# =============================================================================
# Other Commands
# =============================================================================


@app.command("sportgrounds")
def sportgrounds_cmd(
    district: str = typer.Argument(..., help="Название района"),
    count: int = typer.Option(5, "--count", "-c", help="Количество результатов"),
):
    """Спортивные площадки в районе."""
    from langgraph_app.tools.city_tools_v3 import get_sportgrounds

    async def run():
        return await get_sportgrounds.ainvoke({"district": district, "count": count})

    result = run_async(run())
    print_result("get_sportgrounds", {"district": district, "count": count}, result)


@app.command("beautiful-places")
def beautiful_places_cmd(
    district: str = typer.Argument(..., help="Название района"),
    count: int = typer.Option(5, "--count", "-c", help="Количество результатов"),
):
    """Достопримечательности в районе."""
    from langgraph_app.tools.city_tools_v3 import get_beautiful_places

    async def run():
        return await get_beautiful_places.ainvoke({"district": district, "count": count})

    result = run_async(run())
    print_result("get_beautiful_places", {"district": district, "count": count}, result)


@app.command("management-company")
def management_company_cmd(
    address: str = typer.Argument(..., help="Адрес дома"),
):
    """Управляющая компания по адресу."""
    from langgraph_app.tools.city_tools_v3 import get_management_company

    async def run():
        return await get_management_company.ainvoke({"address": address})

    result = run_async(run())
    print_result("get_management_company", {"address": address}, result)


@app.command("districts")
def districts_cmd():
    """Список всех районов СПб."""
    from langgraph_app.tools.city_tools_v3 import get_districts_list

    async def run():
        return await get_districts_list.ainvoke({})

    result = run_async(run())
    print_result("get_districts_list", {}, result)


@app.command("district-info")
def district_info_cmd(
    district: str = typer.Argument(..., help="Название района"),
):
    """Информация о районе."""
    from langgraph_app.tools.city_tools_v3 import get_district_info

    async def run():
        return await get_district_info.ainvoke({"district": district})

    result = run_async(run())
    print_result("get_district_info", {"district": district}, result)


if __name__ == "__main__":
    app()
