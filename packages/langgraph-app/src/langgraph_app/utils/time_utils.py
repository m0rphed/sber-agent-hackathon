"""
Утилиты для работы со временем.

Используют pendulum для корректной работы с часовым поясом Санкт-Петербурга.
Важно для инструментов, работающих с датами (события, памятные даты и т.д.).
"""

import pendulum

# Часовой пояс (aka timezone) Санкт-Петербурга (Europe/Moscow, UTC+3)
SPB_TZ = 'Europe/Moscow'


def get_spb_now() -> pendulum.DateTime:
    """
    Возвращает текущее время в Санкт-Петербурге.

    Returns:
        pendulum.DateTime с часовым поясом Europe/Moscow
    """
    return pendulum.now(SPB_TZ)


def get_today_date() -> str:
    """
    Получить сегодняшнюю дату в формате YYYY-MM-DD.

    Returns:
        Строка даты, например "2024-12-12"
    """
    return get_spb_now().format('YYYY-MM-DD')


def get_current_month() -> int:
    """
    Получить текущий месяц (1-12).

    Returns:
        Номер месяца
    """
    return get_spb_now().month


def get_current_year() -> int:
    """
    Получить текущий год.

    Returns:
        Год
    """
    return get_spb_now().year


def is_weekend() -> bool:
    """
    Проверить, является ли сегодня выходным днём (суббота или воскресенье).

    Returns:
        True если суббота или воскресенье
    """
    return get_spb_now().day_of_week in (pendulum.SATURDAY, pendulum.SUNDAY)


def format_date_for_display(date: pendulum.DateTime) -> str:
    """
    Форматировать дату для отображения пользователю.

    Args:
        date: Дата для форматирования

    Returns:
        Строка вида "12 декабря 2024"
    """
    return date.format('D MMMM YYYY', locale='ru')


def format_datetime_for_display(dt: pendulum.DateTime) -> str:
    """
    Форматировать дату и время для отображения пользователю.

    Args:
        dt: Дата/время для форматирования

    Returns:
        Строка вида "12 декабря 2024, 14:30"
    """
    return dt.format('D MMMM YYYY, HH:mm', locale='ru')


def parse_date(date_str: str) -> pendulum.DateTime | None:
    """
    Парсинг строки даты в pendulum.DateTime.

    Поддерживает форматы:
    - YYYY-MM-DD
    - DD.MM.YYYY
    - DD/MM/YYYY

    Args:
        date_str: Строка с датой

    Returns:
        pendulum.DateTime или None если не удалось распарсить
    """
    formats = [
        'YYYY-MM-DD',
        'DD.MM.YYYY',
        'DD/MM/YYYY',
    ]

    for fmt in formats:
        try:
            return pendulum.from_format(date_str, fmt, tz=SPB_TZ)
        except ValueError:
            continue

    return None


def get_date_range_for_month(year: int | None = None, month: int | None = None) -> tuple[str, str]:
    """
    Возвращает диапазон дат для указанного месяца.

    Args:
        year: Год (по умолчанию текущий)
        month: Месяц (по умолчанию текущий)

    Returns:
        Кортеж (start_date, end_date) в формате YYYY-MM-DD
    """
    now = get_spb_now()
    year = year or now.year
    month = month or now.month

    start = pendulum.datetime(year, month, 1, tz=SPB_TZ)
    end = start.end_of('month')

    return start.format('YYYY-MM-DD'), end.format('YYYY-MM-DD')
