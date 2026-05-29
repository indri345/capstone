import re
from collections import Counter
from typing import List, Tuple


# Pilihan model HF multilingual yang mampu menangani Bahasa Indonesia dan English.
HF_MODEL_NAME = "cardiffnlp/twitter-xlm-roberta-base-sentiment"
LABEL_MAP = {
    'LABEL_0': 'negative',
    'LABEL_1': 'neutral',
    'LABEL_2': 'positive',
}

TRANSFORMER_AVAILABLE = False
try:
    from transformers import pipeline
    from transformers import logging as hf_logging
    hf_logging.set_verbosity_error()
    TRANSFORMER_AVAILABLE = True
except Exception:
    TRANSFORMER_AVAILABLE = False


try:
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
    VADER_AVAILABLE = True
    _vader = SentimentIntensityAnalyzer()
except Exception:
    VADER_AVAILABLE = False


NEUTRAL_PHRASES = [
    'lumayan', 'cukup bagus', 'biasa saja', 'biasa aja', 'ok', 'oke', 'oke deh',
    'so so', 'so-so', 'tidak buruk', 'agak baik', 'agak oke', 'standard',
    'netral', 'normal', 'cukup', 'lumayan ok', 'sudah cukup', 'tidak terlalu',
]

NEGATIVE_PHRASES = [
    'jelek', 'buruk', 'tidak suka', 'mengecewakan', 'lemot', 'lambat',
    'susah', 'sulit', 'gagal', 'tidak puas', 'ngawur', 'parah', 'males',
    'capek', 'bosan', 'jelek sekali', 'kacau', 'tidak nyaman', 'tidak enak',
]

POSITIVE_PHRASES = [
    'bagus', 'baik', 'mantap', 'keren', 'suka', 'puas', 'senang',
    'excellent', 'great', 'good', 'awesome', 'terima kasih', 'thanks',
    'bagus banget', 'sangat baik', 'sangat membantu', 'luar biasa', 'top',
]

STOPWORDS = set([
    'yang', 'dan', 'di', 'ke', 'dari', 'untuk', 'ini', 'itu', 'adalah',
    'saya', 'kamu', 'dia', 'kita', 'kami', 'dengan', 'seperti', 'bahwa',
    'atau', 'juga', 'akan', 'pada', 'tidak', 'tdk', 'yg', 'apa', 'jadi',
    'dgn', 'aja', 'sih', 'ya', 'ga', 'gak', 'juga', 'kami', 'sangat', 'lebih',
    'kurang', 'lagi', 'udah', 'sudah', 'belum', 'lagi', 'sebenernya', 'sih',
])


class SentimentAnalyzer:
    def __init__(self):
        self.pipeline = self._load_transformer_pipeline()

    def _load_transformer_pipeline(self):
        if not TRANSFORMER_AVAILABLE:
            return None

        try:
            return pipeline(
                'sentiment-analysis',
                model=HF_MODEL_NAME,
                tokenizer=HF_MODEL_NAME,
                return_all_scores=False,
            )
        except Exception:
            return None

    @staticmethod
    def normalize_text(text: str) -> str:
        if not text:
            return ''
        text = text.lower().strip()
        text = re.sub(r'https?://\S+|www\.\S+', ' ', text)
        text = re.sub(r'\s+', ' ', text)
        text = re.sub(r'[^\w\s]', ' ', text)
        text = re.sub(r'(.)\1{2,}', r'\1', text)
        text = re.sub(r'\s+', ' ', text)
        text = text.replace('gak', 'tidak').replace('tdk', 'tidak')
        text = text.replace('terimakasih', 'terima kasih')
        text = text.replace('makasih', 'terima kasih')
        text = re.sub(r'\boke+\b', 'oke', text)
        text = re.sub(r'\bok+\b', 'ok', text)
        return text.strip()

    @staticmethod
    def _text_contains_any(text: str, phrases: List[str]) -> bool:
        return any(phrase in text for phrase in phrases)

    def _rule_based_sentiment(self, text: str) -> Tuple[str, float]:
        if not text:
            return 'neutral', 0.5

        if self._text_contains_any(text, NEGATIVE_PHRASES):
            return 'negative', 0.85

        if self._text_contains_any(text, NEUTRAL_PHRASES):
            return 'neutral', 0.73

        if self._text_contains_any(text, POSITIVE_PHRASES):
            return 'positive', 0.82

        if VADER_AVAILABLE:
            scores = _vader.polarity_scores(text)
            compound = scores['compound']
            if compound >= 0.45:
                return 'positive', max(0.6, compound)
            if compound <= -0.45:
                return 'negative', max(0.6, abs(compound))
            return 'neutral', 0.68

        return 'neutral', 0.58

    def predict(self, text: str) -> Tuple[str, float]:
        cleaned = self.normalize_text(text)
        if not cleaned:
            return 'neutral', 0.50

        if self.pipeline is not None:
            try:
                output = self.pipeline(cleaned, truncation=True, top_k=1)
                if output and isinstance(output, list):
                    result = output[0]
                    label = result.get('label', '')
                    score = float(result.get('score', 0.0))
                    sentiment = LABEL_MAP.get(label, 'neutral')

                    if sentiment == 'positive' and self._text_contains_any(cleaned, NEUTRAL_PHRASES):
                        return 'neutral', max(score, 0.60)
                    if sentiment == 'positive' and self._text_contains_any(cleaned, NEGATIVE_PHRASES):
                        return 'negative', max(score, 0.70)
                    if sentiment == 'negative' and self._text_contains_any(cleaned, POSITIVE_PHRASES):
                        return 'negative', max(score, 0.70)

                    return sentiment, score
            except Exception:
                pass

        return self._rule_based_sentiment(cleaned)

    @staticmethod
    def extract_common_words(messages: List[str], limit: int = 10) -> List[Tuple[str, int]]:
        counter = Counter()
        for message in messages:
            cleaned = SentimentAnalyzer.normalize_text(message)
            for word in cleaned.split():
                if len(word) < 3 or word in STOPWORDS:
                    continue
                counter[word] += 1
        return counter.most_common(limit)


sentiment_analyzer = SentimentAnalyzer()
