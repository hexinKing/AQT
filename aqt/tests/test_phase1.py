import unittest
from datetime import datetime
from unittest.mock import patch

import pandas as pd

from aqt.models import User
from aqt import data_fetcher
from aqt.services import market_service, news_service, report_service


class DummySignal:
    def __init__(self, symbol="600519", direction="BUY", strategy="ma_cross", reason="MA5 上穿 MA20"):
        self.symbol = symbol
        self.direction = direction
        self.strategy = strategy
        self.reason = reason
        self.created_at = datetime(2026, 7, 14, 15, 10, 0)


class DummyQuery:
    def __init__(self, items):
        self.items = items

    def filter(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def all(self):
        return list(self.items)


class DummyDB:
    def __init__(self, signals):
        self.signals = signals
        self.added = []

    def query(self, model):
        return DummyQuery(self.signals)

    def add(self, item):
        self.added.append(item)


class NewsServiceTests(unittest.TestCase):
    def tearDown(self):
        news_service._news_cache.clear()

    def test_clear_news_cache_by_symbols(self):
        news_service._news_cache.update(
            {
                "600519": (1.0, [{"title": "A"}]),
                "000001": (1.0, [{"title": "B"}]),
            }
        )

        cleared = news_service.clear_news_cache(["600519"])

        self.assertEqual(cleared, 1)
        self.assertNotIn("600519", news_service._news_cache)
        self.assertIn("000001", news_service._news_cache)

    @patch("aqt.services.news_service._fetch_symbol_news")
    def test_get_news_dedupes_and_sorts(self, mocked_fetch):
        mocked_fetch.side_effect = [
            ([
                {
                    "title": "???",
                    "source": "?A",
                    "url": "https://a",
                    "published_at": "2026-07-14 09:00:00",
                    "symbols": ["600519"],
                    "summary": "",
                },
                {
                    "title": "????",
                    "source": "?A",
                    "url": "https://dup",
                    "published_at": "2026-07-14 10:00:00",
                    "symbols": ["600519"],
                    "summary": "",
                },
            ], "fresh", "2026-07-14 11:00:00"),
            ([
                {
                    "title": "????",
                    "source": "?B",
                    "url": "https://dup",
                    "published_at": "2026-07-14 10:00:00",
                    "symbols": ["000001"],
                    "summary": "",
                },
                {
                    "title": "???",
                    "source": "?B",
                    "url": "https://b",
                    "published_at": "2026-07-14 11:00:00",
                    "symbols": ["000001"],
                    "summary": "",
                },
            ], "fresh", "2026-07-14 11:05:00"),
        ]

        items, total, meta = news_service.get_news(["600519", "000001"], limit=10, page=1)

        self.assertEqual(total, 3)
        self.assertEqual(meta["status"], "ok")
        self.assertEqual(meta["latest_published_at"], "2026-07-14 11:00:00")
        self.assertEqual([item["title"] for item in items], ["???", "????", "???"])

    @patch("aqt.services.news_service._fetch_symbol_news")
    def test_get_news_marks_stale_cache_when_provider_fails(self, mocked_fetch):
        mocked_fetch.side_effect = [
            ([
                {
                    "title": "????",
                    "source": "?A",
                    "url": "https://a",
                    "published_at": "2026-07-14 15:00:00",
                    "symbols": ["600519"],
                    "summary": "",
                },
            ], "stale_cache", "2026-07-14 15:30:00"),
            ([], "failed", None),
        ]

        items, total, meta = news_service.get_news(["600519", "000001"], limit=10, page=1)

        self.assertEqual(total, 1)
        self.assertEqual(meta["status"], "stale_cache")
        self.assertEqual(meta["stale_symbols"], ["600519"])
        self.assertEqual(meta["failed_symbols"], 1)
        self.assertEqual(items[0]["title"], "????")



class ReportServiceTests(unittest.TestCase):
    @patch("aqt.services.report_service.build_dashboard")
    @patch("aqt.services.report_service._today_signals")
    def test_build_market_close_report(self, mocked_signals, mocked_dashboard):
        mocked_dashboard.return_value = {
            "data": {
                "positions": [
                    {
                        "symbol": "600519",
                        "shares": 100,
                        "avg_cost": 1500.0,
                        "last_price": 1512.3,
                        "market_value": 151230.0,
                        "unrealized_pnl": 1230.0,
                        "pnl_pct": 0.82,
                    }
                ],
                "total_pnl": 1230.0,
                "watchlist": [],
                "signals": [],
                "unread_count": 0,
            }
        }
        mocked_signals.return_value = [DummySignal(direction="SELL")]

        user = User(id=1, username="u", password_hash="x", email="a@b.com")
        report = report_service.build_market_close_report(user, DummyDB([]))

        self.assertEqual(report["total_pnl"], 1230.0)
        self.assertEqual(report["signals"][0]["direction"], "SELL")
        self.assertTrue(any("SELL" in item for item in report["highlights"]))

    @patch("aqt.services.report_service.send_email")
    @patch("aqt.services.report_service.build_market_close_report")
    def test_send_market_close_report_logs_result(self, mocked_build, mocked_send):
        mocked_build.return_value = {
            "date": "2026-07-14",
            "total_pnl": 1230.0,
            "positions": [],
            "signals": [],
            "highlights": ["总持仓当前为浮盈状态"],
        }
        mocked_send.return_value = True

        user = User(
            id=1,
            username="u",
            password_hash="x",
            email="a@b.com",
            smtp_host="smtp.qq.com",
            smtp_port=587,
            smtp_user="sender@test.com",
            smtp_password="secret",
        )
        db = DummyDB([])

        result = report_service.send_market_close_report(user, db)

        self.assertTrue(result.attempted)
        self.assertTrue(result.success)
        self.assertEqual(len(db.added), 1)
        self.assertEqual(db.added[0].recipient, "a@b.com")


class MarketServiceTests(unittest.TestCase):
    def tearDown(self):
        market_service._trade_dates_cache = None

    @patch("aqt.services.market_service._fetch_trade_dates")
    def test_is_trade_day_uses_trade_calendar(self, mocked_fetch):
        mocked_fetch.return_value = {datetime(2026, 7, 14).date()}
        self.assertTrue(market_service.is_trade_day(datetime(2026, 7, 14).date()))
        self.assertFalse(market_service.is_trade_day(datetime(2026, 7, 15).date()))


class DataFetcherTests(unittest.TestCase):
    def tearDown(self):
        data_fetcher._daily_cache.clear()
        data_fetcher._daily_disk.clear()
        data_fetcher._realtime_cache.clear()

    def test_fetch_daily_cached_uses_disk_without_network(self):
        data_fetcher._daily_disk["600519"] = [
            {"date": "2026-07-14", "open": 1, "high": 2, "low": 1, "close": 1.5, "volume": 10},
            {"date": "2026-07-15", "open": 1.5, "high": 2.5, "low": 1.4, "close": 2.0, "volume": 12},
        ]

        with patch("aqt.data_fetcher._tencent_fetch_daily", side_effect=AssertionError("should not hit network")):
            df = data_fetcher.fetch_daily_cached("600519", days=2)

        self.assertIsInstance(df, pd.DataFrame)
        self.assertEqual(len(df), 2)
        self.assertEqual(float(df.iloc[-1]["close"]), 2.0)

    @patch("aqt.data_fetcher._tencent_realtime_batch")
    @patch("aqt.data_fetcher.fetch_realtime", side_effect=AssertionError("should not hit per-symbol network fallback"))
    def test_fetch_realtime_batch_fast_uses_cached_daily_snapshot(self, mocked_fetch_realtime, mocked_batch):
        mocked_batch.return_value = {}
        data_fetcher._daily_disk["600519"] = [
            {"date": "2026-07-14", "open": 10, "high": 12, "low": 9, "close": 10.0, "volume": 100},
            {"date": "2026-07-15", "open": 10.2, "high": 12.4, "low": 10, "close": 11.0, "volume": 120},
        ]

        quotes = data_fetcher.fetch_realtime_batch_fast(["600519"])

        self.assertIn("600519", quotes)
        self.assertEqual(quotes["600519"]["last_price"], 11.0)
        self.assertEqual(quotes["600519"]["change_pct"], 10.0)
        mocked_fetch_realtime.assert_not_called()


if __name__ == "__main__":
    unittest.main()
