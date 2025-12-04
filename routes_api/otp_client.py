import json
from dataclasses import dataclass, asdict
from datetime import datetime
import requests


@dataclass
class TripLeg:
    """
    Одна «нога» маршрута
    """

    mode: str
    distance_m: float
    duration_s: int
    from_name: str
    to_name: str
    from_quay_id: str | None
    to_quay_id: str | None
    line_code: str | None
    line_name: str | None
    line_id: str | None
    aimed_start: str | None
    aimed_end: str | None


@dataclass
class TripPattern:
    """
    Вариант маршрута (как приходит из OTP, без группировки)
    """

    aimed_start: str | None
    aimed_end: str | None
    duration_s: int
    distance_m: float
    legs: list[TripLeg]


@dataclass
class Departure:
    """
    Конкретное отправление одного и того же структурного маршрута
    """

    aimed_start: str | None
    aimed_end: str | None
    duration_s: int
    distance_m: float


@dataclass
class GroupedPattern:
    """
    Группа tripPatterns с одинаковой структурой, но разными отправлениями
    """

    signature: str
    legs_template: list[TripLeg]
    departures: list[Departure]


TRIP_QUERY = """
query trip($dateTime: DateTime, $from: Location!, $modes: Modes, $to: Location!) {
  trip(dateTime: $dateTime, from: $from, modes: $modes, to: $to) {
    previousPageCursor
    nextPageCursor
    tripPatterns {
      aimedStartTime
      aimedEndTime
      expectedEndTime
      expectedStartTime
      duration
      distance
      generalizedCost
      legs {
        id
        mode
        aimedStartTime
        aimedEndTime
        expectedEndTime
        expectedStartTime
        realtime
        distance
        duration
        generalizedCost
        fromPlace {
          name
          quay { id }
        }
        toPlace {
          name
          quay { id }
        }
        fromEstimatedCall {
          destinationDisplay { frontText }
        }
        line {
          publicCode
          name
          id
          presentation { colour }
        }
        authority {
          name
          id
        }
        pointsOnLink { points }
        interchangeTo { staySeated }
        interchangeFrom { staySeated }
      }
      systemNotices { tag }
    }
  }
}
""".strip()


def iso_utc(dt: datetime | str | None) -> str | None:
    """
    Привести datetime к строке с Z, если передан объект
    """
    if dt is None:
        return None
    if isinstance(dt, str):
        return dt
    return dt.replace(microsecond=0).isoformat() + "Z"


def call_otp_transmodel(
    base_url: str,
    from_lat: float,
    from_lon: float,
    to_lat: float,
    to_lon: float,
    when: datetime | str | None = None,
) -> list[TripPattern]:
    """
    Вызвать OTP Transmodel API и вернуть «сырые» TripPattern'ы
    """
    url = base_url.rstrip("/") + "/otp/transmodel/v3"

    variables = {
        "from": {
            "coordinates": {
                "latitude": from_lat,
                "longitude": from_lon,
            }
        },
        "to": {
            "coordinates": {
                "latitude": to_lat,
                "longitude": to_lon,
            }
        },
        "dateTime": iso_utc(when),
        "modes": {
            "accessMode": "foot",
            "egressMode": "foot",
            "transportModes": [
                {"transportMode": "bus"},
                {"transportMode": "tram"},
                {"transportMode": "trolleybus"},
                {"transportMode": "metro"},
            ],
        },
    }

    payload = {
        "query": TRIP_QUERY,
        "variables": variables,
        "operationName": "trip",
    }

    headers = {"Content-Type": "application/json"}

    resp = requests.post(url, headers=headers, data=json.dumps(payload))
    status = resp.status_code
    text = resp.text

    print("=== REQUEST JSON ===")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print("=== RESPONSE RAW ===")
    print(status, text[:2000], "..." if len(text) > 2000 else "")
    print("=== END RESPONSE ===")

    resp.raise_for_status()
    data = resp.json()

    if "errors" in data and data["errors"]:
        raise RuntimeError(f"OTP GraphQL errors: {data['errors']}")

    trip = data.get("data", {}).get("trip")
    if not trip:
        return []

    patterns_raw = trip.get("tripPatterns", []) or []
    patterns: list[TripPattern] = []

    for p in patterns_raw:
        legs_raw = p.get("legs", []) or []
        legs: list[TripLeg] = []

        for leg in legs_raw:
            mode = leg.get("mode", "?")

            distance_m = float(leg.get("distance", 0.0) or 0.0)
            duration_s = int(leg.get("duration", 0) or 0)

            from_place = leg.get("fromPlace") or {}
            to_place = leg.get("toPlace") or {}

            from_name = from_place.get("name") or "?"
            to_name = to_place.get("name") or "?"

            from_quay = from_place.get("quay") or {}
            to_quay = to_place.get("quay") or {}

            from_quay_id = from_quay.get("id")
            to_quay_id = to_quay.get("id")

            line = leg.get("line") or {}
            line_code = line.get("publicCode") or None
            line_name = line.get("name") or None
            line_id = line.get("id") or None

            aimed_start = leg.get("aimedStartTime")
            aimed_end = leg.get("aimedEndTime")

            legs.append(
                TripLeg(
                    mode=mode,
                    distance_m=distance_m,
                    duration_s=duration_s,
                    from_name=from_name,
                    to_name=to_name,
                    from_quay_id=from_quay_id,
                    to_quay_id=to_quay_id,
                    line_code=line_code,
                    line_name=line_name,
                    line_id=line_id,
                    aimed_start=aimed_start,
                    aimed_end=aimed_end,
                )
            )

        patterns.append(
            TripPattern(
                aimed_start=p.get("aimedStartTime"),
                aimed_end=p.get("aimedEndTime"),
                duration_s=int(p.get("duration", 0) or 0),
                distance_m=float(p.get("distance", 0.0) or 0.0),
                legs=legs,
            )
        )

    return patterns


def build_pattern_signature(
    pattern: TripPattern,
    include_time_in_signature: bool = False,
) -> str:
    """
    Сигнатура маршрута.

    Если include_time_in_signature=False:
      - берём только структуру:
        mode + from_quay / from_name + to_quay / to_name + (publicCode|line_id)

    Если include_time_in_signature=True:
      - добавляем aimedStart/aimedEnd самого паттерна, чтобы
        каждый tripPattern считался уникальным даже при одинаковой структуре.
    """
    parts: list[str] = []

    for leg in pattern.legs:
        from_id = leg.from_quay_id or f"name:{leg.from_name}"
        to_id = leg.to_quay_id or f"name:{leg.to_name}"
        line_key = (leg.line_code or "") + "|" + (leg.line_id or "")
        part = f"{leg.mode}|{from_id}|{to_id}|{line_key}"
        parts.append(part)

    sig = " -> ".join(parts)

    if include_time_in_signature:
        sig = f"{pattern.aimed_start}|{pattern.aimed_end}|{sig}"

    return sig


def group_trip_patterns(
    patterns: list[TripPattern],
    include_time_in_signature: bool = False,
) -> list[GroupedPattern]:
    """
    Сгруппировать tripPatterns по структуре маршрута.

    include_time_in_signature:
      - False (по умолчанию): группируем одинаковые маршруты с разными отправлениями.
      - True: каждый tripPattern будет отдельной группой (по сути, без группировки).
    """
    groups: dict[str, tuple[list[TripLeg], list[Departure]]] = {}

    for p in patterns:
        sig = build_pattern_signature(
            p, include_time_in_signature=include_time_in_signature
        )
        departure = Departure(
            aimed_start=p.aimed_start,
            aimed_end=p.aimed_end,
            duration_s=p.duration_s,
            distance_m=p.distance_m,
        )

        if sig not in groups:
            # шаблон ног — структура маршрута (времена внутри ног не нужны)
            legs_template = [
                TripLeg(
                    mode=leg.mode,
                    distance_m=leg.distance_m,
                    duration_s=leg.duration_s,
                    from_name=leg.from_name,
                    to_name=leg.to_name,
                    from_quay_id=leg.from_quay_id,
                    to_quay_id=leg.to_quay_id,
                    line_code=leg.line_code,
                    line_name=leg.line_name,
                    line_id=leg.line_id,
                    aimed_start=None,
                    aimed_end=None,
                )
                for leg in p.legs
            ]
            groups[sig] = (legs_template, [departure])
        else:
            groups[sig][1].append(departure)

    grouped: list[GroupedPattern] = []
    for sig, (legs_template, departures) in groups.items():
        departures_sorted = sorted(
            departures,
            key=lambda d: d.aimed_start or "",
        )
        grouped.append(
            GroupedPattern(
                signature=sig,
                legs_template=legs_template,
                departures=departures_sorted,
            )
        )

    grouped.sort(
        key=lambda g: g.departures[0].aimed_start or "" if g.departures else ""
    )
    return grouped


def format_distance(distance_m: float) -> str:
    """
    Человеческий формат расстояния
    """
    if distance_m >= 1000:
        return f"{distance_m / 1000:.2f} км"
    return f"{distance_m:.0f} м"


def pretty_print_grouped(grouped: list[GroupedPattern]) -> None:
    """
    Красивый текстовый вывод (для отладки/CLI)
    """
    if not grouped:
        print("Маршрутов не найдено.")
        return

    print(f"Найдено {len(grouped)} уникальных маршрутов (по структуре)\n")

    for idx, gp in enumerate(grouped, start=1):
        dep_count = len(gp.departures)
        first = gp.departures[0]
        last = gp.departures[-1]

        avg_duration_min = (
            sum(d.duration_s for d in gp.departures) / max(dep_count, 1) / 60
        )
        avg_distance_km = (
            sum(d.distance_m for d in gp.departures) / max(dep_count, 1) / 1000
        )

        print(
            f"Маршрут #{idx}: {dep_count} отправлений, "
            f"~{avg_duration_min:.1f} мин, ~{avg_distance_km:.2f} км"
        )

        if first.aimed_start or last.aimed_end:
            print(f"  Первое отправление: {first.aimed_start}")
            print(f"  Последнее отправление: {last.aimed_end}")

        print("  Структура по участкам (legs):")
        for leg_idx, leg in enumerate(gp.legs_template, start=1):
            dur_min_leg = leg.duration_s / 60 if leg.duration_s else 0.0
            dist_str = format_distance(leg.distance_m)

            if leg.mode.lower() == "foot":
                label = "пешком"
            else:
                label = leg.mode.lower()
            line_part = ""
            if leg.line_code:
                # bus 3, tram 25 и т.п.
                line_part = f" {leg.line_code}"
            elif leg.line_name:
                line_part = f' "{leg.line_name}"'

            print(
                f"    leg #{leg_idx}: {label}{line_part}: "
                f"{leg.from_name} → {leg.to_name} "
                f"({dur_min_leg:.1f} мин, {dist_str})"
            )

        print("  Отправления:")
        for d in gp.departures:
            dur_min = d.duration_s / 60 if d.duration_s else 0.0
            print(f"    {d.aimed_start} → {d.aimed_end} ({dur_min:.1f} мин)")
        print()


# === JSON-сериализация для бэкенда ===


def grouped_to_plain_dict(grouped: list[GroupedPattern]) -> list[dict]:
    """
    Преобразовать GroupedPattern в JSON-friendly структуру
    (чистые dict/list/str/int/float) — удобно отдавать из FastAPI.
    """
    result: list[dict] = []

    for gp in grouped:
        item: dict = {
            "signature": gp.signature,
            "legs": [],
            "departures": [],
        }

        for leg in gp.legs_template:
            item["legs"].append(
                {
                    "mode": leg.mode,
                    "distance_m": leg.distance_m,
                    "duration_s": leg.duration_s,
                    "from_name": leg.from_name,
                    "to_name": leg.to_name,
                    "from_quay_id": leg.from_quay_id,
                    "to_quay_id": leg.to_quay_id,
                    "line_code": leg.line_code,
                    "line_name": leg.line_name,
                    "line_id": leg.line_id,
                }
            )

        for d in gp.departures:
            item["departures"].append(
                {
                    "aimed_start": d.aimed_start,
                    "aimed_end": d.aimed_end,
                    "duration_s": d.duration_s,
                    "distance_m": d.distance_m,
                }
            )

        result.append(item)

    return result


def grouped_to_json(grouped: list[GroupedPattern]) -> str:
    """
    Обёртка: сразу JSON-строка (ensure_ascii=False для русских названий)
    """
    return json.dumps(grouped_to_plain_dict(grouped), ensure_ascii=False, indent=2)


if __name__ == "__main__":
    # Пример: те же координаты, что и в твоём последнем запросе
    patterns = call_otp_transmodel(
        base_url="http://localhost:8080",
        from_lat=59.92836722016219,
        from_lon=30.285417924513723,
        to_lat=59.88150568372481,
        to_lon=30.37711988255549,
        when="2025-12-02T08:43:00Z",
    )

    # Можно переключать стратегию группировки
    grouped = group_trip_patterns(
        patterns,
        include_time_in_signature=False,  # True — каждый tripPattern считается уникальным
    )

    pretty_print_grouped(grouped)

    # Пример, как это можно отдать из FastAPI:
    # print(grouped_to_json(grouped))
