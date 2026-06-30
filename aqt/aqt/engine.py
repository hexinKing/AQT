import json
from datetime import datetime, date

from sqlalchemy.orm import Session

from .config import settings as app_settings
from .data_fetcher import fetch_daily, fetch_realtime
from .models import Signal, User, Watchlist
from .notifier import send_email
from .strategies.ma_cross import MACrossStrategy
from .strategies.grid import GridStrategy
from .strategies.trailing_stop import TrailingStopStrategy

STRATEGIES = {
    "ma_cross": MACrossStrategy(),
    "grid": GridStrategy(),
    "trailing_stop": TrailingStopStrategy(),
}


def _signal_exists_today(db: Session, user_id: int, symbol: str, strategy: str, direction: str) -> bool:
    """Check if the same signal was already generated today."""
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    count = (
        db.query(Signal)
        .filter(
            Signal.user_id == user_id,
            Signal.symbol == symbol,
            Signal.strategy == strategy,
            Signal.direction == direction,
            Signal.created_at >= today_start,
        )
        .count()
    )
    return count > 0


def run_strategies(user_id: int, db: Session) -> list[dict]:
    """
    Run all enabled strategies for a user's watchlist.
    Returns list of new signal dicts.
    """
    user = db.query(User).get(user_id)
    if not user:
        return []

    watchlist = db.query(Watchlist).filter(Watchlist.user_id == user_id).all()
    if not watchlist:
        return []

    new_signals = []

    for item in watchlist:
        df = fetch_daily(item.symbol, days=60)
        if df.empty or len(df) < 20:
            continue

        # Check if market is open today (latest bar date is today)
        try:
            latest_date = df["date"].iloc[-1]
            if hasattr(latest_date, "date"):
                latest_date = latest_date.date()
            if latest_date != date.today():
                # stale data, skip evaluation
                continue
        except Exception:
            continue

        strategies_config = item.strategies

        for strategy_name, strat_obj in STRATEGIES.items():
            config = strategies_config.get(strategy_name, {})
            if not config.get("enabled"):
                continue

            params = {k: v for k, v in config.items() if k != "enabled"}

            signal = strat_obj.evaluate(df, params)
            if signal is None:
                continue

            signal.symbol = item.symbol

            # Dedup: same signal today
            if _signal_exists_today(db, user_id, item.symbol, strategy_name, signal.direction):
                continue

            # For trailing_stop: persist updated highest_since_entry
            if strategy_name == "trailing_stop" and "highest_since_entry" in params:
                strategies_config[strategy_name]["highest_since_entry"] = params["highest_since_entry"]
                item.strategies = strategies_config

            db_signal = Signal(
                user_id=user_id,
                symbol=item.symbol,
                strategy=strategy_name,
                direction=signal.direction,
                price=signal.price,
                reason=signal.reason,
            )
            db.add(db_signal)
            db.flush()

            new_signals.append(
                {
                    "id": db_signal.id,
                    "symbol": db_signal.symbol,
                    "strategy": db_signal.strategy,
                    "direction": db_signal.direction,
                    "price": db_signal.price,
                    "reason": db_signal.reason,
                    "created_at": db_signal.created_at.isoformat(),
                }
            )

            # Send email notification
            if user.email:
                stock_name = item.name or item.symbol
                subject = f"[AQT] {stock_name} {signal.direction} 信号 — {signal.reason}"
                body = f"""\
【A股量化监控 - 交易信号】

股票: {stock_name} ({item.symbol})
方向: {signal.direction}
策略: {strategy_name}
价格: {signal.price}
原因: {signal.reason}
时间: {db_signal.created_at.strftime('%Y-%m-%d %H:%M:%S')}

---
此为策略信号提示，请在华安证券 App 手动操作。
"""
                send_email(app_settings, user.email, subject, body)

    db.commit()
    return new_signals
