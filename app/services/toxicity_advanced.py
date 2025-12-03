"""
ML-based toxicity filter using rubert-tiny-toxicity model.

Provides ToxicityFilterML class that implements same interface as regex-based ToxicityFilter.
Can be used as drop-in replacement or selected via TOXICITY_BACKEND env variable.
"""

from functools import lru_cache
from typing import TYPE_CHECKING

from app.services.toxicity import (
    ToxicityFilter,
    ToxicityLevel,
    ToxicityResult,
)

if TYPE_CHECKING:
    from transformers import PreTrainedModel, PreTrainedTokenizer


# Пороги для определения уровня токсичности на основе ML-скора
TOXICITY_THRESHOLDS = {
    ToxicityLevel.HIGH: 0.8,    # >= 0.8 = HIGH
    ToxicityLevel.MEDIUM: 0.5,  # >= 0.5 = MEDIUM
    ToxicityLevel.LOW: 0.3,     # >= 0.3 = LOW
    # < 0.3 = SAFE
}


@lru_cache(maxsize=1)
def _load_model() -> tuple["PreTrainedTokenizer", "PreTrainedModel", str]:
    """
    Lazy-load ML model (cached).
    
    Returns:
        Tuple of (tokenizer, model, device)
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
    Calculate toxicity score for text(s) using ML model.
    
    Args:
        text: Single text or list of texts
        aggregate: If True, return single aggregated score per text.
                   If False, return all class probabilities.
    
    Returns:
        If aggregate=True: float (single text) or np.array (multiple texts) with scores 0-1
        If aggregate=False: np.array with shape [num_classes] or [batch, num_classes]
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
        proba = torch.sigmoid(logits)  # shape: [batch_size, num_labels]

    if aggregate:
        # первый логит = "нет токсичности", последний = "тяжелая токсичность"
        # 1 - p(non_toxic) * (1 - p(hard_toxic))
        agg = 1.0 - proba[:, 0] * (1.0 - proba[:, -1])
        agg = agg.cpu().numpy()
        return float(agg[0]) if single_input else agg

    proba = proba.cpu().numpy()
    return proba[0] if single_input else proba


def _score_to_level(score: float) -> ToxicityLevel:
    """
    Convert ML toxicity score to ToxicityLevel.
    
    Args:
        score: Toxicity score from 0 to 1
        
    Returns:
        ToxicityLevel based on thresholds
    """
    if score >= TOXICITY_THRESHOLDS[ToxicityLevel.HIGH]:
        return ToxicityLevel.HIGH
    elif score >= TOXICITY_THRESHOLDS[ToxicityLevel.MEDIUM]:
        return ToxicityLevel.MEDIUM
    elif score >= TOXICITY_THRESHOLDS[ToxicityLevel.LOW]:
        return ToxicityLevel.LOW
    else:
        return ToxicityLevel.SAFE


class ToxicityFilterML(ToxicityFilter):
    """
    ML-based toxicity filter using rubert-tiny-toxicity model.
    
    Implements same interface as regex-based ToxicityFilter.
    More accurate but slower and requires torch/transformers.
    
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
            thresholds: Custom thresholds for toxicity levels
            fallback_to_regex: If True, use regex filter when ML fails
        """
        # Initialize parent for fallback
        super().__init__()
        
        self.thresholds = thresholds or TOXICITY_THRESHOLDS.copy()
        self.fallback_to_regex = fallback_to_regex
        self._model_loaded = False
        
    def _ensure_model(self) -> bool:
        """Try to load ML model, return True if successful."""
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
        Check text for toxicity using ML model.
        
        Falls back to regex if ML fails.
        
        Args:
            text: Text to check
            
        Returns:
            ToxicityResult with ML-based analysis
        """
        if not text or not text.strip():
            return ToxicityResult(
                is_toxic=False,
                level=ToxicityLevel.SAFE,
                matched_patterns=[],
                confidence=1.0,
            )
        
        # Try ML first
        if self._ensure_model():
            try:
                score = text2toxicity(text, aggregate=True)
                level = self._score_to_level(score)
                
                return ToxicityResult(
                    is_toxic=level != ToxicityLevel.SAFE,
                    level=level,
                    matched_patterns=['ml_model'],  # Indicate ML was used
                    confidence=score if level != ToxicityLevel.SAFE else 1.0 - score,
                )
            except Exception:
                if not self.fallback_to_regex:
                    raise
        
        # Fallback to regex
        return super().check(text)
    
    def _score_to_level(self, score: float) -> ToxicityLevel:
        """Convert ML score to ToxicityLevel using instance thresholds."""
        if score >= self.thresholds.get(ToxicityLevel.HIGH, 0.8):
            return ToxicityLevel.HIGH
        elif score >= self.thresholds.get(ToxicityLevel.MEDIUM, 0.5):
            return ToxicityLevel.MEDIUM
        elif score >= self.thresholds.get(ToxicityLevel.LOW, 0.3):
            return ToxicityLevel.LOW
        else:
            return ToxicityLevel.SAFE


# === Singleton и выбор бэкенда ===

_ml_filter_instance: ToxicityFilterML | None = None


def get_toxicity_filter_ml() -> ToxicityFilterML:
    """
    Get global ML-based toxicity filter instance.
    """
    global _ml_filter_instance
    if _ml_filter_instance is None:
        _ml_filter_instance = ToxicityFilterML()
    return _ml_filter_instance
