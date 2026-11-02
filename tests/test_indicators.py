import unittest

from levagent.indicators import atr_series, ema_series, macd_series, rsi_series
from tests.support import from_closes


class IndicatorTests(unittest.TestCase):
    def test_ema_seed_is_sma_then_smooths(self) -> None:
        series = ema_series([1, 2, 3, 4, 5], 3)
        self.assertEqual(series[:2], [None, None])
        self.assertAlmostEqual(series[2], 2.0)
        self.assertAlmostEqual(series[3], 3.0)
        self.assertAlmostEqual(series[4], 4.0)

    def test_rsi_is_100_when_price_only_rises(self) -> None:
        series = rsi_series([float(i) for i in range(1, 20)], 14)
        self.assertIsNone(series[13])
        self.assertAlmostEqual(series[14], 100.0)
        self.assertGreater(series[-1], 50)

    def test_macd_histogram_turns_positive_in_an_uptrend(self) -> None:
        _macd, _signal, hist = macd_series([100 * (1.01**i) for i in range(80)])
        values = [item for item in hist if item is not None]
        self.assertTrue(values)
        self.assertGreater(values[-1], 0)

    def test_atr_matches_a_constant_range(self) -> None:
        candles = from_closes([100.0] * 30, spread=1.0)
        series = atr_series(candles, 14)
        self.assertIsNotNone(series[-1])
        self.assertAlmostEqual(series[-1], 2.0, places=6)


if __name__ == "__main__":
    unittest.main()
