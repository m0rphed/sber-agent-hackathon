# """
# LangChain Tools для работы с API "Я Здесь Живу"
# """

# import json

# from langchain_core.tools import tool

# from app.logging_config import get_logger

# logger = get_logger(__name__)

# from app.api.yazzh_new import (
#     API_UNAVAILABLE_MESSAGE,
#     AddressNotFoundError,
#     ServiceUnavailableError,
#     format_building_search_for_chat,
#     format_disconnections_for_chat,
#     format_events_for_chat,
#     format_kindergartens_for_chat,
#     format_polyclinics_for_chat,
#     format_schools_for_chat,
#     format_sport_events_for_chat,
#     get_sync_client_result,
# )

# # ленивый импорт клиента, чтобы избежать циклических зависимостей
# _client = None


# def _get_client():
#     """
#     Получает singleton клиента API (старый синхронный CityAppClient)
#     """
#     global _client
#     if _client is None:
#         from app.api.yazz import CityAppClient

#         _client = CityAppClient()
#     return _client


# # -----------------------------------------------------------------------------
# # БАЗОВЫЕ ТУЛЫ (УЖЕ БЫЛИ)
# # -----------------------------------------------------------------------------


# @tool
# def find_nearest_mfc_tool(address: str) -> str:
#     """
#     Найти ближайший МФЦ (Многофункциональный центр) по адресу пользователя.

#     Используй этот инструмент, когда пользователь спрашивает:
#     - Где находится ближайший МФЦ?
#     - Как найти МФЦ рядом с моим домом?
#     - Адрес МФЦ около [адрес]
#     - Часы работы МФЦ

#     Args:
#         address: Адрес пользователя в Санкт-Петербурге (например: "Невский проспект 1" или "Большевиков 68")

#     Returns:
#         Информация о ближайшем МФЦ в формате JSON (название, адрес, телефоны, часы работы)
#     """
#     logger.info('tool_call', tool='find_nearest_mfc', address=address)

#     client = _get_client()
#     result = client.find_nearest_mfc(address)

#     if result is None:
#         logger.warning('tool_no_result', tool='find_nearest_mfc', address=address)
#         return 'К сожалению, не удалось найти МФЦ по указанному адресу. Пожалуйста, уточните адрес.'

#     logger.info('tool_result', tool='find_nearest_mfc', mfc_name=result.get('name', 'N/A'))
#     return json.dumps(result, ensure_ascii=False, indent=2)


# @tool
# def get_pensioner_categories_tool() -> str:
#     """
#     Получить список категорий услуг для пенсионеров.

#     Используй этот инструмент, когда пользователь спрашивает:
#     - Какие услуги есть для пенсионеров?
#     - Какие кружки/секции доступны для пожилых?
#     - Категории занятий для пенсионеров

#     Returns:
#         Список доступных категорий услуг для пенсионеров
#     """
#     logger.info('tool_call', tool='get_pensioner_categories')

#     client = _get_client()
#     result = client.pensioner_service_category()

#     if result is None:
#         logger.warning('tool_no_result', tool='get_pensioner_categories')
#         return 'Не удалось получить список категорий услуг.'

#     count = len(result) if isinstance(result, list) else 1
#     logger.info('tool_result', tool='get_pensioner_categories', categories_count=count)
#     return json.dumps(result, ensure_ascii=False, indent=2)


# @tool
# def get_pensioner_services_tool(district: str, categories: str) -> str:
#     """
#     Найти услуги для пенсионеров по району и категориям.

#     Используй этот инструмент, когда пользователь спрашивает:
#     - Какие занятия для пенсионеров есть в [район]?
#     - Где записаться на компьютерные курсы для пожилых?
#     - Кружки для пенсионеров в Невском районе

#     Args:
#         district: Название района Санкт-Петербурга (например: "Невский", "Центральный")
#         categories: Категории услуг через запятую (например: "Вокал,Компьютерные курсы")

#     Returns:
#         Список услуг для пенсионеров в указанном районе
#     """
#     logger.info(
#         'tool_call',
#         tool='get_pensioner_services',
#         district=district,
#         categories=categories,
#     )

#     client = _get_client()
#     category_list = [c.strip() for c in categories.split(',')]
#     result = client.pensioner_services(district, category_list)

#     if result is None:
#         logger.warning(
#             'tool_no_result',
#             tool='get_pensioner_services',
#             district=district,
#         )
#         return 'Не удалось найти услуги по указанным параметрам.'

#     count = len(result) if isinstance(result, list) else 1
#     logger.info('tool_result', tool='get_pensioner_services', services_count=count)
#     return json.dumps(result, ensure_ascii=False, indent=2)


# # -----------------------------------------------------------------------------
# # НОВЫЕ ТУЛЫ НА ОСНОВЕ YazzhAsyncClient (app.api.yazzh_new)
# #   Сценарии 2.1–2.6
# # -----------------------------------------------------------------------------

# @tool
# def search_address_candidates_tool(query: str, count: int = 5) -> str:
#     """
#     Поиск и уточнение адреса пользователя.

#     Вспомогательный инструмент для ВСЕХ сценариев 2.1–2.6,
#     когда адрес введён неполно или может быть несколько вариантов.

#     Используй этот инструмент, когда:
#     - Пользователь вводит неточный адрес: "ленина 10" и т.п.
#     - Нужно предложить варианты адресов для уточнения.

#     Args:
#         query: Строка адреса, как её ввёл пользователь.
#         count: Максимальное количество вариантов.

#     Returns:
#         Список найденных адресов в человекочитаемом виде
#         или сообщение, что адрес не найден / сервис недоступен.
#     """
#     logger.info('tool_call', tool='search_address_candidates', query=query, count=count)

#     async def _async_call(client):
#         return await client.search_building(query, count)

#     try:
#         buildings = get_sync_client_result(_async_call)
#     except ServiceUnavailableError:
#         logger.error('tool_error', tool='search_address_candidates', query=query, exc_info=True)
#         return API_UNAVAILABLE_MESSAGE
#     except AddressNotFoundError:
#         logger.info('tool_no_result', tool='search_address_candidates', query=query)
#         return 'Адрес не найден. Пожалуйста, уточните адрес.'
#     except Exception as e:
#         logger.error('tool_error', tool='search_address_candidates', query=query, error=str(e))
#         return 'Произошла ошибка при поиске адреса. Попробуйте переформулировать запрос.'

#     logger.info(
#         'tool_result',
#         tool='search_address_candidates',
#         query=query,
#         count=len(buildings),
#     )
#     return format_building_search_for_chat(buildings)


# @tool
# def get_house_reference_tool(address: str) -> str:
#     """
#     Справка по дому и району (жизненные ситуации, госуслуги по месту жительства).

#     Сценарии:
#     - 2.1: Поиск справочной информации о госуслугах (регистрация, документы, соцуслуги)
#       привязанных к месту жительства.
#     - 2.2: Общая информация о работе местных органов по адресу.
#     - 2.3: Подводка к мерам соцподдержки (куда обращаться в своём районе).
#     - 2.6: Общие вопросы о жизни в районе/муниципалитете.

#     Используй этот инструмент, когда пользователь спрашивает:
#     - К какому району относится мой дом?
#     - Какая администрация / муниципалитет у моего адреса?
#     - Куда обращаться по жилищным/районным вопросам по адресу [адрес]?

#     Args:
#         address: Адрес пользователя.

#     Returns:
#         Структурированная справка по дому и району в формате JSON.
#     """
#     logger.info('tool_call', tool='get_house_reference', address=address)

#     async def _async_call(client):
#         building = await client.search_building_first(address)
#         district_info = await client.get_district_info_by_building(building.building_id)
#         # УК и отключения как важные части "жизненных ситуаций"
#         management_company = await client.get_management_company(building.building_id)
#         disconnections = await client.get_disconnections(building.building_id)

#         return {
#             'input_address': address,
#             'normalized_address': building.full_address,
#             'building_id': building.building_id,
#             'district': building.district,
#             'district_info': district_info,
#             'management_company': (
#                 management_company.model_dump(exclude_none=True) if management_company else None
#             ),
#             'disconnections': [d.model_dump(exclude_none=True) for d in disconnections]
#             if disconnections
#             else [],
#         }

#     try:
#         result = get_sync_client_result(_async_call)
#     except ServiceUnavailableError:
#         logger.error('tool_error', tool='get_house_reference', address=address, exc_info=True)
#         return API_UNAVAILABLE_MESSAGE
#     except AddressNotFoundError:
#         logger.info('tool_no_result', tool='get_house_reference', address=address)
#         return 'Адрес не найден. Пожалуйста, уточните адрес.'
#     except Exception as e:
#         logger.error('tool_error', tool='get_house_reference', address=address, error=str(e))
#         return 'Не удалось получить справку по дому. Попробуйте уточнить адрес.'

#     logger.info(
#         'tool_result',
#         tool='get_house_reference',
#         address=address,
#         building_id=result.get('building_id'),
#     )
#     return json.dumps(result, ensure_ascii=False, indent=2)


# @tool
# def get_polyclinics_tool(address: str) -> str:
#     """
#     Найти поликлиники, обслуживающие дом по адресу.

#     Сценарий 2.2: сведения о работе государственных учреждений (медицина).

#     Используй этот инструмент, когда пользователь спрашивает:
#     - Какая поликлиника прикреплена к моему адресу?
#     - Куда мне обращаться по адресу [адрес]?
#     - Контакты и сайты поликлиник возле дома.

#     Args:
#         address: Адрес пользователя.

#     Returns:
#         Список поликлиник в удобном для пользователя виде (текст),
#         либо сообщение об отсутствии данных / ошибке.
#     """
#     logger.info('tool_call', tool='get_polyclinics', address=address)

#     async def _async_call(client):
#         return await client.get_polyclinics_by_address(address)

#     try:
#         clinics = get_sync_client_result(_async_call)
#     except ServiceUnavailableError:
#         logger.error('tool_error', tool='get_polyclinics', address=address, exc_info=True)
#         return API_UNAVAILABLE_MESSAGE
#     except Exception as e:
#         logger.error('tool_error', tool='get_polyclinics', address=address, error=str(e))
#         return 'Не удалось получить информацию о поликлиниках по указанному адресу.'

#     logger.info(
#         'tool_result',
#         tool='get_polyclinics',
#         address=address,
#         clinics_count=len(clinics),
#     )
#     return format_polyclinics_for_chat(clinics)


# @tool
# def get_schools_tool(address: str) -> str:
#     """
#     Найти школы, прикреплённые к дому.

#     Сценарии:
#     - 2.1 / 2.2: справка и сведения о госучреждениях (образование).
#     - 2.6: общие вопросы о жизни в городе (куда ходят дети по месту жительства).

#     Используй этот инструмент, когда пользователь спрашивает:
#     - В какую школу прикреплён мой дом?
#     - Какие школы доступны по адресу [адрес]?
#     - Есть ли свободные места в школах рядом?

#     Args:
#         address: Адрес пользователя.

#     Returns:
#         Список школ в текстовом виде.
#     """
#     logger.info('tool_call', tool='get_schools', address=address)

#     async def _async_call(client):
#         return await client.get_linked_schools_by_address(address)

#     try:
#         schools = get_sync_client_result(_async_call)
#     except ServiceUnavailableError:
#         logger.error('tool_error', tool='get_schools', address=address, exc_info=True)
#         return API_UNAVAILABLE_MESSAGE
#     except Exception as e:
#         logger.error('tool_error', tool='get_schools', address=address, error=str(e))
#         return 'Не удалось получить информацию о школах по указанному адресу.'

#     logger.info(
#         'tool_result',
#         tool='get_schools',
#         address=address,
#         schools_count=len(schools),
#     )
#     return format_schools_for_chat(schools)


# @tool
# def get_management_company_tool(address: str) -> str:
#     """
#     Найти информацию об управляющей компании (УК) по адресу.

#     Сценарии:
#     - 2.1: госуслуги и жилищные вопросы по дому.
#     - 2.2: сведения о работе УК как гос/муниципальной службы.
#     - 2.6: общие вопросы по обслуживанию дома и двора.

#     Используй этот инструмент, когда пользователь спрашивает:
#     - Какая управляющая компания у дома по адресу [адрес]?
#     - Контакты УК для моего дома.
#     - Куда жаловаться на проблемы с домом/двором?

#     Args:
#         address: Адрес пользователя.

#     Returns:
#         Информация об УК в формате JSON или человекочитаемое сообщение.
#     """
#     logger.info('tool_call', tool='get_management_company', address=address)

#     async def _async_call(client):
#         return await client.get_management_company_by_address(address)

#     try:
#         uk = get_sync_client_result(_async_call)
#     except ServiceUnavailableError:
#         logger.error('tool_error', tool='get_management_company', address=address, exc_info=True)
#         return API_UNAVAILABLE_MESSAGE
#     except Exception as e:
#         logger.error(
#             'tool_error',
#             tool='get_management_company',
#             address=address,
#             error=str(e),
#         )
#         return 'Не удалось получить информацию об управляющей компании.'

#     if uk is None:
#         logger.info('tool_no_result', tool='get_management_company', address=address)
#         return 'Информация об управляющей компании не найдена для указанного адреса.'

#     logger.info(
#         'tool_result',
#         tool='get_management_company',
#         address=address,
#         uk_name=uk.name,
#     )
#     return json.dumps(uk.model_dump(exclude_none=True), ensure_ascii=False, indent=2)


# @tool
# def get_disconnections_tool(address: str) -> str:
#     """
#     Проверить отключения воды/электричества по адресу.

#     Сценарий 2.6: общие вопросы о жизни в СПб (коммунальные сервисы).

#     Используй этот инструмент, когда:
#     - Пользователь спрашивает про отключения ресурсов по своему адресу.
#     - Интересуется, будут ли отключения воды/электричества.

#     Args:
#         address: Адрес пользователя.

#     Returns:
#         Текст с информацией об отключениях (или об отсутствии отключений).
#     """
#     logger.info('tool_call', tool='get_disconnections', address=address)

#     async def _async_call(client):
#         return await client.get_disconnections_by_address(address)

#     try:
#         disconnections = get_sync_client_result(_async_call)
#     except ServiceUnavailableError:
#         logger.error('tool_error', tool='get_disconnections', address=address, exc_info=True)
#         return API_UNAVAILABLE_MESSAGE
#     except Exception as e:
#         logger.error('tool_error', tool='get_disconnections', address=address, error=str(e))
#         return 'Не удалось получить информацию об отключениях по указанному адресу.'

#     logger.info(
#         'tool_result',
#         tool='get_disconnections',
#         address=address,
#         count=len(disconnections),
#     )
#     return format_disconnections_for_chat(disconnections)


# @tool
# def get_kindergartens_tool(
#     district: str | None = None,
#     age_year: int = 0,
#     age_month: int = 0,
#     only_with_spots: bool = True,
#     count: int = 10,
# ) -> str:
#     """
#     Найти детские сады (ДОУ) по району и возрасту ребёнка.

#     Сценарий 2.6: общие вопросы о жизни в Санкт-Петербурге (куда отдать ребёнка).

#     Используй этот инструмент, когда пользователь спрашивает:
#     - Какие детские сады есть в [район]?
#     - Есть ли свободные места для ребёнка [возраст] лет?
#     - Куда можно отдать ребёнка в детский сад в моём районе?

#     Args:
#         district: Район СПб (например: "Невский"). Можно оставить пустым.
#         age_year: Возраст ребёнка в годах.
#         age_month: Возраст ребёнка в месяцах (0–11).
#         only_with_spots: True — только сады со свободными местами.
#         count: Максимальное количество садов.

#     Returns:
#         Отформатированный список детских садов или сообщение, что ничего не найдено.
#     """
#     logger.info(
#         'tool_call',
#         tool='get_kindergartens',
#         district=district,
#         age_year=age_year,
#         age_month=age_month,
#     )

#     async def _async_call(client):
#         return await client.get_kindergartens(
#             district=district or None,
#             age_year=age_year,
#             age_month=age_month,
#             legal_form='Государственная',
#             available_spots=1 if only_with_spots else 0,
#             count=count,
#         )

#     try:
#         kindergartens = get_sync_client_result(_async_call)
#     except ServiceUnavailableError:
#         logger.error(
#             'tool_error',
#             tool='get_kindergartens',
#             district=district,
#             exc_info=True,
#         )
#         return API_UNAVAILABLE_MESSAGE
#     except Exception as e:
#         logger.error(
#             'tool_error',
#             tool='get_kindergartens',
#             district=district,
#             error=str(e),
#         )
#         return 'Не удалось получить информацию о детских садах.'

#     logger.info(
#         'tool_result',
#         tool='get_kindergartens',
#         district=district,
#         count=len(kindergartens),
#     )
#     return format_kindergartens_for_chat(kindergartens)


# @tool
# def get_city_events_tool(
#     start_date: str,
#     end_date: str,
#     category: str | None = None,
#     free: bool | None = None,
#     kids: bool | None = None,
#     count: int = 10,
# ) -> str:
#     """
#     Найти культурные и общественные мероприятия в Санкт-Петербурге.

#     Сценарий 2.5: поиск информации о культурных и общественных мероприятиях города.

#     Используй этот инструмент, когда пользователь спрашивает:
#     - Что интересного происходит в городе в ближайшие выходные?
#     - Бесплатные мероприятия / концерты / выставки.
#     - Куда сходить с детьми в период [даты]?

#     Args:
#         start_date: Дата начала поиска (например: "2025-12-04T00:00:00").
#         end_date: Дата окончания (например: "2025-12-31T23:59:59").
#         category: Категория ("Концерт", "Выставка"), можно None.
#         free: True — только бесплатные; False — только платные; None — не фильтровать.
#         kids: True — мероприятия, подходящие для детей; None — не фильтровать.
#         count: Максимальное количество мероприятий (до 10).

#     Returns:
#         Список мероприятий в удобном для пользователя текстовом формате.
#     """
#     logger.info(
#         'tool_call',
#         tool='get_city_events',
#         start_date=start_date,
#         end_date=end_date,
#         category=category,
#         free=free,
#         kids=kids,
#     )

#     async def _async_call(client):
#         return await client.get_events(
#             start_date=start_date,
#             end_date=end_date,
#             category=category or None,
#             free=free,
#             kids=kids,
#             count=count,
#         )

#     try:
#         events = get_sync_client_result(_async_call)
#     except ServiceUnavailableError:
#         logger.error('tool_error', tool='get_city_events', exc_info=True)
#         return API_UNAVAILABLE_MESSAGE
#     except Exception as e:
#         logger.error('tool_error', tool='get_city_events', error=str(e))
#         return 'Не удалось получить список мероприятий. Попробуйте уточнить параметры.'

#     logger.info(
#         'tool_result',
#         tool='get_city_events',
#         events_count=len(events),
#     )
#     return format_events_for_chat(events)


# @tool
# def get_sport_events_tool(
#     district: str | None = None,
#     categoria: str | None = None,
#     start_date: str | None = None,
#     end_date: str | None = None,
#     for_ovz: bool | None = None,
#     family_hour: bool | None = None,
#     count: int = 10,
# ) -> str:
#     """
#     Найти спортивные мероприятия в Санкт-Петербурге.

#     Сценарий 2.5: часть культурных/общественных мероприятий — спорт.

#     Используй этот инструмент, когда пользователь спрашивает:
#     - Спортивные мероприятия в моём районе.
#     - Куда пойти позаниматься спортом бесплатно/с семьёй.
#     - Спортмероприятия, доступные для людей с ОВЗ.

#     Args:
#         district: Район ("Невский" и т.п.).
#         categoria: Вид спорта ("Футбол", "Баскетбол" и т.д.), можно None.
#         start_date: Дата начала (yyyy-mm-dd) или None.
#         end_date: Дата окончания (yyyy-mm-dd) или None.
#         for_ovz: True — мероприятия, доступные для ОВЗ.
#         family_hour: True — программа "Семейный час".
#         count: Максимальное количество мероприятий (до 10).

#     Returns:
#         Список спортивных мероприятий в текстовом виде.
#     """
#     logger.info(
#         'tool_call',
#         tool='get_sport_events',
#         district=district,
#         categoria=categoria,
#         start_date=start_date,
#         end_date=end_date,
#         for_ovz=for_ovz,
#         family_hour=family_hour,
#     )

#     async def _async_call(client):
#         return await client.get_sport_events(
#             district=district or None,
#             categoria=categoria or None,
#             start_date=start_date or None,
#             end_date=end_date or None,
#             ovz=for_ovz,
#             family_hour=family_hour,
#             count=count,
#         )

#     try:
#         events = get_sync_client_result(_async_call)
#     except ServiceUnavailableError:
#         logger.error('tool_error', tool='get_sport_events', exc_info=True)
#         return API_UNAVAILABLE_MESSAGE
#     except Exception as e:
#         logger.error('tool_error', tool='get_sport_events', error=str(e))
#         return 'Не удалось получить список спортивных мероприятий.'

#     logger.info(
#         'tool_result',
#         tool='get_sport_events',
#         events_count=len(events),
#     )
#     return format_sport_events_for_chat(events)


# # -----------------------------------------------------------------------------
# # СПИСОК ВСЕХ ДОСТУПНЫХ ИНСТРУМЕНТОВ ДЛЯ АГЕНТА
# # -----------------------------------------------------------------------------

# ALL_TOOLS = [
#     # старые
#     find_nearest_mfc_tool,
#     get_pensioner_categories_tool,
#     get_pensioner_services_tool,
#     # новые
#     search_address_candidates_tool,
#     get_house_reference_tool,
#     get_polyclinics_tool,
#     get_schools_tool,
#     get_management_company_tool,
#     get_disconnections_tool,
#     get_kindergartens_tool,
#     get_city_events_tool,
#     get_sport_events_tool,
# ]
