import unittest

from levagent.models import NewsItem
from levagent.news import parse_rss, score_news, score_title


class NewsTests(unittest.TestCase):
    def test_hack_and_bankruptcy_are_bearish(self) -> None:
        self.assertLess(score_title("Bitcoin bị hack, nhà đầu tư phá sản"), -0.55)

    def test_etf_approval_is_bullish_and_rejection_is_bearish(self) -> None:
        self.assertGreater(score_title("SEC phê duyệt ETF Bitcoin, giá tăng mạnh"), 0.55)
        self.assertLess(score_title("SEC rejected the bitcoin ETF"), 0)

    def test_ban_does_not_match_inside_bank(self) -> None:
        self.assertEqual(score_title("The bank raised rates"), 0.0)
        self.assertLess(score_title("A ban on crypto trading"), 0)

    def test_future_headlines_are_ignored(self) -> None:
        as_of = 1_700_000_000_000
        items = [NewsItem(as_of + 60_000, "Bitcoin bị hack", "test")]
        view = score_news(items, as_of=as_of, interval="1h", symbol="BTCUSDT")
        self.assertEqual(view.score, 0.0)

    def test_old_headlines_fall_outside_the_window(self) -> None:
        as_of = 1_700_000_000_000
        items = [NewsItem(as_of - 8 * 86_400_000, "Bitcoin bị hack", "test")]
        view = score_news(items, as_of=as_of, interval="1h", symbol="BTCUSDT")
        self.assertEqual(view.score, 0.0)

    def test_rss_parses_rss_and_atom_and_skips_bad_xml(self) -> None:
        rss = """
        <rss><channel><item>
          <title>Bitcoin rally</title>
          <pubDate>Tue, 14 Nov 2023 22:13:20 GMT</pubDate>
        </item></channel></rss>
        """
        atom = """
        <feed xmlns="http://www.w3.org/2005/Atom"><entry>
          <title>ETF approval</title>
          <updated>2023-11-14T22:13:20Z</updated>
        </entry></feed>
        """
        self.assertEqual(parse_rss(rss, "rss")[0].title, "Bitcoin rally")
        self.assertEqual(parse_rss(atom, "atom")[0].title, "ETF approval")
        self.assertEqual(parse_rss("<not xml", "bad"), [])


if __name__ == "__main__":
    unittest.main()
