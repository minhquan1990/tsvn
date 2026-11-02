"""Dữ liệu nhỏ dùng chung cho kiểm thử."""

from __future__ import annotations

from levagent.models import Candle, OrderPlan, Side
from levagent.risk import liquidation_price

TIME = 1_700_000_000_000
HOUR = 3_600_000


def candle(i: int, open_: float, high: float, low: float, close: float, volume: float = 100.0) -> Candle:
    return Candle(TIME + i * HOUR, open_, high, low, close, volume)


def from_closes(closes: list[float], spread: float = 0.1) -> list[Candle]:
    candles: list[Candle] = []
    for i, close in enumerate(closes):
        open_ = closes[i - 1] if i else close
        candles.append(
            candle(
                i,
                open_,
                max(open_, close) + spread,
                min(open_, close) - spread,
                close,
            )
        )
    return candles


def long_plan(
    *,
    entry: float = 100.0,
    stop: float = 90.0,
    take_profit: float = 120.0,
    qty: float = 1.0,
    leverage: int = 5,
) -> OrderPlan:
    notional = qty * entry
    return OrderPlan(
        symbol="BTCUSDT",
        side=Side.LONG,
        qty=qty,
        entry=entry,
        stop=stop,
        take_profit=take_profit,
        leverage=leverage,
        margin=notional / leverage,
        liquidation=liquidation_price(entry, leverage, Side.LONG, 0.005),
        notional=notional,
        risk_cash=qty * abs(entry - stop),
    )


def short_plan(
    *,
    entry: float = 100.0,
    stop: float = 110.0,
    take_profit: float = 80.0,
    qty: float = 1.0,
    leverage: int = 5,
) -> OrderPlan:
    notional = qty * entry
    return OrderPlan(
        symbol="BTCUSDT",
        side=Side.SHORT,
        qty=qty,
        entry=entry,
        stop=stop,
        take_profit=take_profit,
        leverage=leverage,
        margin=notional / leverage,
        liquidation=liquidation_price(entry, leverage, Side.SHORT, 0.005),
        notional=notional,
        risk_cash=qty * abs(entry - stop),
    )
