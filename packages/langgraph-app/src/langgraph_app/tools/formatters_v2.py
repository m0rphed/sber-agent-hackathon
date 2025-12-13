"""
Форматтеры V2 для преобразования JSON ответов API в читаемый текст.

Исправленная версия с корректными полями из реальных API ответов.
Все форматтеры поддерживают пагинацию через limit/offset.

API поля проверены по дампам в notebooks/api_dumps/
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any


# =============================================================================
# Helper Functions
# =============================================================================


def _safe_get(data: dict, *keys: str, default: str = '') -> str:
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


def _format_phones(phones: list | str | None) -> str:
    """Форматировать телефоны (список или строку)."""
    if not phones:
        return ''
    if isinstance(phones, list):
        return ', '.join(str(p) for p in phones)
    return str(phones)


def _format_distance(distance: float | None) -> str:
    """Форматировать расстояние."""
    if distance is None:
        return ''
    if distance < 1:
        return f'{int(distance * 1000)} м'
    return f'{distance:.1f} км'


def _format_date(date_str: str | None, fmt: str = '%d.%m.%Y') -> str:
    """Форматировать дату."""
    if not date_str:
        return ''
    try:
        for input_fmt in ['%Y-%m-%dT%H:%M:%S', '%Y-%m-%dT%H:%M:%S.%f', '%Y-%m-%d', '%d-%m-%Y']:
            try:
                dt = datetime.strptime(date_str[:19], input_fmt[:19])
                return dt.strftime(fmt)
            except ValueError:
                continue
        return date_str
    except Exception:
        return date_str


def _format_datetime(date_str: str | None) -> str:
    """Форматировать дату и время."""
    if not date_str:
        return ''
    try:
        for input_fmt in ['%Y-%m-%dT%H:%M:%S', '%Y-%m-%dT%H:%M:%S.%f']:
            try:
                dt = datetime.strptime(date_str[:19], input_fmt[:19])
                return dt.strftime('%d.%m.%Y %H:%M')
            except ValueError:
                continue
        return date_str
    except Exception:
        return date_str


def _clean_html(text: str) -> str:
    """Убрать HTML теги из текста."""
    clean = re.sub(r'<[^>]+>', ' ', text)
    return re.sub(r'\s+', ' ', clean).strip()


def _truncate(text: str, max_len: int = 150) -> str:
    """Обрезать текст до указанной длины."""
    if len(text) <= max_len:
        return text
    return text[:max_len] + '...'


def _pagination_info(offset: int, shown: int, total: int, item_name: str = 'элементов') -> str:
    """Сформировать строку с информацией о пагинации."""
    shown_end = offset + shown
    lines = [f'\n📊 Показано {offset + 1}-{shown_end} из {total}']
    if shown_end < total:
        remaining = total - shown_end
        lines.append(f'💡 Ещё {remaining} {item_name}. Используйте offset={shown_end} для следующих.')
    return '\n'.join(lines)


# =============================================================================
# MFC Formatters
# API fields: name, address, nearest_metro, phone[], working_hours, link, accessible_env[]
# =============================================================================


def format_mfc(mfc: dict) -> str:
    """Форматировать один МФЦ."""
    lines = []
    lines.append(f'🏢 **{mfc.get("name", "МФЦ")}**')

    if addr := mfc.get('address'):
        lines.append(f'   📍 {addr}')

    if hours := mfc.get('working_hours'):
        lines.append(f'   🕐 {hours}')

    if phones := mfc.get('phone'):
        lines.append(f'   📞 {_format_phones(phones)}')

    if metro := mfc.get('nearest_metro'):
        lines.append(f'   🚇 Метро: {metro}')

    if link := mfc.get('link'):
        lines.append(f'   🔗 {link}')

    if accessible := mfc.get('accessible_env'):
        if accessible and isinstance(accessible, list):
            lines.append('   ♿ Доступная среда: ' + ', '.join(accessible[:3]))

    return '\n'.join(lines)


def format_mfc_list(mfc_list: list[dict], limit: int = 10, offset: int = 0) -> str:
    """Форматировать список МФЦ с пагинацией."""
    if not mfc_list:
        return 'МФЦ не найдены.'

    total = len(mfc_list)
    paginated = mfc_list[offset : offset + limit]

    if not paginated:
        return f'МФЦ не найдены (offset={offset} выходит за пределы списка из {total}).'

    parts = [f'🏢 Найдено МФЦ: {total}\n']
    for i, mfc in enumerate(paginated, start=offset + 1):
        parts.append(f'{i}. {format_mfc(mfc)}')
        parts.append('')

    parts.append(_pagination_info(offset, len(paginated), total, 'МФЦ'))
    return '\n'.join(parts)


# =============================================================================
# Polyclinic Formatters
# API fields: clinic_name, clinic_address, phone[], url, vk, district_add
# =============================================================================


def format_polyclinic(poly: dict) -> str:
    """Форматировать поликлинику."""
    lines = []

    # API возвращает clinic_name, не name
    name = poly.get('clinic_name') or poly.get('name') or poly.get('title', 'Поликлиника')
    lines.append(f'🏥 **{name}**')

    # API возвращает clinic_address, не address
    if addr := poly.get('clinic_address') or poly.get('address'):
        lines.append(f'   📍 {addr}')

    if district := poly.get('district_add') or poly.get('district'):
        lines.append(f'   🏘️ {district} район')

    if phones := poly.get('phone'):
        lines.append(f'   📞 {_format_phones(phones)}')

    if url := poly.get('url'):
        lines.append(f'   🔗 {url}')

    if vk := poly.get('vk'):
        lines.append(f'   💬 VK: {vk}')

    return '\n'.join(lines)


def format_polyclinics_list(polys: list[dict], limit: int = 10, offset: int = 0) -> str:
    """Форматировать список поликлиник с пагинацией."""
    if not polys:
        return 'Поликлиники не найдены.'

    total = len(polys)
    paginated = polys[offset : offset + limit]

    if not paginated:
        return f'Поликлиники не найдены (offset={offset} выходит за пределы списка из {total}).'

    parts = [f'🏥 Найдено поликлиник: {total}\n']
    for i, poly in enumerate(paginated, start=offset + 1):
        parts.append(f'{i}. {format_polyclinic(poly)}')
        parts.append('')

    parts.append(_pagination_info(offset, len(paginated), total, 'поликлиник'))
    return '\n'.join(parts)


# =============================================================================
# School Formatters
# API fields: name, full_name, kind, district, address, phone[], site, head, vacant, subject[], profile[]
# =============================================================================


def format_school(school: dict) -> str:
    """Форматировать школу."""
    lines = []

    name = school.get('name') or school.get('full_name') or school.get('school_name', 'Школа')
    lines.append(f'🏫 **{name}**')

    if kind := school.get('kind'):
        lines.append(f'   📋 {kind}')

    if addr := school.get('address'):
        lines.append(f'   📍 {addr}')

    if district := school.get('district'):
        lines.append(f'   🏘️ {district} район')

    if phones := school.get('phone'):
        lines.append(f'   📞 {_format_phones(phones)}')

    if site := school.get('site'):
        lines.append(f'   🔗 {site}')

    if head := school.get('head'):
        lines.append(f'   👤 Директор: {head}')

    if (vacant := school.get('vacant')) is not None:
        lines.append(f'   🪑 Свободных мест: {vacant}')

    if profiles := school.get('profile'):
        if isinstance(profiles, list) and profiles:
            lines.append(f'   📚 Профиль: {", ".join(profiles)}')

    return '\n'.join(lines)


def format_schools_list(schools: list[dict], limit: int = 10, offset: int = 0) -> str:
    """Форматировать список школ с пагинацией."""
    if not schools:
        return 'Школы не найдены.'

    total = len(schools)
    paginated = schools[offset : offset + limit]

    if not paginated:
        return f'Школы не найдены (offset={offset} выходит за пределы списка из {total}).'

    parts = [f'🏫 Найдено школ: {total}\n']
    for i, school in enumerate(paginated, start=offset + 1):
        parts.append(f'{i}. {format_school(school)}')
        parts.append('')

    parts.append(_pagination_info(offset, len(paginated), total, 'школ'))
    return '\n'.join(parts)


# =============================================================================
# Kindergarten Formatters
# API fields: doo_short, building_id, sum (spots), coordinates, doo_status, district
# =============================================================================


def format_kindergarten(kg: dict) -> str:
    """Форматировать детский сад."""
    lines = []

    name = kg.get('doo_short') or kg.get('name', 'Детский сад')
    lines.append(f'🧒 **{name}**')

    if status := kg.get('doo_status'):
        lines.append(f'   📊 {status}')

    if (spots := kg.get('sum')) is not None:
        lines.append(f'   👶 Свободных мест: {spots}')

    if district := kg.get('district'):
        lines.append(f'   📍 {district} район')

    if building_id := kg.get('building_id'):
        lines.append(f'   🆔 ID: {building_id}')

    return '\n'.join(lines)


def format_kindergartens_list(kgs: list[dict], limit: int = 10, offset: int = 0) -> str:
    """Форматировать список детских садов с пагинацией."""
    if not kgs:
        return 'Детские сады не найдены.'

    total = len(kgs)
    paginated = kgs[offset : offset + limit]

    if not paginated:
        return f'Детские сады не найдены (offset={offset} выходит за пределы списка из {total}).'

    # Считаем общее количество мест
    total_spots = sum(kg.get('sum', 0) for kg in kgs)

    parts = [f'🧒 Найдено детских садов: {total}']
    parts.append(f'👶 Всего свободных мест: {total_spots}\n')

    for i, kg in enumerate(paginated, start=offset + 1):
        parts.append(f'{i}. {format_kindergarten(kg)}')
        parts.append('')

    parts.append(_pagination_info(offset, len(paginated), total, 'садов'))
    return '\n'.join(parts)


# =============================================================================
# Management Company Formatters
# API fields: data.full_name, data.short_name, data.legal_form, data.head_fio,
#             data.juridical_address, data.phone, data.inn, data.head_position
# =============================================================================


def format_management_company(mc: dict) -> str:
    """Форматировать управляющую компанию."""
    # API возвращает данные во вложенном data
    data = mc.get('data', mc)

    lines = []
    name = data.get('full_name') or data.get('short_name') or data.get('name', 'УК')
    lines.append(f'🏢 **{name}**')

    if legal_form := data.get('legal_form'):
        lines.append(f'   📋 {legal_form}')

    if addr := data.get('juridical_address'):
        lines.append(f'   📍 {addr}')

    if head := data.get('head_fio'):
        position = data.get('head_position', '')
        if position:
            lines.append(f'   👤 {position}: {head}')
        else:
            lines.append(f'   👤 Руководитель: {head}')

    if inn := data.get('inn'):
        lines.append(f'   🔢 ИНН: {inn}')

    if phone := data.get('phone'):
        lines.append(f'   📞 {_format_phones(phone)}')

    if site := data.get('site'):
        lines.append(f'   🔗 {site}')

    if email := data.get('email'):
        lines.append(f'   ✉️ {email}')

    return '\n'.join(lines)


# =============================================================================
# Pet Parks Formatters
# API fields: place.type, place.title, place.address, place.coordinates, place.location.distance
# =============================================================================


def format_pet_park(park: dict) -> str:
    """Форматировать площадку для выгула."""
    place = park.get('place', park)

    lines = []
    lines.append(f'🐕 **{place.get("title", "Площадка")}**')

    if park_type := place.get('type'):
        lines.append(f'   🏷️ {park_type}')

    if addr := place.get('address'):
        lines.append(f'   📍 {addr}')

    if location := place.get('location'):
        if distance := location.get('distance'):
            lines.append(f'   📏 {_format_distance(distance)}')

    return '\n'.join(lines)


def format_pet_parks_list(parks: list[dict], limit: int = 10, offset: int = 0) -> str:
    """Форматировать список площадок для выгула с пагинацией."""
    if not parks:
        return 'Площадки для выгула не найдены.'

    total = len(parks)
    paginated = parks[offset : offset + limit]

    if not paginated:
        return f'Площадки не найдены (offset={offset} выходит за пределы списка из {total}).'

    parts = ['🐕 Площадки для выгула собак:\n']
    for i, park in enumerate(paginated, start=offset + 1):
        parts.append(f'{i}. {format_pet_park(park)}')

    parts.append(_pagination_info(offset, len(paginated), total, 'площадок'))
    return '\n'.join(parts)


# =============================================================================
# Vet Clinics Formatters
# API fields: place.title, place.address, place.location.distance, place.phone
# =============================================================================


def format_vet_clinic(clinic: dict) -> str:
    """Форматировать ветклинику."""
    place = clinic.get('place', clinic)

    lines = []
    lines.append(f'🏥 **{place.get("title", "Ветклиника")}**')

    if addr := place.get('address'):
        lines.append(f'   📍 {addr}')

    if phones := place.get('phone'):
        lines.append(f'   📞 {_format_phones(phones)}')

    if location := place.get('location'):
        if distance := location.get('distance'):
            lines.append(f'   📏 {_format_distance(distance)}')

    return '\n'.join(lines)


def format_vet_clinics_list(clinics: list[dict], limit: int = 10, offset: int = 0) -> str:
    """Форматировать список ветклиник с пагинацией."""
    if not clinics:
        return 'Ветклиники не найдены.'

    total = len(clinics)
    paginated = clinics[offset : offset + limit]

    if not paginated:
        return f'Ветклиники не найдены (offset={offset} выходит за пределы списка из {total}).'

    parts = ['🏥 Ветеринарные клиники:\n']
    for i, clinic in enumerate(paginated, start=offset + 1):
        parts.append(f'{i}. {format_vet_clinic(clinic)}')

    parts.append(_pagination_info(offset, len(paginated), total, 'ветклиник'))
    return '\n'.join(parts)


# =============================================================================
# Pet Shelters Formatters
# API fields: place.title, place.specialization[], place.description,
#             place.address, place.terms_of_visit, place.phone[], place.website
# =============================================================================


def format_shelter(shelter: dict) -> str:
    """Форматировать приют для животных."""
    place = shelter.get('place', shelter)

    lines = []
    lines.append(f'🏠 **{place.get("title", "Приют")}**')

    if spec := place.get('specialization'):
        if isinstance(spec, list):
            lines.append(f'   🐾 {", ".join(spec)}')

    if addr := place.get('address'):
        lines.append(f'   📍 {addr}')

    if phones := place.get('phone'):
        lines.append(f'   📞 {_format_phones(phones)}')

    if terms := place.get('terms_of_visit'):
        first_line = terms.split('\n')[0][:100]
        lines.append(f'   🕐 {first_line}')

    if website := place.get('website'):
        lines.append(f'   🔗 {website}')

    return '\n'.join(lines)


def format_shelters_list(shelters: list[dict], limit: int = 10, offset: int = 0) -> str:
    """Форматировать список приютов с пагинацией."""
    if not shelters:
        return 'Приюты не найдены.'

    total = len(shelters)
    paginated = shelters[offset : offset + limit]

    if not paginated:
        return f'Приюты не найдены (offset={offset} выходит за пределы списка из {total}).'

    parts = ['🏠 Приюты для животных:\n']
    for i, shelter in enumerate(paginated, start=offset + 1):
        parts.append(f'{i}. {format_shelter(shelter)}')

    parts.append(_pagination_info(offset, len(paginated), total, 'приютов'))
    return '\n'.join(parts)


# =============================================================================
# Events Formatters
# API fields: place.title, place.description, place.categories[],
#             place.start_date, place.end_date, place.age, place.location_title, place.address
# =============================================================================


def format_event(event: dict) -> str:
    """Форматировать мероприятие."""
    place = event.get('place', event)

    lines = []
    title = place.get('title') or place.get('title_short', 'Мероприятие')
    lines.append(f'🎉 **{title}**')

    if categories := place.get('categories'):
        if isinstance(categories, list):
            lines.append(f'   🏷️ {", ".join(categories)}')

    if start := place.get('start_date'):
        end = place.get('end_date')
        if end and start != end:
            lines.append(f'   📅 {_format_datetime(start)} — {_format_datetime(end)}')
        else:
            lines.append(f'   📅 {_format_datetime(start)}')

    if location := place.get('location_title'):
        lines.append(f'   🏛️ {location}')

    if addr := place.get('address'):
        lines.append(f'   📍 {addr}')

    if (age := place.get('age')) is not None:
        lines.append(f'   👤 {age}+')

    if desc := place.get('description_short') or place.get('description'):
        lines.append(f'   📝 {_truncate(_clean_html(desc), 150)}')

    return '\n'.join(lines)


def format_events_list(events: list[dict], limit: int = 10, offset: int = 0) -> str:
    """Форматировать список мероприятий с пагинацией."""
    if not events:
        return 'Мероприятия не найдены.'

    total = len(events)
    paginated = events[offset : offset + limit]

    if not paginated:
        return f'Мероприятия не найдены (offset={offset} выходит за пределы списка из {total}).'

    parts = ['🎉 Мероприятия:\n']
    for i, event in enumerate(paginated, start=offset + 1):
        parts.append(f'{i}. {format_event(event)}')

    parts.append(_pagination_info(offset, len(paginated), total, 'мероприятий'))
    return '\n'.join(parts)


# =============================================================================
# Sport Events Formatters
# API fields: title, type, categoria[], address, start_date, start_time, description
# =============================================================================


def format_sport_event(event: dict) -> str:
    """Форматировать спортивное мероприятие."""
    lines = []
    lines.append(f'🏆 **{event.get("title", "Мероприятие")}**')

    if event_type := event.get('type'):
        lines.append(f'   🏷️ {event_type}')

    if categories := event.get('categoria'):
        if isinstance(categories, list):
            lines.append(f'   🎯 {", ".join(categories)}')

    if start_date := event.get('start_date'):
        time_str = event.get('start_time', '')
        if time_str:
            time_str = time_str.replace('-', ':')
        lines.append(f'   📅 {start_date} {time_str}'.strip())

    if addr := event.get('address'):
        lines.append(f'   📍 {addr}')

    if desc := event.get('description'):
        lines.append(f'   📝 {_truncate(_clean_html(desc), 150)}')

    return '\n'.join(lines)


def format_sport_events_list(events: list[dict], limit: int = 10, offset: int = 0) -> str:
    """Форматировать список спортивных мероприятий с пагинацией."""
    if not events:
        return 'Спортивные мероприятия не найдены.'

    total = len(events)
    paginated = events[offset : offset + limit]

    if not paginated:
        return f'Спортивные мероприятия не найдены (offset={offset} выходит за пределы списка).'

    parts = ['🏆 Спортивные мероприятия:\n']
    for i, event in enumerate(paginated, start=offset + 1):
        parts.append(f'{i}. {format_sport_event(event)}')

    parts.append(_pagination_info(offset, len(paginated), total, 'мероприятий'))
    return '\n'.join(parts)


# =============================================================================
# Pensioner Services Formatters
# API fields: title, category[], location_title, address, district, description, photos[]
# =============================================================================


def format_pensioner_service(service: dict) -> str:
    """Форматировать услугу для пенсионеров."""
    lines = []
    lines.append(f'👴 **{service.get("title", "Услуга")}**')

    if categories := service.get('category'):
        if isinstance(categories, list):
            lines.append(f'   🏷️ {", ".join(categories)}')

    if location := service.get('location_title'):
        lines.append(f'   🏛️ {location}')

    if addr := service.get('address'):
        lines.append(f'   📍 {addr}')

    if district := service.get('district'):
        lines.append(f'   🏘️ {district} район')

    if desc := service.get('description'):
        lines.append(f'   📝 {_truncate(_clean_html(desc), 200)}')

    return '\n'.join(lines)


def format_pensioner_services_list(services: list[dict], limit: int = 10, offset: int = 0) -> str:
    """Форматировать список услуг для пенсионеров с пагинацией."""
    if not services:
        return 'Услуги для пенсионеров не найдены.'

    total = len(services)
    paginated = services[offset : offset + limit]

    if not paginated:
        return f'Услуги не найдены (offset={offset} выходит за пределы списка).'

    parts = ['👴 Услуги для пенсионеров:\n']
    for i, service in enumerate(paginated, start=offset + 1):
        parts.append(f'{i}. {format_pensioner_service(service)}')

    parts.append(_pagination_info(offset, len(paginated), total, 'услуг'))
    return '\n'.join(parts)


# =============================================================================
# Sportgrounds Formatters
# API fields: place.name, place.categories, place.address, place.season, place.district
# =============================================================================


def format_sportground(ground: dict) -> str:
    """Форматировать спортплощадку."""
    place = ground.get('place', ground)

    lines = []
    name = place.get('name') or place.get('title', 'Спортплощадка')
    lines.append(f'🏋️ **{name}**')

    if categories := place.get('categories'):
        lines.append(f'   🏷️ {categories}')

    if addr := place.get('address'):
        lines.append(f'   📍 {addr}')

    if season := place.get('season'):
        lines.append(f'   📅 Сезон: {season}')

    if district := place.get('district'):
        lines.append(f'   🏘️ {district}')

    return '\n'.join(lines)


def format_sportgrounds_list(grounds: list[dict], limit: int = 10, offset: int = 0) -> str:
    """Форматировать список спортплощадок с пагинацией."""
    if not grounds:
        return 'Спортплощадки не найдены.'

    total = len(grounds)
    paginated = grounds[offset : offset + limit]

    if not paginated:
        return f'Спортплощадки не найдены (offset={offset} выходит за пределы списка).'

    parts = ['🏋️ Спортплощадки:\n']
    for i, ground in enumerate(paginated, start=offset + 1):
        parts.append(f'{i}. {format_sportground(ground)}')

    parts.append(_pagination_info(offset, len(paginated), total, 'площадок'))
    return '\n'.join(parts)


# =============================================================================
# Beautiful Places (Tourism) Formatters
# API fields: place.title, place.description, place.categories[], place.address,
#             place.district, place.site
# =============================================================================


def format_beautiful_place(place_data: dict) -> str:
    """Форматировать достопримечательность."""
    place = place_data.get('place', place_data)

    lines = []
    lines.append(f'🏛️ **{place.get("title", "Место")}**')

    if categories := place.get('categories'):
        if isinstance(categories, list):
            lines.append(f'   🏷️ {", ".join(categories)}')

    if addr := place.get('address'):
        lines.append(f'   📍 {addr}')

    if district := place.get('district'):
        lines.append(f'   🏘️ {district}')

    if desc := place.get('description'):
        lines.append(f'   📝 {_truncate(_clean_html(desc), 200)}')

    if site := place.get('site'):
        lines.append(f'   🔗 {site}')

    return '\n'.join(lines)


def format_beautiful_places_list(places: list[dict], limit: int = 10, offset: int = 0) -> str:
    """Форматировать список достопримечательностей с пагинацией."""
    if not places:
        return 'Достопримечательности не найдены.'

    total = len(places)
    paginated = places[offset : offset + limit]

    if not paginated:
        return f'Достопримечательности не найдены (offset={offset} выходит за пределы списка).'

    parts = ['🏛️ Достопримечательности:\n']
    for i, place in enumerate(paginated, start=offset + 1):
        parts.append(f'{i}. {format_beautiful_place(place)}')

    parts.append(_pagination_info(offset, len(paginated), total, 'мест'))
    return '\n'.join(parts)


# =============================================================================
# Recycling Formatters
# API fields: title, categories{}, coordinates, location.distance
# For format_recycling_by_category: Category, Count, Objects[{properties.title, properties.address, properties.content_text, distance}]
# =============================================================================


def format_recycling_point(point: dict) -> str:
    """Форматировать точку переработки."""
    props = point.get('properties', point)

    lines = []
    lines.append(f'♻️ **{props.get("title", "Пункт приёма")}**')

    if addr := props.get('address'):
        lines.append(f'   📍 {addr}')

    if content := props.get('content_text'):
        lines.append(f'   🗂️ Принимают: {content}')

    if distance := point.get('distance'):
        lines.append(f'   📏 {_format_distance(distance)}')

    return '\n'.join(lines)


def format_recycling_by_category(data: list[dict], max_per_category: int = 3) -> str:
    """Форматировать точки переработки по категориям."""
    if not data:
        return 'Пункты переработки не найдены.'

    parts = ['♻️ **Ближайшие пункты переработки:**\n']

    for category_data in data:
        category = category_data.get('Category', 'Прочее')
        objects = category_data.get('Objects', [])
        count = category_data.get('Count', len(objects))

        if objects:
            parts.append(f'**{category}** ({count} шт.):')
            for obj in objects[:max_per_category]:
                parts.append(format_recycling_point(obj))
            if count > max_per_category:
                parts.append(f'   ... и ещё {count - max_per_category}')
            parts.append('')

    return '\n'.join(parts)


# =============================================================================
# Disconnections Formatters
# API fields: type, address, start_date, end_date, reason
# =============================================================================


def format_disconnection(disc: dict) -> str:
    """Форматировать отключение."""
    lines = []

    disc_type = disc.get('type', 'Отключение')
    lines.append(f'⚠️ **{disc_type}**')

    if addr := disc.get('address'):
        lines.append(f'   📍 {addr}')

    if start := disc.get('start_date'):
        end = disc.get('end_date', '')
        if end:
            lines.append(f'   📅 {_format_datetime(start)} — {_format_datetime(end)}')
        else:
            lines.append(f'   📅 С {_format_datetime(start)}')

    if reason := disc.get('reason'):
        lines.append(f'   📝 Причина: {reason}')

    return '\n'.join(lines)


def format_disconnections_list(discs: list[dict], limit: int = 10, offset: int = 0) -> str:
    """Форматировать список отключений с пагинацией."""
    if not discs:
        return 'Отключений не найдено. Всё работает! ✅'

    total = len(discs)
    paginated = discs[offset : offset + limit]

    if not paginated:
        return f'Отключения не найдены (offset={offset} выходит за пределы списка из {total}).'

    parts = ['⚠️ Отключения:\n']
    for i, disc in enumerate(paginated, start=offset + 1):
        parts.append(f'{i}. {format_disconnection(disc)}')

    parts.append(_pagination_info(offset, len(paginated), total, 'отключений'))
    return '\n'.join(parts)


# =============================================================================
# Road Works Formatters
# API fields: order_number, work_type, polygon
# =============================================================================


def format_road_work(work: dict) -> str:
    """Форматировать дорожные работы."""
    lines = []

    lines.append(f'🚧 **{work.get("work_type", "Дорожные работы")}**')

    if order := work.get('order_number'):
        lines.append(f'   📄 Ордер: {order}')

    return '\n'.join(lines)


def format_road_works_list(works: list[dict], limit: int = 10, offset: int = 0) -> str:
    """Форматировать список дорожных работ с пагинацией."""
    if not works:
        return 'Дорожных работ не найдено.'

    total = len(works)

    # Группируем по типу для сводки
    by_type: dict[str, int] = {}
    for work in works:
        work_type = work.get('work_type', 'Прочее')
        by_type[work_type] = by_type.get(work_type, 0) + 1

    parts = [f'🚧 Найдено дорожных работ: {total}\n']
    parts.append('**По типам:**')
    for work_type, count in sorted(by_type.items(), key=lambda x: -x[1])[:10]:
        parts.append(f'  • {work_type}: {count}')

    parts.append(_pagination_info(offset, min(limit, total), total, 'работ'))
    return '\n'.join(parts)


# =============================================================================
# Tourist Routes Formatters
# API fields: place.title, place.description
# =============================================================================


def format_tourist_route(route: dict) -> str:
    """Форматировать туристический маршрут."""
    place = route.get('place', route)

    lines = []
    lines.append(f'🗺️ **{place.get("title", "Маршрут")}**')

    if desc := place.get('description'):
        lines.append(f'   {_truncate(_clean_html(desc), 200)}')

    return '\n'.join(lines)


def format_tourist_routes_list(routes: list[dict], limit: int = 10, offset: int = 0) -> str:
    """Форматировать список туристических маршрутов с пагинацией."""
    if not routes:
        return 'Туристические маршруты не найдены.'

    total = len(routes)
    paginated = routes[offset : offset + limit]

    if not paginated:
        return f'Маршруты не найдены (offset={offset} выходит за пределы списка).'

    parts = ['🗺️ Туристические маршруты:\n']
    for i, route in enumerate(paginated, start=offset + 1):
        parts.append(f'{i}. {format_tourist_route(route)}')

    parts.append(_pagination_info(offset, len(paginated), total, 'маршрутов'))
    return '\n'.join(parts)


# =============================================================================
# Generic Formatter (fallback)
# =============================================================================


def format_generic_item(item: dict, title_keys: list[str] | None = None) -> str:
    """Универсальный форматтер для неизвестных типов."""
    title_keys = title_keys or ['title', 'name', 'title_short', 'full_name']

    # Ищем заголовок
    title = None
    for key in title_keys:
        if key in item:
            title = item[key]
            break

    lines = [f'📌 **{title or "Объект"}**']

    if addr := item.get('address'):
        lines.append(f'   📍 {addr}')

    if phone := item.get('phone'):
        lines.append(f'   📞 {_format_phones(phone)}')

    return '\n'.join(lines)


def format_generic_list(items: list[dict], limit: int = 10, offset: int = 0) -> str:
    """Универсальный форматтер для списков с пагинацией."""
    if not items:
        return 'Ничего не найдено.'

    total = len(items)
    paginated = items[offset : offset + limit]

    if not paginated:
        return f'Не найдено (offset={offset} выходит за пределы списка).'

    parts = [f'📋 Найдено: {total}\n']
    for i, item in enumerate(paginated, start=offset + 1):
        parts.append(f'{i}. {format_generic_item(item)}')

    parts.append(_pagination_info(offset, len(paginated), total, 'элементов'))
    return '\n'.join(parts)
