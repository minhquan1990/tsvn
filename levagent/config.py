"""Tham số và trần an toàn. Trần đòn bẩy không nới qua CLI."""

from __future__ import annotations

from dataclasses import dataclass

HARD_MAX_LEVERAGE = 10
MIN_NOTIONAL = 5.0
ARM_PHRASE = "I_ACCEPT_TOTAL_LOSS"
ALLOWED_INTERVALS = ("1m", "5m", "15m", "1h", "4h", "1d")


@dataclass(frozen=True)
class Settings:
    symbol: str = "BTCUSDT"
    interval: str = "1h"
    equity: float = 10_000.0
    risk_pct: float = 0.005
    max_leverage: int = 3
    atr_mult: float = 1.5
    reward_r: float = 2.0
    max_atr_pct: float = 0.05
    fee_rate: float = 0.0004
    maintenance_margin_rate: float = 0.005
    max_daily_loss_pct: float = 0.03
    entry_threshold: float = 0.40
    news_veto: float = 0.55
    stop_buffer: float = 0.85
    ema_fast: int = 20
    ema_slow: int = 50
    rsi_period: int = 14
    rsi_long_min: float = 45.0
    rsi_long_max: float = 85.0
    rsi_short_min: float = 15.0
    rsi_short_max: float = 55.0
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    atr_period: int = 14
    warmup: int = 60

    def __post_init__(self) -> None:
        problems: list[str] = []
        if self.interval not in ALLOWED_INTERVALS:
            problems.append(f"khung thời gian phải thuộc {', '.join(ALLOWED_INTERVALS)}")
        if not 100 <= self.equity <= 100_000_000:
            problems.append("vốn phải từ 100 đến 100 triệu USDT")
        if not 0 < self.risk_pct <= 0.02:
            problems.append("rủi ro mỗi lệnh phải trong (0, 2%]")
        if not isinstance(self.max_leverage, int) or not 1 <= self.max_leverage <= HARD_MAX_LEVERAGE:
            problems.append(f"đòn bẩy phải là số nguyên từ 1 đến {HARD_MAX_LEVERAGE}")
        if not 0.5 <= self.atr_mult <= 5:
            problems.append("bội số ATR phải từ 0.5 đến 5")
        if not 1 <= self.reward_r <= 5:
            problems.append("hệ số chốt lời phải từ 1R đến 5R")
        if not 0.005 <= self.max_atr_pct <= 0.2:
            problems.append("trần ATR% phải từ 0.5% đến 20%")
        if not 0 <= self.fee_rate <= 0.01:
            problems.append("phí phải từ 0 đến 1%")
        if not 0.001 <= self.maintenance_margin_rate <= 0.05:
            problems.append("ký quỹ duy trì phải từ 0.1% đến 5%")
        if not 0.005 <= self.max_daily_loss_pct <= 0.10:
            problems.append("trần lỗ ngày phải từ 0.5% đến 10%")
        if not 0.2 <= self.entry_threshold <= 0.9:
            problems.append("ngưỡng vào lệnh phải từ 0.2 đến 0.9")
        if not 0.2 <= self.news_veto <= 0.95:
            problems.append("ngưỡng phủ quyết của tin phải từ 0.2 đến 0.95")
        if self.ema_fast >= self.ema_slow:
            problems.append("EMA nhanh phải ngắn hơn EMA chậm")
        if self.macd_fast >= self.macd_slow:
            problems.append("MACD nhanh phải ngắn hơn MACD chậm")
        if problems:
            raise ValueError("; ".join(problems))

    def required_bars(self) -> int:
        return max(
            self.warmup,
            self.ema_slow + self.macd_signal,
            self.atr_period + 2,
            self.rsi_period + 2,
        )


def lookback_ms(interval: str) -> int:
    hours = {
        "1m": 6,
        "5m": 12,
        "15m": 24,
        "1h": 24,
        "4h": 72,
        "1d": 24 * 7,
    }[interval]
    return hours * 3_600_000
