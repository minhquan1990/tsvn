import unittest

from levagent.broker import PaperBroker
from levagent.config import Settings
from levagent.decision import decide
from levagent.models import Action, NewsItem
from levagent.synthetic import choppy, trending


class DecisionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.settings = Settings()
        self.account = PaperBroker(self.settings).view()

    def test_uptrend_opens_long_and_bearish_news_blocks_it(self) -> None:
        candles = trending(direction=1)
        found = False
        for i in range(self.settings.required_bars(), len(candles)):
            window = candles[: i + 1]
            plain = decide(window, [], self.account, self.settings)
            if plain.action is not Action.OPEN_LONG:
                continue
            found = True
            assert plain.order is not None
            self.assertLessEqual(plain.order.leverage, 3)
            self.assertLess(plain.order.liquidation, plain.order.stop)
            blocked = decide(
                window,
                [NewsItem(window[-1].time, "Bitcoin bị hack, nhà đầu tư phá sản", "test")],
                self.account,
                self.settings,
            )
            self.assertEqual(blocked.action, Action.HOLD)
            self.assertTrue(any("tiêu cực" in reason for reason in blocked.reasons))
            break
        self.assertTrue(found, plain.reasons)

    def test_downtrend_opens_short_and_bullish_news_blocks_it(self) -> None:
        candles = trending(direction=-1)
        found = False
        for i in range(self.settings.required_bars(), len(candles)):
            window = candles[: i + 1]
            plain = decide(window, [], self.account, self.settings)
            if plain.action is not Action.OPEN_SHORT:
                continue
            found = True
            blocked = decide(
                window,
                [NewsItem(window[-1].time, "SEC phê duyệt ETF Bitcoin, giá tăng mạnh", "test")],
                self.account,
                self.settings,
            )
            self.assertEqual(blocked.action, Action.HOLD)
            self.assertTrue(any("tích cực" in reason for reason in blocked.reasons))
            break
        self.assertTrue(found, plain.reasons)

    def test_news_cannot_create_a_trade_without_enough_bars(self) -> None:
        candles = trending()[:10]
        decision = decide(
            candles,
            [NewsItem(candles[-1].time, "SEC phê duyệt ETF Bitcoin", "test")],
            self.account,
            self.settings,
        )
        self.assertEqual(decision.action, Action.HOLD)

    def test_daily_loss_blocks_a_fresh_entry(self) -> None:
        broker = PaperBroker(self.settings)
        broker.day = "2023-11-14"
        broker.day_start_equity = broker.equity
        broker.day_realized = -broker.equity * 0.03
        candles = trending()
        decision = decide(candles, [], broker.view(), self.settings)
        self.assertEqual(decision.action, Action.HOLD)
        self.assertTrue(any("trần lỗ" in reason for reason in decision.reasons))

    def test_choppy_market_does_not_use_leverage_above_the_cap(self) -> None:
        from levagent.backtest import run_backtest

        result = run_backtest(choppy(), [], self.settings)
        self.assertGreater(result.end_equity, 0)
        self.assertLessEqual(result.max_leverage, self.settings.max_leverage)


if __name__ == "__main__":
    unittest.main()
