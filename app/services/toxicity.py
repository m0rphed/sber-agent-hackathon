"""
Примитивный фильтр токсичности для городского помощника.

Обеспечивает фильтрацию токсичных сообщений пользователей.
"""

from dataclasses import dataclass
from enum import StrEnum
import re


class ToxicityLevel(StrEnum):
    """
    Уровень токсичности
    """

    SAFE    = 'safe'
    LOW     = 'low'
    MEDIUM  = 'medium'
    HIGH    = 'high'


@dataclass
class ToxicityResult:
    """
    Результат проверки на токсичность
    """

    is_toxic: bool
    level: ToxicityLevel
    matched_patterns: list[str]
    confidence: float  # 0.0 - 1.0

    @property
    def should_block(self) -> bool:
        """
        Должно ли сообщение быть заблокировано
        """
        return self.level in (ToxicityLevel.MEDIUM, ToxicityLevel.HIGH)


# паттерны для определения токсичности (русский язык)
# разделены по уровням серьёзности
TOXIC_PATTERNS = {
    ToxicityLevel.HIGH: [
        # мат и грубые оскорбления (замаскированы)
        r'\b[хx][уy][йеяiju]\w*',
        r'\b[пp][иi][зz][дd]\w*',
        r'\b[бb][лl][яa]\w*',
        r'\b[еe][бb]\w*[тt]\w*',
        r'\bсука\w*',
        r'\bсучк\w*',
        r'\bмразь\w*',
        r'\bтварь\b',
        r'\bдерьм\w*',
        r'\bгавн\w*',
        r'\bзасранец\w*',
        r'\bублюд\w*',
        r'\bпадл\w*',
        r'\bшлюх\w*',
        r'\bпроститу\w*',
    ],
    ToxicityLevel.MEDIUM: [
        # оскорбления и агрессия
        r'\bидиот\w*',
        r'\bдебил\w*',
        r'\bдурак\w*',
        r'\bдура\b',
        r'\bкретин\w*',
        r'\bлох\b',
        r'\bлошар\w*',
        r'\bтупой\b',
        r'\bтупая\b',
        r'\bтупица\w*',
        r'\bбыдло\w*',
        r'\bурод\w*',
        r'\bотстой\w*',
        r'\bзаткни\w*',
        r'\bненавижу\b',
        r'\bубью\b',
        r'\bубить\b',
        r'\bсдохни\w*',
    ],
    ToxicityLevel.LOW: [
        # просто грубость
        r'\bчёрт\b',
        r'\bблин\b',
        r'\bдостал\w*',
        r'\bбесит\w*',
        r'\bзадолбал\w*',
        r'\bнафиг\w*',
    ],
}

# фразы для ответа на токсичные сообщения
TOXIC_RESPONSES = {
    ToxicityLevel.HIGH: (
        'Извините, но я не могу отвечать на сообщения, содержащие грубую лексику. '
        'Пожалуйста, переформулируйте ваш вопрос в уважительной форме.'
    ),
    ToxicityLevel.MEDIUM: (
        'Пожалуйста, давайте общаться уважительно. '
        'Я с удовольствием помогу вам, если вы зададите вопрос в корректной форме.'
    ),
    ToxicityLevel.LOW: None, # не блокируем, просто отмечаем
    ToxicityLevel.SAFE: None,
}


class ToxicityFilter:
    """
    Фильтр токсичности на основе паттернов.

    Быстрый и не требует внешних зависимостей.
    """

    def __init__(self, custom_patterns: dict[ToxicityLevel, list[str]] | None = None):
        """
        Args:
            custom_patterns: Дополнительные паттерны для проверки
        """
        self.patterns = TOXIC_PATTERNS.copy()

        if custom_patterns:
            for level, patterns in custom_patterns.items():
                if level in self.patterns:
                    self.patterns[level].extend(patterns)
                else:
                    self.patterns[level] = patterns

        # Компилируем регулярные выражения для скорости
        self._compiled: dict[ToxicityLevel, list[re.Pattern]] = {}
        for level, patterns in self.patterns.items():
            self._compiled[level] = [re.compile(p, re.IGNORECASE | re.UNICODE) for p in patterns]

    def check(self, text: str) -> ToxicityResult:
        """
        Проверить текст на токсичность.

        Args:
            text: Текст для проверки

        Returns:
            ToxicityResult с результатами проверки
        """
        if not text or not text.strip():
            return ToxicityResult(
                is_toxic=False,
                level=ToxicityLevel.SAFE,
                matched_patterns=[],
                confidence=1.0,
            )

        matched_patterns: list[str] = []
        highest_level = ToxicityLevel.SAFE

        # Проверяем от высокого к низкому уровню
        for level in [ToxicityLevel.HIGH, ToxicityLevel.MEDIUM, ToxicityLevel.LOW]:
            for pattern in self._compiled.get(level, []):
                if pattern.search(text):
                    matched_patterns.append(pattern.pattern)
                    if self._level_priority(level) > self._level_priority(highest_level):
                        highest_level = level

        is_toxic = highest_level != ToxicityLevel.SAFE
        confidence = min(1.0, len(matched_patterns) * 0.3 + 0.4) if is_toxic else 1.0

        return ToxicityResult(
            is_toxic=is_toxic,
            level=highest_level,
            matched_patterns=matched_patterns,
            confidence=confidence,
        )

    def get_response(self, result: ToxicityResult) -> str | None:
        """
        Получить ответ для токсичного сообщения.

        Args:
            result: Результат проверки токсичности

        Returns:
            Текст ответа или None если не нужно блокировать
        """
        return TOXIC_RESPONSES.get(result.level)

    def filter_message(self, text: str) -> tuple[bool, str | None]:
        """
        Проверить сообщение и вернуть результат фильтрации.

        Args:
            text: Текст сообщения

        Returns:
            (should_process, response)
            - should_process: True если сообщение можно обработать
            - response: Ответ для пользователя (если заблокировано)
        """
        result = self.check(text)
        if result.should_block:
            return False, self.get_response(result)

        return True, None

    @staticmethod
    def _level_priority(level: ToxicityLevel) -> int:
        """
        Получить приоритет уровня токсичности
        """
        priorities = {
            ToxicityLevel.SAFE: 0,
            ToxicityLevel.LOW: 1,
            ToxicityLevel.MEDIUM: 2,
            ToxicityLevel.HIGH: 3,
        }
        return priorities.get(level, 0)


# глобальный экземпляр фильтра (singleton)
_filter_instance: ToxicityFilter | None = None


def get_toxicity_filter() -> ToxicityFilter:
    """
    Возвращает глобальный экземпляр фильтра токсичности
    """
    global _filter_instance
    if _filter_instance is None:
        _filter_instance = ToxicityFilter()
    return _filter_instance
