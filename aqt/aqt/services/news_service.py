import logging
import time
from datetime import datetime

from ..config import settings

logger = logging.getLogger(__name__)

_news_cache: dict[str, tuple[float, list[dict]]] = {}


def _normalize_symbol(symbol: str) -> str:
    return "".join(ch for ch in (symbol or "").strip() if ch.isdigit())


def _parse_news_row(row: dict, symbol: str) -> dict | None:
    title = str(row.get("新闻标题") or row.get("title") or "").strip()
    if not title:
        return None

    published_at = row.get("发布时间") or row.get("publish_time") or row.get("发布时间戳") or ""
    published_text = str(published_at).strip()
    if published_text:
        published_text = published_text.replace("T", " ").replace("/", "-")
        if len(published_text) == 10:
            published_text += " 00:00:00"

    source = str(row.get("文章来源") or row.get("source") or "东方财富").strip() or "东方财富"
    url = str(row.get("新闻链接") or row.get("url") or "").strip()
    summary = str(row.get("新闻内容") or row.get("摘要") or row.get("content") or "").strip()

    return {
        "title": title,
        "source": source,
        "url": url,
        "published_at": published_text,
        "symbols": [symbol],
        "summary": summary,
    }


def _fetch_symbol_news(symbol: str) -> tuple[list[dict], bool]:
    symbol = _normalize_symbol(symbol)
    if not symbol:
        return [], False

    now = time.time()
    cached = _news_cache.get(symbol)
    if cached and (now - cached[0]) < settings.news_cache_ttl:
        return cached[1], False

    rows: list[dict] = []
    try:
        import akshare as ak

        df = ak.stock_news_em(symbol=symbol)
        if df is not None and not df.empty:
            raw_rows = df.to_dict(orient="records")[:20]
            rows = [item for item in (_parse_news_row(row, symbol) for row in raw_rows) if item]
    except Exception:
        logger.warning("Failed to fetch news for symbol %s", symbol, exc_info=True)
        return [], True

    _news_cache[symbol] = (now, rows)
    return rows, False


def _sort_key(item: dict) -> tuple[int, str]:
    published_at = item.get("published_at") or ""
    if not published_at:
        return (0, "")
    try:
        return (1, datetime.strptime(published_at, "%Y-%m-%d %H:%M:%S").isoformat())
    except ValueError:
        return (1, published_at)


def get_news(symbols: list[str], limit: int = 20, page: int = 1) -> tuple[list[dict], int, str | None]:
    normalized = []
    for symbol in symbols[:20]:
        clean = _normalize_symbol(symbol)
        if clean:
            normalized.append(clean)

    merged: list[dict] = []
    failures = 0
    for symbol in normalized:
        items, failed = _fetch_symbol_news(symbol)
        if failed:
            failures += 1
        merged.extend(items)

    deduped: list[dict] = []
    seen: set[tuple[str, str, str]] = set()
    for item in merged:
        key = (
            (item.get("url") or "").strip(),
            (item.get("title") or "").strip(),
            (item.get("published_at") or "").strip(),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)

    deduped.sort(key=_sort_key, reverse=True)
    limit = max(1, min(limit, 50))
    page = max(1, page)
    start = (page - 1) * limit
    end = start + limit

    message = None
    if normalized and failures == len(normalized):
        message = "news source unavailable"
    elif failures > 0:
        message = "partial news unavailable"

    return deduped[start:end], len(deduped), message
