"""Dữ liệu công khai: nến USDT-M và RSS. Lỗi mạng không làm sập tác nhân."""

from __future__ import annotations

import json
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from levagent.config import ALLOWED_INTERVALS
from levagent.models import Candle, NewsItem
from levagent.news import parse_rss

_SYMBOL = re.compile(r"^[A-Z0-9]{5,20}$")
_KLINE_URLS = (
    "https://fapi.binance.com/fapi/v1/klines",
    "https://data-api.binance.vision/api/v3/klines",
    "https://api.binance.us/api/v3/klines",
)
_FEEDS = (
    ("CoinDesk", "https://www.coindesk.com/arc/outboundfeeds/rss/"),
    ("Cointelegraph", "https://cointelegraph.com/rss"),
)
_USER_AGENT = "levagent/0.1"


def validate_symbol(symbol: str) -> str:
    if not _SYMBOL.fullmatch(symbol):
        raise ValueError("Mã phải gồm 5-20 chữ hoặc số, ví dụ BTCUSDT.")
    return symbol


def validate_interval(interval: str) -> str:
    if interval not in ALLOWED_INTERVALS:
        raise ValueError(f"Khung thời gian phải thuộc {', '.join(ALLOWED_INTERVALS)}.")
    return interval


def parse_klines(payload: list) -> list[Candle]:
    candles: list[Candle] = []
    for row in payload:
        candles.append(
            Candle(
                time=int(row[0]),
                open=float(row[1]),
                high=float(row[2]),
                low=float(row[3]),
                close=float(row[4]),
                volume=float(row[5]),
            )
        )
    candles.sort(key=lambda candle: candle.time)
    return candles


def fetch_klines(
    symbol: str,
    interval: str,
    limit: int = 300,
    timeout: float = 10,
    get=None,
) -> list[Candle]:
    if get is None:
        get = _get
    symbol = validate_symbol(symbol)
    interval = validate_interval(interval)
    limit = max(50, min(int(limit), 1000))
    errors: list[str] = []
    for base in _KLINE_URLS:
        url = f"{base}?symbol={symbol}&interval={interval}&limit={limit}"
        try:
            payload = json.loads(get(url, timeout))
        except (HTTPError, URLError, TimeoutError, RuntimeError, ValueError) as exc:
            errors.append(f"{base}: {exc}")
            continue
        if isinstance(payload, list) and payload:
            return parse_klines(payload)
        errors.append(f"{base}: dữ liệu trống")
    raise RuntimeError("Không tải được nến. " + "; ".join(errors))


def fetch_news(timeout: float = 8) -> tuple[list[NewsItem], str | None]:
    items: list[NewsItem] = []
    errors: list[str] = []
    for source, url in _FEEDS:
        try:
            items.extend(parse_rss(_get(url, timeout), source))
        except (HTTPError, URLError, TimeoutError, RuntimeError, ValueError) as exc:
            errors.append(f"{source}: {exc.__class__.__name__}")
    items.sort(key=lambda item: item.time)
    if items:
        return items, None
    if errors:
        return [], "Không đọc được tin (" + ", ".join(errors) + "). Bỏ qua tin tức."
    return [], "Nguồn tin không có mục nào dùng được."


def _get(url: str, timeout: float) -> str:
    request = Request(url, headers={"User-Agent": _USER_AGENT, "Accept": "*/*"})
    try:
        with urlopen(request, timeout=timeout) as response:
            return response.read().decode("utf-8", errors="replace")
    except HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code}") from exc
