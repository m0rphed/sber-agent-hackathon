"""
Фильтр токсичности на основе ML модели rubert-tiny-toxicity.

Предоставляет класс ToxicityFilterML, который реализует тот же интерфейс, что и фильтр на основе регулярных выражений ToxicityFilter.
Может использоваться как замена "на лету" или выбираться через переменную окружения TOXICITY_BACKEND.
"""

from functools import lru_cache
from typing import TYPE_CHECKING

from langgraph_app.services.toxicity import (
    ToxicityFilter,
    ToxicityLevel,
    ToxicityResult,
)

if TYPE_CHECKING:
    from transformers import PreTrainedModel, PreTrainedTokenizer


# пороги для определения уровня токсичности на основе ML-значения
TOXICITY_THRESHOLDS = {
    ToxicityLevel.HIGH: 0.8,  # >= 0.8 = HIGH
    ToxicityLevel.MEDIUM: 0.5,  # >= 0.5 = MEDIUM
    ToxicityLevel.LOW: 0.3,  # >= 0.3 = LOW
    # < 0.3 = SAFE
}


@lru_cache(maxsize=1)
def _load_model() -> tuple['PreTrainedTokenizer', 'PreTrainedModel', str]:
    """
    Ленивая загрузка ML модели (кэшируется).

    Returns:
        Tuple состоящий из (tokenizer, model, device)
    """
    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    model_checkpoint = 'cointegrated/rubert-tiny-toxicity'

    tokenizer = AutoTokenizer.from_pretrained(model_checkpoint)
    model = AutoModelForSequenceClassification.from_pretrained(model_checkpoint)

    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    model.to(device)
    model.eval()

    return tokenizer, model, device


def text2toxicity(text: str | list[str], aggregate: bool = True):
    """
    Высчитывает токсичность текста(ов) с помощью ML модели.

    Args:
        text:  Один текст или список текстов
        aggregate:
            Если True, возвращает один агрегированный балл для каждого текста.
            Если False, возвращает вероятности для всех классов.

    Returns:
        Если aggregate=True: float (single text) или np.array (несколько текстов) с оценками от 0 до 1
        Если aggregate=False: np.array имеющий shape [num_classes] или [batch, num_classes]
    """
    import torch

    tokenizer, model, device = _load_model()

    if isinstance(text, str):
        texts = [text]
        single_input = True
    else:
        texts = text
        single_input = False

    with torch.inference_mode():
        inputs = tokenizer(
            texts,
            return_tensors='pt',
            truncation=True,
            padding=True,
            max_length=512,
        ).to(device)

        logits = model(**inputs).logits
        probability = torch.sigmoid(logits)  # shape: [batch_size, num_labels]

    if aggregate:
        # первый логит = "нет токсичности", последний = "тяжелая токсичность"
        # 1 - p(non_toxic) * (1 - p(hard_toxic))
        agg = 1.0 - probability[:, 0] * (1.0 - probability[:, -1])
        agg = agg.cpu().numpy()
        return float(agg[0]) if single_input else agg

    probability = probability.cpu().numpy()
    return probability[0] if single_input else probability


def _score_to_level(score: float) -> ToxicityLevel:
    """
    Конвертирует ML-оценку токсичности в уровень ToxicityLevel.

    Args:
        score: значение токсичности от 0 до 1

    Returns:
        ToxicityLevel основанный на пороговых значениях
    """
    if score >= TOXICITY_THRESHOLDS[ToxicityLevel.HIGH]:
        return ToxicityLevel.HIGH
    if score >= TOXICITY_THRESHOLDS[ToxicityLevel.MEDIUM]:
        return ToxicityLevel.MEDIUM
    if score >= TOXICITY_THRESHOLDS[ToxicityLevel.LOW]:
        return ToxicityLevel.LOW

    return ToxicityLevel.SAFE


class ToxicityFilterML(ToxicityFilter):
    """
    Фильтр токсичности на основе ML модели rubert-tiny-toxicity.

    Реализует тот же интерфейс, что и фильтр на основе регулярных выражений.
    Более точный, но медленнее и требует torch/transformers.

    Usage:
        filter = ToxicityFilterML()
        result = filter.check("some text")
        if result.should_block:
            print(filter.get_response(result))
    """

    def __init__(
        self,
        thresholds: dict[ToxicityLevel, float] | None = None,
        fallback_to_regex: bool = True,
    ):
        """
        Args:
            thresholds: переопределения собственных порогов для уровней токсичности
            fallback_to_regex: Если True, использовать фильтр на основе регулярных выражений при сбое ML модели
        """
        # инициализируем родительский класс
        # для регулярных выражений
        # в качестве запасного варианта
        super().__init__()

        self.thresholds = thresholds or TOXICITY_THRESHOLDS.copy()
        self.fallback_to_regex = fallback_to_regex
        self._model_loaded = False

    def _ensure_model(self) -> bool:
        """
        Пытается загрузить ML модель, возвращает True если успешно
        """
        if self._model_loaded:
            return True
        try:
            _load_model()
            self._model_loaded = True
            return True
        except Exception:
            return False

    def check(self, text: str) -> ToxicityResult:
        """
        Проверяет текст на токсичность с использованием ML модели.

        Если ML не сработала, откатывается на regex.

        Args:
            text: Текст для проверки

        Returns:
            ToxicityResult c результатами проверки ML модели или regex.
        """
        if not text or not text.strip():
            return ToxicityResult(
                is_toxic=False,
                level=ToxicityLevel.SAFE,
                matched_patterns=[],
                confidence=1.0,
            )

        # сначала пытаемся использовать ML модель
        if self._ensure_model():
            try:
                score = text2toxicity(text, aggregate=True)
                level = self._score_to_level(score)

                return ToxicityResult(
                    is_toxic=level != ToxicityLevel.SAFE,
                    level=level,
                    matched_patterns=['ml_model'],  # указывает, что использовалась ML модель
                    confidence=score if level != ToxicityLevel.SAFE else 1.0 - score,
                )
            except Exception:
                if not self.fallback_to_regex:
                    raise

        # если ML не сработала, откатываемся на regex
        return super().check(text)

    def _score_to_level(self, score: float) -> ToxicityLevel:
        """
        Конвертировать коэффициент ML-модели в уровень токсичности с использованием порогов экземпляра.
        """
        if score >= self.thresholds.get(ToxicityLevel.HIGH, 0.8):
            return ToxicityLevel.HIGH
        if score >= self.thresholds.get(ToxicityLevel.MEDIUM, 0.5):
            return ToxicityLevel.MEDIUM
        if score >= self.thresholds.get(ToxicityLevel.LOW, 0.3):
            return ToxicityLevel.LOW

        return ToxicityLevel.SAFE


# Singleton, определяет бэкенд

_ml_filter_instance: ToxicityFilterML | None = None


def get_toxicity_filter_ml() -> ToxicityFilterML:
    """
    Возвращает глобальный экземпляр ML-фильтра токсичности.
    """
    global _ml_filter_instance
    if _ml_filter_instance is None:
        _ml_filter_instance = ToxicityFilterML()
    return _ml_filter_instance
