import logging
from datetime import date

from ..config import settings

logger = logging.getLogger(__name__)

_trade_dates_cache: set[date] | None = None


def _fetch_trade_dates() -> set[date]:
    import akshare as ak

    df = ak.tool_trade_date_hist_sina()
    if df is None or df.empty or "trade_date" not in df.columns:
        return set()
    return {
        value.date() if hasattr(value, "date") else value
        for value in df["trade_date"].tolist()
    }


def is_trade_day(target: date | None = None) -> bool:
    global _trade_dates_cache

    target = target or date.today()
    if _trade_dates_cache is None:
        try:
            _trade_dates_cache = _fetch_trade_dates()
        except Exception:
            logger.warning("Failed to load trade calendar, falling back to weekday check", exc_info=True)
            return target.weekday() < 5

    if not _trade_dates_cache:
        return target.weekday() < 5
    return target in _trade_dates_cache


def market_close_minutes() -> int:
    try:
        hour_str, minute_str = settings.market_close_report_time.split(":", 1)
        return int(hour_str) * 60 + int(minute_str)
    except Exception:
        logger.warning("Invalid MARKET_CLOSE_REPORT_TIME=%s, fallback to 15:05", settings.market_close_report_time)
        return 15 * 60 + 5
