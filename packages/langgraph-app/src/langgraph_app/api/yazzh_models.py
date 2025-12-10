from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from langgraph_app.logging_config import get_logger

logger = get_logger(__name__)


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
            lines.append('   ♿ Доступно для людей с ОВЗ')
        if self.family_hour:
            lines.append('   👨‍👩‍👧 Семейный час')
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
    waypoints: list[BeautifulPlaceRouteWaypoint] | None = Field(None, description='Точки маршрута')
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
