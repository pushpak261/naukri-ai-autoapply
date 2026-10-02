"""
Human-like timing jitter for browser automation.

These helpers exist so browser code never has to reach for ``random`` directly.
The standard-library ``random`` module is a pseudo-random generator and is
flagged as security-sensitive by static analysis (SonarCloud python:S2245),
even though the values here only drive typing/scroll timing. Drawing from the
OS CSPRNG via ``os.urandom`` is both unambiguous to analysers and better for
the purpose: the jitter is non-reproducible and unpredictable, which is exactly
what makes synthetic input harder to fingerprint.
"""

from __future__ import annotations

import os

_UINT64 = 1 << 64


def _rand_unit() -> float:
    """A float uniformly distributed in ``[0.0, 1.0)``."""
    return int.from_bytes(os.urandom(8), "big") / float(_UINT64)


def jitter_uniform(low: float, high: float) -> float:
    """Return a float uniformly distributed in ``[low, high)``."""
    if high <= low:
        return low
    return low + (high - low) * _rand_unit()


def jitter_int(low: int, high: int) -> int:
    """Return an integer uniformly distributed in ``[low, high]`` (inclusive)."""
    if high <= low:
        return low
    span = high - low + 1
    return low + int.from_bytes(os.urandom(8), "big") % span


def jitter_chance(probability: float) -> bool:
    """Return ``True`` with the given probability (``0.0``-``1.0``)."""
    if probability <= 0.0:
        return False
    if probability >= 1.0:
        return True
    return _rand_unit() < probability


def jitter_choice(options: list) -> object:
    """Return one element chosen uniformly at random from ``options``."""
    if not options:
        raise ValueError("options must not be empty")
    return options[int.from_bytes(os.urandom(8), "big") % len(options)]