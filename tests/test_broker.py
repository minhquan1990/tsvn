import unittest

from levagent.broker import PaperBroker
from levagent.config import Settings
from levagent.models import OrderPlan, Side
from levagent.risk import liquidation_price
from tests.support import TIME, candle, long_plan, short_plan


class BrokerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.broker = PaperBroker(Settings(max_leverage=5), equity=10_000)

    def test_stop_fills_at_the_stop_and_pnl_includes_fees(self) -> None:
        self.assertIsNone(self.broker.open(long_plan(), TIME))
        trade = self.broker.on_candle(candle(1, 100, 101, 89, 99))
        assert trade is not None
        self.assertEqual(trade.reason, "Dừng lỗ")
        self.assertAlmostEqual(trade.exit, 90.0)
        self.assertAlmostEqual(trade.pnl, -10.076)
        self.assertAlmostEqual(self.broker.equity, 9_989.924)
        self.assertIsNone(self.broker.position)
        self.assertAlmostEqual(sum(item.pnl for item in self.broker.trades), self.broker.equity - 10_000)

    def test_gap_through_the_stop_fills_worse(self) -> None:
        self.broker.open(long_plan(), TIME)
        trade = self.broker.on_candle(candle(1, 88, 89, 87, 88.5))
        assert trade is not None
        self.assertEqual(trade.reason, "Dừng lỗ")
        self.assertAlmostEqual(trade.exit, 88.0)

    def test_gap_through_liquidation_loses_only_isolated_margin(self) -> None:
        broker = PaperBroker(Settings(max_leverage=5), equity=500)
        broker.open(long_plan(), TIME)
        trade = broker.on_candle(candle(1, 70, 71, 69, 70.5))
        assert trade is not None
        self.assertEqual(trade.reason, "Thanh lý")
        self.assertAlmostEqual(trade.pnl, -20.04)
        self.assertAlmostEqual(broker.equity, 479.96)
        self.assertTrue(broker.entries_halted)

    def test_take_profit_and_short_stop(self) -> None:
        self.broker.open(long_plan(), TIME)
        trade = self.broker.on_candle(candle(1, 100, 121, 99, 110))
        assert trade is not None
        self.assertEqual(trade.reason, "Chốt lời")
        self.assertAlmostEqual(trade.exit, 120.0)

        broker = PaperBroker(Settings(max_leverage=5), equity=10_000)
        broker.open(short_plan(), TIME)
        stopped = broker.on_candle(candle(1, 100, 111, 99, 105))
        assert stopped is not None
        self.assertEqual(stopped.reason, "Dừng lỗ")
        self.assertAlmostEqual(stopped.exit, 110.0)

    def test_rejected_order_does_not_change_equity(self) -> None:
        before = self.broker.equity
        bad = OrderPlan(
            symbol="BTCUSDT",
            side=Side.LONG,
            qty=1,
            entry=100,
            stop=90,
            take_profit=120,
            leverage=11,
            margin=100 / 11,
            liquidation=liquidation_price(100, 11, Side.LONG, 0.005),
            notional=100,
            risk_cash=10,
        )
        self.assertIsNotNone(self.broker.open(bad, TIME))
        self.assertEqual(self.broker.equity, before)
        self.assertIsNone(self.broker.position)

    def test_state_roundtrip(self) -> None:
        self.broker.open(long_plan(), TIME)
        self.broker.on_candle(candle(1, 100, 101, 99.5, 100.2))
        restored = PaperBroker(Settings(max_leverage=5), equity=1)
        restored.load_dict(self.broker.to_dict())
        self.assertAlmostEqual(restored.equity, self.broker.equity)
        assert restored.position is not None and self.broker.position is not None
        self.assertEqual(restored.position.side, self.broker.position.side)
        self.assertAlmostEqual(restored.position.stop, self.broker.position.stop)


if __name__ == "__main__":
    unittest.main()
