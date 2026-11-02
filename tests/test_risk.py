import unittest

from levagent.config import HARD_MAX_LEVERAGE, Settings
from levagent.models import Side, Snapshot
from levagent.risk import geometry_ok, liquidation_price, size_order


def snap(price: float = 100.0, atr: float = 0.2) -> Snapshot:
    return Snapshot(
        price=price,
        ema_fast=price + 1,
        ema_slow=price - 1,
        rsi=60,
        macd_hist=0.2,
        macd_rising=True,
        atr=atr,
        atr_pct=atr / price,
        score=0.8,
    )


class RiskTests(unittest.TestCase):
    def test_liquidation_formula(self) -> None:
        self.assertAlmostEqual(liquidation_price(100, 10, Side.LONG, 0.005), 90.5)
        self.assertAlmostEqual(liquidation_price(100, 10, Side.SHORT, 0.005), 109.5)

    def test_sizes_risk_not_maximum_leverage(self) -> None:
        plan, error = size_order(
            symbol="BTCUSDT",
            side=Side.LONG,
            snapshot=snap(atr=0.2),
            equity=10_000,
            settings=Settings(),
        )
        self.assertIsNone(error)
        assert plan is not None
        self.assertLessEqual(plan.leverage, 3)
        self.assertAlmostEqual(plan.risk_cash, 50.0, delta=0.05)
        self.assertTrue(geometry_ok(plan))
        self.assertLess(plan.liquidation, plan.stop)
        self.assertLess(plan.stop, plan.entry)
        self.assertLess(plan.entry, plan.take_profit)

    def test_caps_leverage_when_the_stop_is_tight(self) -> None:
        plan, error = size_order(
            symbol="BTCUSDT",
            side=Side.SHORT,
            snapshot=snap(atr=0.05),
            equity=10_000,
            settings=Settings(max_leverage=10),
        )
        self.assertIsNone(error)
        assert plan is not None
        self.assertLessEqual(plan.leverage, HARD_MAX_LEVERAGE)
        self.assertLessEqual(plan.risk_cash, 50.0 + 1e-6)
        self.assertGreater(plan.stop, plan.entry)
        self.assertLess(plan.stop, plan.liquidation)

    def test_rejects_a_stop_wider_than_liquidation(self) -> None:
        _plan, error = size_order(
            symbol="BTCUSDT",
            side=Side.LONG,
            snapshot=snap(atr=80),
            equity=10_000,
            settings=Settings(),
        )
        self.assertIsNotNone(error)

    def test_rejects_dust_and_illegal_settings(self) -> None:
        _plan, error = size_order(
            symbol="BTCUSDT",
            side=Side.LONG,
            snapshot=snap(atr=10),
            equity=100,
            settings=Settings(equity=100),
        )
        self.assertIsNotNone(error)
        with self.assertRaises(ValueError):
            Settings(max_leverage=25)
        with self.assertRaises(ValueError):
            Settings(risk_pct=0.5)


if __name__ == "__main__":
    unittest.main()
