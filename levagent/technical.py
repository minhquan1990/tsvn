"""Điểm kỹ thuật từ -1 (giảm) đến +1 (tăng)."""

from __future__ import annotations

from levagent.config import Settings
from levagent.indicators import atr_series, ema_series, macd_series, rsi_series
from levagent.models import Candle, Snapshot


def combine_scores(trend: float, rsi_score: float, macd_score: float) -> float:
    raw = 0.5 * trend + 0.25 * rsi_score + 0.25 * macd_score
    return max(-1.0, min(1.0, raw))


def analyze(candles: list[Candle], settings: Settings) -> Snapshot | None:
    if len(candles) < settings.required_bars():
        return None
    closes = [candle.close for candle in candles]
    ema_fast = ema_series(closes, settings.ema_fast)
    ema_slow = ema_series(closes, settings.ema_slow)
    rsi = rsi_series(closes, settings.rsi_period)
    _macd, _signal, hist = macd_series(
        closes, settings.macd_fast, settings.macd_slow, settings.macd_signal
    )
    atr = atr_series(candles, settings.atr_period)
    fast = ema_fast[-1]
    slow = ema_slow[-1]
    rsi_now = rsi[-1]
    hist_now = hist[-1]
    atr_now = atr[-1]
    if None in (fast, slow, rsi_now, hist_now, atr_now):
        return None
    price = closes[-1]
    assert fast is not None and slow is not None
    assert rsi_now is not None and hist_now is not None and atr_now is not None
    if atr_now > 0:
        trend = max(-1.0, min(1.0, (fast - slow) / atr_now))
    else:
        trend = 0.0
    rsi_score = max(-1.0, min(1.0, (rsi_now - 50) / 25))
    if hist_now > 0:
        macd_score = 1.0
    elif hist_now < 0:
        macd_score = -1.0
    else:
        macd_score = 0.0
    prev = hist[-2] if len(hist) > 1 else None
    rising = prev is not None and hist_now > prev
    if prev is not None and abs(hist_now) < abs(prev):
        macd_score *= 0.6
    return Snapshot(
        price=price,
        ema_fast=fast,
        ema_slow=slow,
        rsi=rsi_now,
        macd_hist=hist_now,
        macd_rising=rising,
        atr=atr_now,
        atr_pct=(atr_now / price) if price else 0.0,
        score=combine_scores(trend, rsi_score, macd_score),
    )
