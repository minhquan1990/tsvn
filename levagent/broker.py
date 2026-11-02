"""Sổ lệnh giả lập với ký quỹ cô lập, phí, dừng lỗ, chốt lời và thanh lý."""

from __future__ import annotations

from datetime import datetime, timezone

from levagent.config import HARD_MAX_LEVERAGE, Settings
from levagent.models import AccountView, Candle, ClosedTrade, OrderPlan, Position, Side
from levagent.risk import geometry_ok


class PaperBroker:
    def __init__(self, settings: Settings, equity: float | None = None) -> None:
        self.settings = settings
        self.equity = settings.equity if equity is None else equity
        self.position: Position | None = None
        self.trades: list[ClosedTrade] = []
        self.day = ""
        self.day_start_equity = self.equity
        self.day_realized = 0.0
        self.last_candle_time = 0
        self.peak = self.equity
        self.max_drawdown = 0.0

    def view(self) -> AccountView:
        return AccountView(
            equity=self.equity,
            entries_halted=self.entries_halted,
            position=self.position,
            day_realized=self.day_realized,
        )

    @property
    def entries_halted(self) -> bool:
        if self.day_start_equity <= 0:
            return True
        return self.day_realized <= -self.settings.max_daily_loss_pct * self.day_start_equity

    def equity_mark(self, price: float) -> float:
        if self.position is None:
            return self.equity
        pnl = _pnl(self.position, price)
        close_fee = price * self.position.qty * self.settings.fee_rate
        return self.equity + pnl - close_fee

    def mark(self, price: float) -> None:
        current = self.equity_mark(price)
        self.peak = max(self.peak, current)
        if self.peak > 0:
            self.max_drawdown = max(self.max_drawdown, (self.peak - current) / self.peak)

    def open(self, plan: OrderPlan, time_ms: int) -> str | None:
        if self.position is not None:
            return "Đã có vị thế, không mở thêm."
        if plan.symbol != self.settings.symbol:
            return "Mã lệnh khác mã đang theo dõi."
        if plan.leverage > min(self.settings.max_leverage, HARD_MAX_LEVERAGE):
            return "Đòn bẩy vượt trần đã cấu hình."
        if not geometry_ok(plan):
            return "Dừng lỗ không bảo vệ được trước thanh lý."
        fee = plan.notional * self.settings.fee_rate
        if plan.margin + fee > self.equity + 1e-8:
            return "Không đủ vốn cho ký quỹ và phí."
        self._roll_day(time_ms)
        self.equity -= fee
        self.day_realized -= fee
        self.position = Position(
            symbol=plan.symbol,
            side=plan.side,
            qty=plan.qty,
            entry=plan.entry,
            leverage=plan.leverage,
            margin=plan.margin,
            stop=plan.stop,
            take_profit=plan.take_profit,
            liquidation=plan.liquidation,
            opened_at=time_ms,
            open_fee=fee,
        )
        return None

    def close(self, price: float, time_ms: int, reason: str) -> ClosedTrade | None:
        if self.position is None or price <= 0:
            return None
        self._roll_day(time_ms)
        return self._close(price, time_ms, reason)

    def on_candle(self, candle: Candle) -> ClosedTrade | None:
        self._roll_day(candle.time)
        position = self.position
        if position is None:
            self.mark(candle.close)
            return None
        exit_plan = _exit_fill(position, candle)
        if exit_plan is None:
            self.mark(candle.close)
            return None
        kind, price = exit_plan
        if kind == "liq":
            return self._liquidate(candle.time)
        reason = "Dừng lỗ" if kind == "stop" else "Chốt lời"
        return self._close(price, candle.time, reason)

    def to_dict(self) -> dict:
        position = None
        if self.position is not None:
            pos = self.position
            position = {
                "symbol": pos.symbol,
                "side": pos.side.value,
                "qty": pos.qty,
                "entry": pos.entry,
                "leverage": pos.leverage,
                "margin": pos.margin,
                "stop": pos.stop,
                "take_profit": pos.take_profit,
                "liquidation": pos.liquidation,
                "opened_at": pos.opened_at,
                "open_fee": pos.open_fee,
            }
        return {
            "version": 1,
            "symbol": self.settings.symbol,
            "equity": self.equity,
            "day": self.day,
            "day_start_equity": self.day_start_equity,
            "day_realized": self.day_realized,
            "last_candle_time": self.last_candle_time,
            "position": position,
            "trades": [
                {
                    "symbol": trade.symbol,
                    "side": trade.side.value,
                    "qty": trade.qty,
                    "entry": trade.entry,
                    "exit": trade.exit,
                    "leverage": trade.leverage,
                    "pnl": trade.pnl,
                    "reason": trade.reason,
                    "opened_at": trade.opened_at,
                    "closed_at": trade.closed_at,
                }
                for trade in self.trades
            ],
        }

    def load_dict(self, data: dict) -> None:
        if data.get("version") != 1:
            raise ValueError("Tệp trạng thái không đúng phiên bản.")
        if data.get("symbol") != self.settings.symbol:
            raise ValueError("Tệp trạng thái thuộc mã khác.")
        self.equity = float(data["equity"])
        self.day = str(data.get("day") or "")
        self.day_start_equity = float(data["day_start_equity"])
        self.day_realized = float(data["day_realized"])
        self.last_candle_time = int(data.get("last_candle_time") or 0)
        self.trades = [
            ClosedTrade(
                symbol=item["symbol"],
                side=Side(item["side"]),
                qty=float(item["qty"]),
                entry=float(item["entry"]),
                exit=float(item["exit"]),
                leverage=int(item["leverage"]),
                pnl=float(item["pnl"]),
                reason=str(item["reason"]),
                opened_at=int(item["opened_at"]),
                closed_at=int(item["closed_at"]),
            )
            for item in data.get("trades", [])
        ]
        raw = data.get("position")
        if raw is None:
            self.position = None
        else:
            self.position = Position(
                symbol=raw["symbol"],
                side=Side(raw["side"]),
                qty=float(raw["qty"]),
                entry=float(raw["entry"]),
                leverage=int(raw["leverage"]),
                margin=float(raw["margin"]),
                stop=float(raw["stop"]),
                take_profit=float(raw["take_profit"]),
                liquidation=float(raw["liquidation"]),
                opened_at=int(raw["opened_at"]),
                open_fee=float(raw["open_fee"]),
            )
        self.peak = self.equity
        self.max_drawdown = 0.0

    def _close(self, price: float, time_ms: int, reason: str) -> ClosedTrade:
        position = self.position
        assert position is not None
        gross = _pnl(position, price)
        close_fee = price * position.qty * self.settings.fee_rate
        self.equity += gross - close_fee
        self.day_realized += gross - close_fee
        trade = ClosedTrade(
            symbol=position.symbol,
            side=position.side,
            qty=position.qty,
            entry=position.entry,
            exit=price,
            leverage=position.leverage,
            pnl=gross - close_fee - position.open_fee,
            reason=reason,
            opened_at=position.opened_at,
            closed_at=time_ms,
        )
        self.trades.append(trade)
        self.position = None
        self.mark(price)
        return trade

    def _liquidate(self, time_ms: int) -> ClosedTrade:
        position = self.position
        assert position is not None
        self.equity -= position.margin
        self.day_realized -= position.margin
        reported = -position.margin - position.open_fee
        trade = ClosedTrade(
            symbol=position.symbol,
            side=position.side,
            qty=position.qty,
            entry=position.entry,
            exit=position.liquidation,
            leverage=position.leverage,
            pnl=reported,
            reason="Thanh lý",
            opened_at=position.opened_at,
            closed_at=time_ms,
        )
        self.trades.append(trade)
        self.position = None
        self.mark(position.liquidation)
        return trade

    def _roll_day(self, time_ms: int) -> None:
        day = datetime.fromtimestamp(time_ms / 1000, timezone.utc).date().isoformat()
        if day != self.day:
            self.day = day
            self.day_start_equity = self.equity
            self.day_realized = 0.0


def _pnl(position: Position, price: float) -> float:
    if position.side is Side.LONG:
        return (price - position.entry) * position.qty
    return (position.entry - price) * position.qty


def _exit_fill(position: Position, candle: Candle) -> tuple[str, float] | None:
    if position.side is Side.LONG:
        if position.stop <= position.liquidation:
            return ("liq", candle.open)
        if candle.low <= position.stop or candle.open <= position.stop:
            if candle.open <= position.liquidation:
                return ("liq", candle.open)
            if candle.open < position.stop:
                return ("stop", candle.open)
            return ("stop", position.stop)
        if candle.high >= position.take_profit:
            if candle.open > position.take_profit:
                return ("tp", candle.open)
            return ("tp", position.take_profit)
        return None
    if position.stop >= position.liquidation:
        return ("liq", candle.open)
    if candle.high >= position.stop or candle.open >= position.stop:
        if candle.open >= position.liquidation:
            return ("liq", candle.open)
        if candle.open > position.stop:
            return ("stop", candle.open)
        return ("stop", position.stop)
    if candle.low <= position.take_profit:
        if candle.open < position.take_profit:
            return ("tp", candle.open)
        return ("tp", position.take_profit)
    return None
