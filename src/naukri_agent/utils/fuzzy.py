"""
Pure Python implementation of Levenshtein Distance and String Similarity Ratio.
"""

from __future__ import annotations


def levenshtein_distance(s1: str, s2: str) -> int:
    """
    Calculate the Levenshtein distance (edit distance) between two strings.

    Time Complexity: O(M * N)
    Space Complexity: O(min(M, N))
    """
    # Normalize strings for comparison
    str1 = s1.lower().strip()
    str2 = s2.lower().strip()

    if len(str1) < len(str2):
        str1, str2 = str2, str1

    if len(str2) == 0:
        return len(str1)

    previous_row = list(range(len(str2) + 1))
    for i, c1 in enumerate(str1):
        current_row = [i + 1]
        for j, c2 in enumerate(str2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (0 if c1 == c2 else 1)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row

    return previous_row[-1]


def fuzzy_similarity_ratio(s1: str, s2: str) -> float:
    """
    Calculate a normalized similarity ratio between 0.0 and 1.0.
    1.0 means exact match, 0.0 means completely different.
    """
    str1 = s1.lower().strip()
    str2 = s2.lower().strip()

    max_len = max(len(str1), len(str2))
    if max_len == 0:
        return 1.0

    distance = levenshtein_distance(str1, str2)
    return (max_len - distance) / max_len
