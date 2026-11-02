import json
import unittest

from levagent.market import fetch_klines, parse_klines, validate_interval, validate_symbol


class MarketTests(unittest.TestCase):
    def test_parses_futures_klines(self) -> None:
        candles = parse_klines([[1_700_000_000_000, "100", "105", "99", "102", "12"]])
        self.assertEqual(len(candles), 1)
        self.assertAlmostEqual(candles[0].close, 102.0)
        self.assertAlmostEqual(candles[0].volume, 12.0)

    def test_falls_back_when_the_first_candle_source_fails(self) -> None:
        def get(url: str, _timeout: float) -> str:
            if "fapi.binance.com" in url:
                raise RuntimeError("HTTP 451")
            return json.dumps([[1_700_000_000_000, "100", "105", "99", "102", "12"]])

        candles = fetch_klines("BTCUSDT", "1h", limit=50, get=get)
        self.assertAlmostEqual(candles[-1].close, 102.0)

    def test_rejects_bad_symbols_and_intervals(self) -> None:
        validate_symbol("BTCUSDT")
        with self.assertRaises(ValueError):
            validate_symbol("btc/usdt")
        with self.assertRaises(ValueError):
            validate_interval("2h")


if __name__ == "__main__":
    unittest.main()
