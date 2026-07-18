"""
TF-IDF based similarity filter for LinkedIn job pre-screening.
Provides a cheap, fast way to filter out obviously irrelevant jobs
before making expensive AI API calls.
"""

from __future__ import annotations

import math
import re
from collections import Counter

from src.linked_agent.utils.logger import get_logger

logger = get_logger(__name__)


_TECH_NORMALIZE: dict[str, str] = {
    "c#": "csharp",
    "c++": "cpp",
    "f#": "fsharp",
}


def _normalize_tech_names(text: str) -> str:
    """Normalize symbol-containing tech names (C# → csharp, C++ → cpp, etc.)."""
    txt = text.lower()
    for raw, normalized in _TECH_NORMALIZE.items():
        txt = txt.replace(raw, normalized)
    return txt


class LinkedInVectorSimilarityFilter:
    """
    Pre-filters jobs using TF-IDF cosine similarity against the resume text.
    Jobs below a configurable threshold are skipped without AI evaluation.
    """

    def __init__(
        self,
        resume_text: str,
        doc_frequencies: dict[str, int] | None = None,
        total_documents: int = 0,
    ) -> None:
        self._resume_text = resume_text.lower()
        self._resume_words = set(re.findall(r"\b[a-z0-9]+\b", _normalize_tech_names(self._resume_text)))

        # TF-IDF components
        self._doc_frequencies = doc_frequencies or {}
        self._total_documents = max(total_documents, 1)

        # Pre-compute resume TF vector
        self._resume_tf = self._compute_tf(self._resume_text)

    def _compute_tf(self, text: str) -> dict[str, float]:
        """Compute term frequency for a text."""
        words = re.findall(r"\b[a-z0-9]+\b", _normalize_tech_names(text))
        if not words:
            return {}
        counter = Counter(words)
        max_freq = max(counter.values())
        return {word: count / max_freq for word, count in counter.items()}

    def _compute_idf(self, word: str) -> float:
        """Compute inverse document frequency for a word."""
        df = self._doc_frequencies.get(word, 0)
        return math.log((self._total_documents + 1) / (df + 1)) + 1

    def get_similarity_score(self, job_text: str) -> float:
        """
        Compute cosine similarity between resume and job text using TF-IDF.
        Returns a score between 0.0 (no match) and 1.0 (perfect match).
        """
        job_words = re.findall(r"\b[a-z0-9]+\b", _normalize_tech_names(job_text))
        if not job_words or not self._resume_words:
            return 0.0

        job_counter = Counter(job_words)
        max_freq = max(job_counter.values()) if job_counter else 1
        job_tf = {word: count / max_freq for word, count in job_counter.items()}

        # Cosine similarity
        dot_product = 0.0
        resume_magnitude = 0.0
        job_magnitude = 0.0

        all_words = set(self._resume_tf.keys()) | set(job_tf.keys())
        for word in all_words:
            resume_val = self._resume_tf.get(word, 0.0) * self._compute_idf(word)
            job_val = job_tf.get(word, 0.0) * self._compute_idf(word)

            dot_product += resume_val * job_val
            resume_magnitude += resume_val ** 2
            job_magnitude += job_val ** 2

        if resume_magnitude == 0 or job_magnitude == 0:
            return 0.0

        return dot_product / (math.sqrt(resume_magnitude) * math.sqrt(job_magnitude))
