from app.services.toxicity import (
    ToxicityFilter,
    ToxicityLevel,
    ToxicityResult,
    get_toxicity_filter,
)


class TestToxicityFilter:
    """
    Тесты фильтра токсичности
    """

    def test_safe_message(self):
        """
        Тест безопасного сообщения
        """
        _filter = ToxicityFilter()
        _msg = 'Здравствуйте, подскажите где находится МФЦ?'
        result: ToxicityResult = _filter.check(_msg)

        assert not result.is_toxic
        assert result.level == ToxicityLevel.SAFE
        assert not result.should_block
        assert result.matched_patterns == []

    def test_safe_question_about_services(self):
        """
        Тест обычного вопроса о городских услугах
        """
        _filter = ToxicityFilter()
        result = _filter.check('Как получить справку о регистрации?')

        assert not result.is_toxic
        assert result.level == ToxicityLevel.SAFE

    def test_high_toxicity_blocked(self):
        """
        Тест блокировки высокотоксичного сообщения
        """
        _filter = ToxicityFilter()
        # Используем явно токсичное слово
        result = _filter.check('Ты сука тупая')

        assert result.is_toxic
        assert result.level == ToxicityLevel.HIGH
        assert result.should_block

    def test_medium_toxicity_blocked(self):
        """
        Тест блокировки сообщения средней токсичности
        """
        _filter = ToxicityFilter()
        result = _filter.check('Какой идиот это придумал?')

        assert result.is_toxic
        assert result.level == ToxicityLevel.MEDIUM
        assert result.should_block

    def test_low_toxicity_not_blocked(self):
        """
        Тест, что низкая токсичность не блокируется
        """
        _filter = ToxicityFilter()
        result = _filter.check('Блин, опять не работает')

        assert result.is_toxic
        assert result.level == ToxicityLevel.LOW
        assert not result.should_block

    def test_empty_message(self):
        """
        Тест пустого сообщения
        """
        _filter = ToxicityFilter()
        result = _filter.check('')

        assert not result.is_toxic
        assert result.level == ToxicityLevel.SAFE

    def test_whitespace_message(self):
        """
        Тест сообщения из пробелов
        """
        _filter = ToxicityFilter()
        result = _filter.check('   ')

        assert not result.is_toxic
        assert result.level == ToxicityLevel.SAFE


class TestToxicityFilterResponse:
    """
    Тесты ответов фильтра
    """

    def test_get_response_high_toxicity(self):
        """
        Тест ответа на высокотоксичное сообщение
        """
        _filter = ToxicityFilter()
        result = _filter.check('Сука, где мой документ?')
        response = _filter.get_response(result)

        assert response is not None
        assert 'грубую лексику' in response.lower() or 'уважительной' in response.lower()

    def test_get_response_safe_message(self):
        """
        Тест, что для безопасных сообщений нет ответа
        """
        _filter = ToxicityFilter()
        result = _filter.check('Спасибо за помощь!')
        response = _filter.get_response(result)

        assert response is None

    def test_filter_message_blocks_toxic(self):
        """
        Тест метода filter_message для токсичного сообщения
        """
        _filter = ToxicityFilter()
        should_process, response = _filter.filter_message('Идиоты, ничего не работает')

        assert not should_process
        assert response is not None

    def test_filter_message_allows_safe(self):
        """
        Тест метода filter_message для безопасного сообщения
        """
        _filter = ToxicityFilter()
        should_process, response = _filter.filter_message('Как записаться в поликлинику?')

        assert should_process
        assert response is None


class TestToxicityFilterCaseInsensitive:
    """
    Тесты регистронезависимости
    """

    def test_uppercase_toxic(self):
        """
        Тест токсичности в верхнем регистре
        """
        _filter = ToxicityFilter()
        result = _filter.check('ИДИОТ')

        assert result.is_toxic

    def test_mixed_case_toxic(self):
        """
        Тест токсичности в смешанном регистре
        """
        _filter = ToxicityFilter()
        result = _filter.check('ИдИоТ')

        assert result.is_toxic


class TestCustomPatterns:
    """
    Тесты пользовательских паттернов
    """

    def test_custom_pattern_added(self):
        """
        Тест добавления пользовательского паттерна
        """
        custom = {ToxicityLevel.HIGH: [r'\bзапрещённоеслово\b']}
        _filter = ToxicityFilter(custom_patterns=custom)
        result = _filter.check('Это запрещённоеслово в тексте')

        assert result.is_toxic
        assert result.level == ToxicityLevel.HIGH


class TestGlobalFilter:
    """
    Тесты глобального экземпляра
    """

    def test_singleton(self):
        """
        Тест, что get_toxicity_filter возвращает singleton
        """
        filter1 = get_toxicity_filter()
        filter2 = get_toxicity_filter()

        assert filter1 is filter2

    def test_global_filter_works(self):
        """
        Тест работы глобального фильтра
        """
        _filter = get_toxicity_filter()
        result = _filter.check('Нормальный вопрос')

        assert not result.is_toxic
