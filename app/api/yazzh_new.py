"""
Новый асинхронный клиент для API "Я Здесь Живу" (YAZZH)
на основе httpx с Pydantic моделями для типизации.

Этот клиент заменяет старый синхронный app.api.yazz и предоставляет:
- Асинхронные запросы через httpx
- Pydantic модели для типизации ответов
- Удобные форматтеры для человекочитаемого вывода
- Улучшенную обработку ошибок
"""

from __future__ import annotations

import json
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field

from app.config import API_GEO, API_SITE, REGION_ID
from app.logging_config import get_logger

logger = get_logger(__name__)

# ============================================================================
# Pydantic модели для типизации API ответов
# ============================================================================


class BuildingSearchResult(BaseModel):
    """Результат поиска здания по адресу"""

    model_config = ConfigDict(extra='ignore')

    id: int | str = Field(..., description='ID здания в системе YAZZH')
    full_address: str = Field(..., description='Полный адрес здания')
    latitude: float | None = Field(None, description='Широта')
    longitude: float | None = Field(None, description='Долгота')
    district: str | None = Field(None, description='Район')

    @property
    def building_id(self) -> str:
        """ID здания как строка (для использования в API запросах)"""
        return str(self.id)

    @property
    def coords(self) -> tuple[float, float] | None:
        """Координаты здания как кортеж (lat, lon)"""
        if self.latitude is not None and self.longitude is not None:
            return (self.latitude, self.longitude)
        return None


class BuildingInfo(BaseModel):
    """Расширенная информация о здании"""

    model_config = ConfigDict(extra='ignore')

    id: str = Field(..., description='ID здания')
    full_address: str | None = Field(None, description='Полный адрес')
    district: str | None = Field(None, description='Район')
    latitude: float | None = Field(None)
    longitude: float | None = Field(None)
    year_build: int | None = Field(None, description='Год постройки')
    floors: int | None = Field(None, description='Этажность')


class ManagementCompanyInfo(BaseModel):
    """Информация об управляющей компании"""

    model_config = ConfigDict(extra='ignore')

    name: str | None = Field(None, description='Название УК')
    address: str | None = Field(None, description='Адрес УК')
    phone: str | None = Field(None, description='Телефон')
    email: str | None = Field(None, description='Email')
    inn: str | None = Field(None, description='ИНН')
    ogrn: str | None = Field(None, description='ОГРН')


class MFCInfo(BaseModel):
    """Информация о МФЦ"""

    model_config = ConfigDict(extra='ignore')

    name: str | None = Field(None, description='Название МФЦ')
    address: str | None = Field(None, description='Адрес')
    nearest_metro: str | None = Field(None, description='Ближайшее метро')
    phone: str | list[str] | None = Field(None, description='Телефоны')
    working_hours: str | None = Field(None, description='Часы работы')
    coordinates: str | list | None = Field(None, description='Координаты')
    distance: float | None = Field(None, description='Расстояние в км')
    link: str | None = Field(None, description='Ссылка')
    chat_bot: str | None = Field(None, description='Чат-бот')

    @property
    def coords_tuple(self) -> tuple[float, float] | None:
        """Получить координаты как кортеж (lat, lon)"""
        if isinstance(self.coordinates, list) and len(self.coordinates) == 2:
            return (float(self.coordinates[0]), float(self.coordinates[1]))
        return None

    def format_for_human(self) -> str:
        """Форматирует информацию о МФЦ для человека"""
        lines = []
        if self.name:
            lines.append(f'📍 {self.name}')
        if self.address:
            lines.append(f'   Адрес: {self.address}')
        if self.nearest_metro:
            lines.append(f'   🚇 Метро: {self.nearest_metro}')
        if self.phone:
            phones = self.phone if isinstance(self.phone, str) else ', '.join(self.phone)
            lines.append(f'   📞 Телефон: {phones}')
        if self.working_hours:
            lines.append(f'   🕐 Часы работы: {self.working_hours}')
        if self.distance is not None:
            lines.append(f'   📏 Расстояние: {self.distance:.1f} км')
        if self.link:
            lines.append(f'   🔗 {self.link}')
        return '\n'.join(lines)


class PolyclinicInfo(BaseModel):
    """Информация о поликлинике"""

    model_config = ConfigDict(extra='ignore')

    clinic_name: str | None = Field(None, description='Название поликлиники')
    clinic_address: str | None = Field(None, description='Адрес')
    phone: list[str] | str | None = Field(None, description='Телефоны')
    url: str | None = Field(None, description='Сайт')
    type: str | None = Field(None, description='Тип (взрослая/детская)')

    def format_for_human(self) -> str:
        """Форматирует информацию о поликлинике для человека"""
        lines = []
        if self.clinic_name:
            lines.append(f'🏥 {self.clinic_name}')
        if self.type:
            lines.append(f'   Тип: {self.type}')
        if self.clinic_address:
            lines.append(f'   Адрес: {self.clinic_address}')
        if self.phone:
            phones = self.phone if isinstance(self.phone, str) else ', '.join(self.phone)
            lines.append(f'   📞 Телефон: {phones}')
        if self.url:
            lines.append(f'   🔗 {self.url}')
        return '\n'.join(lines)


class SchoolInfo(BaseModel):
    """Информация о школе"""

    model_config = ConfigDict(extra='ignore')

    id: int | None = Field(None)
    uid: str | None = Field(None, description='UID школы')
    name: str | None = Field(None, description='Краткое название')
    full_name: str | None = Field(None, description='Полное название школы')
    address: str | None = Field(None)
    district: str | None = Field(None, description='Район')
    phone: list[str] | str | None = Field(None, description='Телефоны')
    site: str | None = Field(None, description='Сайт')
    email: str | None = Field(None)
    kind: str | None = Field(None, description='Вид школы')
    head: str | None = Field(None, description='Директор')
    vacant: int | None = Field(None, description='Свободные места')
    subject: list[str] | None = Field(None, description='Профильные предметы')
    profile: list[str] | None = Field(None, description='Профили обучения')
    coordinates: list[float] | None = Field(None, description='Координаты')

    def format_for_human(self) -> str:
        """Форматирует информацию о школе для человека"""
        lines = []
        school_name = self.name or self.full_name
        if school_name:
            lines.append(f'🏫 {school_name}')
        if self.kind:
            lines.append(f'   Вид: {self.kind}')
        if self.address:
            lines.append(f'   Адрес: {self.address}')
        if self.district:
            lines.append(f'   Район: {self.district}')
        if self.vacant is not None:
            lines.append(f'   📚 Свободных мест: {self.vacant}')
        if self.profile:
            lines.append(f'   📖 Профили: {", ".join(self.profile)}')
        if self.head:
            lines.append(f'   👤 Директор: {self.head}')
        if self.phone:
            phones = self.phone if isinstance(self.phone, list) else [self.phone]
            lines.append(f'   📞 Телефон: {", ".join(phones)}')
        if self.site:
            lines.append(f'   🔗 {self.site}')
        return '\n'.join(lines)


class DistrictInfo(BaseModel):
    """Информация о районе города"""

    model_config = ConfigDict(extra='ignore')

    id: int | None = Field(None)
    name: str = Field(..., description='Название района')


class KindergartenInfo(BaseModel):
    """Информация о детском саде (ДОУ)"""

    model_config = ConfigDict(extra='ignore')

    short_name: str | None = Field(None, alias='doo_short', description='Краткое название')
    building_id: str | None = Field(None, description='ID здания')
    available_spots: int | None = Field(None, alias='sum', description='Свободные места')
    coordinates: list[float] | None = Field(None, description='Координаты [lat, lon]')
    status: str | None = Field(None, alias='doo_status', description='Статус')

    def format_for_human(self) -> str:
        """Форматирует информацию о детском саде для человека"""
        lines = []
        if self.short_name:
            lines.append(f'🏒 {self.short_name}')
        if self.status:
            lines.append(f'   Статус: {self.status}')
        if self.available_spots is not None:
            lines.append(f'   👶 Свободных мест: {self.available_spots}')
        if self.coordinates:
            lines.append(f'   📍 Координаты: {self.coordinates[0]:.6f}, {self.coordinates[1]:.6f}')
        return '\n'.join(lines)


class DisconnectionInfo(BaseModel):
    """Информация об отключении коммунальных услуг (вода, электричество)"""

    model_config = ConfigDict(extra='ignore')

    id: int | None = Field(None)
    type: str | None = Field(None, alias='type_name', description='Тип отключения')
    resource_type: str | None = Field(None, description='Тип ресурса (ГВС, ХВС, электричество)')
    start_date: str | None = Field(None, description='Дата начала отключения')
    end_date: str | None = Field(None, description='Дата окончания отключения')
    reason: str | None = Field(None, description='Причина отключения')
    address: str | None = Field(None, description='Адрес')
    organization: str | None = Field(None, description='Организация')

    def format_for_human(self) -> str:
        """Форматирует информацию об отключении для человека"""
        lines = []
        resource = self.resource_type or self.type or 'Отключение'
        lines.append(f'⚠️ {resource}')
        if self.start_date and self.end_date:
            lines.append(f'   📅 Период: {self.start_date} — {self.end_date}')
        elif self.start_date:
            lines.append(f'   📅 Начало: {self.start_date}')
        if self.reason:
            lines.append(f'   📝 Причина: {self.reason}')
        if self.organization:
            lines.append(f'   🏢 Организация: {self.organization}')
        if self.address:
            lines.append(f'   📍 Адрес: {self.address}')
        return '\n'.join(lines)


class SportEventInfo(BaseModel):
    """Информация о спортивном мероприятии"""

    model_config = ConfigDict(extra='ignore')

    id: int | None = Field(None)
    title: str | None = Field(None, description='Название мероприятия')
    type: str | None = Field(None, description='Тип (Физкультурное/Спортивное)')
    categoria: list[str] | None = Field(None, description='Категории/виды спорта')
    description: str | None = Field(None, description='Описание')
    address: str | None = Field(None, description='Адрес проведения')
    start_date: str | None = Field(None, description='Дата начала (dd-mm-yyyy)')
    start_time: str | None = Field(None, description='Время начала (hh-mm-ss)')
    end_date: str | None = Field(None, description='Дата окончания')
    end_time: str | None = Field(None, description='Время окончания')
    images: list[str] | None = Field(None, description='Изображения')
    district: str | None = Field(None, description='Район')
    ovz: bool | None = Field(None, description='Доступно для инвалидов')
    family_hour: bool | None = Field(None, description='Семейный час')

    def format_for_human(self) -> str:
        """Форматирует информацию о спортивном мероприятии для человека"""
        lines = []
        if self.title:
            lines.append(f'🏆 {self.title}')
        if self.type:
            lines.append(f'   Тип: {self.type}')
        if self.categoria:
            lines.append(f'   🏅 {", ".join(self.categoria)}')
        if self.start_date:
            # Конвертируем dd-mm-yyyy в более читаемый формат
            date_str = self.start_date
            time_str = self.start_time.replace('-', ':') if self.start_time else ''
            lines.append(f'   📅 Дата: {date_str} {time_str}')
        if self.address:
            lines.append(f'   📍 {self.address}')
        if self.district:
            lines.append(f'   🏙️ Район: {self.district}')
        if self.ovz:
            lines.append(f'   ♿ Доступно для людей с ОВЗ')
        if self.family_hour:
            lines.append(f'   👨‍👩‍👧 Семейный час')
        if self.description:
            desc = (
                self.description[:150] + '...' if len(self.description) > 150 else self.description
            )
            lines.append(f'   📝 {desc}')
        return '\n'.join(lines)


class EventInfo(BaseModel):
    """Информация о событии/мероприятии из афиши"""

    model_config = ConfigDict(extra='ignore')

    id: int | None = Field(None)
    title: str | None = Field(None, description='Название мероприятия')
    title_short: str | None = Field(None, description='Краткое название')
    categories: list[str] | None = Field(None, description='Категории')
    description_short: str | None = Field(None, description='Краткое описание')
    start_date: str | None = Field(None, description='Дата начала')
    end_date: str | None = Field(None, description='Дата окончания')
    location_title: str | None = Field(None, description='Название места')
    address: str | None = Field(None, description='Адрес')
    age: int | None = Field(None, description='Возрастное ограничение')
    photo: str | None = Field(None, description='Фото')
    coordinates: list[float] | None = Field(None, description='Координаты')

    def format_for_human(self) -> str:
        """Форматирует информацию о мероприятии для человека"""
        lines = []
        if self.title:
            lines.append(f'🎭 {self.title}')
        if self.categories:
            lines.append(f'   Категория: {", ".join(self.categories)}')
        if self.start_date:
            # Форматируем дату красиво
            date_str = self.start_date.split('T')[0] if 'T' in self.start_date else self.start_date
            time_str = self.start_date.split('T')[1][:5] if 'T' in self.start_date else ''
            lines.append(f'   📅 Дата: {date_str} {time_str}')
        if self.location_title:
            lines.append(f'   📍 {self.location_title}')
        if self.address:
            lines.append(f'   Адрес: {self.address}')
        if self.age is not None:
            lines.append(f'   {self.age}+')
        if self.description_short:
            # Убираем HTML теги и обрезаем до 150 символов
            import re

            desc = re.sub(r'<[^>]+>', '', self.description_short).strip()
            if len(desc) > 150:
                desc = desc[:147] + '...'
            lines.append(f'   📝 {desc}')
        return '\n'.join(lines)


class PensionerServiceInfo(BaseModel):
    """Информация об услуге для пенсионеров (программа Долголетие)"""

    model_config = ConfigDict(extra='ignore')

    id: str | None = Field(None)
    title: str | None = Field(None, description='Название услуги')
    category: list[str] | None = Field(None, description='Категории')
    location_title: str | None = Field(None, description='Название учреждения')
    address: str | None = Field(None, description='Адрес')
    district: str | None = Field(None, description='Район')
    description: str | None = Field(None, description='Описание')
    photos: list[str] | None = Field(None, description='Фотографии')
    icon: str | None = Field(None, description='Иконка категории')

    def format_for_human(self) -> str:
        """Форматирует информацию об услуге для человека"""
        lines = []
        if self.title:
            lines.append(f'👴 {self.title}')
        if self.category:
            lines.append(f'   Категория: {", ".join(self.category)}')
        if self.location_title:
            # Обрезаем длинные названия учреждений
            loc = self.location_title
            if len(loc) > 80:
                loc = loc[:77] + '...'
            lines.append(f'   🏢 {loc}')
        if self.address:
            lines.append(f'   📍 {self.address}')
        if self.district:
            lines.append(f'   🏙️ Район: {self.district}')
        if self.description:
            desc = self.description
            if len(desc) > 200:
                desc = desc[:197] + '...'
            lines.append(f'   📝 {desc}')
        return '\n'.join(lines)


class MemorableDateInfo(BaseModel):
    """Информация о памятной дате в истории Санкт-Петербурга"""

    model_config = ConfigDict(extra='ignore')

    id: int | None = Field(None)
    title: str | None = Field(None, description='Название события')
    date: str | None = Field(None, description='Дата события (ISO)')
    description: str | None = Field(None, description='Описание')
    str_date: str | None = Field(None, description='Дата прописью')

    def format_for_human(self) -> str:
        """Форматирует информацию о памятной дате для человека"""
        lines = []
        if self.title:
            lines.append(f'📅 {self.title}')
        if self.date:
            # Извлекаем год из ISO даты
            try:
                year = self.date.split('-')[0]
                lines.append(f'   📆 Год: {year}')
            except Exception:
                pass
        if self.str_date:
            lines.append(f'   🗓️ {self.str_date}')
        if self.description:
            lines.append(f'   📖 {self.description}')
        return '\n'.join(lines)


class SportgroundCountInfo(BaseModel):
    """Информация о количестве спортплощадок"""

    model_config = ConfigDict(extra='ignore')

    count: int = Field(..., description='Количество площадок')
    region: str | None = Field(None, description='Регион (по городу)')
    district: str | None = Field(None, description='Район')
    district_id: int | None = Field(None, description='ID района')

    def format_for_human(self) -> str:
        """Форматирует информацию о количестве площадок"""
        if self.district:
            return f'🏟️ {self.district}: {self.count} площадок'
        elif self.region:
            return f'🏟️ {self.region}: {self.count} площадок'
        return f'🏟️ Количество площадок: {self.count}'


class SportgroundInfo(BaseModel):
    """Информация о спортивной площадке"""

    model_config = ConfigDict(extra='ignore')

    id: int = Field(..., description='ID площадки')
    name: str | None = Field(None, description='Название')
    categories: str | None = Field(None, description='Категории спорта (через запятую)')
    address: str | None = Field(None, description='Адрес')
    coordinates: list[float] | None = Field(None, description='Координаты [lat, lon]')
    district: str | None = Field(None, description='Район')
    location: str | None = Field(None, description='Дополнительная локация')

    def format_for_human(self) -> str:
        """Форматирует информацию о площадке"""
        lines = []
        if self.name:
            lines.append(f'🏟️ {self.name}')
        if self.categories:
            lines.append(f'   🏀 Виды спорта: {self.categories}')
        if self.address:
            lines.append(f'   📍 {self.address}')
        if self.district:
            lines.append(f'   🏙️ Район: {self.district}')
        return '\n'.join(lines)


# ============================================================================
# Tier 2: Дорожные работы ГАТИ
# ============================================================================


class RoadWorkDistrictInfo(BaseModel):
    """Информация о дорожных работах в районе"""

    model_config = ConfigDict(extra='ignore')

    district_id: int = Field(..., description='ID района')
    district: str = Field(..., description='Название района')
    count: int = Field(..., description='Количество работ')

    def format_for_human(self) -> str:
        """Форматирует информацию для человека"""
        return f'🚧 {self.district}: {self.count} работ'


class RoadWorkStats(BaseModel):
    """Статистика дорожных работ по городу"""

    model_config = ConfigDict(extra='ignore')

    count: int = Field(..., description='Общее количество работ')
    count_district: list[RoadWorkDistrictInfo] = Field(
        default_factory=list,
        description='Количество по районам',
    )


class RoadWorkInfo(BaseModel):
    """Информация о конкретных дорожных работах"""

    model_config = ConfigDict(extra='ignore')

    id: int = Field(..., description='ID работы')
    title: str | None = Field(None, description='Название/описание работ')
    address: str | None = Field(None, description='Адрес')
    district: str | None = Field(None, description='Район')
    work_type: str | None = Field(None, description='Тип работ')
    coordinates: list[float] | None = Field(None, description='Координаты')
    date_start: str | None = Field(None, description='Дата начала')
    date_end: str | None = Field(None, description='Дата окончания')
    organization: str | None = Field(None, description='Организация')
    distance: float | None = Field(None, description='Расстояние в км')

    def format_for_human(self) -> str:
        """Форматирует информацию для человека"""
        lines = []
        # Используем work_type как основной текст если нет title
        main_text = self.title or self.work_type or 'Дорожные работы'
        lines.append(f'🚧 {main_text}')
        if self.address:
            lines.append(f'   📍 {self.address}')
        elif self.coordinates:
            lines.append(f'   📍 Координаты: {self.coordinates[0]:.5f}, {self.coordinates[1]:.5f}')
        if self.work_type and self.title:
            # Показываем work_type только если есть отдельный title
            lines.append(f'   🔧 Тип: {self.work_type}')
        if self.date_start and self.date_end:
            lines.append(f'   📅 {self.date_start} — {self.date_end}')
        elif self.date_start:
            lines.append(f'   📅 С {self.date_start}')
        if self.organization:
            lines.append(f'   🏢 {self.organization}')
        if self.distance:
            lines.append(f'   📏 Расстояние: {self.distance:.1f} км')
        return '\n'.join(lines)


# ============================================================================
# Tier 2: Ветклиники и парки для питомцев
# ============================================================================


class VetClinicInfo(BaseModel):
    """Информация о ветеринарной клинике"""

    model_config = ConfigDict(extra='ignore')

    id: int = Field(..., description='ID клиники')
    type: str | None = Field(None, description='Тип (Ветклиника)')
    title: str | None = Field(None, description='Название')
    address: str | None = Field(None, description='Адрес')
    coordinates: list[float] | None = Field(None, description='Координаты')
    phone: list[str] | None = Field(None, description='Телефоны')
    website: str | None = Field(None, description='Сайт')
    operating_mode: str | None = Field(None, description='Режим работы')
    around_the_clock: bool | None = Field(None, description='Круглосуточно')
    list_service: list[str] | None = Field(None, description='Услуги')
    distance: float | None = Field(None, description='Расстояние в км')

    def format_for_human(self) -> str:
        """Форматирует информацию для человека"""
        lines = []
        if self.title:
            lines.append(f'🏥 {self.title}')
        if self.address:
            lines.append(f'   📍 {self.address}')
        if self.phone:
            lines.append(f'   📞 {", ".join(self.phone)}')
        if self.around_the_clock:
            lines.append('   ⏰ Круглосуточно')
        elif self.operating_mode:
            # Берём первую строку режима работы
            mode = self.operating_mode.split('\n')[0][:80]
            lines.append(f'   ⏰ {mode}')
        if self.list_service and len(self.list_service) > 0:
            services = ', '.join(self.list_service[:5])
            if len(self.list_service) > 5:
                services += f' и ещё {len(self.list_service) - 5}'
            lines.append(f'   💊 Услуги: {services}')
        if self.distance is not None:
            lines.append(f'   📏 Расстояние: {self.distance:.1f} км')
        return '\n'.join(lines)


class PetParkInfo(BaseModel):
    """Информация о площадке/парке для питомцев"""

    model_config = ConfigDict(extra='ignore')

    id: str | int = Field(..., description='ID площадки')
    type: str | None = Field(None, description='Тип (Площадка/Парк)')
    title: str | None = Field(None, description='Название')
    address: str | None = Field(None, description='Адрес')
    coordinates: list[float] | None = Field(None, description='Координаты')
    distance: float | None = Field(None, description='Расстояние в км')

    def format_for_human(self) -> str:
        """Форматирует информацию для человека"""
        lines = []
        emoji = '🌳' if self.type == 'Парк' else '🐕'
        if self.title:
            lines.append(f'{emoji} {self.title}')
        if self.address:
            lines.append(f'   📍 {self.address}')
        if self.type:
            lines.append(f'   🏷️ Тип: {self.type}')
        if self.distance is not None:
            lines.append(f'   📏 Расстояние: {self.distance:.1f} км')
        return '\n'.join(lines)


# ============================================================================
# Tier 2: Школы по району
# ============================================================================


class SchoolMapInfo(BaseModel):
    """Информация о школе из карты школ"""

    model_config = ConfigDict(extra='ignore')

    id: int = Field(..., description='ID школы')
    name: str | None = Field(None, description='Название')
    kind: str | None = Field(None, description='Тип школы')
    subject: list[str] | None = Field(None, description='Углублённые предметы')
    district: str | None = Field(None, description='Район')
    address: str | None = Field(None, description='Адрес')
    coordinates: list[float] | None = Field(None, description='Координаты')
    ogrn: str | None = Field(None, description='ОГРН')
    profile: list[str] | None = Field(None, description='Профили обучения')

    def format_for_human(self) -> str:
        """Форматирует информацию для человека"""
        lines = []
        if self.name:
            lines.append(f'🏫 {self.name}')
        if self.kind:
            lines.append(f'   🎓 {self.kind}')
        if self.address:
            lines.append(f'   📍 {self.address}')
        if self.subject:
            lines.append(f'   📚 Углублённое: {", ".join(self.subject)}')
        if self.profile:
            lines.append(f'   🎯 Профили: {", ".join(self.profile)}')
        return '\n'.join(lines)


# ============================================================================
# Tier 2: Красивые места и маршруты
# ============================================================================


class BeautifulPlaceInfo(BaseModel):
    """Информация о красивом месте Санкт-Петербурга"""

    model_config = ConfigDict(extra='ignore')

    id: int | str = Field(..., description='ID места')
    title: str | None = Field(None, description='Название')
    description: str | None = Field(None, description='Описание')
    address: str | None = Field(None, description='Адрес')
    district: str | None = Field(None, description='Район')
    area: str | None = Field(None, description='Область (Районы города/ЛО/Карелия)')
    coordinates: list[float] | None = Field(None, description='Координаты [lat, lon]')
    categories: list[str] | None = Field(None, description='Категории')
    keywords: str | None = Field(None, description='Ключевые слова')
    site: str | None = Field(None, description='Ссылка на источник')
    link_to_photos: list[str] | None = Field(None, description='Ссылки на фото')
    distance: float | None = Field(None, description='Расстояние в км')

    def format_for_human(self) -> str:
        """Форматирует информацию для человека"""
        lines = []
        if self.title:
            lines.append(f'🏛️ {self.title}')
        if self.categories:
            lines.append(f'   🏷️ {", ".join(self.categories)}')
        if self.address:
            lines.append(f'   📍 {self.address}')
        elif self.district:
            lines.append(f'   📍 {self.district}')
        if self.area and self.area != 'Районы города':
            lines.append(f'   🗺️ {self.area}')
        if self.description:
            desc = self.description
            if len(desc) > 200:
                desc = desc[:197] + '...'
            lines.append(f'   📝 {desc}')
        if self.distance is not None:
            lines.append(f'   📏 Расстояние: {self.distance:.1f} км')
        if self.site:
            lines.append(f'   🔗 {self.site}')
        return '\n'.join(lines)


class BeautifulPlaceRouteWaypoint(BaseModel):
    """Точка маршрута"""

    model_config = ConfigDict(extra='ignore')

    id: int | None = Field(None, description='ID точки')
    title: str | None = Field(None, description='Название')
    coordinates: list[float] | None = Field(None, description='Координаты')


class BeautifulPlaceRouteInfo(BaseModel):
    """Информация о туристическом маршруте"""

    model_config = ConfigDict(extra='ignore')

    id: int = Field(..., description='ID маршрута')
    title: str | None = Field(None, description='Название')
    description: str | None = Field(None, description='Описание')
    description_for_announcement: str | None = Field(None, description='Краткое описание')
    theme: str | None = Field(None, description='Тематика маршрута')
    type: str | None = Field(None, description='Тип маршрута')
    length_km: int | None = Field(None, description='Протяжённость в км')
    time_min: int | None = Field(None, description='Длительность в минутах')
    access_for_disabled: list[str] | None = Field(None, description='Доступность для ОВЗ')
    district: list[str] | None = Field(None, description='Районы')
    author_or_organizer: str | None = Field(None, description='Автор/организатор')
    audio: str | None = Field(None, description='Ссылка на аудиогид')
    photo: list[str] | None = Field(None, description='Ссылки на фото')
    start_point: list[float] | None = Field(None, description='Точка старта')
    waypoints: list[BeautifulPlaceRouteWaypoint] | None = Field(
        None, description='Точки маршрута'
    )
    national_tourist_routes: bool | None = Field(
        None, description='Входит в национальный справочник'
    )
    distance: float | None = Field(None, description='Расстояние до старта в км')

    def format_for_human(self) -> str:
        """Форматирует информацию для человека"""
        lines = []
        if self.title:
            lines.append(f'🚶 {self.title}')
        if self.theme:
            lines.append(f'   🎭 Тема: {self.theme}')
        if self.type:
            lines.append(f'   🏷️ Тип: {self.type}')
        # Длительность и протяжённость
        route_info = []
        if self.length_km:
            route_info.append(f'{self.length_km} км')
        if self.time_min:
            hours = self.time_min // 60
            mins = self.time_min % 60
            if hours > 0:
                route_info.append(f'{hours}ч {mins}мин' if mins else f'{hours}ч')
            else:
                route_info.append(f'{mins} мин')
        if route_info:
            lines.append(f'   📏 {" • ".join(route_info)}')
        if self.district:
            lines.append(f'   📍 Районы: {", ".join(self.district)}')
        if self.audio:
            lines.append('   🎧 Есть аудиогид')
        if self.access_for_disabled:
            lines.append(f'   ♿ Доступно: {", ".join(self.access_for_disabled)}')
        if self.national_tourist_routes:
            lines.append('   ⭐ Национальный туристический маршрут')
        if self.description_for_announcement:
            desc = self.description_for_announcement
            if len(desc) > 150:
                desc = desc[:147] + '...'
            lines.append(f'   📝 {desc}')
        if self.distance is not None:
            lines.append(f'   📏 До старта: {self.distance:.1f} км')
        if self.author_or_organizer:
            lines.append(f'   👤 {self.author_or_organizer}')
        return '\n'.join(lines)


# ============================================================================
# API Error handling
# ============================================================================


class YazzhAPIError(Exception):
    """Базовое исключение для ошибок API"""

    def __init__(self, message: str, status_code: int | None = None, response: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.response = response


class AddressNotFoundError(YazzhAPIError):
    """Адрес не найден в базе"""


class BuildingNotFoundError(YazzhAPIError):
    """Здание не найдено по ID"""


class ServiceUnavailableError(YazzhAPIError):
    """API временно недоступен (502/504 Gateway Error)"""

    def __init__(
        self, message: str = 'API временно недоступен. Попробуйте позже.', status_code: int = 502
    ):
        super().__init__(message, status_code=status_code)


# Сообщение об ошибке для пользователя
API_UNAVAILABLE_MESSAGE = (
    '⚠️ Сервис городских услуг временно недоступен.\n'
    'Пожалуйста, попробуйте повторить запрос через несколько минут.'
)


# ============================================================================
# Основной клиент API
# ============================================================================


class YazzhAsyncClient:
    """
    Асинхронный клиент для работы с API "Я Здесь Живу".

    Примеры использования:

        async with YazzhAsyncClient() as client:
            # Поиск здания по адресу
            building = await client.search_building("Невский проспект 1")

            # Получение ближайшего МФЦ
            mfc = await client.get_nearest_mfc_by_address("Большевиков 68")

            # Поликлиники по адресу
            clinics = await client.get_polyclinics_by_address("Лиговский 50")
    """

    def __init__(
        self,
        api_geo: str = API_GEO,
        api_site: str = API_SITE,
        region_id: str = REGION_ID,
        timeout: float = 30.0,
    ):
        self.api_geo = f'{api_geo.rstrip("/")}/api/v2'
        self.api_site = api_site.rstrip('/')
        # Для mancompany используется v1
        self.api_geo_v1 = f'{api_geo.rstrip("/")}/api/v1'
        self.region_id = region_id
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> YazzhAsyncClient:
        """Входим в контекстный менеджер, создаём httpx клиент"""
        self._client = httpx.AsyncClient(
            timeout=self.timeout,
            headers={'region': self.region_id},
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Закрываем httpx клиент"""
        if self._client:
            await self._client.aclose()
            self._client = None

    @property
    def client(self) -> httpx.AsyncClient:
        """Получить HTTP клиент (проверяет, что клиент создан)"""
        if self._client is None:
            raise RuntimeError(
                'YazzhAsyncClient должен использоваться как контекстный менеджер: '
                'async with YazzhAsyncClient() as client: ...'
            )
        return self._client

    def _check_gateway_errors(self, response: httpx.Response, method: str) -> None:
        """
        Проверяет ответ на наличие Gateway ошибок (502, 504).

        Raises:
            ServiceUnavailableError: Если API вернул 502 или 504
        """
        if response.status_code in (502, 504):
            logger.error(
                'api_gateway_error',
                method=method,
                status=response.status_code,
                url=str(response.url),
            )
            raise ServiceUnavailableError(
                f'API временно недоступен (HTTP {response.status_code}). Попробуйте позже.',
                status_code=response.status_code,
            )

    # -------------------------------------------------------------------------
    # Геокодирование: поиск зданий, районов
    # -------------------------------------------------------------------------

    async def search_building(
        self,
        query: str,
        count: int = 5,
    ) -> list[BuildingSearchResult]:
        """
        Поиск здания по адресу (полнотекстовый поиск).

        Args:
            query: Адрес для поиска (например: "Невский проспект 1" или "Большевиков 68")
            count: Максимальное количество результатов (по умолчанию 5, макс 12)

        Returns:
            Список найденных зданий

        Raises:
            AddressNotFoundError: Если ничего не найдено
        """
        logger.info('api_call', method='search_building', query=query, count=count)

        response = await self.client.get(
            f'{self.api_geo}/geo/buildings/search/',
            params={
                'query': query,
                'count': min(count, 12),  # API ограничение
                'region_of_search': self.region_id,
            },
        )

        self._check_gateway_errors(response, 'search_building')

        if response.status_code != 200:
            logger.warning('api_error', method='search_building', status=response.status_code)
            raise YazzhAPIError(
                f'Ошибка API при поиске адреса: {response.status_code}',
                status_code=response.status_code,
            )

        data = response.json()
        buildings_data = data.get('data', [])

        if not buildings_data:
            logger.info('api_empty_result', method='search_building', query=query)
            raise AddressNotFoundError(f'Адрес не найден: {query}')

        results = [BuildingSearchResult.model_validate(b) for b in buildings_data]
        logger.info('api_result', method='search_building', count=len(results))
        return results

    async def search_building_first(self, query: str) -> BuildingSearchResult:
        """
        Поиск здания и возврат первого результата.

        Удобный метод для случаев, когда нужен только один результат.

        Args:
            query: Адрес для поиска

        Returns:
            Информация о первом найденном здании

        Raises:
            AddressNotFoundError: Если ничего не найдено
        """
        results = await self.search_building(query, count=1)
        return results[0]

    async def get_building_info(
        self,
        building_id: str,
        output_format: str = 'extended',
    ) -> BuildingInfo:
        """
        Получить информацию о здании по его ID.

        Args:
            building_id: ID здания
            format: "short" (координаты, район) или "extended" (+ УК и др.)

        Returns:
            Информация о здании
        """
        logger.info('api_call', method='get_building_info', building_id=building_id)

        response = await self.client.get(
            f'{self.api_geo}/geo/buildings/{building_id}',
            params={'format': output_format},
        )

        self._check_gateway_errors(response, 'get_building_info')

        if response.status_code != 200:
            raise BuildingNotFoundError(
                f'Здание не найдено: {building_id}',
                status_code=response.status_code,
            )

        data = response.json()
        # API возвращает data с информацией о здании
        building_data = data.get('data', data)
        return BuildingInfo.model_validate(building_data)

    async def get_districts(self) -> list[DistrictInfo]:
        """
        Получить список районов Санкт-Петербурга.

        Returns:
            Список районов с их ID и названиями
        """
        logger.info('api_call', method='get_districts')

        response = await self.client.get(f'{self.api_geo}/geo/district/')

        self._check_gateway_errors(response, 'get_districts')

        if response.status_code != 200:
            raise YazzhAPIError(
                f'Ошибка получения списка районов: {response.status_code}',
                status_code=response.status_code,
            )

        data = response.json()
        districts_data = data.get('data', data)

        if isinstance(districts_data, list):
            return [DistrictInfo.model_validate(d) for d in districts_data]
        return []

    # -------------------------------------------------------------------------
    # Управляющие компании
    # -------------------------------------------------------------------------

    async def get_management_company(self, building_id: str) -> ManagementCompanyInfo | None:
        """
        Получить информацию об управляющей компании по ID здания.

        Args:
            building_id: ID здания

        Returns:
            Информация об УК или None если не найдена
        """
        logger.info('api_call', method='get_management_company', building_id=building_id)

        response = await self.client.get(
            f'{self.api_geo_v1}/mancompany/{building_id}',
            params={'region_of_search': self.region_id},
        )

        self._check_gateway_errors(response, 'get_management_company')

        if response.status_code != 200:
            logger.warning(
                'api_error', method='get_management_company', status=response.status_code
            )
            return None

        data = response.json()
        if not data or (isinstance(data, dict) and not data.get('data')):
            return None

        uk_data = data.get('data', data)
        if isinstance(uk_data, list) and uk_data:
            uk_data = uk_data[0]

        return ManagementCompanyInfo.model_validate(uk_data)

    async def get_management_company_by_address(self, address: str) -> ManagementCompanyInfo | None:
        """
        Получить информацию об УК по адресу.

        Комбинирует поиск здания и запрос УК.

        Args:
            address: Адрес здания

        Returns:
            Информация об УК или None
        """
        try:
            building = await self.search_building_first(address)
            return await self.get_management_company(building.building_id)
        except AddressNotFoundError:
            return None

    # -------------------------------------------------------------------------
    # МФЦ
    # -------------------------------------------------------------------------

    async def get_mfc_by_building(self, building_id: str) -> MFCInfo | None:
        """
        Получить ближайший МФЦ по ID здания.

        Args:
            building_id: ID здания

        Returns:
            Информация о ближайшем МФЦ
        """
        logger.info('api_call', method='get_mfc_by_building', building_id=building_id)

        response = await self.client.get(
            f'{self.api_site}/mfc/',
            params={'id_building': building_id},
        )

        self._check_gateway_errors(response, 'get_mfc_by_building')

        if response.status_code != 200:
            logger.warning('api_error', method='get_mfc_by_building', status=response.status_code)
            return None

        payload = response.json()

        # Парсим ответ (может быть list, dict с data, или просто dict)
        mfc_data = None
        if isinstance(payload, dict):
            data = payload.get('data')
            if isinstance(data, list) and data:
                mfc_data = data[0]
            elif data:
                mfc_data = data
            elif payload.get('name'):  # Сам payload - это МФЦ
                mfc_data = payload
        elif isinstance(payload, list) and payload:
            mfc_data = payload[0]

        if not mfc_data:
            return None

        return MFCInfo.model_validate(mfc_data)

    async def get_nearest_mfc_by_address(self, address: str) -> MFCInfo | None:
        """
        Найти ближайший МФЦ по адресу пользователя.

        Удобный метод для пользовательских запросов.

        Args:
            address: Адрес пользователя

        Returns:
            Информация о ближайшем МФЦ или None
        """
        try:
            building = await self.search_building_first(address)
            return await self.get_mfc_by_building(building.building_id)
        except AddressNotFoundError:
            return None

    async def get_all_mfc(self) -> list[MFCInfo]:
        """
        Получить список всех МФЦ в регионе.

        Returns:
            Список всех МФЦ
        """
        logger.info('api_call', method='get_all_mfc')

        response = await self.client.get(f'{self.api_site}/mfc/all/')

        self._check_gateway_errors(response, 'get_all_mfc')

        if response.status_code != 200:
            return []

        data = response.json()
        mfc_list = data.get('data', data)

        if isinstance(mfc_list, list):
            return [MFCInfo.model_validate(m) for m in mfc_list]
        return []

    async def get_mfc_by_district(self, district: str) -> list[MFCInfo]:
        """
        Получить МФЦ по району.

        Args:
            district: Название района (например: "Невский", "Адмиралтейский")

        Returns:
            Список МФЦ в указанном районе
        """
        logger.info('api_call', method='get_mfc_by_district', district=district)

        response = await self.client.get(
            f'{self.api_site}/mfc/district/',
            params={'district': district},
        )

        self._check_gateway_errors(response, 'get_mfc_by_district')

        if response.status_code != 200:
            return []

        data = response.json()
        mfc_list = data.get('data', data)

        if isinstance(mfc_list, list):
            return [MFCInfo.model_validate(m) for m in mfc_list]
        return []

    # -------------------------------------------------------------------------
    # Поликлиники
    # -------------------------------------------------------------------------

    async def get_polyclinics_by_building(self, building_id: str) -> list[PolyclinicInfo]:
        """
        Получить поликлиники, обслуживающие дом по ID здания.

        Args:
            building_id: ID здания

        Returns:
            Список поликлиник
        """
        logger.info('api_call', method='get_polyclinics_by_building', building_id=building_id)

        response = await self.client.get(
            f'{self.api_site}/polyclinics/',
            params={'id': building_id},
        )

        self._check_gateway_errors(response, 'get_polyclinics_by_building')

        if response.status_code != 200:
            return []

        data = response.json()
        if isinstance(data, list):
            return [PolyclinicInfo.model_validate(p) for p in data]
        return []

    async def get_polyclinics_by_address(self, address: str) -> list[PolyclinicInfo]:
        """
        Получить поликлиники по адресу пользователя.

        Args:
            address: Адрес пользователя

        Returns:
            Список поликлиник, обслуживающих данный адрес
        """
        try:
            building = await self.search_building_first(address)
            return await self.get_polyclinics_by_building(building.building_id)
        except AddressNotFoundError:
            return []

    # -------------------------------------------------------------------------
    # Школы
    # -------------------------------------------------------------------------

    async def get_linked_schools(self, building_id: str, scheme: int = 1) -> list[SchoolInfo]:
        """
        Получить школы, привязанные к дому (для записи в первый класс).

        Args:
            building_id: ID здания или FIAS ID
            scheme: 1 = период 2-й волны набора, 2 = остальной период

        Returns:
            Список прикреплённых школ
        """
        logger.info('api_call', method='get_linked_schools', building_id=building_id, scheme=scheme)

        response = await self.client.get(
            f'{self.api_site}/school/linked/{building_id}',
            params={'scheme': scheme},
        )

        self._check_gateway_errors(response, 'get_linked_schools')

        if response.status_code != 200:
            return []

        data = response.json()
        schools_data = data.get('data', data)

        if isinstance(schools_data, list):
            return [SchoolInfo.model_validate(s) for s in schools_data]
        return []

    async def get_linked_schools_by_address(
        self, address: str, scheme: int = 1
    ) -> list[SchoolInfo]:
        """
        Получить прикреплённые школы по адресу.

        Args:
            address: Адрес пользователя
            scheme: 1 = 2-я волна набора, 2 = остальной период

        Returns:
            Список школ
        """
        try:
            building = await self.search_building_first(address)
            return await self.get_linked_schools(building.building_id, scheme)
        except AddressNotFoundError:
            return []

    async def get_school_by_id(self, school_id: int) -> SchoolInfo | None:
        """
        Получить информацию о школе по ID.

        Args:
            school_id: ID школы

        Returns:
            Информация о школе или None
        """
        logger.info('api_call', method='get_school_by_id', school_id=school_id)

        response = await self.client.get(f'{self.api_site}/school/{school_id}')

        self._check_gateway_errors(response, 'get_school_by_id')

        if response.status_code != 200:
            return None

        data = response.json()
        return SchoolInfo.model_validate(data)

    # -------------------------------------------------------------------------
    # Справка по дому
    # -------------------------------------------------------------------------

    async def get_district_info_by_building(self, building_id: str) -> dict[str, Any]:
        """
        Получить районную справку по ID здания.

        Включает информацию о районе, муниципалитете и другие данные.

        Args:
            building_id: ID здания

        Returns:
            Словарь с информацией о районе
        """
        logger.info('api_call', method='get_district_info', building_id=building_id)

        response = await self.client.get(
            f'{self.api_site}/districts-info/building-id/{building_id}'
        )

        self._check_gateway_errors(response, 'get_district_info')

        if response.status_code != 200:
            return {}

        return response.json()

    # -------------------------------------------------------------------------
    # Отключения коммунальных услуг
    # -------------------------------------------------------------------------

    async def get_disconnections(self, building_id: str) -> list[DisconnectionInfo]:
        """
        Получить информацию об отключениях воды/электричества по ID здания.

        Args:
            building_id: ID здания

        Returns:
            Список отключений или пустой список если нет отключений
        """
        logger.info('api_call', method='get_disconnections', building_id=building_id)

        response = await self.client.get(
            f'{self.api_site}/disconnections/',
            params={'id': building_id},
        )

        self._check_gateway_errors(response, 'get_disconnections')

        # 204 = нет отключений
        if response.status_code == 204:
            logger.info('api_result', method='get_disconnections', message='no disconnections')
            return []

        if response.status_code != 200:
            logger.warning('api_error', method='get_disconnections', status=response.status_code)
            return []

        data = response.json()
        # API может вернуть список или dict с data
        if isinstance(data, list):
            return [DisconnectionInfo.model_validate(d) for d in data]
        elif isinstance(data, dict):
            items = data.get('data', [])
            if isinstance(items, list):
                return [DisconnectionInfo.model_validate(d) for d in items]
        return []

    async def get_disconnections_by_address(self, address: str) -> list[DisconnectionInfo]:
        """
        Получить информацию об отключениях по адресу.

        Args:
            address: Адрес здания

        Returns:
            Список отключений или пустой список
        """
        try:
            building = await self.search_building_first(address)
            return await self.get_disconnections(building.building_id)
        except AddressNotFoundError:
            return []

    # -------------------------------------------------------------------------
    # Спортивные мероприятия
    # -------------------------------------------------------------------------

    async def get_sport_events(
        self,
        district: str | None = None,
        categoria: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        ovz: bool | None = None,
        family_hour: bool | None = None,
        count: int = 10,
        page: int = 1,
    ) -> list[SportEventInfo]:
        """
        Получить список спортивных мероприятий.

        Args:
            district: Район (например: "Невский")
            categoria: Вид спорта (например: "Футбол", "Баскетбол")
            start_date: Дата начала в формате yyyy-mm-dd
            end_date: Дата окончания в формате yyyy-mm-dd
            ovz: True = доступно для инвалидов
            family_hour: True = программа "Семейный час"
            count: Количество результатов (макс 10)
            page: Номер страницы

        Returns:
            Список спортивных мероприятий
        """
        logger.info(
            'api_call',
            method='get_sport_events',
            district=district,
            categoria=categoria,
        )

        params: dict[str, Any] = {
            'count': min(count, 10),
            'page': page,
        }
        if district:
            params['district'] = district
        if categoria:
            params['categoria'] = categoria
        if start_date:
            params['start_date'] = start_date
        if end_date:
            params['end_date'] = end_date
        if ovz is not None:
            params['ovz'] = 'true' if ovz else 'false'
        if family_hour is not None:
            params['family_hour'] = 'true' if family_hour else 'false'

        response = await self.client.get(
            f'{self.api_site}/sport-events/',
            params=params,
        )

        self._check_gateway_errors(response, 'get_sport_events')

        if response.status_code != 200:
            logger.warning('api_error', method='get_sport_events', status=response.status_code)
            return []

        data = response.json()
        # Формат: {"status": true, "data": {"count": N, "data": [...]}}
        if isinstance(data, dict):
            inner = data.get('data', {})
            if isinstance(inner, dict):
                events_list = inner.get('data', [])
            else:
                events_list = inner
        else:
            events_list = data

        if isinstance(events_list, list):
            return [SportEventInfo.model_validate(e) for e in events_list]
        return []

    async def get_sport_event_categories(self, district: str) -> list[str]:
        """
        Получить список видов спорта для района.

        Args:
            district: Название района

        Returns:
            Список категорий/видов спорта
        """
        logger.info('api_call', method='get_sport_event_categories', district=district)

        response = await self.client.get(
            f'{self.api_site}/sport-events/categoria/',
            params={'district': district},
        )

        self._check_gateway_errors(response, 'get_sport_event_categories')

        if response.status_code != 200:
            return []

        data = response.json()
        # {"status": true, "count": N, "category": [...]}
        if isinstance(data, dict):
            return data.get('category', [])
        return []

    # -------------------------------------------------------------------------
    # Детские сады (ДОУ)
    # -------------------------------------------------------------------------

    async def get_kindergartens(
        self,
        district: str | None = None,
        age_year: int = 0,
        age_month: int = 0,
        legal_form: str = 'Государственная',
        available_spots: int = 1,
        count: int = 10,
    ) -> list[KindergartenInfo]:
        """
        Получить список детских садов по фильтрам.

        Args:
            district: Район города (например: "Невский")
            age_year: Возраст ребёнка, лет (0-9)
            age_month: Возраст ребёнка, месяцев (0-11)
            legal_form: Форма собственности ("Государственная", "Частная")
            available_spots: 1 = только со свободными местами, 0 = все
            count: Количество результатов

        Returns:
            Список детских садов
        """
        logger.info(
            'api_call',
            method='get_kindergartens',
            district=district,
            age_year=age_year,
            age_month=age_month,
        )

        params: dict[str, Any] = {
            'legal_form': legal_form,
            'age_year': age_year,
            'age_month': age_month,
            'available_spots': available_spots,
            'doo_status': 'Функционирует',
        }
        if district:
            params['district'] = district

        response = await self.client.get(
            f'{self.api_site}/dou/',
            params=params,
        )

        self._check_gateway_errors(response, 'get_kindergartens')

        if response.status_code != 200:
            logger.warning('api_error', method='get_kindergartens', status=response.status_code)
            return []

        data = response.json()
        kindergartens_data = data.get('data', data)

        if isinstance(kindergartens_data, list):
            return [KindergartenInfo.model_validate(k) for k in kindergartens_data[:count]]
        return []

    async def get_kindergarten_districts(self) -> list[str]:
        """
        Получить список районов с детскими садами.

        Returns:
            Список названий районов
        """
        logger.info('api_call', method='get_kindergarten_districts')

        response = await self.client.get(f'{self.api_site}/dou/district/')

        self._check_gateway_errors(response, 'get_kindergarten_districts')

        if response.status_code != 200:
            return []

        data = response.json()
        if isinstance(data, list):
            return data
        return data.get('data', [])

    # -------------------------------------------------------------------------
    # Афиша (мероприятия)
    # -------------------------------------------------------------------------

    async def get_events(
        self,
        start_date: str,
        end_date: str,
        category: str | None = None,
        free: bool | None = None,
        kids: bool | None = None,
        count: int = 10,
        page: int = 1,
    ) -> list[EventInfo]:
        """
        Получить список мероприятий из афиши.

        Args:
            start_date: Дата начала поиска (формат: "2025-12-04T00:00:00")
            end_date: Дата окончания поиска (формат: "2025-12-31T23:59:59")
            category: Категория мероприятия (например: "Концерт", "Выставка")
            free: True = только бесплатные, False = только платные
            kids: True = подходит для детей
            count: Количество результатов (макс 10)
            page: Номер страницы

        Returns:
            Список мероприятий
        """
        logger.info(
            'api_call',
            method='get_events',
            start_date=start_date,
            end_date=end_date,
            category=category,
        )

        params: dict[str, Any] = {
            'start_date': start_date,
            'end_date': end_date,
            'count': min(count, 10),  # API ограничение
            'page': page,
            'format': 'list',
        }
        if category:
            params['categoria'] = category
        if free is not None:
            params['free'] = free
        if kids is not None:
            params['kids'] = kids

        response = await self.client.get(
            f'{self.api_site}/afisha/all/',
            params=params,
        )

        self._check_gateway_errors(response, 'get_events')

        if response.status_code != 200:
            logger.warning('api_error', method='get_events', status=response.status_code)
            return []

        data = response.json()
        events_data = data.get('data', data)

        if isinstance(events_data, list):
            # API возвращает {"place": {...}} для каждого элемента
            result = []
            for e in events_data:
                place = e.get('place', e)
                result.append(EventInfo.model_validate(place))
            return result
        return []

    async def get_event_categories(
        self,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> dict[str, int]:
        """
        Получить список категорий мероприятий с количеством.

        Args:
            start_date: Дата начала (опционально)
            end_date: Дата окончания (опционально)

        Returns:
            Словарь {категория: количество_мероприятий}
        """
        logger.info('api_call', method='get_event_categories')

        params: dict[str, Any] = {}
        if start_date:
            params['start_date'] = start_date
        if end_date:
            params['end_date'] = end_date

        response = await self.client.get(
            f'{self.api_site}/afisha/category/all/',
            params=params,
        )

        self._check_gateway_errors(response, 'get_event_categories')

        if response.status_code != 200:
            return {}

        data = response.json()
        if isinstance(data, dict):
            # API возвращает {"type": [...], "views": {...}}
            views = data.get('views', {})
            if views:
                # Возвращаем views - там есть количество по каждой категории
                return views
            # Если views нет, создаём из type с нулевыми значениями
            return {cat: 0 for cat in data.get('type', [])}
        return {}

    # -------------------------------------------------------------------------
    # Услуги для пенсионеров (Долголетие)
    # -------------------------------------------------------------------------

    async def get_pensioner_service_categories(self) -> list[str]:
        """
        Получить список категорий услуг для пенсионеров.

        Returns:
            Список категорий (например: ["Вокал", "Здоровье", "Спорт"])
        """
        logger.info('api_call', method='get_pensioner_service_categories')

        response = await self.client.get(f'{self.api_site}/pensioner/services/category/')

        self._check_gateway_errors(response, 'get_pensioner_service_categories')

        if response.status_code != 200:
            return []

        data = response.json()
        return data.get('category', [])

    async def get_pensioner_services(
        self,
        district: str,
        categories: list[str] | None = None,
        count: int = 10,
        page: int = 1,
    ) -> list[PensionerServiceInfo]:
        """
        Получить услуги для пенсионеров по району и категориям.

        Args:
            district: Район города (например: "Невский")
            categories: Список категорий (например: ["Здоровье", "Спорт"])
            count: Количество результатов
            page: Номер страницы

        Returns:
            Список услуг для пенсионеров
        """
        logger.info(
            'api_call',
            method='get_pensioner_services',
            district=district,
            categories=categories,
        )

        params: dict[str, Any] = {
            'district': district,
            'count': count,
            'page': page,
        }
        if categories:
            params['category'] = ','.join(categories)

        response = await self.client.get(
            f'{self.api_site}/pensioner/services/',
            params=params,
        )

        self._check_gateway_errors(response, 'get_pensioner_services')

        if response.status_code != 200:
            logger.warning(
                'api_error', method='get_pensioner_services', status=response.status_code
            )
            return []

        data = response.json()
        services_data = data.get('data', [])

        if isinstance(services_data, list):
            return [PensionerServiceInfo.model_validate(s) for s in services_data]
        return []

    # -------------------------------------------------------------------------
    # Памятные даты
    # -------------------------------------------------------------------------

    async def get_memorable_dates_by_date(
        self,
        day: int,
        month: int,
    ) -> list[MemorableDateInfo]:
        """
        Получить памятные даты на конкретный день.

        Args:
            day: День месяца (1-31)
            month: Месяц (1-12)

        Returns:
            Список памятных дат для указанного дня
        """
        logger.info(
            'api_call',
            method='get_memorable_dates_by_date',
            day=day,
            month=month,
        )

        response = await self.client.get(
            f'{self.api_site}/memorable_dates/date/',
            params={'day': day, 'month': month},
        )

        self._check_gateway_errors(response, 'get_memorable_dates_by_date')

        if response.status_code != 200:
            logger.warning(
                'api_error', method='get_memorable_dates_by_date', status=response.status_code
            )
            return []

        data = response.json()
        dates_data = data.get('data', [])

        if isinstance(dates_data, list):
            return [MemorableDateInfo.model_validate(d) for d in dates_data]
        return []

    async def get_memorable_dates_today(self) -> list[MemorableDateInfo]:
        """
        Получить памятные даты на сегодня.

        Returns:
            Список памятных дат на сегодняшний день
        """
        import pendulum

        now = pendulum.now('Europe/Moscow')
        return await self.get_memorable_dates_by_date(day=now.day, month=now.month)

    # -------------------------------------------------------------------------
    # Спортплощадки
    # -------------------------------------------------------------------------

    async def get_sportgrounds_count(self) -> SportgroundCountInfo | None:
        """
        Получить общее количество спортплощадок в городе.

        Returns:
            Информация о количестве площадок
        """
        logger.info('api_call', method='get_sportgrounds_count')

        response = await self.client.get(f'{self.api_site}/sportgrounds/count/')

        self._check_gateway_errors(response, 'get_sportgrounds_count')

        if response.status_code != 200:
            return None

        data = response.json()
        return SportgroundCountInfo.model_validate(data)

    async def get_sportgrounds_count_by_district(
        self,
        district: str | None = None,
    ) -> list[SportgroundCountInfo]:
        """
        Получить количество спортплощадок по районам.

        Args:
            district: Название района (если None — все районы)

        Returns:
            Список с количеством площадок по районам
        """
        logger.info('api_call', method='get_sportgrounds_count_by_district', district=district)

        params: dict[str, str] = {}
        if district:
            params['district'] = district

        response = await self.client.get(
            f'{self.api_site}/sportgrounds/count/district/',
            params=params,
        )

        self._check_gateway_errors(response, 'get_sportgrounds_count_by_district')

        if response.status_code != 200:
            return []

        data = response.json()
        if isinstance(data, list):
            return [SportgroundCountInfo.model_validate(d) for d in data]
        return []

    async def get_sportgrounds_types(self) -> dict[str, list[str]]:
        """
        Получить список типов спортплощадок.

        Returns:
            Словарь с типами: {"summer": [...], "winter": [...], "all": [...]}
        """
        logger.info('api_call', method='get_sportgrounds_types')

        response = await self.client.get(f'{self.api_site}/sportgrounds/types/')

        self._check_gateway_errors(response, 'get_sportgrounds_types')

        if response.status_code != 200:
            return {}

        data = response.json()
        return {
            'summer': data.get('summer', []),
            'winter': data.get('winter', []),
            'all': data.get('all', []),
        }

    async def get_sportgrounds(
        self,
        district: str | None = None,
        sport_types: str | None = None,
        season: str = 'Все',
        ovz: bool | None = None,
        light: bool | None = None,
        count: int = 10,
        page: int = 1,
    ) -> tuple[list[SportgroundInfo], int]:
        """
        Получить список спортплощадок с фильтрами.

        Args:
            district: Фильтр по району (напр. "Невский")
            sport_types: Фильтр по типам спорта (напр. "Футбол, Баскетбол")
            season: Сезон - "Все", "Лето", "Зима"
            ovz: Доступность для людей с ОВЗ
            light: Наличие освещения
            count: Количество на странице
            page: Номер страницы

        Returns:
            Кортеж (список площадок, общее количество)
        """
        logger.info(
            'api_call',
            method='get_sportgrounds',
            district=district,
            sport_types=sport_types,
            season=season,
        )

        params: dict[str, str | int | bool] = {
            'page': page,
            'count': count,
        }
        if district:
            params['district'] = district
        if sport_types:
            params['types'] = sport_types
        if season:
            params['season'] = season
        if ovz is not None:
            params['ovz'] = ovz
        if light is not None:
            params['light'] = light

        response = await self.client.get(
            f'{self.api_site}/sportgrounds/',
            params=params,
        )

        self._check_gateway_errors(response, 'get_sportgrounds')

        if response.status_code != 200:
            return [], 0

        data = response.json()
        total_count = data.get('count', 0)
        items = data.get('data', [])

        sportgrounds = []
        for item in items:
            place = item.get('place', {})
            if place:
                sportgrounds.append(SportgroundInfo.model_validate(place))

        return sportgrounds, total_count

    # ========================================================================
    # Tier 2: Дорожные работы ГАТИ
    # ========================================================================

    async def get_road_works_stats(self) -> RoadWorkStats | None:
        """
        Получить статистику дорожных работ по всему городу и районам.

        Returns:
            Статистика работ с разбивкой по районам
        """
        logger.info('api_call', method='get_road_works_stats')

        response = await self.client.get(f'{self.api_site}/gati/orders/district/')

        self._check_gateway_errors(response, 'get_road_works_stats')

        if response.status_code != 200:
            return None

        data = response.json()
        return RoadWorkStats.model_validate(data)

    async def get_road_works_by_district(
        self,
        district: str | None = None,
    ) -> list[RoadWorkDistrictInfo]:
        """
        Получить статистику дорожных работ по районам.

        Args:
            district: Фильтр по району (напр. "Невский"). Пустая строка = все районы.

        Returns:
            Список с количеством работ по районам
        """
        logger.info('api_call', method='get_road_works_by_district', district=district)

        stats = await self.get_road_works_stats()
        if not stats:
            return []

        if district:
            # Фильтруем по конкретному району
            return [d for d in stats.count_district if d.district == district]
        return stats.count_district

    async def get_road_works(
        self,
        district: str | None = None,
        work_type: str | None = None,
        latitude: float | None = None,
        longitude: float | None = None,
        radius: int = 5,
        count: int = 10,
    ) -> tuple[list[RoadWorkInfo], int]:
        """
        Получить список дорожных работ.

        Args:
            district: Район (напр. "Невский")
            work_type: Тип работ
            latitude: Широта для поиска рядом
            longitude: Долгота для поиска рядом
            radius: Радиус поиска в км
            count: Количество результатов (макс 10000)

        Returns:
            Кортеж (список работ, общее количество)
        """
        logger.info(
            'api_call',
            method='get_road_works',
            district=district,
            work_type=work_type,
            count=count,
        )

        params: dict = {'count': min(count, 100)}
        if district:
            params['district'] = district
        if work_type:
            params['work_type'] = work_type
        if latitude and longitude:
            params['location_latitude'] = latitude
            params['location_longitude'] = longitude
            params['location_radius'] = radius

        response = await self.client.get(
            f'{self.api_site}/gati/orders/map/',
            params=params,
        )

        self._check_gateway_errors(response, 'get_road_works')

        if response.status_code != 200:
            return [], 0

        data = response.json()
        total_count = data.get('count', 0)
        items = data.get('data', [])

        works = []
        for item in items:
            # Извлекаем distance из location если есть
            location = item.get('location', {})
            if location:
                item['distance'] = location.get('distance')
            works.append(RoadWorkInfo.model_validate(item))

        return works, total_count

    async def get_road_works_by_address(
        self,
        address: str,
        radius: int = 3,
        count: int = 10,
    ) -> tuple[list[RoadWorkInfo], int]:
        """
        Получить дорожные работы рядом с адресом.

        Args:
            address: Адрес для поиска
            radius: Радиус в км
            count: Количество результатов

        Returns:
            Кортеж (список работ, общее количество)
        """
        buildings = await self.search_building(address, count=1)
        if not buildings:
            return [], 0

        building = buildings[0]
        return await self.get_road_works(
            latitude=building.latitude,
            longitude=building.longitude,
            radius=radius,
            count=count,
        )

    # ========================================================================
    # Tier 2: Ветклиники
    # ========================================================================

    async def get_vet_clinics(
        self,
        latitude: float,
        longitude: float,
        radius: int = 5,
    ) -> tuple[list[VetClinicInfo], int]:
        """
        Получить ветеринарные клиники рядом с координатами.

        Args:
            latitude: Широта
            longitude: Долгота
            radius: Радиус поиска в км (по умолчанию 5)

        Returns:
            Кортеж (список клиник, общее количество)
        """
        logger.info(
            'api_call',
            method='get_vet_clinics',
            lat=latitude,
            lon=longitude,
            radius=radius,
        )

        params = {
            'location_latitude': latitude,
            'location_longitude': longitude,
            'location_radius': radius,
        }

        response = await self.client.get(
            f'{self.api_site}/mypets/clinics/',
            params=params,
        )

        self._check_gateway_errors(response, 'get_vet_clinics')

        if response.status_code != 200:
            return [], 0

        data = response.json()
        total_count = data.get('count', 0)
        items = data.get('data', [])

        clinics = []
        for item in items:
            place = item.get('place', {})
            if place:
                # Извлекаем distance из location
                location = place.get('location', {})
                if location:
                    place['distance'] = location.get('distance')
                clinics.append(VetClinicInfo.model_validate(place))

        return clinics, total_count

    async def get_vet_clinics_by_address(
        self,
        address: str,
        radius: int = 5,
    ) -> tuple[list[VetClinicInfo], int]:
        """
        Получить ветеринарные клиники рядом с адресом.

        Args:
            address: Адрес для поиска
            radius: Радиус поиска в км

        Returns:
            Кортеж (список клиник, общее количество)
        """
        # Сначала получаем координаты здания
        buildings = await self.search_building(address)
        if not buildings:
            return [], 0

        # Берём первое здание из списка
        building = buildings[0]
        coords = building.coords  # property, возвращает (lat, lon) или None
        if not coords:
            return [], 0

        lat, lon = coords
        return await self.get_vet_clinics(lat, lon, radius)

    # ========================================================================
    # Tier 2: Парки и площадки для питомцев
    # ========================================================================

    async def get_pet_parks(
        self,
        latitude: float,
        longitude: float,
        radius: int = 5,
        place_type: str | None = None,
    ) -> tuple[list[PetParkInfo], int]:
        """
        Получить площадки и парки для выгула питомцев.

        Args:
            latitude: Широта
            longitude: Долгота
            radius: Радиус поиска в км (по умолчанию 5)
            place_type: Тип места ("Площадка" или "Парк")

        Returns:
            Кортеж (список мест, общее количество)
        """
        logger.info(
            'api_call',
            method='get_pet_parks',
            lat=latitude,
            lon=longitude,
            radius=radius,
            place_type=place_type,
        )

        params: dict[str, float | int | str] = {
            'location_latitude': latitude,
            'location_longitude': longitude,
            'location_radius': radius,
        }
        if place_type:
            params['type'] = place_type

        response = await self.client.get(
            f'{self.api_site}/mypets/parks-playground/',
            params=params,
        )

        self._check_gateway_errors(response, 'get_pet_parks')

        if response.status_code != 200:
            return [], 0

        data = response.json()
        total_count = data.get('count', 0)
        items = data.get('data', [])

        parks = []
        for item in items:
            place = item.get('place', {})
            if place:
                # Извлекаем distance из location
                location = place.get('location', {})
                if location:
                    place['distance'] = location.get('distance')
                parks.append(PetParkInfo.model_validate(place))

        return parks, total_count

    async def get_pet_parks_by_address(
        self,
        address: str,
        radius: int = 5,
    ) -> tuple[list[PetParkInfo], int]:
        """
        Получить площадки для питомцев рядом с адресом.

        Args:
            address: Адрес для поиска
            radius: Радиус поиска в км

        Returns:
            Кортеж (список мест, общее количество)
        """
        buildings = await self.search_building(address)
        if not buildings:
            return [], 0

        building = buildings[0]
        coords = building.coords
        if not coords:
            return [], 0

        lat, lon = coords
        return await self.get_pet_parks(lat, lon, radius)

    # ========================================================================
    # Tier 2: Школы по району
    # ========================================================================

    async def get_schools_by_district(
        self,
        district: str,
        kind: str | None = None,
        count: int = 20,
    ) -> list[SchoolMapInfo]:
        """
        Получить школы в районе.

        Args:
            district: Район (напр. "Невский")
            kind: Тип школы (напр. "Лицей", "Гимназия")
            count: Максимальное количество

        Returns:
            Список школ
        """
        logger.info(
            'api_call',
            method='get_schools_by_district',
            district=district,
            kind=kind,
        )

        response = await self.client.get(f'{self.api_site}/school/map/')

        self._check_gateway_errors(response, 'get_schools_by_district')

        if response.status_code != 200:
            return []

        data = response.json()
        all_schools = data.get('data', [])

        # Фильтруем по району
        filtered = [s for s in all_schools if s.get('district') == district]

        # Фильтруем по типу если указан
        if kind:
            filtered = [s for s in filtered if kind.lower() in (s.get('kind') or '').lower()]

        # Ограничиваем количество
        filtered = filtered[:count]

        return [SchoolMapInfo.model_validate(s) for s in filtered]

    # ========================================================================
    # Tier 2: Красивые места и туристические маршруты
    # ========================================================================

    async def get_beautiful_places(
        self,
        *,
        area: str | None = None,
        categoria: str | None = None,
        district: str | None = None,
        keywords: str | None = None,
        latitude: float | None = None,
        longitude: float | None = None,
        radius_km: int | None = None,
        count: int = 10,
        page: int = 1,
    ) -> tuple[list[BeautifulPlaceInfo], int]:
        """
        Получить список красивых мест Санкт-Петербурга.

        Args:
            area: Область (Районы города | Районы Ленинградской области | Карелия)
            categoria: Категория (Природа | Архитектура | Развлечения | Гастрономия)
            district: Район (Центральный район, Приморский район и т.д.)
            keywords: Ключевое слово (озеро, сад, архитектура, скала)
            latitude, longitude: Координаты для поиска рядом
            radius_km: Радиус поиска в км (макс. 500)
            count: Количество результатов (макс. 1000)
            page: Номер страницы

        Returns:
            Кортеж (список BeautifulPlaceInfo, общее количество)
        """
        logger.info(
            'api_call',
            method='get_beautiful_places',
            area=area,
            categoria=categoria,
            district=district,
        )

        params: dict[str, Any] = {'count': count, 'page': page}

        if area:
            params['area'] = area
        if categoria:
            params['categoria'] = categoria
        if district:
            params['district'] = district
        if keywords:
            params['keywords'] = keywords
        if latitude is not None:
            params['location_latitude'] = latitude
        if longitude is not None:
            params['location_longitude'] = longitude
        if radius_km is not None:
            params['location_radius'] = min(radius_km, 500)

        response = await self.client.get(
            f'{self.api_site}/beautiful_places/',
            params=params,
        )

        self._check_gateway_errors(response, 'get_beautiful_places')

        if response.status_code != 200:
            return [], 0

        data = response.json()
        total_count = data.get('count', 0)
        places_data = data.get('data', [])

        places = []
        for item in places_data:
            # Данные обёрнуты в 'place'
            place_data = item.get('place', item)
            # Обрабатываем distance из location
            if 'location' in place_data and place_data['location']:
                location = place_data['location']
                if isinstance(location, dict) and 'distance' in location:
                    place_data['distance'] = location['distance']
            places.append(BeautifulPlaceInfo.model_validate(place_data))

        return places, total_count

    async def get_beautiful_places_by_address(
        self,
        address: str,
        *,
        categoria: str | None = None,
        keywords: str | None = None,
        radius_km: int = 5,
        count: int = 10,
    ) -> tuple[list[BeautifulPlaceInfo], int]:
        """
        Найти красивые места рядом с адресом.

        Args:
            address: Адрес для поиска
            categoria: Категория (Природа | Архитектура | Развлечения | Гастрономия)
            keywords: Ключевое слово
            radius_km: Радиус поиска в км
            count: Количество результатов

        Returns:
            Кортеж (список BeautifulPlaceInfo, общее количество)
        """
        # Получаем координаты адреса
        buildings = await self.search_building(address, count=1)
        if not buildings:
            return [], 0

        building = buildings[0]
        if building.latitude is None or building.longitude is None:
            return [], 0

        return await self.get_beautiful_places(
            latitude=building.latitude,
            longitude=building.longitude,
            radius_km=radius_km,
            categoria=categoria,
            keywords=keywords,
            count=count,
        )

    async def get_beautiful_place_categories(self) -> list[str]:
        """
        Получить список всех категорий красивых мест.

        Returns:
            Список категорий (Природа, Архитектура, Развлечения, Гастрономия и др.)
        """
        logger.info('api_call', method='get_beautiful_place_categories')

        response = await self.client.get(f'{self.api_site}/beautiful_places/categoria/')

        self._check_gateway_errors(response, 'get_beautiful_place_categories')

        if response.status_code != 200:
            return []

        data = response.json()
        # API возвращает ключ "category", не "categoria"
        categories = data.get('category', data.get('categoria', []))
        return categories if isinstance(categories, list) else []

    async def get_beautiful_place_keywords(self) -> list[str]:
        """
        Получить список всех ключевых слов для фильтрации красивых мест.

        Returns:
            Список ключевых слов (озеро, сад, архитектура и др.)
        """
        logger.info('api_call', method='get_beautiful_place_keywords')

        response = await self.client.get(f'{self.api_site}/beautiful_places/keywords/')

        self._check_gateway_errors(response, 'get_beautiful_place_keywords')

        if response.status_code != 200:
            return []

        data = response.json()
        keywords = data.get('keywords', [])
        return keywords if isinstance(keywords, list) else []

    async def get_beautiful_place_routes(
        self,
        *,
        theme: str | None = None,
        route_type: str | None = None,
        access_for_disabled: bool | None = None,
        audio: bool | None = None,
        length_km_from: int | None = None,
        length_km_to: int | None = None,
        time_min_from: int | None = None,
        time_min_to: int | None = None,
        latitude: float | None = None,
        longitude: float | None = None,
        radius_km: int | None = None,
        count: int = 10,
        page: int = 1,
        expanded: bool = False,
    ) -> tuple[list[BeautifulPlaceRouteInfo], int]:
        """
        Получить список туристических маршрутов.

        Args:
            theme: Тематика маршрута (можно через запятую)
            route_type: Тип маршрута
            access_for_disabled: Доступность для людей с ОВЗ
            audio: Наличие аудиогида
            length_km_from, length_km_to: Диапазон протяжённости в км
            time_min_from, time_min_to: Диапазон длительности в минутах
            latitude, longitude: Координаты для поиска рядом
            radius_km: Радиус поиска в км
            count: Количество результатов
            page: Номер страницы
            expanded: Включить полное описание и waypoints

        Returns:
            Кортеж (список BeautifulPlaceRouteInfo, общее количество)
        """
        logger.info(
            'api_call',
            method='get_beautiful_place_routes',
            theme=theme,
            route_type=route_type,
        )

        params: dict[str, Any] = {'count': count, 'page': page, 'expanded': expanded}

        if theme:
            params['theme'] = theme
        if route_type:
            params['type'] = route_type
        if access_for_disabled is not None:
            params['access_for_disabled'] = access_for_disabled
        if audio is not None:
            params['audio'] = audio
        if length_km_from is not None:
            params['length_km_from'] = length_km_from
        if length_km_to is not None:
            params['length_km_to'] = length_km_to
        if time_min_from is not None:
            params['time_min_from'] = time_min_from
        if time_min_to is not None:
            params['time_min_to'] = time_min_to
        if latitude is not None:
            params['location_latitude'] = latitude
        if longitude is not None:
            params['location_longitude'] = longitude
        if radius_km is not None:
            params['location_radius'] = min(radius_km, 500)

        response = await self.client.get(
            f'{self.api_site}/beautiful_places/routes/all/',
            params=params,
        )

        self._check_gateway_errors(response, 'get_beautiful_place_routes')

        if response.status_code != 200:
            return [], 0

        data = response.json()
        total_count = data.get('count', 0)
        routes_data = data.get('data', [])

        routes = []
        for item in routes_data:
            # Данные обёрнуты в 'place'
            route_data = item.get('place', item)
            # Обрабатываем distance из location
            if 'location' in route_data and route_data['location']:
                location = route_data['location']
                if isinstance(location, dict) and 'distance' in location:
                    route_data['distance'] = location['distance']
            routes.append(BeautifulPlaceRouteInfo.model_validate(route_data))

        return routes, total_count

    async def get_beautiful_place_routes_by_address(
        self,
        address: str,
        *,
        theme: str | None = None,
        route_type: str | None = None,
        radius_km: int = 10,
        count: int = 10,
    ) -> tuple[list[BeautifulPlaceRouteInfo], int]:
        """
        Найти туристические маршруты рядом с адресом.

        Args:
            address: Адрес для поиска
            theme: Тематика маршрута
            route_type: Тип маршрута
            radius_km: Радиус поиска в км
            count: Количество результатов

        Returns:
            Кортеж (список BeautifulPlaceRouteInfo, общее количество)
        """
        # Получаем координаты адреса
        buildings = await self.search_building(address, count=1)
        if not buildings:
            return [], 0

        building = buildings[0]
        if building.latitude is None or building.longitude is None:
            return [], 0

        return await self.get_beautiful_place_routes(
            latitude=building.latitude,
            longitude=building.longitude,
            radius_km=radius_km,
            theme=theme,
            route_type=route_type,
            count=count,
        )

    async def get_beautiful_place_route_themes(self) -> list[str]:
        """
        Получить список тематик маршрутов.

        Returns:
            Список тематик
        """
        logger.info('api_call', method='get_beautiful_place_route_themes')

        response = await self.client.get(f'{self.api_site}/beautiful_places/routes/theme/')

        self._check_gateway_errors(response, 'get_beautiful_place_route_themes')

        if response.status_code != 200:
            return []

        data = response.json()
        themes = data.get('theme', [])
        return themes if isinstance(themes, list) else []

    async def get_beautiful_place_route_types(self) -> list[str]:
        """
        Получить список типов маршрутов.

        Returns:
            Список типов
        """
        logger.info('api_call', method='get_beautiful_place_route_types')

        response = await self.client.get(f'{self.api_site}/beautiful_places/routes/type/')

        self._check_gateway_errors(response, 'get_beautiful_place_route_types')

        if response.status_code != 200:
            return []

        data = response.json()
        types = data.get('type', [])
        return types if isinstance(types, list) else []


# ============================================================================
# Форматтеры для вывода в чат
# ============================================================================


def format_mfc_for_chat(mfc: MFCInfo | None) -> str:
    """Форматировать МФЦ для вывода в чат агента"""
    if mfc is None:
        return 'К сожалению, не удалось найти ближайший МФЦ по указанному адресу.'
    return mfc.format_for_human()


def format_polyclinics_for_chat(clinics: list[PolyclinicInfo]) -> str:
    """Форматировать список поликлиник для чата"""
    if not clinics:
        return 'По указанному адресу не найдено прикреплённых поликлиник.'

    lines = [f'Найдено поликлиник: {len(clinics)}\n']
    for clinic in clinics:
        lines.append(clinic.format_for_human())
        lines.append('')  # пустая строка между записями
    return '\n'.join(lines)


def format_schools_for_chat(schools: list[SchoolInfo]) -> str:
    """Форматировать список школ для чата"""
    if not schools:
        return 'По указанному адресу не найдено прикреплённых школ.'

    lines = [f'Найдено школ: {len(schools)}\n']
    for school in schools:
        lines.append(school.format_for_human())
        lines.append('')
    return '\n'.join(lines)


def format_building_search_for_chat(buildings: list[BuildingSearchResult]) -> str:
    """Форматировать результаты поиска адресов для уточнения"""
    if not buildings:
        return 'Адрес не найден. Пожалуйста, уточните адрес.'

    if len(buildings) == 1:
        return f'Найден адрес: {buildings[0].full_address}'

    lines = ['Найдено несколько адресов. Уточните, какой из них вам нужен:\n']
    for i, b in enumerate(buildings, 1):
        lines.append(f'{i}. {b.full_address}')
    return '\n'.join(lines)


def format_kindergartens_for_chat(kindergartens: list[KindergartenInfo]) -> str:
    """Форматировать список детских садов для чата"""
    if not kindergartens:
        return 'Детские сады по указанным критериям не найдены.'

    lines = [f'Найдено детских садов: {len(kindergartens)}\n']
    for kg in kindergartens:
        lines.append(kg.format_for_human())
        lines.append('')
    return '\n'.join(lines)


def format_events_for_chat(events: list[EventInfo]) -> str:
    """Форматировать список мероприятий для чата"""
    if not events:
        return 'Мероприятия по указанным критериям не найдены.'

    lines = [f'Найдено мероприятий: {len(events)}\n']
    for event in events:
        lines.append(event.format_for_human())
        lines.append('')
    return '\n'.join(lines)


def format_disconnections_for_chat(disconnections: list[DisconnectionInfo]) -> str:
    """Форматировать список отключений для чата"""
    if not disconnections:
        return '✅ По указанному адресу нет запланированных отключений воды или электричества.'

    lines = [f'⚠️ Найдено отключений: {len(disconnections)}\n']
    for disc in disconnections:
        lines.append(disc.format_for_human())
        lines.append('')
    return '\n'.join(lines)


def format_sport_events_for_chat(events: list[SportEventInfo]) -> str:
    """Форматировать список спортивных мероприятий для чата"""
    if not events:
        return 'Спортивные мероприятия по указанным критериям не найдены.'

    lines = [f'Найдено спортивных мероприятий: {len(events)}\n']
    for event in events:
        lines.append(event.format_for_human())
        lines.append('')
    return '\n'.join(lines)


def format_pensioner_services_for_chat(services: list[PensionerServiceInfo]) -> str:
    """Форматировать список услуг для пенсионеров"""
    if not services:
        return 'Услуги для пенсионеров не найдены по указанным параметрам.'

    lines = [f'Найдено услуг для пенсионеров: {len(services)}\n']
    for service in services:
        lines.append(service.format_for_human())
        lines.append('')
    return '\n'.join(lines)


def format_memorable_dates_for_chat(dates: list[MemorableDateInfo]) -> str:
    """Форматировать памятные даты"""
    if not dates:
        return 'На эту дату памятных событий не найдено.'

    lines = [f'📜 Памятные даты ({len(dates)} событий):\n']
    for date in dates:
        lines.append(date.format_for_human())
        lines.append('')
    return '\n'.join(lines)


def format_sportgrounds_count_for_chat(
    counts: list[SportgroundCountInfo] | SportgroundCountInfo | None,
) -> str:
    """Форматировать статистику спортплощадок"""
    if counts is None:
        return 'Не удалось получить информацию о спортплощадках.'

    if isinstance(counts, SportgroundCountInfo):
        return counts.format_for_human()

    if not counts:
        return 'Информация о спортплощадках не найдена.'

    # Сортируем по количеству (убывание)
    sorted_counts = sorted(counts, key=lambda x: x.count, reverse=True)

    total = sum(c.count for c in sorted_counts)
    lines = [f'🏟️ Спортплощадки по районам (всего {total}):\n']
    for c in sorted_counts:
        lines.append(f'• {c.district}: {c.count}')
    return '\n'.join(lines)


def format_sportgrounds_for_chat(
    sportgrounds: list[SportgroundInfo],
    total_count: int | None = None,
) -> str:
    """Форматировать список спортплощадок для чата"""
    if not sportgrounds:
        return 'Спортплощадки не найдены по указанным критериям.'

    lines = []
    if total_count is not None:
        lines.append(f'🏟️ Найдено спортплощадок: {total_count} (показано {len(sportgrounds)})\n')
    else:
        lines.append(f'🏟️ Найдено спортплощадок: {len(sportgrounds)}\n')

    for sg in sportgrounds:
        lines.append(sg.format_for_human())
        lines.append('')  # пустая строка

    return '\n'.join(lines)


# ============================================================================
# Tier 2: Форматтеры
# ============================================================================


def format_road_works_for_chat(
    works: list[RoadWorkDistrictInfo] | RoadWorkStats | None,
    district: str | None = None,
) -> str:
    """Форматировать статистику дорожных работ для чата"""
    if works is None:
        return 'Не удалось получить информацию о дорожных работах.'

    if isinstance(works, RoadWorkStats):
        lines = [f'🚧 Дорожные работы в Санкт-Петербурге: всего {works.count}\n']
        # Сортируем по количеству
        sorted_districts = sorted(works.count_district, key=lambda x: x.count, reverse=True)
        for d in sorted_districts:
            lines.append(f'• {d.district}: {d.count}')
        return '\n'.join(lines)

    if not works:
        if district:
            return f'В районе {district} активных дорожных работ не найдено.'
        return 'Информация о дорожных работах не найдена.'

    if len(works) == 1:
        w = works[0]
        if w.count == 0:
            return f'🚧 В районе {w.district} сейчас нет активных дорожных работ.'
        return f'🚧 В районе {w.district}: {w.count} дорожных работ.'

    # Несколько районов
    lines = ['🚧 Дорожные работы по районам:\n']
    sorted_works = sorted(works, key=lambda x: x.count, reverse=True)
    for w in sorted_works:
        lines.append(f'• {w.district}: {w.count}')
    return '\n'.join(lines)


def format_road_works_list_for_chat(
    works: list[RoadWorkInfo],
    total_count: int | None = None,
    district: str | None = None,
) -> str:
    """Форматировать список дорожных работ для чата"""
    if not works:
        if district:
            return f'В районе {district} активных дорожных работ не найдено.'
        return 'Дорожные работы в указанном месте не найдены.'

    lines = []
    header = '🚧 Дорожные работы'
    if district:
        header += f' в районе {district}'
    if total_count is not None:
        header += f': найдено {total_count}'
        if len(works) < total_count:
            header += f' (показано {len(works)})'
    lines.append(header + '\n')

    for work in works:
        lines.append(work.format_for_human())
        lines.append('')

    return '\n'.join(lines)


def format_vet_clinics_for_chat(
    clinics: list[VetClinicInfo],
    total_count: int | None = None,
) -> str:
    """Форматировать список ветклиник для чата"""
    if not clinics:
        return 'Ветеринарные клиники не найдены поблизости. Попробуйте увеличить радиус поиска.'

    lines = []
    if total_count is not None:
        lines.append(f'🏥 Найдено ветклиник: {total_count} (показано {len(clinics)})\n')
    else:
        lines.append(f'🏥 Найдено ветклиник: {len(clinics)}\n')

    for clinic in clinics:
        lines.append(clinic.format_for_human())
        lines.append('')

    return '\n'.join(lines)


def format_pet_parks_for_chat(
    parks: list[PetParkInfo],
    total_count: int | None = None,
) -> str:
    """Форматировать список парков/площадок для питомцев"""
    if not parks:
        return 'Площадки для выгула питомцев не найдены поблизости. Попробуйте увеличить радиус поиска.'

    lines = []
    if total_count is not None:
        lines.append(f'🐕 Найдено мест для выгула: {total_count} (показано {len(parks)})\n')
    else:
        lines.append(f'🐕 Найдено мест для выгула: {len(parks)}\n')

    for park in parks:
        lines.append(park.format_for_human())
        lines.append('')

    return '\n'.join(lines)


def format_schools_by_district_for_chat(
    schools: list[SchoolMapInfo],
    district: str,
) -> str:
    """Форматировать список школ в районе"""
    if not schools:
        return f'В районе {district} школы не найдены.'

    lines = [f'🏫 Школы в районе {district}: найдено {len(schools)}\n']

    for school in schools:
        lines.append(school.format_for_human())
        lines.append('')

    return '\n'.join(lines)


def format_beautiful_places_for_chat(
    places: list[BeautifulPlaceInfo],
    total_count: int | None = None,
) -> str:
    """Форматировать список красивых мест для чата"""
    if not places:
        return 'Красивые места по указанным критериям не найдены.'

    lines = []
    if total_count is not None:
        lines.append(f'🏛️ Найдено красивых мест: {total_count} (показано {len(places)})\n')
    else:
        lines.append(f'🏛️ Найдено красивых мест: {len(places)}\n')

    for place in places:
        lines.append(place.format_for_human())
        lines.append('')

    return '\n'.join(lines)


def format_beautiful_routes_for_chat(
    routes: list[BeautifulPlaceRouteInfo],
    total_count: int | None = None,
) -> str:
    """Форматировать список туристических маршрутов для чата"""
    if not routes:
        return 'Туристические маршруты по указанным критериям не найдены.'

    lines = []
    if total_count is not None:
        lines.append(f'🚶 Найдено маршрутов: {total_count} (показано {len(routes)})\n')
    else:
        lines.append(f'🚶 Найдено маршрутов: {len(routes)}\n')

    for route in routes:
        lines.append(route.format_for_human())
        lines.append('')

    return '\n'.join(lines)


# ============================================================================
# Синхронная обёртка для использования в инструментах LangChain
# ============================================================================


async def _run_async(coro):
    """Запустить асинхронную функцию"""
    return await coro


def get_sync_client_result(async_func):
    """
    Хелпер для вызова асинхронных методов клиента синхронно.

    Пример:
        result = get_sync_client_result(
            lambda client: client.get_nearest_mfc_by_address("Невский 1")
        )
    """
    import asyncio

    async def _wrapper():
        async with YazzhAsyncClient() as client:
            return await async_func(client)

    # Создаём новый event loop
    return asyncio.run(_wrapper())


# ============================================================================
# Удобные функции для использования в tools
# ============================================================================


async def find_nearest_mfc_async(address: str) -> str:
    """
    Асинхронно найти ближайший МФЦ и вернуть отформатированный результат.
    """
    async with YazzhAsyncClient() as client:
        mfc = await client.get_nearest_mfc_by_address(address)
        if mfc:
            return json.dumps(mfc.model_dump(exclude_none=True), ensure_ascii=False, indent=2)
        return 'К сожалению, не удалось найти МФЦ по указанному адресу.'


async def get_polyclinics_async(address: str) -> str:
    """
    Асинхронно получить поликлиники по адресу.
    """
    async with YazzhAsyncClient() as client:
        clinics = await client.get_polyclinics_by_address(address)
        if clinics:
            return json.dumps(
                [c.model_dump(exclude_none=True) for c in clinics],
                ensure_ascii=False,
                indent=2,
            )
        return 'По указанному адресу не найдено прикреплённых поликлиник.'


async def get_schools_async(address: str) -> str:
    """
    Асинхронно получить школы по адресу.
    """
    async with YazzhAsyncClient() as client:
        schools = await client.get_linked_schools_by_address(address)
        if schools:
            return json.dumps(
                [s.model_dump(exclude_none=True) for s in schools],
                ensure_ascii=False,
                indent=2,
            )
        return 'По указанному адресу не найдено прикреплённых школ.'


async def get_management_company_async(address: str) -> str:
    """
    Асинхронно получить информацию об УК по адресу.
    """
    async with YazzhAsyncClient() as client:
        uk = await client.get_management_company_by_address(address)
        if uk:
            return json.dumps(uk.model_dump(exclude_none=True), ensure_ascii=False, indent=2)
        return 'Информация об управляющей компании не найдена для указанного адреса.'


async def search_address_async(query: str, count: int = 5) -> str:
    """
    Асинхронно найти адреса по запросу.
    """
    async with YazzhAsyncClient() as client:
        try:
            buildings = await client.search_building(query, count)
            return json.dumps(
                [b.model_dump(exclude_none=True) for b in buildings],
                ensure_ascii=False,
                indent=2,
            )
        except AddressNotFoundError:
            return 'Адрес не найден. Пожалуйста, уточните запрос.'
