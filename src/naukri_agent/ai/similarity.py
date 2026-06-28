"""
Mathematical similarity scoring for jobs.
Implements TF and Cosine Similarity to mathematically pre-filter jobs
in O(N) time before sending them to the expensive AI API.
"""

import math
import re
from collections import Counter

from src.naukri_agent.core.interfaces import IJobFilter


class VectorSimilarityFilter(IJobFilter):
    """Pre-filters jobs using vector space mathematics (TF-IDF and Cosine Similarity)."""

    def __init__(
        self,
        resume_text_blocks: list[str],
        doc_frequencies: dict[str, int] | None = None,
        total_documents: int = 0,
    ) -> None:
        """Initialize with resume content to build the base vector."""
        text = " ".join(resume_text_blocks)
        self.resume_tokens = self._tokenize(text)
        self.resume_tf = self._compute_tf(self.resume_tokens)
        self.doc_frequencies = doc_frequencies or {}
        self.total_documents = total_documents

        # Pre-compute TF-IDF for resume
        self.resume_tfidf = {}
        for word, tf in self.resume_tf.items():
            self.resume_tfidf[word] = tf * self._compute_idf(word)

        self.mag_resume = math.sqrt(sum(v**2 for v in self.resume_tfidf.values()))

    def _tokenize(self, text: str) -> list[str]:
        """Convert text into lowercase word tokens."""
        if not text:
            return []
        text = text.lower()
        # Extract alphanumeric words
        return re.findall(r"\b[a-z0-9]+\b", text)

    def _compute_tf(self, tokens: list[str]) -> dict[str, float]:
        """Compute Term Frequency (TF) for a list of tokens."""
        count = Counter(tokens)
        total = len(tokens)
        if total == 0:
            return {}
        return {word: c / total for word, c in count.items()}

    def _compute_idf(self, word: str) -> float:
        """Compute the Inverse Document Frequency (IDF) of a word."""
        if self.total_documents <= 0 or word not in self.doc_frequencies:
            # Fallback to pure TF weighting if corpus data is missing
            return 1.0
        # Smoothed IDF formula
        df = self.doc_frequencies.get(word, 0)
        return math.log((1 + self.total_documents) / (1 + df)) + 1.0

    def get_similarity_score(self, job_text: str) -> float:
        """
        Calculate cosine similarity between resume and job description using TF-IDF.
        Returns a score between 0.0 and 1.0.
        """
        job_tokens = self._tokenize(job_text)
        job_tf = self._compute_tf(job_tokens)

        # Compute TF-IDF for job
        job_tfidf = {}
        for word, tf in job_tf.items():
            job_tfidf[word] = tf * self._compute_idf(word)

        mag_job = math.sqrt(sum(v**2 for v in job_tfidf.values()))
        if self.mag_resume * mag_job == 0:
            return 0.0

        # Calculate dot product only on intersecting words for O(K) speed
        intersection = set(self.resume_tfidf.keys()) & set(job_tfidf.keys())
        dot_product = sum(self.resume_tfidf[w] * job_tfidf[w] for w in intersection)

        return dot_product / (self.mag_resume * mag_job)
