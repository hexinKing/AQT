from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..database import get_db
from ..models import User
from ..models import Watchlist
from ..services.news_service import clear_news_cache, get_news

router = APIRouter(prefix="/api/news", tags=["news"])


@router.get("")
def list_news(
    symbols: str = Query(..., description="Comma-separated stock symbols"),
    limit: int = Query(20, ge=1, le=50),
    page: int = Query(1, ge=1),
    _: User = Depends(get_current_user),
):
    symbol_list = [item.strip() for item in symbols.split(",") if item.strip()]
    items, total, message = get_news(symbol_list, limit=limit, page=page)
    return {
        "ok": True,
        "data": {
            "items": items,
            "total": total,
            "page": page,
            "limit": limit,
        },
        "message": message,
    }


@router.post("/refresh")
def refresh_news(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    watchlist_symbols = [
        item.symbol
        for item in db.query(Watchlist.symbol).filter(Watchlist.user_id == user.id).all()
    ]
    cleared = clear_news_cache(watchlist_symbols)
    return {
        "ok": True,
        "data": {
            "cleared": cleared,
            "symbols": watchlist_symbols,
        },
    }
