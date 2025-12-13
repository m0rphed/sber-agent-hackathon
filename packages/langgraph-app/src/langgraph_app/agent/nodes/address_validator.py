"""
Нода валидации адреса через API.

Использует LangGraph interrupt() для HITL (Human-in-the-Loop):
- Если найден однозначно — валидирует и продолжает
- Если несколько кандидатов — interrupt() для выбора пользователем
- Если не найден — interrupt() для уточнения

Требует checkpointer для сохранения состояния между interrupt/resume.
"""

from typing import Any

from langgraph.types import interrupt

from langgraph_app.agent.models import AddressCandidate
from langgraph_app.agent.state_v2 import HybridStateV2
from langgraph_app.api.yazzh_final import ApiClientUnified
from langgraph_app.logging_config import get_logger

logger = get_logger(__name__)


async def validate_address_node(state: HybridStateV2) -> dict[str, Any]:
    """
    Валидирует извлечённый адрес через API.

    Использует interrupt() для HITL когда требуется уточнение.

    Flow:
    1. Если адрес найден однозначно → продолжаем
    2. Если несколько кандидатов → interrupt() с вопросом выбора
    3. После resume → выбранный кандидат сохраняется в state
    4. Если не найден → interrupt() с просьбой уточнить

    Args:
        state: Текущее состояние графа

    Returns:
        Dict с обновлениями для state
    """
    address = state.get('extracted_address')

    if not address:
        # Нет адреса для валидации — пропускаем
        logger.debug('validate_address_skip', reason='no_address')
        return {
            'address_validated': True,
            'address_candidates': [],
        }

    logger.info('validate_address_start', address=address)

    # Валидируем адрес через API
    candidates = await _search_address_candidates(address)

    if not candidates:
        # Адрес не найден — просим уточнить
        logger.warning('address_not_found', address=address)

        # interrupt() приостанавливает граф и ждёт ответа
        # После resume пользователь должен указать новый адрес
        user_response = interrupt(
            {
                'type': 'address_not_found',
                'message': f"Адрес '{address}' не найден. Уточните, пожалуйста, адрес.",
                'original_address': address,
            }
        )

        # После resume — user_response содержит новый адрес
        if user_response:
            # Рекурсивно проверяем новый адрес
            return {
                'extracted_address': str(user_response),
                'address_validated': False,  # Требуется повторная валидация
            }

        return {
            'address_validated': False,
            'address_candidates': [],
        }

    if len(candidates) == 1:
        # Единственный результат — адрес валиден
        candidate = candidates[0]
        logger.info('address_validated_unique', address=candidate.full_address)

        return {
            'address_validated': True,
            'extracted_address': candidate.full_address,
            'address_candidates': [candidate],
            'validated_building_id': candidate.building_id,
        }

    # Несколько кандидатов — нужен выбор пользователя
    logger.info('address_ambiguous', candidates_count=len(candidates))

    # Форматируем сообщение для пользователя
    options_text = _format_candidates_message(candidates)

    # interrupt() возвращает ответ пользователя после resume
    user_selection = interrupt(
        {
            'type': 'address_candidates',
            'message': options_text,
            'candidates': [
                {'index': i, 'address': c.full_address, 'building_id': c.building_id}
                for i, c in enumerate(candidates, 1)
            ],
        }
    )

    # Обрабатываем выбор пользователя
    selected_index = _parse_user_selection(user_selection, len(candidates))

    if selected_index is not None:
        selected_candidate = candidates[selected_index]
        logger.info(
            'address_selected',
            index=selected_index + 1,
            address=selected_candidate.full_address,
        )

        return {
            'address_validated': True,
            'extracted_address': selected_candidate.full_address,
            'address_candidates': candidates,
            'selected_candidate_index': selected_index,
            'validated_building_id': selected_candidate.building_id,
        }

    # Не удалось распознать выбор — просим уточнить
    logger.warning('invalid_selection', user_input=user_selection)
    return {
        'address_validated': False,
        'address_candidates': candidates,
    }


async def _search_address_candidates(address: str) -> list[AddressCandidate]:
    """
    Поиск кандидатов адреса через YAZZH API.

    Args:
        address: Текстовый запрос адреса

    Returns:
        Список AddressCandidate
    """
    async with ApiClientUnified(verbose=False) as client:
        try:
            result = await client.search_building_full_text_search(query=address, count=5)
        except Exception as e:
            logger.error('address_search_failed', error=str(e))
            return []

    # Проверяем результат
    if result.get('status_code') != 200 or not result.get('json'):
        return []

    data = result['json']
    buildings = data if isinstance(data, list) else data.get('data') or data.get('results') or []

    candidates = []
    for building in buildings:
        if isinstance(building, dict):
            candidates.append(
                AddressCandidate(
                    full_address=building.get('full_address')
                    or building.get('address')
                    or str(building),
                    building_id=int(building.get('id')) if building.get('id') else None,
                    lat=building.get('lat') or building.get('latitude'),
                    lon=building.get('lon') or building.get('longitude'),
                )
            )

    return candidates


def _format_candidates_message(candidates: list[AddressCandidate]) -> str:
    """
    Форматирует сообщение с кандидатами для пользователя.

    Args:
        candidates: Список кандидатов

    Returns:
        Форматированное сообщение
    """
    lines = ['Найдено несколько адресов. Какой вам нужен?']
    for i, c in enumerate(candidates, 1):
        lines.append(f'{i}. {c.full_address}')
    lines.append('')
    lines.append('Введите номер (1-5):')
    return '\n'.join(lines)


def _parse_user_selection(user_input: Any, max_options: int) -> int | None:
    """
    Парсит выбор пользователя.

    Args:
        user_input: Ответ пользователя (строка или число)
        max_options: Максимальное количество вариантов

    Returns:
        Индекс (0-based) или None если не удалось распознать
    """
    if user_input is None:
        return None

    try:
        # Пробуем как число
        if isinstance(user_input, int):
            selection = user_input
        else:
            # Извлекаем первое число из строки
            import re

            match = re.search(r'\d+', str(user_input))
            if not match:
                return None
            selection = int(match.group())

        # Валидируем диапазон (1-based → 0-based)
        if 1 <= selection <= max_options:
            return selection - 1

        return None

    except (ValueError, TypeError):
        return None
