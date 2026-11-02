"""Chuỗi nến giả lập, xác định, để chạy không cần mạng."""

from __future__ import annotations

import math

from levagent.models import Candle

_HOUR = 3_600_000
_START = 1_700_000_000_000


def trending(n: int = 220, *, direction: int = 1, start: float = 100.0) -> list[Candle]:
    """Xu hướng có nhịp hồi, đủ để RSI không dính trần 100."""

    if direction not in (1, -1):
        raise ValueError("direction phải là 1 hoặc -1")
    price = start
    candles: list[Candle] = []
    for i in range(n):
        cycle = i % 7
        if cycle == 5:
            step = -0.55 * direction
        elif cycle == 6:
            step = -0.15 * direction
        else:
            step = 0.42 * direction
        opened = price
        closed = max(1.0, price + step)
        high = max(opened, closed) + 0.08
        low = max(0.5, min(opened, closed) - 0.08)
        candles.append(Candle(_START + i * _HOUR, opened, high, low, closed, 1_000 + i))
        price = closed
    return candles


def choppy(n: int = 220, *, start: float = 100.0) -> list[Candle]:
    price = start
    candles: list[Candle] = []
    for i in range(n):
        step = 0.35 * math.sin(i / 2.2)
        opened = price
        closed = max(1.0, price + step)
        high = max(opened, closed) + 0.12
        low = max(0.5, min(opened, closed) - 0.12)
        candles.append(Candle(_START + i * _HOUR, opened, high, low, closed, 800.0))
        price = closed
    return candles
