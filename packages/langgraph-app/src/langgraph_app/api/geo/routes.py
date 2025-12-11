"""
Маршрут по OSM в пределах Санкт-Петербурга.

Функциональность:
- геокодирование двух адресов (с кешем в SQLite)
- длина пешего и автомобильного маршрутов
- координаты маршрута (для интерактивной карты / фронтенда)
- кеш графов OSM на диске (graphml + pickle) и в памяти процесса

Конфигурация:
- Все настройки берутся из langgraph_app.config (GeoConfig)
- Пути относительно DATA_DIR (в Docker это /app/data, монтируется как volume)
- Переменные окружения: DATA_DIR, GEO_CITY_NAME, GEO_GRAPHS_SUBDIR и др.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from functools import lru_cache
import pickle
import sqlite3

import networkx as nx
import osmnx as ox
import rich

from langgraph_app.config import get_geo_config, get_geo_paths

# -----------------------------
# Настройки osmnx
# -----------------------------


def _configure_osmnx() -> None:
    """
    Настраивает osmnx с путями из конфига
    """
    paths = get_geo_paths()
    ox.settings.use_cache = True
    ox.settings.cache_folder = str(paths['osmnx_cache'])
    ox.settings.log_console = True


# Вызываем при импорте модуля
_configure_osmnx()


@dataclass(slots=True)
class RouteResult:
    mode: str
    length_m: float
    coords: list[tuple[float, float]]  # [(lat, lon), ...]


# -----------------------------
# Инфраструктура
# -----------------------------


def _ensure_dirs() -> None:
    paths = get_geo_paths()
    paths['data_dir'].mkdir(parents=True, exist_ok=True)
    paths['graph_dir'].mkdir(parents=True, exist_ok=True)


def init_geocode_db() -> None:
    """
    Создаёт SQLite-БД для кеша геокодирования, если её ещё нет
    """
    _ensure_dirs()
    paths = get_geo_paths()
    with sqlite3.connect(paths['geocode_db']) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS geocode_cache (
                full_address TEXT PRIMARY KEY,
                lat REAL NOT NULL,
                lon REAL NOT NULL
            )
            """
        )
        conn.commit()


# -----------------------------
# Геокодирование с кешем
# -----------------------------


class GeocodingError(RuntimeError):
    """
    Ошибка геокодирования адреса через Nominatim
    """


def geocode_with_cache(address: str) -> tuple[float, float]:
    """
    Геокодирует адрес в пределах СПб с кешем в SQLite.
    Возвращает (lat, lon).

    Если Nominatim не смог найти или вернул ошибку — бросает GeocodingError.
    """
    init_geocode_db()
    geo_cfg = get_geo_config()
    paths = get_geo_paths()
    full = f'{address}, {geo_cfg.city_name}'

    # 1) Проверяем кеш
    with sqlite3.connect(paths['geocode_db']) as conn:
        cur = conn.cursor()
        cur.execute(
            'SELECT lat, lon FROM geocode_cache WHERE full_address = ?',
            (full,),
        )
        row = cur.fetchone()

        if row is not None:
            lat, lon = row
            return float(lat), float(lon)

    # 2) Если в кеше нет — идём в Nominatim
    try:
        lat, lon = ox.geocode(full)
    except Exception as exc:  # osmnx/Nominatim могут кидать разные ошибки
        raise GeocodingError(f'Не удалось геокодировать адрес: {full}') from exc

    if lat is None or lon is None:
        raise GeocodingError(f'Nominatim не вернул координаты для: {full}')

    # 3) Сохраняем в кеш
    with sqlite3.connect(paths['geocode_db']) as conn:
        conn.execute(
            'INSERT OR REPLACE INTO geocode_cache (full_address, lat, lon) VALUES (?, ?, ?)',
            (full, float(lat), float(lon)),
        )
        conn.commit()

    return float(lat), float(lon)


# -----------------------------
# Работа с графами
# -----------------------------


def download_and_save_graphs(logging: bool = True) -> tuple[nx.MultiDiGraph, nx.MultiDiGraph]:
    """
    Первичная тяжёлая загрузка графов из OSM и сохранение на диск.
    Вызывается только если кеш пуст.
    """
    _ensure_dirs()
    geo_cfg = get_geo_config()
    paths = get_geo_paths()

    if logging:
        rich.print('[yellow]Скачиваю пешеходный граф…[/yellow]')

    G_walk = ox.graph_from_place(geo_cfg.city_name, network_type='walk')

    if logging:
        rich.print('[yellow]Скачиваю автомобильный граф…[/yellow]')

    G_drive = ox.graph_from_place(geo_cfg.city_name, network_type='drive')

    # TODO: при желании можно упростить графы (project_graph, truncate и т.п.)

    if logging:
        rich.print('[yellow]Сохраняю графы (graphml + pickle)…[/yellow]')

    ox.save_graphml(G_walk, paths['walk_graphml'])
    ox.save_graphml(G_drive, paths['drive_graphml'])

    if logging:
        rich.print('[yellow]Создаю pickle кеш…[/yellow]')

    with open(paths['walk_pickle'], 'wb') as f:
        pickle.dump(G_walk, f, protocol=pickle.HIGHEST_PROTOCOL)
    with open(paths['drive_pickle'], 'wb') as f:
        pickle.dump(G_drive, f, protocol=pickle.HIGHEST_PROTOCOL)

    return G_walk, G_drive


def _load_graphs_from_disk(logging: bool = True) -> tuple[nx.MultiDiGraph, nx.MultiDiGraph]:
    """
    Низкоуровневая загрузка графов с диска (без in-memory кеша).
    Пытается сначала читать бинарный pickle, потом graphml, в крайнем случае — качает.
    """
    _ensure_dirs()
    paths = get_geo_paths()

    # 1) быстрый бинарный кеш (обычный pickle)
    if paths['walk_pickle'].exists() and paths['drive_pickle'].exists():
        if logging:
            rich.print('[dim]Загружаю графы из pickle…[/dim]')
        with open(paths['walk_pickle'], 'rb') as f:
            G_walk = pickle.load(f)
        with open(paths['drive_pickle'], 'rb') as f:
            G_drive = pickle.load(f)
        return G_walk, G_drive

    # 2) Если pickle нет, пробуем graphml
    if paths['walk_graphml'].exists() and paths['drive_graphml'].exists():
        if logging:
            rich.print('[dim]Загружаю графы из graphml…[/dim]')
        G_walk = ox.load_graphml(paths['walk_graphml'])
        G_drive = ox.load_graphml(paths['drive_graphml'])

        if logging:
            rich.print('[yellow]Создаю pickle кеш…[/yellow]')
        with open(paths['walk_pickle'], 'wb') as f:
            pickle.dump(G_walk, f, protocol=pickle.HIGHEST_PROTOCOL)
        with open(paths['drive_pickle'], 'wb') as f:
            pickle.dump(G_drive, f, protocol=pickle.HIGHEST_PROTOCOL)

        return G_walk, G_drive

    # 3) Если вообще ничего нет — первичная тяжёлая загрузка
    if logging:
        rich.print('[red]Графы не найдены, выполняю первичное скачивание…[/red]')
    return download_and_save_graphs(logging=logging)


@lru_cache(maxsize=1)
def get_graphs() -> tuple[nx.MultiDiGraph, nx.MultiDiGraph]:
    """
    Ленивая загрузка графов с диска + кеш в памяти процесса.
    При первом вызове читает с диска, дальше — только из памяти.
    """
    return _load_graphs_from_disk()


# -----------------------------
# Маршрут: длина + координаты
# -----------------------------


def get_route_length_m(G: nx.MultiDiGraph, route: list[int]) -> float:
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


def get_route_coords(G: nx.MultiDiGraph, route: Iterable[int]) -> list[tuple[float, float]]:
    """
    Возвращает список (lat, lon) по списку вершин маршрута.
    Для непрожектированного графа:
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
    length_m = get_route_length_m(G, route)
    coords = get_route_coords(G, route)

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
