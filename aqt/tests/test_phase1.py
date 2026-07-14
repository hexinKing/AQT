import unittest
from datetime import datetime
from unittest.mock import patch

from aqt.models import User
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

    @patch("aqt.services.news_service._fetch_symbol_news")
    def test_get_news_dedupes_and_sorts(self, mocked_fetch):
        mocked_fetch.side_effect = [
            ([
                {
                    "title": "旧新闻",
                    "source": "源A",
                    "url": "https://a",
                    "published_at": "2026-07-14 09:00:00",
                    "symbols": ["600519"],
                    "summary": "",
                },
                {
                    "title": "重复新闻",
                    "source": "源A",
                    "url": "https://dup",
                    "published_at": "2026-07-14 10:00:00",
                    "symbols": ["600519"],
                    "summary": "",
                },
            ], False),
            ([
                {
                    "title": "重复新闻",
                    "source": "源B",
                    "url": "https://dup",
                    "published_at": "2026-07-14 10:00:00",
                    "symbols": ["000001"],
                    "summary": "",
                },
                {
                    "title": "新新闻",
                    "source": "源B",
                    "url": "https://b",
                    "published_at": "2026-07-14 11:00:00",
                    "symbols": ["000001"],
                    "summary": "",
                },
            ], False),
        ]

        items, total, message = news_service.get_news(["600519", "000001"], limit=10, page=1)

        self.assertEqual(total, 3)
        self.assertIsNone(message)
        self.assertEqual([item["title"] for item in items], ["新新闻", "重复新闻", "旧新闻"])


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


if __name__ == "__main__":
    unittest.main()
