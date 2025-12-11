""" "
Кеш графов OSM на диске (graphml + pickle) и в памяти процесса

Конфигурация:
- Все настройки берутся из langgraph_app.config (GeoConfig)
- Пути относительно DATA_DIR (в Docker это /app/data, монтируется как volume)
- Переменные окружения: DATA_DIR, GEO_CITY_NAME, GEO_GRAPHS_SUBDIR и др.
"""

from functools import lru_cache
import pickle
import sqlite3
import threading

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


# -----------------------------
# SQLite Geocode Cache (Singleton)
# -----------------------------

_geocode_db_conn: sqlite3.Connection | None = None
_geocode_db_lock = threading.Lock()


def _init_geocode_db_schema(conn: sqlite3.Connection) -> None:
    """Создаёт таблицу кеша геокодирования, если её нет."""
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


def get_osm_geocode_db() -> sqlite3.Connection:
    """
    Возвращает singleton подключение к SQLite кешу геокодирования.

    Потокобезопасно. При первом вызове создаёт директории, файл БД и таблицу.
    Подключение настроено с check_same_thread=False для использования
    из разных потоков (безопасно при использовании через эту функцию с lock).

    Returns:
        sqlite3.Connection: подключение к БД кеша
    """
    global _geocode_db_conn

    if _geocode_db_conn is not None:
        return _geocode_db_conn

    with _geocode_db_lock:
        # Double-check locking
        if _geocode_db_conn is not None:
            return _geocode_db_conn

        _ensure_dirs()
        paths = get_geo_paths()
        db_path = paths['geocode_db']

        # check_same_thread=False позволяет использовать из разных потоков
        # WAL mode для лучшей производительности при concurrent reads
        conn = sqlite3.connect(str(db_path), check_same_thread=False)
        conn.execute('PRAGMA journal_mode=WAL')
        _init_geocode_db_schema(conn)

        _geocode_db_conn = conn

    return _geocode_db_conn


def close_osm_geocode_db() -> None:
    """
    Закрывает подключение к SQLite кешу (для graceful shutdown).
    """
    global _geocode_db_conn

    with _geocode_db_lock:
        if _geocode_db_conn is not None:
            _geocode_db_conn.close()
            _geocode_db_conn = None


# -----------------------------
# Инфраструктура
# -----------------------------


def _ensure_dirs() -> None:
    paths = get_geo_paths()
    paths['data_dir'].mkdir(parents=True, exist_ok=True)
    paths['graph_dir'].mkdir(parents=True, exist_ok=True)


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
