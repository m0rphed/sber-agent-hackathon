"""
Форматтеры для преобразования JSON ответов API в читаемый текст.

Каждый форматтер:
- Принимает dict/list из API
- Возвращает строку для ответа пользователю
- Обрабатывает отсутствующие поля gracefully
- Использует emoji для улучшения читаемости

Категории:
- MFC: МФЦ
- PETS: Питомцы (парки, ветклиники, приюты)
- EVENTS: Мероприятия
- PENSIONER: Услуги для пенсионеров
- SPORT: Спортплощадки
- TOURISM: Достопримечательности
- RECYCLING: Переработка
- INFRASTRUCTURE: Инфраструктура (отключения, дорожные работы)
- EDUCATION: Образование (школы, детсады)
- HEALTHCARE: Поликлиники
"""

from __future__ import annotations

from datetime import datetime
from typing import Any


def _safe_get(data: dict, *keys: str, default: str = "") -> str:
    """Безопасно извлечь вложенное значение."""
    result = data
    for key in keys:
        if isinstance(result, dict):
            result = result.get(key)
        else:
            return default
        if result is None:
            return default
    return str(result) if result else default


def _format_phones(phones: list | None) -> str:
    """Форматировать список телефонов."""
    if not phones:
        return ""
    return ", ".join(str(p) for p in phones)


def _format_distance(distance: float | None) -> str:
    """Форматировать расстояние."""
    if distance is None:
        return ""
    if distance < 1:
        return f"{int(distance * 1000)} м"
    return f"{distance:.1f} км"


def _format_date(date_str: str | None, fmt: str = "%d.%m.%Y") -> str:
    """Форматировать дату."""
    if not date_str:
        return ""
    try:
        # Пробуем разные форматы
        for input_fmt in ["%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f", "%d-%m-%Y"]:
            try:
                dt = datetime.strptime(date_str[:19], input_fmt[:len(date_str)])
                return dt.strftime(fmt)
            except ValueError:
                continue
        return date_str
    except Exception:
        return date_str


def _format_datetime(date_str: str | None) -> str:
    """Форматировать дату и время."""
    if not date_str:
        return ""
    try:
        for input_fmt in ["%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f"]:
            try:
                dt = datetime.strptime(date_str[:19], input_fmt[:19])
                return dt.strftime("%d.%m.%Y %H:%M")
            except ValueError:
                continue
        return date_str
    except Exception:
        return date_str


# =============================================================================
# MFC Formatters
# =============================================================================


def format_mfc(mfc: dict) -> str:
    """Форматировать один МФЦ."""
    lines = []
    lines.append(f"🏢 **{mfc.get('name', 'МФЦ')}**")

    if addr := mfc.get("address"):
        lines.append(f"📍 {addr}")

    if hours := mfc.get("working_hours"):
        lines.append(f"🕐 {hours}")

    if phones := mfc.get("phone"):
        lines.append(f"📞 {_format_phones(phones)}")

    if metro := mfc.get("nearest_metro"):
        lines.append(f"🚇 Метро: {metro}")

    if link := mfc.get("link"):
        lines.append(f"🔗 {link}")

    if accessible := mfc.get("accessible_env"):
        if accessible:
            lines.append("♿ Доступная среда: " + ", ".join(accessible[:3]))

    return "\n".join(lines)


def format_mfc_list(mfc_list: list[dict], max_items: int = 5) -> str:
    """Форматировать список МФЦ."""
    if not mfc_list:
        return "МФЦ не найдены."

    count = len(mfc_list)
    items = mfc_list[:max_items]

    parts = [f"Найдено МФЦ: {count}\n"]
    for i, mfc in enumerate(items, 1):
        parts.append(f"**{i}.** {format_mfc(mfc)}")
        parts.append("")  # пустая строка между

    if count > max_items:
        parts.append(f"... и ещё {count - max_items}")

    return "\n".join(parts)


# =============================================================================
# PETS Formatters
# =============================================================================


def format_pet_park(park: dict) -> str:
    """Форматировать площадку для выгула."""
    place = park.get("place", park)

    lines = []
    lines.append(f"🐕 **{place.get('title', 'Площадка')}**")

    if park_type := place.get("type"):
        lines.append(f"   Тип: {park_type}")

    if addr := place.get("address"):
        lines.append(f"   📍 {addr}")

    if location := place.get("location"):
        if distance := location.get("distance"):
            lines.append(f"   📏 {_format_distance(distance)}")

    return "\n".join(lines)


def format_pet_parks_list(parks: list[dict], max_items: int = 5) -> str:
    """Форматировать список площадок для выгула."""
    if not parks:
        return "Площадки для выгула не найдены."

    parts = [f"🐕 Найдено площадок: {len(parks)}\n"]
    for park in parks[:max_items]:
        parts.append(format_pet_park(park))
        parts.append("")

    return "\n".join(parts)


def format_vet_clinic(clinic: dict) -> str:
    """Форматировать ветклинику."""
    place = clinic.get("place", clinic)

    lines = []
    lines.append(f"🏥 **{place.get('title', 'Ветклиника')}**")

    if addr := place.get("address"):
        lines.append(f"   📍 {addr}")

    if location := place.get("location"):
        if distance := location.get("distance"):
            lines.append(f"   📏 {_format_distance(distance)}")

    return "\n".join(lines)


def format_vet_clinics_list(clinics: list[dict], max_items: int = 5) -> str:
    """Форматировать список ветклиник."""
    if not clinics:
        return "Ветклиники не найдены."

    parts = [f"🏥 Найдено ветклиник: {len(clinics)}\n"]
    for clinic in clinics[:max_items]:
        parts.append(format_vet_clinic(clinic))
        parts.append("")

    return "\n".join(parts)


def format_shelter(shelter: dict) -> str:
    """Форматировать приют для животных."""
    place = shelter.get("place", shelter)

    lines = []
    lines.append(f"🏠 **{place.get('title', 'Приют')}**")

    if spec := place.get("specialization"):
        lines.append(f"   🐾 {', '.join(spec)}")

    if addr := place.get("address"):
        lines.append(f"   📍 {addr}")

    if phones := place.get("phone"):
        lines.append(f"   📞 {_format_phones(phones)}")

    if terms := place.get("terms_of_visit"):
        # Первая строка условий посещения
        first_line = terms.split("\n")[0][:100]
        lines.append(f"   🕐 {first_line}")

    if website := place.get("website"):
        lines.append(f"   🔗 {website}")

    return "\n".join(lines)


def format_shelters_list(shelters: list[dict], max_items: int = 5) -> str:
    """Форматировать список приютов."""
    if not shelters:
        return "Приюты не найдены."

    parts = [f"🏠 Найдено приютов: {len(shelters)}\n"]
    for shelter in shelters[:max_items]:
        parts.append(format_shelter(shelter))
        parts.append("")

    return "\n".join(parts)


# =============================================================================
# EVENTS Formatters
# =============================================================================


def format_event(event: dict) -> str:
    """Форматировать мероприятие."""
    place = event.get("place", event)

    lines = []
    title = place.get("title") or place.get("title_short", "Мероприятие")
    lines.append(f"🎉 **{title}**")

    if categories := place.get("categories"):
        lines.append(f"   🏷️ {', '.join(categories)}")

    if start := place.get("start_date"):
        end = place.get("end_date")
        if end and start != end:
            lines.append(f"   📅 {_format_datetime(start)} — {_format_datetime(end)}")
        else:
            lines.append(f"   📅 {_format_datetime(start)}")

    if location := place.get("location_title"):
        lines.append(f"   🏛️ {location}")

    if addr := place.get("address"):
        lines.append(f"   📍 {addr}")

    if age := place.get("age"):
        lines.append(f"   👤 {age}+")

    if desc := place.get("description_short") or place.get("description"):
        # Обрезаем описание
        short_desc = desc[:150] + "..." if len(desc) > 150 else desc
        lines.append(f"   📝 {short_desc}")

    return "\n".join(lines)


def format_events_list(events: list[dict], max_items: int = 5) -> str:
    """Форматировать список мероприятий."""
    if not events:
        return "Мероприятия не найдены."

    parts = [f"🎉 Найдено мероприятий: {len(events)}\n"]
    for event in events[:max_items]:
        parts.append(format_event(event))
        parts.append("")

    return "\n".join(parts)


def format_sport_event(event: dict) -> str:
    """Форматировать спортивное мероприятие."""
    lines = []
    lines.append(f"🏆 **{event.get('title', 'Мероприятие')}**")

    if event_type := event.get("type"):
        lines.append(f"   🏷️ {event_type}")

    if categories := event.get("categoria"):
        lines.append(f"   🎯 {', '.join(categories)}")

    if start_date := event.get("start_date"):
        time_str = event.get("start_time", "")
        if time_str:
            time_str = time_str.replace("-", ":")
        lines.append(f"   📅 {start_date} {time_str}")

    if addr := event.get("address"):
        lines.append(f"   📍 {addr}")

    if desc := event.get("description"):
        short_desc = desc[:150] + "..." if len(desc) > 150 else desc
        lines.append(f"   📝 {short_desc}")

    return "\n".join(lines)


def format_sport_events_list(events: list[dict], max_items: int = 5) -> str:
    """Форматировать список спортивных мероприятий."""
    if not events:
        return "Спортивные мероприятия не найдены."

    parts = [f"🏆 Найдено мероприятий: {len(events)}\n"]
    for event in events[:max_items]:
        parts.append(format_sport_event(event))
        parts.append("")

    return "\n".join(parts)


# =============================================================================
# PENSIONER Formatters
# =============================================================================


def format_pensioner_service(service: dict) -> str:
    """Форматировать услугу для пенсионеров."""
    lines = []
    lines.append(f"👴 **{service.get('title', 'Услуга')}**")

    if categories := service.get("category"):
        lines.append(f"   🏷️ {', '.join(categories)}")

    if location := service.get("location_title"):
        lines.append(f"   🏛️ {location}")

    if addr := service.get("address"):
        lines.append(f"   📍 {addr}")

    if district := service.get("district"):
        lines.append(f"   📍 {district} район")

    if desc := service.get("description"):
        # Убираем HTML теги и обрезаем
        import re
        clean_desc = re.sub(r'<[^>]+>', ' ', desc)
        clean_desc = re.sub(r'\s+', ' ', clean_desc).strip()
        short_desc = clean_desc[:200] + "..." if len(clean_desc) > 200 else clean_desc
        lines.append(f"   📝 {short_desc}")

    return "\n".join(lines)


def format_pensioner_services_list(services: list[dict], max_items: int = 5) -> str:
    """Форматировать список услуг для пенсионеров."""
    if not services:
        return "Услуги для пенсионеров не найдены."

    parts = [f"👴 Найдено услуг: {len(services)}\n"]
    for service in services[:max_items]:
        parts.append(format_pensioner_service(service))
        parts.append("")

    return "\n".join(parts)


# =============================================================================
# SPORT Formatters
# =============================================================================


def format_sportground(ground: dict) -> str:
    """Форматировать спортплощадку."""
    place = ground.get("place", ground)

    lines = []
    name = place.get("name", "Спортплощадка")
    lines.append(f"🏋️ **{name}**")

    if categories := place.get("categories"):
        lines.append(f"   🏷️ {categories}")

    if addr := place.get("address"):
        lines.append(f"   📍 {addr}")

    if district := place.get("district"):
        lines.append(f"   📍 {district}")

    return "\n".join(lines)


def format_sportgrounds_list(grounds: list[dict], max_items: int = 5) -> str:
    """Форматировать список спортплощадок."""
    if not grounds:
        return "Спортплощадки не найдены."

    parts = [f"🏋️ Найдено площадок: {len(grounds)}\n"]
    for ground in grounds[:max_items]:
        parts.append(format_sportground(ground))
        parts.append("")

    return "\n".join(parts)


# =============================================================================
# TOURISM Formatters
# =============================================================================


def format_beautiful_place(place_data: dict) -> str:
    """Форматировать достопримечательность."""
    place = place_data.get("place", place_data)

    lines = []
    lines.append(f"🏛️ **{place.get('title', 'Место')}**")

    if categories := place.get("categories"):
        lines.append(f"   🏷️ {', '.join(categories)}")

    if addr := place.get("address"):
        lines.append(f"   📍 {addr}")

    if district := place.get("district"):
        lines.append(f"   📍 {district}")

    if desc := place.get("description"):
        short_desc = desc[:200] + "..." if len(desc) > 200 else desc
        lines.append(f"   📝 {short_desc}")

    if site := place.get("site"):
        lines.append(f"   🔗 {site}")

    return "\n".join(lines)


def format_beautiful_places_list(places: list[dict], max_items: int = 5) -> str:
    """Форматировать список достопримечательностей."""
    if not places:
        return "Достопримечательности не найдены."

    parts = [f"🏛️ Найдено мест: {len(places)}\n"]
    for place in places[:max_items]:
        parts.append(format_beautiful_place(place))
        parts.append("")

    return "\n".join(parts)


# =============================================================================
# RECYCLING Formatters
# =============================================================================


def format_recycling_point(point: dict) -> str:
    """Форматировать точку переработки."""
    props = point.get("properties", point)

    lines = []
    lines.append(f"♻️ **{props.get('title', 'Пункт приёма')}**")

    if addr := props.get("address"):
        lines.append(f"   📍 {addr}")

    if content := props.get("content_text"):
        lines.append(f"   🗂️ Принимают: {content}")

    if distance := point.get("distance"):
        lines.append(f"   📏 {_format_distance(distance)}")

    return "\n".join(lines)


def format_recycling_by_category(data: list[dict], max_per_category: int = 2) -> str:
    """Форматировать точки переработки по категориям."""
    if not data:
        return "Пункты переработки не найдены."

    parts = ["♻️ **Ближайшие пункты переработки:**\n"]

    for category_data in data:
        category = category_data.get("Category", "Прочее")
        objects = category_data.get("Objects", [])

        if objects:
            parts.append(f"**{category}** ({len(objects)} шт.):")
            for obj in objects[:max_per_category]:
                parts.append(format_recycling_point(obj))
            parts.append("")

    return "\n".join(parts)


# =============================================================================
# INFRASTRUCTURE Formatters
# =============================================================================


def format_disconnection(disc: dict) -> str:
    """Форматировать отключение."""
    lines = []

    disc_type = disc.get("type", "Отключение")
    lines.append(f"⚠️ **{disc_type}**")

    if addr := disc.get("address"):
        lines.append(f"   📍 {addr}")

    if start := disc.get("start_date"):
        end = disc.get("end_date", "")
        lines.append(f"   📅 {_format_datetime(start)} — {_format_datetime(end)}")

    if reason := disc.get("reason"):
        lines.append(f"   📝 Причина: {reason}")

    return "\n".join(lines)


def format_disconnections_list(discs: list[dict]) -> str:
    """Форматировать список отключений."""
    if not discs:
        return "Отключений не найдено. Всё работает! ✅"

    parts = [f"⚠️ Найдено отключений: {len(discs)}\n"]
    for disc in discs[:5]:
        parts.append(format_disconnection(disc))
        parts.append("")

    return "\n".join(parts)


def format_road_work(work: dict) -> str:
    """Форматировать дорожные работы."""
    lines = []

    lines.append(f"🚧 **{work.get('work_type', 'Дорожные работы')}**")

    if order := work.get("order_number"):
        lines.append(f"   📄 {order}")

    return "\n".join(lines)


def format_road_works_list(works: list[dict], max_items: int = 5) -> str:
    """Форматировать список дорожных работ."""
    if not works:
        return "Дорожных работ не найдено."

    # Группируем по типу
    by_type: dict[str, int] = {}
    for work in works:
        work_type = work.get("work_type", "Прочее")
        by_type[work_type] = by_type.get(work_type, 0) + 1

    parts = [f"🚧 Найдено дорожных работ: {len(works)}\n"]
    parts.append("**По типам:**")
    for work_type, count in sorted(by_type.items(), key=lambda x: -x[1])[:10]:
        parts.append(f"  • {work_type}: {count}")

    return "\n".join(parts)


# =============================================================================
# EDUCATION Formatters
# =============================================================================


def format_school(school: dict) -> str:
    """Форматировать школу."""
    lines = []

    name = school.get("name") or school.get("school_name", "Школа")
    lines.append(f"🏫 **{name}**")

    if addr := school.get("address"):
        lines.append(f"   📍 {addr}")

    if phone := school.get("phone"):
        lines.append(f"   📞 {_format_phones(phone) if isinstance(phone, list) else phone}")

    if email := school.get("email"):
        lines.append(f"   ✉️ {email}")

    if website := school.get("website"):
        lines.append(f"   🔗 {website}")

    return "\n".join(lines)


def format_schools_list(schools: list[dict], max_items: int = 5) -> str:
    """Форматировать список школ."""
    if not schools:
        return "Школы не найдены."

    parts = [f"🏫 Найдено школ: {len(schools)}\n"]
    for school in schools[:max_items]:
        parts.append(format_school(school))
        parts.append("")

    return "\n".join(parts)


def format_kindergarten(kg: dict) -> str:
    """Форматировать детский сад."""
    lines = []

    name = kg.get("doo_short") or kg.get("name", "Детский сад")
    lines.append(f"🧒 **{name}**")

    if status := kg.get("doo_status"):
        lines.append(f"   📊 {status}")

    if spots := kg.get("sum"):
        lines.append(f"   👶 Мест: {spots}")

    if district := kg.get("district"):
        lines.append(f"   📍 {district} район")

    return "\n".join(lines)


def format_kindergartens_list(kgs: list[dict], max_items: int = 10) -> str:
    """Форматировать список детских садов."""
    if not kgs:
        return "Детские сады не найдены."

    # Считаем общее количество мест
    total_spots = sum(kg.get("sum", 0) for kg in kgs)

    parts = [f"🧒 Найдено детских садов: {len(kgs)}"]
    parts.append(f"👶 Всего мест: {total_spots}\n")

    for kg in kgs[:max_items]:
        parts.append(format_kindergarten(kg))
        parts.append("")

    if len(kgs) > max_items:
        parts.append(f"... и ещё {len(kgs) - max_items}")

    return "\n".join(parts)


# =============================================================================
# HEALTHCARE Formatters
# =============================================================================


def format_polyclinic(poly: dict) -> str:
    """Форматировать поликлинику."""
    lines = []

    name = poly.get("name") or poly.get("title", "Поликлиника")
    lines.append(f"🏥 **{name}**")

    if addr := poly.get("address"):
        lines.append(f"   📍 {addr}")

    if phone := poly.get("phone"):
        lines.append(f"   📞 {_format_phones(phone) if isinstance(phone, list) else phone}")

    if hours := poly.get("working_hours") or poly.get("schedule"):
        lines.append(f"   🕐 {hours}")

    if website := poly.get("website"):
        lines.append(f"   🔗 {website}")

    return "\n".join(lines)


def format_polyclinics_list(polys: list[dict], max_items: int = 5) -> str:
    """Форматировать список поликлиник."""
    if not polys:
        return "Поликлиники не найдены."

    parts = [f"🏥 Найдено поликлиник: {len(polys)}\n"]
    for poly in polys[:max_items]:
        parts.append(format_polyclinic(poly))
        parts.append("")

    return "\n".join(parts)


# =============================================================================
# Generic Formatter (fallback)
# =============================================================================


def format_generic_item(item: dict, title_keys: list[str] | None = None) -> str:
    """Универсальный форматтер для неизвестных типов."""
    title_keys = title_keys or ["title", "name", "title_short"]

    # Ищем заголовок
    title = None
    for key in title_keys:
        if key in item:
            title = item[key]
            break

    lines = [f"📌 **{title or 'Объект'}**"]

    # Добавляем известные поля
    if addr := item.get("address"):
        lines.append(f"   📍 {addr}")

    if phone := item.get("phone"):
        lines.append(f"   📞 {_format_phones(phone) if isinstance(phone, list) else phone}")

    return "\n".join(lines)


def format_generic_list(items: list[dict], max_items: int = 5) -> str:
    """Универсальный форматтер для списков."""
    if not items:
        return "Ничего не найдено."

    parts = [f"Найдено: {len(items)}\n"]
    for item in items[:max_items]:
        parts.append(format_generic_item(item))
        parts.append("")

    return "\n".join(parts)
