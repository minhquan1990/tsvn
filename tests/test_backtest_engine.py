import unittest

from levagent.backtest import run_backtest
from levagent.broker import PaperBroker
from levagent.config import Settings
from levagent.decision import decide
from levagent.engine import run_once
from levagent.models import Action
from levagent.synthetic import trending


class BacktestEngineTests(unittest.TestCase):
    def test_uptrend_backtest_stays_inside_risk_limits(self) -> None:
        settings = Settings()
        result = run_backtest(trending(), [], settings)
        self.assertGreater(result.end_equity, 0)
        self.assertGreaterEqual(len(result.trades), 1)
        self.assertLessEqual(result.max_leverage, settings.max_leverage)
        self.assertGreaterEqual(result.max_drawdown, 0)
        self.assertLessEqual(result.max_drawdown, 1)
        for trade in result.trades:
            self.assertGreater(trade.qty, 0)

    def test_run_once_is_idempotent_on_the_same_candles(self) -> None:
        settings = Settings()
        candles = trending()
        broker = PaperBroker(settings)
        first = run_once(candles, [], broker, settings)
        equity = broker.equity
        side = None if broker.position is None else broker.position.side
        second = run_once(candles, [], broker, settings)
        self.assertAlmostEqual(broker.equity, equity)
        if side is None:
            self.assertIsNone(broker.position)
            self.assertEqual(second.action, first.action)
        else:
            assert broker.position is not None
            self.assertEqual(broker.position.side, side)
            self.assertEqual(second.action, Action.HOLD)

    def test_saved_state_reloads_the_open_position(self) -> None:
        settings = Settings()
        candles = trending()
        window = None
        for i in range(settings.required_bars(), len(candles)):
            view = PaperBroker(settings).view()
            if decide(candles[: i + 1], [], view, settings).action is Action.OPEN_LONG:
                window = candles[: i + 1]
                break
        self.assertIsNotNone(window)
        assert window is not None
        broker = PaperBroker(settings)
        decision = run_once(window, [], broker, settings)
        self.assertEqual(decision.action, Action.OPEN_LONG)
        assert broker.position is not None
        restored = PaperBroker(settings, equity=1)
        restored.load_dict(broker.to_dict())
        run_once(window, [], restored, settings)
        assert restored.position is not None
        self.assertEqual(restored.position.opened_at, broker.position.opened_at)


if __name__ == "__main__":
    unittest.main()
