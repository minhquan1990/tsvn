import hashlib
import hmac
import os
import unittest
from unittest import mock
from urllib.parse import parse_qsl, urlencode

from levagent.config import ARM_PHRASE, Settings
from levagent.live import Credentials, LiveTradingDisabled, LiveTradingError, execute, sign
from levagent.models import Side, Snapshot
from levagent.risk import size_order


def plan():
    snapshot = Snapshot(100, 101, 99, 60, 0.2, True, 0.2, 0.002, 0.8)
    order, error = size_order(
        symbol="BTCUSDT",
        side=Side.LONG,
        snapshot=snapshot,
        equity=10_000,
        settings=Settings(),
    )
    if error or order is None:
        raise AssertionError(error)
    return order


class FakeHttp:
    def __init__(self, fail_types: set[str] | None = None) -> None:
        self.fail_types = fail_types or set()
        self.calls: list[dict] = []

    def send(self, method: str, path: str, query: str, api_key: str) -> dict:
        if "super-secret" in query:
            raise AssertionError("khóa bí mật lọt vào đường dẫn")
        params = dict(parse_qsl(query))
        self.calls.append({"method": method, "path": path, "params": params, "key": api_key})
        if params.get("type") in self.fail_types:
            raise LiveTradingError("fail")
        return {"ok": True}


class LiveGateTests(unittest.TestCase):
    def test_signature_matches_hmac_and_credentials_stay_hidden(self) -> None:
        secret = "super-secret"
        query = "symbol=BTCUSDT&timestamp=1"
        expected = hmac.new(secret.encode(), query.encode(), hashlib.sha256).hexdigest()
        self.assertEqual(sign(secret, query), expected)
        self.assertNotIn(secret, repr(Credentials("key-id", secret)))

    def test_preview_and_locked_live_never_call_the_exchange(self) -> None:
        http = FakeHttp()
        creds = Credentials("key-id", "super-secret")
        with self.assertRaises(LiveTradingDisabled):
            execute(plan(), creds, http, send=False)
        self.assertEqual(http.calls, [])
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("LEVAGENT_ARM_LIVE", None)
            with self.assertRaises(LiveTradingDisabled):
                execute(plan(), creds, http, send=True)
        self.assertEqual(http.calls, [])

    def test_armed_order_places_protection_and_flattens_if_the_stop_fails(self) -> None:
        creds = Credentials("key-id", "super-secret")
        env = {"LEVAGENT_ARM_LIVE": ARM_PHRASE}
        with mock.patch.dict(os.environ, env, clear=False):
            http = FakeHttp()
            execute(plan(), creds, http, send=True, now_ms=1)
            self.assertEqual(
                [call["path"] for call in http.calls],
                [
                    "/fapi/v1/marginType",
                    "/fapi/v1/leverage",
                    "/fapi/v1/order",
                    "/fapi/v1/order",
                    "/fapi/v1/order",
                ],
            )
            signed = http.calls[2]
            raw = urlencode([(key, value) for key, value in signed["params"].items() if key != "signature"])
            self.assertEqual(signed["params"]["signature"], sign(creds.secret, raw))
            self.assertEqual(signed["params"]["type"], "MARKET")
            self.assertEqual(signed["key"], "key-id")
            self.assertLessEqual(int(http.calls[1]["params"]["leverage"]), 10)

            failing = FakeHttp({"STOP_MARKET"})
            with self.assertRaises(LiveTradingError) as caught:
                execute(plan(), creds, failing, send=True, now_ms=1)
            self.assertIn("đóng vị thế", str(caught.exception))
            self.assertEqual(failing.calls[-2]["method"], "DELETE")
            self.assertEqual(failing.calls[-1]["params"]["reduceOnly"], "true")


if __name__ == "__main__":
    unittest.main()
