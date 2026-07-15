import json
import logging
import re
import time
from pathlib import Path

import pandas as pd
import requests
from datetime import datetime

logger = logging.getLogger(__name__)

# ── Persistent caches ──
_name_cache_path = Path(__file__).resolve().parent.parent / ".stock_names.json"
_name_cache: dict[str, str] = {}
_daily_disk_path = Path(__file__).resolve().parent.parent / ".daily_cache.json"
_daily_disk: dict[str, list[dict]] = {}

# ── In-memory caches ──
_daily_cache: dict[str, tuple[float, "pd.DataFrame"]] = {}
_daily_cache_ttl: float = 300
_realtime_cache: dict[str, tuple[float, dict]] = {}
_realtime_cache_ttl: float = 10
_minute_cache: dict[str, tuple[float, dict]] = {}
_minute_cache_ttl: float = 60


def _load_json(path: Path) -> dict:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _save_json(path: Path, data: dict):
    try:
        path.write_text(json.dumps(data, ensure_ascii=False, default=str), encoding="utf-8")
    except Exception:
        pass


_name_cache = _load_json(_name_cache_path)
_daily_disk = _load_json(_daily_disk_path)


def _market_prefix(symbol: str) -> str:
    """sh=Shanghai, sz=Shenzhen."""
    return "sh" if symbol.startswith(("6", "5", "9")) else "sz"


def _df_from_rows(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"])
    return df


def fetch_daily_cached(symbol: str, days: int = 60) -> pd.DataFrame:
    """Cache-only daily data for non-critical UI like sparklines."""
    prev = _daily_cache.get(symbol)
    if prev:
        return prev[1].tail(days).reset_index(drop=True)

    disk_rows = _daily_disk.get(symbol)
    if disk_rows:
        return _df_from_rows(disk_rows).tail(days).reset_index(drop=True)

    return pd.DataFrame()


# ═══════════════════════════════════════════════════════════════
# Tencent — realtime batch quotes
# ═══════════════════════════════════════════════════════════════

_TENCENT_REALTIME_FIELDS = {
    "name": 1, "price": 3, "prev_close": 4, "open": 5,
    "volume": 6, "high": 33, "low": 34, "change_pct": 32,
    "change_amount": 31, "turnover_rate": 38, "pe": 39,
    "amplitude": 43, "market_cap": 44, "circulating_cap": 45,
    "high52": 47, "low52": 48, "type": 61, "total_shares": 72,
}


def _tencent_realtime_batch(symbols: list[str]) -> dict[str, dict]:
    """
    Batch realtime from Tencent. 1 request for all symbols.
    Returns: symbol -> {name, price, change_pct, open, high, low, volume,
                        turnover_rate, pe, market_cap, ...}
    """
    result = {}
    if not symbols:
        return result

    now = time.time()
    uncached = []
    for sym in symbols:
        prev = _realtime_cache.get(sym)
        if prev and (now - prev[0]) < _realtime_cache_ttl:
            result[sym] = prev[1]
        else:
            uncached.append(sym)

    if not uncached:
        return result

    codes = ",".join(_market_prefix(s) + s for s in uncached)
    try:
        r = requests.get(
            f"https://qt.gtimg.cn/q={codes}",
            headers={"Referer": "https://stock.qq.com"},
            timeout=8,
        )
        r.encoding = "gbk"
        if r.status_code != 200:
            return result

        for line in r.text.strip().split("\n"):
            line = line.strip()
            if not line or "=" not in line or '=""' in line:
                continue
            eq = line.index("=")
            raw_code = line[:eq].strip().replace("v_", "")
            # raw_code includes market prefix; strip it
            sym = raw_code[2:] if len(raw_code) > 2 else raw_code
            data = line[eq + 2 : -2]  # strip =" and ";
            fields = data.split("~")
            if len(fields) < 40:
                continue

            def _f(key):
                idx = _TENCENT_REALTIME_FIELDS.get(key, -1)
                return fields[idx] if 0 <= idx < len(fields) else ""

            try:
                price = float(_f("price"))
                prev_close = float(_f("prev_close"))
                change_pct = float(_f("change_pct"))
            except ValueError:
                continue

            rd = {
                "name": _f("name"),
                "price": price,
                "change_pct": change_pct,
                "change_amount": float(_f("change_amount") or 0),
                "open": float(_f("open") or 0),
                "high": float(_f("high") or prev_close),
                "low": float(_f("low") or prev_close),
                "prev_close": prev_close,
                "volume": int(float(_f("volume") or 0)),
                "turnover_rate": float(_f("turnover_rate") or 0),
                "pe": float(_f("pe") or 0),
                "market_cap": float(_f("market_cap") or 0),  # 亿
                "circulating_cap": float(_f("circulating_cap") or 0),
                "high52": float(_f("high52") or 0),
                "low52": float(_f("low52") or 0),
                "amplitude": float(_f("amplitude") or 0),
                "type": _f("type"),  # GP-A, ETF, etc.
            }
            _realtime_cache[sym] = (now, rd)
            result[sym] = rd
            if rd["name"] and sym not in _name_cache:
                _name_cache[sym] = rd["name"]

        if any(s in result for s in uncached):
            _save_json(_name_cache_path, _name_cache)
    except Exception:
        logger.warning("Tencent realtime batch failed", exc_info=True)

    return result


# ═══════════════════════════════════════════════════════════════
# Tencent — daily K-line (前复权)
# ═══════════════════════════════════════════════════════════════

def _tencent_fetch_daily(symbol: str, days: int) -> pd.DataFrame | None:
    """
    Daily K-line from Tencent, 前复权.
    Returns DataFrame: date, open, high, low, close, volume.
    NOTE: Tencent field order is [date, open, close, high, low, volume].
    """
    code = _market_prefix(symbol) + symbol
    try:
        r = requests.get(
            "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get",
            params={"param": f"{code},day,,,{days},qfq"},
            headers={"Referer": "https://stock.qq.com"},
            timeout=10,
        )
        if r.status_code != 200:
            return None
        body = r.json()
        if body.get("code") != 0:
            return None
        inner = body.get("data", {}).get(code, {})
        rows = inner.get("qfqday") or inner.get("day")
        if not rows:
            return None
        # Tencent order: date, open, close, high, low, volume
        records = []
        for row in rows:
            records.append({
                "date": row[0],
                "open": float(row[1]),
                "high": float(row[3]),
                "low": float(row[4]),
                "close": float(row[2]),
                "volume": int(float(row[5])),
            })
        df = pd.DataFrame(records)
        df["date"] = pd.to_datetime(df["date"])
        df = df[["date", "open", "high", "low", "close", "volume"]]
        df = df.sort_values("date").reset_index(drop=True)
        return df
    except Exception:
        return None


def fetch_daily(symbol: str, days: int = 60) -> pd.DataFrame:
    """
    Daily OHLCV with 前复权. Tencent → disk cache → akshare fallback.
    """
    now = time.time()
    prev = _daily_cache.get(symbol)
    if prev and (now - prev[0]) < _daily_cache_ttl:
        return prev[1]

    df = _tencent_fetch_daily(symbol, days)

    if df is not None and not df.empty:
        _daily_cache[symbol] = (now, df)
        try:
            _daily_disk[symbol] = df.tail(days).to_dict(orient="records")
            _save_json(_daily_disk_path, _daily_disk)
        except Exception:
            pass
        return df

    # Fallback: memory → disk → akshare
    if prev:
        return prev[1]
    disk_rows = _daily_disk.get(symbol)
    if disk_rows:
        return _df_from_rows(disk_rows)

    # Last resort: akshare
    try:
        import akshare as ak
        from datetime import timedelta
        end_date = datetime.now().strftime("%Y%m%d")
        start_date = (datetime.now() - timedelta(days=days + 10)).strftime("%Y%m%d")
        df = ak.stock_zh_a_hist(
            symbol=symbol, period="daily",
            start_date=start_date, end_date=end_date, adjust="qfq",
        )
        if df is not None and not df.empty:
            df = df.rename(columns={
                "日期": "date", "开盘": "open", "最高": "high",
                "最低": "low", "收盘": "close", "成交量": "volume",
            })
            df = df[["date", "open", "high", "low", "close", "volume"]]
            df["date"] = pd.to_datetime(df["date"])
            df = df.sort_values("date").reset_index(drop=True)
            _daily_cache[symbol] = (now, df)
            _daily_disk[symbol] = df.tail(days).to_dict(orient="records")
            _save_json(_daily_disk_path, _daily_disk)
            return df
    except Exception:
        pass

    return pd.DataFrame()


# ═══════════════════════════════════════════════════════════════
# Tencent — minute chart (分时图)
# ═══════════════════════════════════════════════════════════════

def fetch_minute(symbol: str) -> dict | None:
    """Fetch today's minute-by-minute data (240 points)."""
    now = time.time()
    prev = _minute_cache.get(symbol)
    if prev and (now - prev[0]) < _minute_cache_ttl:
        return prev[1]

    code = _market_prefix(symbol) + symbol
    try:
        r = requests.get(
            "https://ifzq.gtimg.cn/appstock/app/minute/query",
            params={"_var": "min_data", "code": code},
            headers={"Referer": "https://stock.qq.com"},
            timeout=8,
        )
        if r.status_code != 200:
            return None
        # Parse "var min_data={...};" or "min_data={...}"
        text = r.text.strip()
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if not m:
            return None
        body = json.loads(m.group())
        if body.get("code") != 0:
            return None
        rows = body.get("data", {}).get(code, {}).get("data", {}).get("data", [])
        if not rows:
            return None

        # Each row: "HHMM price cum_vol cum_amount"
        times, prices, volumes, amounts = [], [], [], []
        prev_vol = 0
        for row in rows:
            parts = row.split(" ")
            if len(parts) < 3:
                continue
            t = parts[0]
            p = float(parts[1])
            cv = int(float(parts[2]))
            times.append(f"{t[:2]}:{t[2:]}")
            prices.append(p)
            # Turn cumulative into per-minute volume
            volumes.append(max(0, cv - prev_vol))
            prev_vol = cv
            amounts.append(float(parts[3]) if len(parts) > 3 else 0)

        yesterday_close = _realtime_cache.get(symbol, (0, {})
            )[1].get("prev_close", prices[0]) if _realtime_cache.get(symbol) else prices[0]

        result = {
            "symbol": symbol,
            "yesterday_close": yesterday_close,
            "times": times,
            "prices": prices,
            "volumes": volumes,
        }
        _minute_cache[symbol] = (now, result)
        return result
    except Exception:
        logger.warning("fetch_minute failed for %s", symbol, exc_info=True)
        return None


# ═══════════════════════════════════════════════════════════════
# Realtime wrappers
# ═══════════════════════════════════════════════════════════════

def _lookup_name(symbol: str) -> str:
    if symbol in _name_cache:
        return _name_cache[symbol]
    batch = _tencent_realtime_batch([symbol])
    if symbol in batch:
        return batch[symbol]["name"]
    return ""


def fetch_realtime(symbol: str) -> dict | None:
    batch = _tencent_realtime_batch([symbol])
    rt = batch.get(symbol)
    if rt:
        return {
            "symbol": symbol,
            "name": rt["name"],
            "last_price": rt["price"],
            "change_pct": rt["change_pct"],
            # Extra fields
            "pe": rt["pe"],
            "turnover_rate": rt["turnover_rate"],
            "market_cap": rt["market_cap"],
        }
    df = fetch_daily(symbol, days=5)
    if df.empty:
        return None
    latest = df.iloc[-1]
    prev = df.iloc[-2] if len(df) > 1 else latest
    change_pct = (float(latest["close"]) - float(prev["close"])) / float(prev["close"]) * 100 if float(prev["close"]) else 0
    return {
        "symbol": symbol,
        "name": _name_cache.get(symbol, ""),
        "last_price": float(latest["close"]),
        "change_pct": round(change_pct, 2),
        "pe": 0, "turnover_rate": 0, "market_cap": 0,
    }


def fetch_realtime_batch(symbols: list[str]) -> dict[str, dict]:
    if not symbols:
        return {}
    batch = _tencent_realtime_batch(symbols)
    result = {}
    for sym in symbols:
        rt = batch.get(sym)
        if rt:
            result[sym] = {
                "symbol": sym,
                "name": rt["name"],
                "last_price": rt["price"],
                "change_pct": rt["change_pct"],
                "pe": rt["pe"],
                "turnover_rate": rt["turnover_rate"],
                "market_cap": rt["market_cap"],
            }
        else:
            q = fetch_realtime(sym)
            if q:
                result[sym] = q
    return result


# ═══════════════════════════════════════════════════════════════
# Warmup
# ═══════════════════════════════════════════════════════════════

def warmup_cache():
    """Pre-fetch realtime + K-line for all user symbols on startup."""
    from .database import SessionLocal
    from .models import Position, Watchlist

    db = SessionLocal()
    try:
        positions = [p.symbol for p in db.query(Position.symbol).distinct()]
        watchlist = [w.symbol for w in db.query(Watchlist.symbol).distinct()]
        symbols = list(set(positions + watchlist))
    except Exception:
        logger.exception("warmup: failed to query symbols")
        symbols = []
    finally:
        db.close()

    if not symbols:
        logger.info("warmup: no symbols")
        return

    logger.info("warmup: %d symbols", len(symbols))

    # 1. Realtime (1 batch request)
    _tencent_realtime_batch(symbols)

    # 2. K-line (1 req each, with delay)
    for i, sym in enumerate(symbols):
        try:
            fetch_daily(sym, days=60)
        except Exception:
            logger.warning("warmup K-line failed for %s", sym)
        if i < len(symbols) - 1:
            time.sleep(0.5)

    _save_json(_name_cache_path, _name_cache)
    _save_json(_daily_disk_path, _daily_disk)
    logger.info("warmup: done — %d names, %d K-line sets", len(_name_cache), len(_daily_disk))
