"""Các kiểu dữ liệu dùng chung."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Side(str, Enum):
    LONG = "long"
    SHORT = "short"


class Action(str, Enum):
    HOLD = "hold"
    OPEN_LONG = "open_long"
    OPEN_SHORT = "open_short"
    CLOSE = "close"


@dataclass(frozen=True)
class Candle:
    time: int
    open: float
    high: float
    low: float
    close: float
    volume: float

    def __post_init__(self) -> None:
        if min(self.open, self.high, self.low, self.close) <= 0:
            raise ValueError("giá nến phải dương")
        if self.high < self.low:
            raise ValueError("high nhỏ hơn low")
        if self.high < max(self.open, self.close) or self.low > min(self.open, self.close):
            raise ValueError("nến không bao được giá mở và giá đóng")
        if self.volume < 0:
            raise ValueError("khối lượng không được âm")


@dataclass(frozen=True)
class NewsItem:
    time: int
    title: str
    source: str

    def __post_init__(self) -> None:
        if not self.title.strip():
            raise ValueError("tiêu đề tin trống")


@dataclass(frozen=True)
class Snapshot:
    price: float
    ema_fast: float
    ema_slow: float
    rsi: float
    macd_hist: float
    macd_rising: bool
    atr: float
    atr_pct: float
    score: float


@dataclass(frozen=True)
class NewsView:
    score: float
    titles: tuple[str, ...]
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class OrderPlan:
    symbol: str
    side: Side
    qty: float
    entry: float
    stop: float
    take_profit: float
    leverage: int
    margin: float
    liquidation: float
    notional: float
    risk_cash: float

    def __post_init__(self) -> None:
        if self.qty <= 0 or self.entry <= 0 or self.notional <= 0 or self.margin <= 0:
            raise ValueError("kế hoạch lệnh có kích thước không hợp lệ")
        if self.leverage < 1:
            raise ValueError("đòn bẩy phải >= 1")


@dataclass(frozen=True)
class Decision:
    action: Action
    symbol: str
    score: float
    news_score: float
    reasons: tuple[str, ...]
    order: OrderPlan | None = None
    snapshot: Snapshot | None = None


@dataclass(frozen=True)
class Position:
    symbol: str
    side: Side
    qty: float
    entry: float
    leverage: int
    margin: float
    stop: float
    take_profit: float
    liquidation: float
    opened_at: int
    open_fee: float


@dataclass(frozen=True)
class ClosedTrade:
    symbol: str
    side: Side
    qty: float
    entry: float
    exit: float
    leverage: int
    pnl: float
    reason: str
    opened_at: int
    closed_at: int


@dataclass(frozen=True)
class AccountView:
    equity: float
    entries_halted: bool
    position: Position | None
    day_realized: float
