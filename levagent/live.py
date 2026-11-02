"""Lệnh thật trên Binance USDT-M. Không gửi nếu thiếu cụm khóa và cờ --send."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from levagent.config import ARM_PHRASE, HARD_MAX_LEVERAGE
from levagent.models import OrderPlan, Side

_BASE = "https://fapi.binance.com"


class LiveTradingDisabled(RuntimeError):
    pass


class LiveTradingError(RuntimeError):
    pass


@dataclass(frozen=True)
class Credentials:
    key: str
    secret: str

    def __repr__(self) -> str:
        return "Credentials(key='***', secret='***')"


def credentials_from_env() -> Credentials | None:
    key = os.environ.get("BINANCE_API_KEY", "").strip()
    secret = os.environ.get("BINANCE_API_SECRET", "").strip()
    if not key or not secret:
        return None
    return Credentials(key, secret)


def arm_enabled() -> bool:
    return os.environ.get("LEVAGENT_ARM_LIVE", "") == ARM_PHRASE


def block_reason(*, send: bool, creds: Credentials | None) -> str | None:
    if not send:
        return "Thiếu --send. Kế hoạch chỉ được in ra, không gửi sàn."
    if not arm_enabled():
        return (
            "Lệnh thật đang khóa. Đặt LEVAGENT_ARM_LIVE="
            f"{ARM_PHRASE} chỉ khi chấp nhận có thể mất hết vốn."
        )
    if creds is None or not creds.key.strip() or not creds.secret.strip():
        return "Thiếu BINANCE_API_KEY hoặc BINANCE_API_SECRET."
    return None


def sign(secret: str, query: str) -> str:
    return hmac.new(secret.encode(), query.encode(), hashlib.sha256).hexdigest()


class UrllibHttp:
    def send(self, method: str, path: str, query: str, api_key: str) -> dict:
        request = Request(
            _BASE + path + "?" + query,
            method=method,
            headers={"X-MBX-APIKEY": api_key, "User-Agent": "levagent/0.1"},
        )
        try:
            with urlopen(request, timeout=10) as response:
                body = response.read().decode()
        except HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")[:300]
            raise LiveTradingError(f"Sàn từ chối lệnh: {raw}") from exc
        except URLError as exc:
            raise LiveTradingError("Không kết nối được sàn.") from exc
        try:
            payload = json.loads(body)
        except json.JSONDecodeError as exc:
            raise LiveTradingError("Sàn trả về dữ liệu không đọc được.") from exc
        if not isinstance(payload, dict):
            raise LiveTradingError("Sàn trả về dữ liệu không đúng dạng.")
        return payload


def execute(
    plan: OrderPlan,
    creds: Credentials | None,
    http: UrllibHttp,
    *,
    send: bool,
    now_ms: int | None = None,
) -> list[dict]:
    reason = block_reason(send=send, creds=creds)
    if reason or creds is None:
        raise LiveTradingDisabled(reason or "Thiếu khóa API.")
    _validate(plan)
    stamp = int(time.time() * 1000) if now_ms is None else now_ms
    entry_side = "BUY" if plan.side is Side.LONG else "SELL"
    exit_side = "SELL" if plan.side is Side.LONG else "BUY"
    qty = _format_number(plan.qty)
    if float(qty) <= 0:
        raise LiveTradingDisabled("Khối lượng sau khi làm tròn bằng 0, không gửi.")

    responses = [
        _margin(http, creds, plan, stamp),
        _signed(
            http,
            creds,
            "POST",
            "/fapi/v1/leverage",
            [("symbol", plan.symbol), ("leverage", str(plan.leverage)), ("timestamp", str(stamp))],
        ),
    ]
    responses.append(
        _signed(
            http,
            creds,
            "POST",
            "/fapi/v1/order",
            [
                ("symbol", plan.symbol),
                ("side", entry_side),
                ("type", "MARKET"),
                ("quantity", qty),
                ("timestamp", str(stamp)),
            ],
        )
    )
    try:
        responses.append(_protection(http, creds, plan, exit_side, "STOP_MARKET", plan.stop, stamp))
        responses.append(
            _protection(http, creds, plan, exit_side, "TAKE_PROFIT_MARKET", plan.take_profit, stamp)
        )
    except LiveTradingError as exc:
        _abandon(http, creds, plan, exit_side, qty, stamp, exc)
    return responses


def _margin(http: UrllibHttp, creds: Credentials, plan: OrderPlan, stamp: int) -> dict:
    try:
        return _signed(
            http,
            creds,
            "POST",
            "/fapi/v1/marginType",
            [("symbol", plan.symbol), ("marginType", "ISOLATED"), ("timestamp", str(stamp))],
        )
    except LiveTradingError as exc:
        text = str(exc)
        if "-4046" in text or "No need to change margin type" in text:
            return {"marginType": "unchanged"}
        raise


def _protection(
    http: UrllibHttp,
    creds: Credentials,
    plan: OrderPlan,
    exit_side: str,
    order_type: str,
    stop_price: float,
    stamp: int,
) -> dict:
    return _signed(
        http,
        creds,
        "POST",
        "/fapi/v1/order",
        [
            ("symbol", plan.symbol),
            ("side", exit_side),
            ("type", order_type),
            ("stopPrice", _format_number(stop_price)),
            ("closePosition", "true"),
            ("workingType", "MARK_PRICE"),
            ("timestamp", str(stamp)),
        ],
    )


def _abandon(
    http: UrllibHttp,
    creds: Credentials,
    plan: OrderPlan,
    exit_side: str,
    qty: str,
    stamp: int,
    cause: LiveTradingError,
) -> None:
    try:
        _signed(
            http,
            creds,
            "DELETE",
            "/fapi/v1/allOpenOrders",
            [("symbol", plan.symbol), ("timestamp", str(stamp))],
        )
    except LiveTradingError:
        pass
    try:
        _signed(
            http,
            creds,
            "POST",
            "/fapi/v1/order",
            [
                ("symbol", plan.symbol),
                ("side", exit_side),
                ("type", "MARKET"),
                ("quantity", qty),
                ("reduceOnly", "true"),
                ("timestamp", str(stamp)),
            ],
        )
    except LiveTradingError as close_error:
        raise LiveTradingError(
            "Đã khớp lệnh nhưng không đặt được dừng lỗ, và không đóng được vị thế. "
            "Hãy kiểm tra sàn ngay. " + str(close_error)
        ) from cause
    raise LiveTradingError(
        "Đã khớp lệnh nhưng không đặt được dừng lỗ hoặc chốt lời. Đã gửi lệnh đóng vị thế."
    ) from cause


def _signed(
    http: UrllibHttp,
    creds: Credentials,
    method: str,
    path: str,
    params: list[tuple[str, str]],
) -> dict:
    query = urlencode(params)
    signed = query + "&signature=" + sign(creds.secret, query)
    return http.send(method, path, signed, creds.key)


def _validate(plan: OrderPlan) -> None:
    if not 1 <= plan.leverage <= HARD_MAX_LEVERAGE:
        raise LiveTradingDisabled("Đòn bẩy ngoài trần, không gửi lệnh thật.")
    if plan.side is Side.LONG and not (plan.stop < plan.entry < plan.take_profit):
        raise LiveTradingDisabled("Lệnh mua thiếu dừng lỗ hoặc chốt lời.")
    if plan.side is Side.SHORT and not (plan.take_profit < plan.entry < plan.stop):
        raise LiveTradingDisabled("Lệnh bán thiếu dừng lỗ hoặc chốt lời.")


def _format_number(value: float) -> str:
    return f"{value:.8f}".rstrip("0").rstrip(".")
