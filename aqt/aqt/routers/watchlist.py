from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import schemas
from ..auth import get_current_user
from ..data_fetcher import fetch_realtime
from ..database import get_db
from ..models import User, Watchlist

router = APIRouter(prefix="/api/watchlist", tags=["watchlist"])

DEFAULT_STRATEGY_PARAMS = (
    '{"ma_cross":{"short_window":5,"long_window":20,"enabled":true},'
    '"grid":{"grid_pct":0.03,"base_price":0,"enabled":false},'
    '"trailing_stop":{"trail_pct":0.05,"entry_price":0,"enabled":false}}'
)


@router.get("")
def list_watchlist(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    items = db.query(Watchlist).filter(Watchlist.user_id == user.id).all()
    return {"ok": True, "data": [schemas.WatchlistOut.model_validate(i).model_dump(mode="json") for i in items]}


@router.post("")
def add_watchlist(req: schemas.WatchlistCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if db.query(Watchlist).filter(Watchlist.user_id == user.id, Watchlist.symbol == req.symbol).first():
        raise HTTPException(400, "Already in watchlist")
    info = fetch_realtime(req.symbol)
    name = req.name or (info["name"] if info else "")
    item = Watchlist(
        user_id=user.id,
        symbol=req.symbol,
        name=name,
        strategy_params=DEFAULT_STRATEGY_PARAMS,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return {"ok": True, "data": schemas.WatchlistOut.model_validate(item).model_dump(mode="json")}


@router.delete("/{item_id}")
def delete_watchlist(item_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    item = db.query(Watchlist).filter(Watchlist.id == item_id, Watchlist.user_id == user.id).first()
    if not item:
        raise HTTPException(404, "Not found")
    db.delete(item)
    db.commit()
    return {"ok": True, "data": None}


@router.put("/{item_id}/strategies")
def update_strategies(
    item_id: int,
    body: dict,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    item = db.query(Watchlist).filter(Watchlist.id == item_id, Watchlist.user_id == user.id).first()
    if not item:
        raise HTTPException(404, "Not found")
    item.strategies = body
    db.commit()
    return {"ok": True, "data": {"strategies": body}}
