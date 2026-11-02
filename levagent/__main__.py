"""Giao diện dòng lệnh của LevAgent."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from levagent.backtest import run_backtest
from levagent.broker import PaperBroker
from levagent.config import HARD_MAX_LEVERAGE, Settings
from levagent.decision import decide
from levagent.engine import run_once
from levagent.live import LiveTradingDisabled, UrllibHttp, credentials_from_env, execute
from levagent.market import fetch_klines, fetch_news, validate_interval, validate_symbol
from levagent.models import NewsItem
from levagent.report import format_backtest, format_decision, format_status
from levagent.synthetic import trending

_STATE = Path("state/paper.json")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="levagent",
        description="Tác nhân giao dịch đòn bẩy. Mặc định chỉ giả lập, không gửi lệnh thật.",
    )
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--symbol", default="BTCUSDT")
    common.add_argument("--interval", default="1h")
    common.add_argument("--equity", type=float, default=10_000)
    common.add_argument("--risk", type=float, default=0.005)
    common.add_argument("--leverage", type=int, default=3)
    sub = parser.add_subparsers(dest="command", required=True)

    demo = sub.add_parser("demo", parents=[common], help="Backtest trên nến giả lập, không cần mạng")
    demo.add_argument("--direction", choices=("up", "down"), default="up")
    _add_headlines(demo)

    decide_cmd = sub.add_parser("decide", parents=[common], help="In quyết định, không vào lệnh")
    decide_cmd.add_argument("--synthetic", action="store_true")
    decide_cmd.add_argument("--limit", type=int, default=300)
    _add_headlines(decide_cmd)

    backtest = sub.add_parser("backtest", parents=[common], help="Backtest giả lập")
    backtest.add_argument("--synthetic", action="store_true")
    backtest.add_argument("--direction", choices=("up", "down"), default="up")
    backtest.add_argument("--limit", type=int, default=300)
    _add_headlines(backtest)

    run = sub.add_parser("run", parents=[common], help="Một vòng sổ giả lập, có ghi trạng thái")
    run.add_argument("--synthetic", action="store_true")
    run.add_argument("--reset", action="store_true")
    run.add_argument("--state", default=str(_STATE))
    run.add_argument("--limit", type=int, default=300)
    _add_headlines(run)

    status = sub.add_parser("status", parents=[common], help="Xem sổ giả lập")
    status.add_argument("--state", default=str(_STATE))

    live = sub.add_parser("live", parents=[common], help="Xem kế hoạch lệnh thật; chỉ gửi khi có --send")
    live.add_argument("--send", action="store_true")
    live.add_argument("--limit", type=int, default=300)
    _add_headlines(live)

    args = parser.parse_args(argv)
    try:
        settings = _settings(args)
    except ValueError as exc:
        print(f"Cấu hình không hợp lệ: {exc}", file=sys.stderr)
        return 2

    try:
        if args.command == "demo":
            return _demo(args, settings)
        if args.command == "decide":
            return _decide(args, settings)
        if args.command == "backtest":
            return _backtest(args, settings)
        if args.command == "run":
            return _run(args, settings)
        if args.command == "status":
            return _status(args, settings)
        if args.command == "live":
            return _live(args, settings)
    except (ValueError, RuntimeError, OSError) as exc:
        print(f"Lỗi: {exc}", file=sys.stderr)
        return 1
    print("Lệnh không xác định.", file=sys.stderr)
    return 2


def _add_headlines(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--headline",
        action="append",
        default=[],
        help="Tiêu đề tin thêm vào, có thể lặp lại",
    )


def _settings(args: argparse.Namespace) -> Settings:
    symbol = validate_symbol(args.symbol.upper())
    interval = validate_interval(args.interval)
    if args.leverage > HARD_MAX_LEVERAGE:
        raise ValueError(f"đòn bẩy tối đa là {HARD_MAX_LEVERAGE}")
    return Settings(
        symbol=symbol,
        interval=interval,
        equity=args.equity,
        risk_pct=args.risk,
        max_leverage=args.leverage,
    )


def _headlines(args: argparse.Namespace, as_of: int) -> list[NewsItem]:
    items: list[NewsItem] = []
    for title in args.headline:
        compact = " ".join(title.split())
        if not compact:
            continue
        items.append(NewsItem(time=as_of, title=compact[:300], source="cli"))
    return items


def _load_market(args: argparse.Namespace, settings: Settings):
    if getattr(args, "synthetic", False) or args.command == "demo":
        direction = 1 if getattr(args, "direction", "up") == "up" else -1
        candles = trending(direction=direction)
        news = _headlines(args, candles[-1].time)
        return candles, news, None
    candles = fetch_klines(settings.symbol, settings.interval, args.limit)
    news, warning = fetch_news()
    news = [*news, *_headlines(args, candles[-1].time if candles else 0)]
    return candles, news, warning


def _demo(args: argparse.Namespace, settings: Settings) -> int:
    candles, news, _warning = _load_market(args, settings)
    result = run_backtest(candles, news, settings)
    print(format_backtest(result, settings.symbol))
    print(
        "Chuỗi này là xu hướng giả lập rất mượt. "
        "Số lệnh thắng trên chuỗi đó chỉ kiểm tra cách khớp lệnh, không phải lợi thế ngoài thị trường."
    )
    fresh = PaperBroker(settings)
    decision = decide(candles, news, fresh.view(), settings)
    print()
    print(format_decision(decision, mode="tín hiệu cuối trên dữ liệu giả lập"))
    return 0


def _decide(args: argparse.Namespace, settings: Settings) -> int:
    candles, news, warning = _load_market(args, settings)
    if warning:
        print(warning)
    decision = decide(candles, news, PaperBroker(settings).view(), settings)
    print(format_decision(decision, mode="chỉ xem, không vào lệnh"))
    return 0


def _backtest(args: argparse.Namespace, settings: Settings) -> int:
    candles, news, warning = _load_market(args, settings)
    if warning:
        print(warning)
    result = run_backtest(candles, news, settings)
    print(format_backtest(result, settings.symbol))
    return 0


def _run(args: argparse.Namespace, settings: Settings) -> int:
    path = Path(args.state)
    broker = PaperBroker(settings)
    if path.exists() and not args.reset:
        broker.load_dict(json.loads(path.read_text(encoding="utf-8")))
    elif args.reset and path.exists():
        path.unlink()
    candles, news, warning = _load_market(args, settings)
    if warning:
        print(warning)
    decision = run_once(candles, news, broker, settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(broker.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    print(format_decision(decision, mode="GIẢ LẬP — không gửi sàn"))
    print()
    print(format_status(broker))
    print(f"Đã ghi trạng thái: {path}")
    return 0


def _status(args: argparse.Namespace, settings: Settings) -> int:
    path = Path(args.state)
    if not path.exists():
        print("Chưa có sổ giả lập. Chạy: python -m levagent run --synthetic")
        return 0
    broker = PaperBroker(settings)
    broker.load_dict(json.loads(path.read_text(encoding="utf-8")))
    print(format_status(broker))
    return 0


def _live(args: argparse.Namespace, settings: Settings) -> int:
    candles = fetch_klines(settings.symbol, settings.interval, args.limit)
    news, warning = fetch_news()
    if warning:
        print(warning)
    news = [*news, *_headlines(args, candles[-1].time)]
    decision = decide(candles, news, PaperBroker(settings).view(), settings)
    print(format_decision(decision, mode="xem trước lệnh thật"))
    if decision.order is None:
        print("Không có lệnh để gửi.")
        return 0
    print("Chế độ một chiều (one-way) của Binance USDT-M. Dừng lỗ là bắt buộc.")
    try:
        execute(decision.order, credentials_from_env(), UrllibHttp(), send=args.send)
    except LiveTradingDisabled as exc:
        print(str(exc))
        return 0 if not args.send else 1
    print("Đã gửi lệnh thị trường kèm dừng lỗ và chốt lời.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
