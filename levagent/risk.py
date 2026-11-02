"""Khối lượng lệnh theo số tiền chấp nhận mất tại dừng lỗ, không theo đòn bẩy tối đa."""

from __future__ import annotations

import math

from levagent.config import HARD_MAX_LEVERAGE, MIN_NOTIONAL, Settings
from levagent.models import OrderPlan, Side, Snapshot


def liquidation_price(entry: float, leverage: int, side: Side, maintenance: float) -> float:
    if leverage < 1:
        raise ValueError("đòn bẩy phải >= 1")
    if side is Side.LONG:
        price = entry * (1 - 1 / leverage + maintenance)
    else:
        price = entry * (1 + 1 / leverage - maintenance)
    return max(price, 0.0)


def stop_protects(
    *,
    entry: float,
    stop: float,
    leverage: int,
    side: Side,
    maintenance: float,
    buffer: float,
) -> bool:
    liq = liquidation_price(entry, leverage, side, maintenance)
    room = abs(entry - liq)
    if room <= 0:
        return False
    distance = abs(entry - stop)
    if distance <= 0 or distance > room * buffer:
        return False
    if side is Side.LONG:
        return liq < stop < entry
    return entry < stop < liq


def geometry_ok(plan: OrderPlan) -> bool:
    if plan.side is Side.LONG:
        return plan.liquidation < plan.stop < plan.entry < plan.take_profit
    return 0 < plan.take_profit < plan.entry < plan.stop < plan.liquidation


def size_order(
    *,
    symbol: str,
    side: Side,
    snapshot: Snapshot,
    equity: float,
    settings: Settings,
) -> tuple[OrderPlan | None, str | None]:
    if equity <= 0 or snapshot.price <= 0 or snapshot.atr <= 0:
        return None, "Thiếu vốn, giá hoặc ATR để tính khối lượng."
    if settings.max_leverage > HARD_MAX_LEVERAGE:
        return None, f"Đòn bẩy vượt trần cứng {HARD_MAX_LEVERAGE}."
    return _build(
        symbol=symbol,
        side=side,
        entry=snapshot.price,
        stop_distance=snapshot.atr * settings.atr_mult,
        equity=equity,
        settings=settings,
    )


def reprice_with_equity(
    plan: OrderPlan, fill: float, equity: float, settings: Settings
) -> tuple[OrderPlan | None, str | None]:
    """Giữ khoảng dừng và hệ số R, tính lại giá khi khớp ở nến sau."""

    if fill <= 0 or equity <= 0:
        return None, "Giá khớp hoặc vốn không hợp lệ."
    stop_distance = abs(plan.entry - plan.stop)
    scale = fill / plan.entry
    qty = plan.qty / scale
    return _from_qty(
        symbol=plan.symbol,
        side=plan.side,
        entry=fill,
        stop_distance=stop_distance,
        qty=qty,
        leverage=plan.leverage,
        equity=equity,
        settings=settings,
    )


def _build(
    *,
    symbol: str,
    side: Side,
    entry: float,
    stop_distance: float,
    equity: float,
    settings: Settings,
) -> tuple[OrderPlan | None, str | None]:
    if stop_distance <= 0 or entry <= 0:
        return None, "Khoảng dừng lỗ không hợp lệ."
    risk_cash = equity * settings.risk_pct
    qty = risk_cash / stop_distance
    notional = qty * entry
    if notional < MIN_NOTIONAL:
        return None, f"Khối lượng {notional:.2f} USDT nhỏ hơn mức tối thiểu {MIN_NOTIONAL:.0f}."
    stop_pct = stop_distance / entry
    raw_fit = settings.stop_buffer / (stop_pct + settings.stop_buffer * settings.maintenance_margin_rate)
    lev_fit = int(math.floor(raw_fit))
    if lev_fit < 1:
        return None, "Khoảng dừng lỗ quá rộng so với giá thanh lý ở đòn bẩy 1."
    if notional <= equity:
        needed = 1
    else:
        needed = math.ceil(notional / equity - 1e-9)
    leverage = min(settings.max_leverage, lev_fit, needed, HARD_MAX_LEVERAGE)
    while leverage >= 1:
        capped = min(notional, equity * leverage)
        capped = min(capped, (equity * 0.999) / (1 / leverage + settings.fee_rate))
        if capped >= MIN_NOTIONAL:
            plan, error = _from_qty(
                symbol=symbol,
                side=side,
                entry=entry,
                stop_distance=stop_distance,
                qty=capped / entry,
                leverage=leverage,
                equity=equity,
                settings=settings,
            )
            if plan is not None:
                return plan, None
        leverage -= 1
    return None, "Không tìm được đòn bẩy để dừng lỗ nằm trước giá thanh lý."


def _from_qty(
    *,
    symbol: str,
    side: Side,
    entry: float,
    stop_distance: float,
    qty: float,
    leverage: int,
    equity: float,
    settings: Settings,
) -> tuple[OrderPlan | None, str | None]:
    if leverage < 1 or leverage > HARD_MAX_LEVERAGE:
        return None, "Đòn bẩy ngoài trần cho phép."
    if qty <= 0:
        return None, "Khối lượng bằng 0."
    notional = qty * entry
    if notional < MIN_NOTIONAL:
        return None, f"Khối lượng {notional:.2f} USDT nhỏ hơn mức tối thiểu {MIN_NOTIONAL:.0f}."
    margin = notional / leverage
    fee = notional * settings.fee_rate
    if margin + fee > equity + 1e-8:
        return None, "Không đủ vốn cho ký quỹ cô lập và phí."
    if side is Side.LONG:
        stop = entry - stop_distance
        take_profit = entry + stop_distance * settings.reward_r
    else:
        stop = entry + stop_distance
        take_profit = entry - stop_distance * settings.reward_r
    if min(stop, take_profit) <= 0:
        return None, "Giá dừng hoặc giá chốt không dương."
    if not stop_protects(
        entry=entry,
        stop=stop,
        leverage=leverage,
        side=side,
        maintenance=settings.maintenance_margin_rate,
        buffer=settings.stop_buffer,
    ):
        return None, "Dừng lỗ không nằm an toàn trước giá thanh lý."
    plan = OrderPlan(
        symbol=symbol,
        side=side,
        qty=qty,
        entry=entry,
        stop=stop,
        take_profit=take_profit,
        leverage=leverage,
        margin=margin,
        liquidation=liquidation_price(entry, leverage, side, settings.maintenance_margin_rate),
        notional=notional,
        risk_cash=qty * stop_distance,
    )
    if not geometry_ok(plan):
        return None, "Hình học lệnh không hợp lệ."
    return plan, None
