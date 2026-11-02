"""Backtest khớp ở giá mở nến sau, không dùng giá tương lai để ra tín hiệu."""

from __future__ import annotations

from dataclasses import dataclass

from levagent.broker import PaperBroker
from levagent.config import Settings
from levagent.decision import decide
from levagent.models import Action, Candle, ClosedTrade, NewsItem, OrderPlan
from levagent.risk import reprice_with_equity


@dataclass(frozen=True)
class BacktestResult:
    start_equity: float
    end_equity: float
    trades: tuple[ClosedTrade, ...]
    max_drawdown: float
    holds: int
    skipped: int

    @property
    def wins(self) -> int:
        return sum(1 for trade in self.trades if trade.pnl > 0)

    @property
    def max_leverage(self) -> int:
        if not self.trades:
            return 0
        return max(trade.leverage for trade in self.trades)


def run_backtest(
    candles: list[Candle], news: list[NewsItem], settings: Settings
) -> BacktestResult:
    candles = sorted(candles, key=lambda candle: candle.time)
    broker = PaperBroker(settings)
    start = broker.equity
    pending: OrderPlan | None = None
    holds = 0
    skipped = 0
    for index, candle in enumerate(candles):
        if pending is not None and broker.position is None:
            plan, error = reprice_with_equity(pending, candle.open, broker.equity, settings)
            pending = None
            if error or plan is None or broker.open(plan, candle.time):
                skipped += 1
        if broker.position is not None:
            broker.on_candle(candle)
        window = candles[: index + 1]
        visible = [item for item in news if item.time <= candle.time]
        decision = decide(window, visible, broker.view(), settings)
        if decision.action is Action.CLOSE and broker.position is not None:
            broker.close(candle.close, candle.time, "Tín hiệu đảo chiều")
            pending = None
        elif (
            decision.action in (Action.OPEN_LONG, Action.OPEN_SHORT)
            and decision.order is not None
            and broker.position is None
        ):
            pending = decision.order
        else:
            holds += 1
        broker.mark(candle.close)
    if broker.position is not None:
        last = candles[-1]
        broker.close(last.close, last.time, "Đóng cuối kỳ")
    return BacktestResult(
        start_equity=start,
        end_equity=broker.equity,
        trades=tuple(broker.trades),
        max_drawdown=broker.max_drawdown,
        holds=holds,
        skipped=skipped,
    )
