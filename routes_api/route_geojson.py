# route_geojson.py
import polyline
from typing import Any

# -----------------------------------------------------
# UTILS
# -----------------------------------------------------

def decode_otp_polyline(encoded: str | None) -> list[list[float]]:
    """
    Декодирует OTP polyline в GeoJSON координаты [[lon, lat], ...]
    """
    if not encoded:
        return []

    # polyline.decode → [(lat, lon), ...]
    points = polyline.decode(encoded)
    return [[lon, lat] for (lat, lon) in points]


# -----------------------------------------------------
# OTP → GeoJSON Feature
# -----------------------------------------------------

def otp_leg_to_feature(
    itinerary_index: int,
    leg_index: int,
    leg: dict[str, Any]
) -> dict[str, Any]:
    """
    Преобразует leg из OTP в GeoJSON Feature
    """

    points = leg.get("pointsOnLink", {}) or {}
    coords = decode_otp_polyline(points.get("points"))

    return {
        "type": "Feature",
        "geometry": {
            "type": "LineString",
            "coordinates": coords,
        },
        "properties": {
            "provider": "otp",
            "itinerary_index": itinerary_index,
            "leg_index": leg_index,
            "mode": leg.get("mode"),
            "distance_m": leg.get("distance"),
            "duration_s": leg.get("duration"),
            "from_name": (leg.get("fromPlace") or {}).get("name"),
            "to_name": (leg.get("toPlace") or {}).get("name"),
            "line_code": (leg.get("line") or {}).get("publicCode"),
            "line_name": (leg.get("line") or {}).get("name"),
        },
    }


# -----------------------------------------------------
# ORS → GeoJSON Feature
# -----------------------------------------------------

def ors_to_feature(
    profile: str,
    route: dict[str, Any],
) -> dict[str, Any]:
    """
    Преобразует данные ORS (наш словарь из ors_route) в GeoJSON Feature
    """
    return {
        "type": "Feature",
        "geometry": {
            "type": "LineString",
            "coordinates": route["geometry"],
        },
        "properties": {
            "provider": "ors",
            "profile": profile,
            "distance_m": route["distance_m"],
            "duration_s": route["duration_s"],
        },
    }


# -----------------------------------------------------
# Главная функция сборки FeatureCollection
# -----------------------------------------------------

def build_geojson(
    otp_patterns: list[dict[str, Any]] | None = None,
    ors_car: dict[str, Any] | None = None,
    ors_walk: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Формирует FeatureCollection из OTP и ORS данных.
    """

    features: list[dict[str, Any]] = []

    # 1) Transit legs (OTP)
    if otp_patterns:
        for it_idx, pattern in enumerate(otp_patterns):
            legs = pattern.get("legs") or []
            for leg_idx, leg in enumerate(legs):
                if leg.get("pointsOnLink"):
                    features.append(
                        otp_leg_to_feature(it_idx, leg_idx, leg)
                    )

    # 2) Car route (ORS)
    if ors_car:
        features.append(
            ors_to_feature("driving-car", ors_car)
        )

    # 3) Walk route (ORS)
    if ors_walk:
        features.append(
            ors_to_feature("foot-walking", ors_walk)
        )

    return {
        "type": "FeatureCollection",
        "features": features,
    }
