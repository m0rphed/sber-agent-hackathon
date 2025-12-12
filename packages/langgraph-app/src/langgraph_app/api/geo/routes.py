from collections.abc import Iterable
from dataclasses import dataclass

import networkx as nx
import osmnx as ox

from langgraph_app.api.geo.geocoding import GeocodingError, geocode_with_cache
from langgraph_app.config import get_geo_config
from langgraph_app.osmnx_config import get_graphs


@dataclass(slots=True)
class RouteResult:
    mode: str
    length_m: float
    coords: list[tuple[float, float]]  # [(lat, lon), ...]


# -----------------------------
# Маршрут: длина + координаты
# -----------------------------


def _get_route_length_m(G: nx.MultiDiGraph, route: list[int]) -> float:
    """
    Считает длину маршрута по атрибуту 'length' рёбер.
    """
    length = 0.0
    for u, v in zip(route[:-1], route[1:], strict=False):
        edge_data = G.get_edge_data(u, v)
        if not edge_data:
            continue
        first_edge = next(iter(edge_data.values()))
        length += float(first_edge.get('length', 0.0))
    return length


def _get_route_coords(G: nx.MultiDiGraph, route: Iterable[int]) -> list[tuple[float, float]]:
    """
    Возвращает список (lat, lon) по списку вершин маршрута.
    Для неспроецированного графа:
        node['y'] = lat, node['x'] = lon.
    """
    coords: list[tuple[float, float]] = []
    for node in route:
        data = G.nodes[node]
        lat = float(data['y'])
        lon = float(data['x'])
        coords.append((lat, lon))
    return coords


def compute_route(
    G: nx.MultiDiGraph,
    origin: tuple[float, float],
    dest: tuple[float, float],
    mode: str,
) -> RouteResult:
    """
    Строит кратчайший маршрут по длине.
    Возвращает длину и координаты маршрута.
    origin/dest: (lat, lon)
    """
    orig_lat, orig_lon = origin
    dest_lat, dest_lon = dest

    orig_node = ox.nearest_nodes(G, orig_lon, orig_lat)
    dest_node = ox.nearest_nodes(G, dest_lon, dest_lat)

    route = nx.shortest_path(G, orig_node, dest_node, weight='length')
    length_m = _get_route_length_m(G, route)
    coords = _get_route_coords(G, route)

    return RouteResult(
        mode=mode,
        length_m=length_m,
        coords=coords,
    )


# -----------------------------
# Высокоуровневая функция
# -----------------------------


def build_routes_for_addresses(
    address_from: str,
    address_to: str,
    logging: bool = False,
) -> tuple[RouteResult, RouteResult]:
    """
    Геокодирование + загрузка графов + расчёт пешего и автомобильного маршрутов.

    Удобно вызывать:
    - из сервиса (FastAPI endpoint),
    - из Jupyter (.ipynb) для отрисовки маршрута на интерактивной карте.
    """
    geo_cfg = get_geo_config()
    if logging:
        print(f'Геокодирую адреса в пределах {geo_cfg.city_name}…')

    origin = geocode_with_cache(address_from)
    dest = geocode_with_cache(address_to)
    if origin is None or dest is None:
        raise GeocodingError(
            f'Не удалось геокодировать один из адресов. {address_from} -> {origin}, {address_to} -> {dest}'
        )

    if logging:
        print(f'Адрес 1: {origin}')
        print(f'Адрес 2: {dest}')

    G_walk, G_drive = get_graphs()

    walk_result = compute_route(
        G_walk,
        origin,
        dest,
        mode='walk',
    )

    drive_result = compute_route(
        G_drive,
        origin,
        dest,
        mode='drive',
    )

    return walk_result, drive_result


# -----------------------------
# GeoJSON helper (под фронтенд)
# -----------------------------


def route_to_geojson(route: RouteResult) -> dict:
    """
    Преобразует маршрут в GeoJSON Feature с LineString.
    Координаты в формате [lon, lat] (стандарт GeoJSON).
    """
    return {
        'type': 'Feature',
        'properties': {
            'mode': route.mode,
            'length_m': route.length_m,
        },
        'geometry': {
            'type': 'LineString',
            'coordinates': [[lon, lat] for lat, lon in route.coords],
        },
    }
