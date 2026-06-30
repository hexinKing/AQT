import time

import pandas as pd
from datetime import datetime, timedelta

# Simple in-memory cache for realtime quotes (akshare fetches all stocks each time)
_cache_ts: float = 0
_cache_data: dict[str, dict] = {}
_cache_ttl: float = 30  # seconds


def _get_realtime_snapshot() -> dict[str, dict]:
    """Get all realtime quotes, cached for _cache_ttl seconds."""
    global _cache_ts, _cache_data
    now = time.time()
    if now - _cache_ts < _cache_ttl and _cache_data:
        return _cache_data

    import akshare as ak

    try:
        df = ak.stock_zh_a_spot_em()
    except Exception:
        return _cache_data  # return stale cache on error

    if df is None or df.empty:
        return _cache_data

    result = {}
    for _, r in df.iterrows():
        code = r.get("代码", "")
        if not code:
            continue
        change_pct = r.get("涨跌幅", 0)
        last_price = r.get("最新价", 0)
        result[code] = {
            "symbol": code,
            "name": r.get("名称", ""),
            "last_price": float(last_price) if pd.notna(last_price) else 0,
            "change_pct": float(change_pct) if pd.notna(change_pct) else 0,
        }

    _cache_data = result
    _cache_ts = now
    return result


def fetch_daily(symbol: str, days: int = 60) -> pd.DataFrame:
    """
    Fetch daily OHLCV for an A-share stock.
    Returns DataFrame with columns: date, open, high, low, close, volume.
    """
    import akshare as ak

    end_date = datetime.now().strftime("%Y%m%d")
    start_date = (datetime.now() - timedelta(days=days + 10)).strftime("%Y%m%d")

    try:
        df = ak.stock_zh_a_hist(
            symbol=symbol,
            period="daily",
            start_date=start_date,
            end_date=end_date,
            adjust="qfq",
        )
    except Exception:
        return pd.DataFrame()

    if df is None or df.empty:
        return pd.DataFrame()

    df = df.rename(
        columns={
            "日期": "date",
            "开盘": "open",
            "最高": "high",
            "最低": "low",
            "收盘": "close",
            "成交量": "volume",
        }
    )
    cols = ["date", "open", "high", "low", "close", "volume"]
    df = df[[c for c in cols if c in df.columns]]
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)
    return df


def fetch_realtime(symbol: str) -> dict | None:
    """Fetch realtime quote for a single A-share stock. Returns dict or None."""
    return _get_realtime_snapshot().get(symbol)


def fetch_realtime_batch(symbols: list[str]) -> dict[str, dict]:
    """Fetch realtime quotes for multiple symbols. Returns {symbol: quote_dict}."""
    snapshot = _get_realtime_snapshot()
    return {sym: snapshot[sym] for sym in symbols if sym in snapshot}
