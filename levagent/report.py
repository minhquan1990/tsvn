"""Bản in tiếng Việt cho quyết định và kết quả backtest."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from levagent.backtest import BacktestResult
from levagent.formatting import format_number
from levagent.broker import PaperBroker
from levagent.models import Action, Decision

_ICT = timezone(timedelta(hours=7))
_ACTION = {
    Action.HOLD: "ĐỨNG NGOÀI",
    Action.OPEN_LONG: "VÀO LỆNH MUA",
    Action.OPEN_SHORT: "VÀO LỆNH BÁN",
    Action.CLOSE: "ĐÓNG LỆNH",
}


def format_time(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, _ICT).strftime("%Y-%m-%d %H:%M ICT")


def format_decision(decision: Decision, *, mode: str) -> str:
    lines = [
        f"LevAgent — {mode} — {decision.symbol}",
        f"Quyết định: {_ACTION[decision.action]}",
        f"Điểm kỹ thuật {decision.score:+.2f} | điểm tin {decision.news_score:+.2f}",
        "Lý do:",
    ]
    lines.extend(f"- {reason}" for reason in decision.reasons)
    lines.append("Đây không phải lời khuyên đầu tư. Đòn bẩy có thể làm mất hết vốn.")
    return "\n".join(lines)


def format_backtest(result: BacktestResult, symbol: str) -> str:
    pnl = result.end_equity - result.start_equity
    lines = [
        f"LevAgent — backtest giả lập {symbol}",
        f"Vốn đầu: {result.start_equity:,.2f} USDT",
        f"Vốn cuối: {result.end_equity:,.2f} USDT",
        f"Lãi/lỗ: {pnl:,.2f} USDT",
        f"Số lệnh: {len(result.trades)} (thắng {result.wins})",
        f"Lệnh bỏ qua vì không khớp an toàn: {result.skipped}",
        f"Drawdown tối đa: {result.max_drawdown:.2%}",
        f"Đòn bẩy cao nhất đã dùng: {result.max_leverage}x",
    ]
    if result.trades:
        last = result.trades[-1]
        lines.append(
            f"Lệnh cuối: {last.side.value} {last.leverage}x, "
            f"vào {format_number(last.entry)} ra {format_number(last.exit)}, "
            f"{last.pnl:+.2f} USDT ({last.reason}) "
            f"lúc {format_time(last.closed_at)}"
        )
    lines.append("Kết quả quá khứ không phải lợi nhuận tương lai.")
    return "\n".join(lines)


def format_status(broker: PaperBroker) -> str:
    lines = [
        f"LevAgent — sổ giả lập {broker.settings.symbol}",
        f"Vốn: {broker.equity:,.2f} USDT",
        f"Lỗ/lãi đã chốt trong ngày UTC {broker.day or 'chưa có'}: {broker.day_realized:+.2f} USDT",
        "Đang khóa lệnh mới." if broker.entries_halted else "Có thể mở lệnh mới.",
    ]
    position = broker.position
    if position is None:
        lines.append("Không có vị thế.")
    else:
        lines.append(
            f"Vị thế {position.side.value} {position.leverage}x, "
            f"khối lượng {position.qty:.6g} tại {format_number(position.entry)}, "
            f"dừng {format_number(position.stop)}, chốt {format_number(position.take_profit)}, "
            f"thanh lý {format_number(position.liquidation)}."
        )
    lines.append(f"Số lệnh đã đóng: {len(broker.trades)}")
    return "\n".join(lines)
