"""Chỉ báo kỹ thuật thuần, không phụ thuộc thư viện ngoài."""

from __future__ import annotations

from levagent.models import Candle


def ema_series(values: list[float], period: int) -> list[float | None]:
    if period < 1:
        raise ValueError("chu kỳ EMA phải >= 1")
    out: list[float | None] = [None] * len(values)
    if len(values) < period:
        return out
    acc = sum(values[:period]) / period
    out[period - 1] = acc
    k = 2 / (period + 1)
    for i in range(period, len(values)):
        acc = values[i] * k + acc * (1 - k)
        out[i] = acc
    return out


def rsi_series(values: list[float], period: int = 14) -> list[float | None]:
    if period < 1:
        raise ValueError("chu kỳ RSI phải >= 1")
    out: list[float | None] = [None] * len(values)
    if len(values) <= period:
        return out
    gains = 0.0
    losses = 0.0
    for i in range(1, period + 1):
        change = values[i] - values[i - 1]
        gains += max(change, 0.0)
        losses += max(-change, 0.0)
    avg_gain = gains / period
    avg_loss = losses / period
    out[period] = _rsi(avg_gain, avg_loss)
    for i in range(period + 1, len(values)):
        change = values[i] - values[i - 1]
        avg_gain = (avg_gain * (period - 1) + max(change, 0.0)) / period
        avg_loss = (avg_loss * (period - 1) + max(-change, 0.0)) / period
        out[i] = _rsi(avg_gain, avg_loss)
    return out


def _rsi(avg_gain: float, avg_loss: float) -> float:
    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else 50.0
    rs = avg_gain / avg_loss
    return 100 - 100 / (1 + rs)


def macd_series(
    values: list[float], fast: int = 12, slow: int = 26, signal: int = 9
) -> tuple[list[float | None], list[float | None], list[float | None]]:
    ema_fast = ema_series(values, fast)
    ema_slow = ema_series(values, slow)
    macd: list[float | None] = [None] * len(values)
    compact: list[float] = []
    indexes: list[int] = []
    for i in range(len(values)):
        if ema_fast[i] is None or ema_slow[i] is None:
            continue
        macd[i] = ema_fast[i] - ema_slow[i]
        compact.append(macd[i])
        indexes.append(i)
    signal_compact = ema_series(compact, signal)
    signal_line: list[float | None] = [None] * len(values)
    hist: list[float | None] = [None] * len(values)
    for j, i in enumerate(indexes):
        if signal_compact[j] is None or macd[i] is None:
            continue
        signal_line[i] = signal_compact[j]
        hist[i] = macd[i] - signal_compact[j]
    return macd, signal_line, hist


def atr_series(candles: list[Candle], period: int = 14) -> list[float | None]:
    if period < 1:
        raise ValueError("chu kỳ ATR phải >= 1")
    out: list[float | None] = [None] * len(candles)
    if len(candles) <= period:
        return out
    true_ranges = [candles[0].high - candles[0].low]
    for i in range(1, len(candles)):
        high = candles[i].high
        low = candles[i].low
        prev_close = candles[i - 1].close
        true_ranges.append(max(high - low, abs(high - prev_close), abs(low - prev_close)))
    atr = sum(true_ranges[1 : period + 1]) / period
    out[period] = atr
    for i in range(period + 1, len(candles)):
        atr = (atr * (period - 1) + true_ranges[i]) / period
        out[i] = atr
    return out
