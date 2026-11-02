"""Điểm tin tức bằng từ điển. Tin không tự tạo lệnh, chỉ có thể chặn lệnh."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

from levagent.config import lookback_ms
from levagent.models import NewsItem, NewsView

# Quy tắc cụ thể đứng trước quy tắc chung. Điểm mỗi tiêu đề bị kẹp trong [-1, 1].
_RULES: tuple[tuple[str, float], ...] = (
    (r"etf.{0,40}(từ chối|rejected|rejection)|((từ chối|rejected|rejection).{0,40}etf)", -1.0),
    (r"(phê duyệt|approved|approval).{0,40}etf|etf.{0,40}(phê duyệt|approved|approval)", 1.0),
    (r"bị hack|\bhacked\b|\bhacker\b|\bhack\b|\bexploit\b", -1.0),
    (r"phá sản|\bbankruptcy\b|\bbankrupt\b", -1.0),
    (r"\bcrash\b|sụp đổ", -0.8),
    (r"\blawsuit\b|kiện tụng|\bfraud\b|\bscam\b", -0.8),
    (r"\bban\b|\bcấm\b|siết chặt", -0.7),
    (r"tăng mạnh|phá đỉnh|\brally\b|\bsurge\b|\bbreakout\b", 0.7),
    (r"\badoption\b|mua vào|dòng vốn", 0.6),
    (r"\bbullish\b", 0.5),
    (r"\bbearish\b", -0.5),
    (r"\bliquidation\b|bị thanh lý", -0.4),
)
_COMPILED = tuple((re.compile(pattern, re.IGNORECASE), weight) for pattern, weight in _RULES)

_QUOTES = ("USDT", "USDC", "BUSD", "FDUSD")
_ALIASES = {
    "BTC": ("btc", "bitcoin"),
    "ETH": ("eth", "ethereum"),
    "SOL": ("sol", "solana"),
    "BNB": ("bnb",),
    "XRP": ("xrp", "ripple"),
    "DOGE": ("doge", "dogecoin"),
}


def score_title(title: str) -> float:
    total = 0.0
    for pattern, weight in _COMPILED:
        if pattern.search(title):
            total += weight
    return max(-1.0, min(1.0, total))


def base_asset(symbol: str) -> str:
    for quote in _QUOTES:
        if symbol.endswith(quote) and len(symbol) > len(quote):
            return symbol[: -len(quote)]
    return symbol


def mentions_asset(title: str, symbol: str) -> bool:
    aliases = _ALIASES.get(base_asset(symbol), (base_asset(symbol).lower(),))
    for alias in aliases:
        if re.search(rf"\b{re.escape(alias)}\b", title, flags=re.IGNORECASE):
            return True
    return False


def score_news(
    items: list[NewsItem], *, as_of: int, interval: str, symbol: str
) -> NewsView:
    window = lookback_ms(interval)
    recent = [item for item in items if as_of - window <= item.time <= as_of]
    if not recent:
        return NewsView(0.0, (), ("Không có tin trong cửa sổ thời gian.",))
    focused = [item for item in recent if mentions_asset(item.title, symbol)]
    reasons: list[str] = []
    chosen = focused or recent
    if focused:
        reasons.append(f"Dùng {len(focused)} tin có nhắc {base_asset(symbol)}.")
    else:
        reasons.append("Không có tin riêng cho mã, dùng tin chung trong cửa sổ.")
    scores = [score_title(item.title) for item in chosen]
    score = max(-1.0, min(1.0, sum(scores) / len(scores)))
    reasons.append(f"Điểm tin {score:+.2f} trên {len(chosen)} tiêu đề.")
    titles = tuple(item.title for item in chosen[:5])
    return NewsView(score, titles, tuple(reasons))


def parse_rss(xml_text: str, source: str) -> list[NewsItem]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []
    items: list[NewsItem] = []
    for node in root.iter():
        tag = node.tag.split("}")[-1]
        if tag not in ("item", "entry"):
            continue
        title = _child_text(node, "title")
        if not title:
            continue
        stamp = _child_time(node)
        if stamp is None:
            continue
        items.append(NewsItem(time=stamp, title=title, source=source))
    return items


def _child_text(node: ET.Element, name: str) -> str:
    for child in list(node):
        if child.tag.split("}")[-1] == name and child.text:
            return " ".join(child.text.split())
    return ""


def _child_time(node: ET.Element) -> int | None:
    for name in ("pubDate", "published", "updated", "date"):
        raw = _child_text(node, name)
        if not raw:
            continue
        parsed = _parse_time(raw)
        if parsed is not None:
            return parsed
    return None


def _parse_time(raw: str) -> int | None:
    try:
        return int(parsedate_to_datetime(raw).timestamp() * 1000)
    except (TypeError, ValueError, IndexError, OverflowError):
        pass
    try:
        from datetime import datetime

        text = raw.replace("Z", "+00:00")
        return int(datetime.fromisoformat(text).timestamp() * 1000)
    except ValueError:
        return None
