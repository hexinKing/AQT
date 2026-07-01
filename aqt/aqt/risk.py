"""Risk control — trading-hours checks, ST/limit filters, signal validation."""

from datetime import datetime, time


_ST_PREFIXES = ("ST", "*ST", "NST")


def is_trading_time() -> bool:
    """Return True if now is within A-share trading hours on a weekday."""
    now = datetime.now()
    if now.weekday() >= 5:
        return False
    t = now.time()
    # 9:25–11:35 or 13:00–14:55 Beijing time
    morning_start = time(9, 25)
    morning_end = time(11, 35)
    afternoon_start = time(13, 0)
    afternoon_end = time(14, 55)
    return (morning_start <= t <= morning_end) or (afternoon_start <= t <= afternoon_end)


def is_suspect_stock(name: str) -> bool:
    """Check whether a stock name indicates ST / delisting risk."""
    if not name:
        return False
    return any(name.startswith(p) for p in _ST_PREFIXES)


def is_limit_hit(last_price: float, prev_close: float | None, direction: str) -> bool:
    """Return True if the stock is at +/-10% limit."""
    if prev_close is None or prev_close <= 0:
        return False
    pct = (last_price - prev_close) / prev_close
    if direction == "BUY" and pct >= 0.099:
        return True
    if direction == "SELL" and pct <= -0.099:
        return True
    return False


def validate_signal(
    symbol: str,
    name: str,
    direction: str,
    last_price: float,
    prev_close: float | None,
    signals_today: int,
    max_signals_per_day: int = 3,
) -> str | None:
    """
    Run risk checks for a candidate signal.
    Returns None if the signal is allowed, or a rejection reason string.
    """
    if is_suspect_stock(name):
        return f"{symbol} 疑似 ST/退市股票，已过滤"

    if not is_trading_time():
        return f"{symbol} 当前非交易时段，已过滤"

    if is_limit_hit(last_price, prev_close, direction):
        return f"{symbol} 已触及涨跌停，{direction} 信号已过滤"

    if signals_today >= max_signals_per_day:
        return f"{symbol} 今日信号已达上限 ({max_signals_per_day})，已过滤"

    return None
