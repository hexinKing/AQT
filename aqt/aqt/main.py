from contextlib import asynccontextmanager

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import Depends, FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from . import schemas
from .auth import create_token, get_current_user, hash_password, verify_password
from .config import settings
from .database import Base, engine, get_db
from .engine import run_strategies
from .models import Position, Signal, User, Watchlist
from .data_fetcher import fetch_realtime, fetch_realtime_batch

scheduler = BackgroundScheduler()


def _scheduled_check():
    """Run strategies for all users every 5 minutes."""
    db = next(get_db())
    try:
        users = db.query(User).all()
        for user in users:
            run_strategies(user.id, db)
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    scheduler.add_job(_scheduled_check, "interval", minutes=5, id="strategy_check")
    scheduler.start()
    yield
    scheduler.shutdown(wait=False)


app = FastAPI(title="AQT", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


# ── Auth ──
@app.post("/api/auth/register")
def register(req: schemas.RegisterRequest, db: Session = Depends(get_db)):
    if db.query(User).filter(User.username == req.username).first():
        raise HTTPException(400, "Username already exists")
    user = User(
        username=req.username,
        password_hash=hash_password(req.password),
        email=req.email,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    token = create_token(user.id)
    return {"ok": True, "data": {"token": token, "username": user.username}}


@app.post("/api/auth/login")
def login(req: schemas.LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == req.username).first()
    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(401, "Invalid credentials")
    token = create_token(user.id)
    return {"ok": True, "data": {"token": token, "username": user.username}}


# ── Watchlist ──
@app.get("/api/watchlist")
def list_watchlist(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    items = db.query(Watchlist).filter(Watchlist.user_id == user.id).all()
    return {"ok": True, "data": [schemas.WatchlistOut.model_validate(i).model_dump(mode="json") for i in items]}


@app.post("/api/watchlist")
def add_watchlist(req: schemas.WatchlistCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if db.query(Watchlist).filter(Watchlist.user_id == user.id, Watchlist.symbol == req.symbol).first():
        raise HTTPException(400, "Already in watchlist")
    # auto-fetch name
    info = fetch_realtime(req.symbol)
    name = req.name or (info["name"] if info else "")
    item = Watchlist(
        user_id=user.id,
        symbol=req.symbol,
        name=name,
        strategy_params='{"ma_cross":{"short_window":5,"long_window":20,"enabled":true},"grid":{"grid_pct":0.03,"base_price":0,"enabled":false},"trailing_stop":{"trail_pct":0.05,"entry_price":0,"enabled":false}}',
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return {"ok": True, "data": schemas.WatchlistOut.model_validate(item).model_dump(mode="json")}


@app.delete("/api/watchlist/{item_id}")
def delete_watchlist(item_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    item = db.query(Watchlist).filter(Watchlist.id == item_id, Watchlist.user_id == user.id).first()
    if not item:
        raise HTTPException(404, "Not found")
    db.delete(item)
    db.commit()
    return {"ok": True, "data": None}


@app.put("/api/watchlist/{item_id}/strategies")
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


# ── Positions ──
@app.get("/api/positions")
def list_positions(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    items = db.query(Position).filter(Position.user_id == user.id).all()
    return {"ok": True, "data": [schemas.PositionOut.model_validate(i).model_dump(mode="json") for i in items]}


@app.post("/api/positions")
def create_position(req: schemas.PositionCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    pos = Position(user_id=user.id, **req.model_dump())
    db.add(pos)
    db.commit()
    db.refresh(pos)
    return {"ok": True, "data": schemas.PositionOut.model_validate(pos).model_dump(mode="json")}


@app.put("/api/positions/{pos_id}")
def update_position(
    pos_id: int,
    req: schemas.PositionUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    pos = db.query(Position).filter(Position.id == pos_id, Position.user_id == user.id).first()
    if not pos:
        raise HTTPException(404, "Not found")
    updates = req.model_dump(exclude_unset=True)
    for k, v in updates.items():
        setattr(pos, k, v)
    db.commit()
    db.refresh(pos)
    return {"ok": True, "data": schemas.PositionOut.model_validate(pos).model_dump(mode="json")}


@app.delete("/api/positions/{pos_id}")
def delete_position(pos_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    pos = db.query(Position).filter(Position.id == pos_id, Position.user_id == user.id).first()
    if not pos:
        raise HTTPException(404, "Not found")
    db.delete(pos)
    db.commit()
    return {"ok": True, "data": None}


# ── Signals ──
@app.get("/api/signals")
def list_signals(
    unread_only: int = 0,
    limit: int = 50,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = db.query(Signal).filter(Signal.user_id == user.id)
    if unread_only:
        q = q.filter(Signal.is_read == 0)
    items = q.order_by(Signal.created_at.desc()).limit(limit).all()
    return {"ok": True, "data": [schemas.SignalOut.model_validate(i).model_dump(mode="json") for i in items]}


@app.put("/api/signals/{sig_id}/read")
def mark_read(sig_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    sig = db.query(Signal).filter(Signal.id == sig_id, Signal.user_id == user.id).first()
    if not sig:
        raise HTTPException(404, "Not found")
    sig.is_read = 1
    db.commit()
    return {"ok": True, "data": None}


@app.put("/api/signals/read-all")
def mark_all_read(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    db.query(Signal).filter(Signal.user_id == user.id, Signal.is_read == 0).update({"is_read": 1})
    db.commit()
    return {"ok": True, "data": None}


# ── Dashboard ──
@app.get("/api/dashboard")
def dashboard(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    # positions
    positions = db.query(Position).filter(Position.user_id == user.id).all()
    pos_data = [schemas.PositionOut.model_validate(p).model_dump(mode="json") for p in positions]

    # watchlist
    wl = db.query(Watchlist).filter(Watchlist.user_id == user.id).all()

    # realtime quotes for watchlist + positions
    symbols = list({p.symbol for p in positions} | {w.symbol for w in wl})
    quotes = fetch_realtime_batch(symbols)

    # enrich watchlist
    watchlist_data = []
    for w in wl:
        q = quotes.get(w.symbol, {})
        watchlist_data.append({
            "id": w.id,
            "symbol": w.symbol,
            "name": w.name or q.get("name", ""),
            "last_price": q.get("last_price", 0),
            "change_pct": q.get("change_pct", 0),
            "strategy_params": w.strategy_params,
        })

    # enrich positions with P&L
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

    # unread signals
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


# ── Settings ──
@app.get("/api/settings")
def get_settings(user: User = Depends(get_current_user)):
    return {
        "ok": True,
        "data": {
            "email": user.email,
            "smtp_host": user.smtp_host,
            "smtp_port": user.smtp_port,
            "smtp_user": user.smtp_user,
        },
    }


@app.put("/api/settings")
def update_settings(req: schemas.SettingsUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    updates = req.model_dump(exclude_unset=True)
    for k, v in updates.items():
        setattr(user, k, v)
    db.commit()
    return {"ok": True, "data": None}


# ── Manual Check ──
@app.post("/api/check-now")
def check_now(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    new_signals = run_strategies(user.id, db)
    return {"ok": True, "data": {"new_signals": new_signals}}


# ── Static ──
app.mount("/", StaticFiles(directory="static", html=True), name="static")
