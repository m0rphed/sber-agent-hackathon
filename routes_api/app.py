import os
from datetime import datetime

import openrouteservice
from fastapi import FastAPI
from pydantic import BaseModel, Field

from routes_api.otp_client import call_otp_transmodel, group_trip_patterns, grouped_to_plain_dict
from routes_api.route_geojson import build_geojson

app = FastAPI(
    title="Routing API",
    description="Объединённый API: общественный транспорт (OTP) + авто/пешком (OpenRouteService).",
    version="0.1.0",
)


class Coordinate(BaseModel):
    """Координата точки.

    Parameters
    ----------
    lat : float
        Широта.
    lon : float
        Долгота.
    """

    lat: float
    lon: float


class RouteRequest(BaseModel):
    """Запрос на построение маршрута.

    Parameters
    ----------
    from_ : Coordinate
        Точка отправления.
    to : Coordinate
        Точка назначения.
    when : datetime | None
        Время отправления (UTC или с таймзоной). Если None — сейчас.
    include_transit : bool
        Строить ли маршрут на общественном транспорте (OTP).
    include_car : bool
        Строить ли маршрут для автомобиля (ORS, driving-car).
    include_walk : bool
        Строить ли пеший маршрут (ORS, foot-walking).
    group_transit_by_structure : bool
        Группировать ли transit-маршруты по структуре (True)
        или считать каждое отправление отдельным (False).
    """

    from_: Coordinate = Field(..., alias="from")
    to: Coordinate
    when: datetime | None = None
    include_transit: bool = True
    include_car: bool = True
    include_walk: bool = True
    group_transit_by_structure: bool = True

    class Config:
        allow_population_by_field_name = True


class OrsRoute(BaseModel):
    """Маршрут от OpenRouteService.

    Parameters
    ----------
    provider : str
        Имя провайдера ('openrouteservice').
    profile : str
        Профиль маршрута (driving-car, foot-walking и т.п.).
    distance_m : float
        Длина маршрута в метрах.
    duration_s : float
        Время в секундах.
    geometry : list[list[float]] | None
        Ломаная маршрута в формате [ [lon, lat], ... ].
    """

    provider: str
    profile: str
    distance_m: float
    duration_s: float
    geometry: list[list[float]] | None


class CombinedResponse(BaseModel):
    """Общий ответ по маршрутам.

    Parameters
    ----------
    transit : list[dict] | None
        Список сгруппированных transit-маршрутов (результат grouped_to_plain_dict).
    car : OrsRoute | None
        Маршрут для автомобиля.
    walk : OrsRoute | None
        Пеший маршрут.
    """

    transit: list[dict] | None
    car: OrsRoute | None
    walk: OrsRoute | None


def _iso_utc(dt: datetime | None) -> str | None:
    """Перевести datetime в строку с суффиксом Z.

    Parameters
    ----------
    dt : datetime | None
        Входное время.

    Returns
    -------
    str | None
        Строка вида 'YYYY-MM-DDTHH:MM:SSZ' или None.
    """
    if dt is None:
        return None
    return dt.replace(microsecond=0).isoformat().replace("+00:00", "") + "Z"


@app.post("/route/geojson")
async def route_geojson(req: RouteRequest):
    otp_patterns = None
    ors_car = None
    ors_walk = None

    _from_lat, _from_lon = req.from_.lat, req.from_.lon
    _to_lat, _to_lon = req.to.lat, req.to.lon
    # -------------------------
    # 1) Transit (OTP)
    # -------------------------
    if req.include_transit:
        otp_patterns = call_otp_transmodel(
            "http://localhost:8080",
            _from_lat,
            _from_lon,
            _to_lat,
            _to_lon,
            when=None,  # можно добавить параметр
        )
    if otp_patterns:
        # группируем по структуре маршрута
        grouped = group_trip_patterns(
            otp_patterns,
            include_time_in_signature=not req.group_transit_by_structure,
        )
        otp_patterns_dict = grouped_to_plain_dict(grouped)
    # -------------------------
    # 2) Car (ORS)
    # -------------------------
    if req.include_car:
        ors_car = ors_route("driving-car", req.from_, req.to)

    # -------------------------
    # 3) Walk (ORS)
    # -------------------------
    if req.include_walk:
        ors_walk = ors_route("foot-walking", req.from_, req.to)

    # -------------------------
    # Сбор GeoJSON FeatureCollection
    # -------------------------
    return build_geojson(
        otp_patterns=otp_patterns_dict,
        ors_car=ors_car,
        ors_walk=ors_walk,
    )


# ==== OpenRouteService client ====

ORS_API_KEY = os.getenv("ORS_API_KEY")
_ors_client = openrouteservice.Client(key=ORS_API_KEY) if ORS_API_KEY else None


def ors_route(profile: str, start: Coordinate, end: Coordinate) -> dict | None:
    """Запросить маршрут у OpenRouteService.

    Parameters
    ----------
    profile : str
        Профиль маршрута ('driving-car', 'foot-walking', ...).
    start : Coordinate
        Точка старта.
    end : Coordinate
        Точка финиша.

    Returns
    -------
    dict | None
        Словарь с полями provider/profile/distance_m/duration_s/geometry
        или None, если ORS отключён (нет ключа).
    """
    if _ors_client is None:
        return None

    # ORS ожидает координаты в формате (lon, lat)
    coords = (
        (start.lon, start.lat),
        (end.lon, end.lat),
    )

    # format='geojson', чтобы было удобно доставать summary и geometry
    res = _ors_client.directions(
        coords,
        profile=profile,
        format="geojson",
    )

    features = res.get("features") or []
    if not features:
        return None

    feat = features[0]
    props = feat.get("properties") or {}
    summ = props.get("summary") or {}

    distance = float(summ.get("distance", 0.0) or 0.0)
    duration = float(summ.get("duration", 0.0) or 0.0)

    geom = feat.get("geometry") or {}
    if geom.get("type") == "LineString":
        coords_list = geom.get("coordinates") or None
    else:
        coords_list = None

    return {
        "provider": "openrouteservice",
        "profile": profile,
        "distance_m": distance,
        "duration_s": duration,
        "geometry": coords_list,
    }


# ==== Основной эндпойнт ====


@app.post("/route", response_model=CombinedResponse)
def get_route(request: RouteRequest) -> CombinedResponse:
    """Построить маршруты разными способами.

    Notes
    -----
    - Общественный транспорт: берётся из локального OTP по Transmodel GraphQL.
    - Машина и пешком: маршруты по OSM через OpenRouteService.
    """
    # 1) Время
    when = request.when or datetime.utcnow()

    # 2) Общественный транспорт (OTP)
    transit_grouped_dicts: list[dict] | None = None
    if request.include_transit:
        patterns = call_otp_transmodel(
            base_url="http://localhost:8080",
            from_lat=request.from_.lat,
            from_lon=request.from_.lon,
            to_lat=request.to.lat,
            to_lon=request.to.lon,
            when=_iso_utc(when),
        )

        grouped = group_trip_patterns(
            patterns,
            include_time_in_signature=not request.group_transit_by_structure,
        )

        # здесь у нас уже есть duration_s/distance_m на каждом leg
        transit_grouped_dicts = grouped_to_plain_dict(grouped)

    # 3) Машина
    car_route_obj: OrsRoute | None = None
    if request.include_car:
        car_raw = ors_route("driving-car", request.from_, request.to)
        if car_raw is not None:
            car_route_obj = OrsRoute(**car_raw)

    # 4) Пешком
    walk_route_obj: OrsRoute | None = None
    if request.include_walk:
        walk_raw = ors_route("foot-walking", request.from_, request.to)
        if walk_raw is not None:
            walk_route_obj = OrsRoute(**walk_raw)

    return CombinedResponse(
        transit=transit_grouped_dicts,
        car=car_route_obj,
        walk=walk_route_obj,
    )
