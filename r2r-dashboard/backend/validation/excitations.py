"""Excitation profiles used by SysID validation studies."""

from __future__ import annotations

import math
import random
from typing import Callable

ExcitationProfile = Callable[[float], tuple[float, float, float]]

_NAMES = ("ET1", "ET3", "ET6", "E_Toggle", "EVR")


def excitation_names() -> tuple[str, ...]:
    return _NAMES


def _square(t_s: float, period_s: float) -> float:
    phase = (t_s % period_s) / period_s
    return 1.0 if phase < 0.5 else -1.0


def get_excitation_profile(name: str, amplitude_V: float = 0.75) -> ExcitationProfile:
    """Return an excitation profile by paper-study name."""

    normalized = name.strip()
    if normalized not in _NAMES:
        raise ValueError(f"unknown excitation profile {name!r}; expected one of {_NAMES}")

    if normalized == "ET1":
        return lambda t: (
            amplitude_V * math.sin(2.0 * math.pi * 0.70 * t),
            0.0,
            0.0,
        )

    if normalized == "ET3":
        return lambda t: (
            amplitude_V * math.sin(2.0 * math.pi * 0.55 * t),
            amplitude_V * math.sin(2.0 * math.pi * 0.80 * t + 0.7),
            amplitude_V * math.sin(2.0 * math.pi * 1.10 * t + 1.4),
        )

    if normalized == "ET6":
        return lambda t: (
            amplitude_V
            * (
                0.55 * math.sin(2.0 * math.pi * 0.45 * t)
                + 0.45 * math.sin(2.0 * math.pi * 1.25 * t + 0.2)
            ),
            amplitude_V
            * (
                0.55 * math.sin(2.0 * math.pi * 0.75 * t + 0.8)
                + 0.45 * math.sin(2.0 * math.pi * 1.55 * t)
            ),
            amplitude_V
            * (
                0.55 * math.sin(2.0 * math.pi * 1.05 * t + 1.5)
                + 0.45 * math.sin(2.0 * math.pi * 1.85 * t + 0.4)
            ),
        )

    if normalized == "E_Toggle":
        return lambda t: (
            amplitude_V * _square(t, 0.42),
            amplitude_V * _square(t + 0.11, 0.58),
            amplitude_V * _square(t + 0.23, 0.74),
        )

    def evr(t: float) -> tuple[float, float, float]:
        bucket = int(t / 0.15)
        rng = random.Random(101 + bucket)
        return tuple(amplitude_V * rng.uniform(-1.0, 1.0) for _ in range(3))  # type: ignore[return-value]

    return evr
