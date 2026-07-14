from fastapi import APIRouter, Depends, Query

from ..auth import get_current_user
from ..models import User
from ..services.news_service import get_news

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
