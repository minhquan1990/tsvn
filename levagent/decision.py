"""Ghép kỹ thuật, tin và trạng thái tài khoản thành một quyết định."""

from __future__ import annotations

from levagent.config import Settings
from levagent.formatting import format_number
from levagent.models import (
    AccountView,
    Action,
    Candle,
    Decision,
    NewsItem,
    Side,
    Snapshot,
)
from levagent.news import score_news
from levagent.risk import size_order
from levagent.technical import analyze


def decide(
    candles: list[Candle],
    news: list[NewsItem],
    account: AccountView,
    settings: Settings,
) -> Decision:
    symbol = settings.symbol
    if len(candles) < settings.required_bars():
        return _hold(
            symbol,
            0.0,
            0.0,
            (f"Chưa đủ nến: cần {settings.required_bars()}, đang có {len(candles)}.",),
        )
    snapshot = analyze(candles, settings)
    if snapshot is None:
        return _hold(symbol, 0.0, 0.0, ("Chưa tính đủ chỉ báo trên chuỗi nến.",))
    news_view = score_news(
        news, as_of=candles[-1].time, interval=settings.interval, symbol=symbol
    )
    reasons = [
        (
            f"Giá {format_number(snapshot.price)}, điểm kỹ thuật {snapshot.score:+.2f}, "
            f"RSI {snapshot.rsi:.1f}, ATR {snapshot.atr_pct:.2%}."
        ),
        (
            f"EMA {settings.ema_fast} {format_number(snapshot.ema_fast)} / "
            f"EMA {settings.ema_slow} {format_number(snapshot.ema_slow)}, "
            f"histogram MACD {_signed(snapshot.macd_hist)}."
        ),
        *news_view.reasons,
    ]

    if account.position is not None:
        return _manage_open(symbol, snapshot, news_view.score, account, settings, reasons)

    if account.entries_halted:
        reasons.append("Đã chạm trần lỗ trong ngày, không mở lệnh mới.")
        return _hold(symbol, snapshot.score, news_view.score, tuple(reasons), snapshot)

    if snapshot.atr_pct > settings.max_atr_pct:
        reasons.append(
            f"ATR {snapshot.atr_pct:.2%} vượt trần {settings.max_atr_pct:.2%}, đứng ngoài."
        )
        return _hold(symbol, snapshot.score, news_view.score, tuple(reasons), snapshot)

    long_blocks = _long_blocks(snapshot, settings)
    short_blocks = _short_blocks(snapshot, settings)
    if not long_blocks:
        if news_view.score <= -settings.news_veto:
            reasons.append("Tin tiêu cực át tín hiệu mua. Bỏ qua lệnh.")
            if news_view.titles:
                reasons.append("Tin: " + " | ".join(news_view.titles))
            return _hold(symbol, snapshot.score, news_view.score, tuple(reasons), snapshot)
        return _open(symbol, Side.LONG, snapshot, news_view.score, account, settings, reasons, news_view.titles)
    if not short_blocks:
        if news_view.score >= settings.news_veto:
            reasons.append("Tin tích cực át tín hiệu bán. Bỏ qua lệnh.")
            if news_view.titles:
                reasons.append("Tin: " + " | ".join(news_view.titles))
            return _hold(symbol, snapshot.score, news_view.score, tuple(reasons), snapshot)
        return _open(symbol, Side.SHORT, snapshot, news_view.score, account, settings, reasons, news_view.titles)

    if abs(snapshot.score) >= settings.entry_threshold * 0.8:
        nearer = long_blocks if snapshot.score > 0 else short_blocks
        reasons.extend(nearer)
    else:
        reasons.append("Các chỉ báo chưa lệch đủ để vào lệnh.")
    return _hold(symbol, snapshot.score, news_view.score, tuple(reasons), snapshot)


def _manage_open(
    symbol: str,
    snapshot: Snapshot,
    news_score: float,
    account: AccountView,
    settings: Settings,
    reasons: list[str],
) -> Decision:
    position = account.position
    assert position is not None
    side_name = "mua" if position.side is Side.LONG else "bán"
    flipped_long = position.side is Side.LONG and snapshot.score <= -settings.entry_threshold
    flipped_short = position.side is Side.SHORT and snapshot.score >= settings.entry_threshold
    trend_against = (
        position.side is Side.LONG and snapshot.ema_fast < snapshot.ema_slow
    ) or (position.side is Side.SHORT and snapshot.ema_fast > snapshot.ema_slow)
    if (flipped_long or flipped_short) and trend_against:
        reasons.append(f"Đóng lệnh {side_name} vì tín hiệu đảo chiều.")
        return Decision(
            action=Action.CLOSE,
            symbol=symbol,
            score=snapshot.score,
            news_score=news_score,
            reasons=tuple(reasons),
            snapshot=snapshot,
        )
    reasons.append(
        f"Giữ lệnh {side_name} {position.leverage}x, "
        f"dừng {format_number(position.stop)}, chốt {format_number(position.take_profit)}, "
        f"thanh lý {format_number(position.liquidation)}."
    )
    return _hold(symbol, snapshot.score, news_score, tuple(reasons), snapshot)


def _open(
    symbol: str,
    side: Side,
    snapshot: Snapshot,
    news_score: float,
    account: AccountView,
    settings: Settings,
    reasons: list[str],
    titles: tuple[str, ...],
) -> Decision:
    plan, error = size_order(
        symbol=symbol,
        side=side,
        snapshot=snapshot,
        equity=account.equity,
        settings=settings,
    )
    name = "mua" if side is Side.LONG else "bán"
    if error or plan is None:
        reasons.append(error or "Không lập được kế hoạch lệnh.")
        return _hold(symbol, snapshot.score, news_score, tuple(reasons), snapshot)
    reasons.append(
        f"Vào lệnh {name} {plan.leverage}x, khối lượng {plan.qty:.6g}, "
        f"ký quỹ {plan.margin:.2f} USDT, rủi ro tại dừng lỗ {plan.risk_cash:.2f} USDT."
    )
    reasons.append(
        f"Dừng {format_number(plan.stop)}, chốt {format_number(plan.take_profit)}, "
        f"thanh lý {format_number(plan.liquidation)}."
    )
    if titles:
        reasons.append("Tin đã đọc: " + " | ".join(titles))
    return Decision(
        action=Action.OPEN_LONG if side is Side.LONG else Action.OPEN_SHORT,
        symbol=symbol,
        score=snapshot.score,
        news_score=news_score,
        reasons=tuple(reasons),
        order=plan,
        snapshot=snapshot,
    )


def _long_blocks(snapshot: Snapshot, settings: Settings) -> list[str]:
    blocks: list[str] = []
    if snapshot.score < settings.entry_threshold:
        blocks.append(f"Điểm {snapshot.score:+.2f} chưa đạt ngưỡng mua {settings.entry_threshold:.2f}.")
    if snapshot.ema_fast <= snapshot.ema_slow:
        blocks.append("EMA nhanh chưa nằm trên EMA chậm.")
    if snapshot.macd_hist <= 0:
        blocks.append("Histogram MACD chưa dương.")
    if not settings.rsi_long_min <= snapshot.rsi <= settings.rsi_long_max:
        blocks.append(
            f"RSI {snapshot.rsi:.1f} ngoài vùng mua {settings.rsi_long_min:.0f}-{settings.rsi_long_max:.0f}."
        )
    return blocks


def _short_blocks(snapshot: Snapshot, settings: Settings) -> list[str]:
    blocks: list[str] = []
    if snapshot.score > -settings.entry_threshold:
        blocks.append(f"Điểm {snapshot.score:+.2f} chưa đạt ngưỡng bán {-settings.entry_threshold:.2f}.")
    if snapshot.ema_fast >= snapshot.ema_slow:
        blocks.append("EMA nhanh chưa nằm dưới EMA chậm.")
    if snapshot.macd_hist >= 0:
        blocks.append("Histogram MACD chưa âm.")
    if not settings.rsi_short_min <= snapshot.rsi <= settings.rsi_short_max:
        blocks.append(
            f"RSI {snapshot.rsi:.1f} ngoài vùng bán {settings.rsi_short_min:.0f}-{settings.rsi_short_max:.0f}."
        )
    return blocks


def _signed(value: float) -> str:
    text = format_number(value)
    if value > 0:
        return "+" + text
    return text


def _hold(
    symbol: str,
    score: float,
    news_score: float,
    reasons: tuple[str, ...],
    snapshot: Snapshot | None = None,
) -> Decision:
    return Decision(
        action=Action.HOLD,
        symbol=symbol,
        score=score,
        news_score=news_score,
        reasons=reasons,
        snapshot=snapshot,
    )
