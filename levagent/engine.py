"""Một vòng quyết định trên dữ liệu đã có, có ghi sổ giả lập."""

from __future__ import annotations

from levagent.broker import PaperBroker
from levagent.config import Settings
from levagent.decision import decide
from levagent.models import Action, Candle, Decision, NewsItem
from levagent.risk import reprice_with_equity


def apply_new_candles(broker: PaperBroker, candles: list[Candle]) -> None:
    for candle in candles:
        if candle.time <= broker.last_candle_time:
            continue
        if broker.position is None or candle.time > broker.position.opened_at:
            broker.on_candle(candle)
        broker.last_candle_time = candle.time


def run_once(
    candles: list[Candle],
    news: list[NewsItem],
    broker: PaperBroker,
    settings: Settings,
) -> Decision:
    candles = sorted(candles, key=lambda candle: candle.time)
    if not candles:
        return decide(candles, news, broker.view(), settings)
    apply_new_candles(broker, candles)
    decision = decide(candles, news, broker.view(), settings)
    last = candles[-1]
    if decision.action is Action.CLOSE and broker.position is not None:
        broker.close(last.close, last.time, "Tín hiệu đảo chiều")
        return decision
    if decision.action in (Action.OPEN_LONG, Action.OPEN_SHORT):
        if decision.order is None:
            return _blocked(decision, "Không có kế hoạch lệnh.")
        if broker.position is not None:
            return decision
        plan, error = reprice_with_equity(decision.order, last.close, broker.equity, settings)
        if error or plan is None:
            return _blocked(decision, error or "Không khớp được lệnh.")
        error = broker.open(plan, last.time)
        if error:
            return _blocked(decision, error)
        return Decision(
            action=decision.action,
            symbol=decision.symbol,
            score=decision.score,
            news_score=decision.news_score,
            reasons=decision.reasons,
            order=plan,
            snapshot=decision.snapshot,
        )
    return decision


def _blocked(decision: Decision, error: str) -> Decision:
    return Decision(
        action=Action.HOLD,
        symbol=decision.symbol,
        score=decision.score,
        news_score=decision.news_score,
        reasons=decision.reasons + (error,),
        snapshot=decision.snapshot,
    )
