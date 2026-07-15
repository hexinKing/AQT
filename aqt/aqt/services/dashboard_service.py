"""Dashboard data aggregation — keeps business logic out of the router."""
from sqlalchemy.orm import Session

from .. import schemas
from ..data_fetcher import fetch_daily_cached, fetch_realtime_batch
from ..models import Position, Signal, User, Watchlist


def build_dashboard(user: User, db: Session) -> dict:
    """Assemble the dashboard payload: positions + watchlist + signals."""
    positions = db.query(Position).filter(Position.user_id == user.id).all()
    pos_data = [schemas.PositionOut.model_validate(p).model_dump(mode="json") for p in positions]

    wl = db.query(Watchlist).filter(Watchlist.user_id == user.id).all()

    symbols = list({p.symbol for p in positions} | {w.symbol for w in wl})
    quotes = fetch_realtime_batch(symbols) if symbols else {}

    watchlist_data = []
    for w in wl:
        q = quotes.get(w.symbol, {})
        # Sparkline: last 30 daily closes
        df = fetch_daily_cached(w.symbol, days=30)
        sparkline = [round(float(r["close"]), 2) for _, r in df.tail(30).iterrows()] if not df.empty else []
        watchlist_data.append({
            "id": w.id,
            "symbol": w.symbol,
            "name": w.name or q.get("name", ""),
            "last_price": q.get("last_price", 0),
            "change_pct": q.get("change_pct", 0),
            "pe": q.get("pe", 0),
            "turnover_rate": q.get("turnover_rate", 0),
            "market_cap": q.get("market_cap", 0),  # 亿
            "strategy_params": w.strategy_params,
            "sparkline": sparkline,
        })

    enriched_pos = []
    total_pnl = 0.0
    for p in pos_data:
        q = quotes.get(p["symbol"], {})
        last_price = q.get("last_price", 0)
        market_value = last_price * p["shares"] if last_price else 0
        cost = p["avg_cost"] * p["shares"]
        unrealized_pnl = market_value - cost if market_value else 0
        pnl_pct = (unrealized_pnl / cost * 100) if cost else 0
        total_pnl += unrealized_pnl
        enriched_pos.append({
            **p,
            "last_price": last_price,
            "market_value": round(market_value, 2),
            "unrealized_pnl": round(unrealized_pnl, 2),
            "pnl_pct": round(pnl_pct, 2),
        })

    sigs = (
        db.query(Signal)
        .filter(Signal.user_id == user.id)
        .order_by(Signal.created_at.desc())
        .limit(20)
        .all()
    )
    signals_data = [schemas.SignalOut.model_validate(s).model_dump(mode="json") for s in sigs]
    unread_count = sum(1 for s in signals_data if s["is_read"] == 0)

    return {
        "ok": True,
        "data": {
            "positions": enriched_pos,
            "total_pnl": round(total_pnl, 2),
            "watchlist": watchlist_data,
            "signals": signals_data,
            "unread_count": unread_count,
        },
    }
