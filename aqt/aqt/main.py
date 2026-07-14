import logging
from contextlib import asynccontextmanager
from datetime import date, datetime
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .data_fetcher import warmup_cache
from .database import Base, engine, get_db
from .engine import run_strategies
from .models import User
from .routers import auth, dashboard, news, positions, settings, signals, watchlist
from .services.market_service import is_trade_day, market_close_minutes
from .services.report_service import send_market_close_report

logger = logging.getLogger(__name__)
scheduler = BackgroundScheduler()
_last_report_run: date | None = None


def _scheduled_tick():
    """Single scheduler tick: refresh data + run strategies, weekdays 9:00-15:30 only."""
    now = datetime.now()
    if not is_trade_day(now.date()):
        return
    t = now.hour * 60 + now.minute
    if not (540 <= t <= 930):  # 9:00-15:30
        return

    try:
        warmup_cache()
    except Exception:
        logger.exception("Scheduled warmup failed")

    db = next(get_db())
    try:
        users = db.query(User).all()
        for user in users:
            try:
                run_strategies(user.id, db)
            except Exception:
                logger.exception("Strategy check failed for user %s", user.id)
    finally:
        db.close()


def _scheduled_market_close_report():
    global _last_report_run

    now = datetime.now()
    if not is_trade_day(now.date()):
        return
    if now.hour * 60 + now.minute < market_close_minutes():
        return
    if _last_report_run == now.date():
        return

    db = next(get_db())
    try:
        users = db.query(User).all()
        for user in users:
            try:
                send_market_close_report(user, db, report_date=now.date())
            except Exception:
                logger.exception("Market close report failed for user %s", user.id)
        db.commit()
        _last_report_run = now.date()
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    warmup_cache()
    scheduler.add_job(_scheduled_tick, "interval", minutes=5, id="tick")
    scheduler.add_job(_scheduled_market_close_report, "interval", minutes=5, id="market-close-report")
    scheduler.start()
    yield
    scheduler.shutdown(wait=False)


app = FastAPI(title="AQT", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8000", "http://127.0.0.1:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def _no_cache_html(request, call_next):
    response = await call_next(request)
    if request.url.path == "/" or request.url.path.endswith(".html"):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


# Register routers
app.include_router(auth.router)
app.include_router(watchlist.router)
app.include_router(positions.router)
app.include_router(signals.router)
app.include_router(dashboard.router)
app.include_router(news.router)
app.include_router(settings.router)

_STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


@app.get("/")
async def root():
    return FileResponse(_STATIC_DIR / "index.html", media_type="text/html")


app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")
