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
    """Pre-filters jobs using vector space mathematics."""

    def __init__(self, resume_text_blocks: list[str]):
        """Initialize with resume content to build the base vector."""
        text = " ".join(resume_text_blocks)
        self.resume_tokens = self._tokenize(text)
        self.resume_tf = self._compute_tf(self.resume_tokens)
        self.mag_resume = math.sqrt(sum(v**2 for v in self.resume_tf.values()))

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

    def get_similarity_score(self, job_text: str) -> float:
        """
        Calculate cosine similarity between resume and job description.
        Returns a score between 0.0 and 1.0.
        """
        job_tokens = self._tokenize(job_text)
        job_tf = self._compute_tf(job_tokens)

        mag_job = math.sqrt(sum(v**2 for v in job_tf.values()))
        if self.mag_resume * mag_job == 0:
            return 0.0

        # Calculate dot product only on intersecting words for O(K) speed
        intersection = set(self.resume_tf.keys()) & set(job_tf.keys())
        dot_product = sum(self.resume_tf[w] * job_tf[w] for w in intersection)

        return dot_product / (self.mag_resume * mag_job)
