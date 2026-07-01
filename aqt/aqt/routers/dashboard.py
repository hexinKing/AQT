from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..data_fetcher import fetch_daily, fetch_minute
from ..database import get_db
from ..engine import run_strategies
from ..models import User
from ..services.dashboard_service import build_dashboard

router = APIRouter(tags=["dashboard"])


@router.get("/api/dashboard")
def dashboard(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return build_dashboard(user, db)


@router.get("/api/kline/{symbol}")
def kline(symbol: str, days: int = 60, _=Depends(get_current_user)):
    df = fetch_daily(symbol, days=days)
    if df.empty:
        return {"ok": True, "data": []}
    records = df.to_dict(orient="records")
    for r in records:
        r["date"] = r["date"].strftime("%Y-%m-%d") if hasattr(r["date"], "strftime") else str(r["date"])
    return {"ok": True, "data": records}


@router.get("/api/kline/{symbol}/minute")
def minute_kline(symbol: str, _=Depends(get_current_user)):
    data = fetch_minute(symbol)
    if not data:
        return {"ok": True, "data": None}
    return {"ok": True, "data": data}


@router.post("/api/check-now")
def check_now(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    new_signals = run_strategies(user.id, db)
    return {"ok": True, "data": {"new_signals": new_signals}}
