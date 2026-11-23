"""Live news adapter: GDELT, Yahoo Finance, then Google News RSS.
Provider failure is distinct from a successful empty result; no headlines are fabricated.
"""
import time
import requests
from datetime import datetime, timezone
from urllib.parse import quote_plus
import xml.etree.ElementTree as ET

_cache = {}
HEADERS = {"User-Agent": "Mozilla/5.0 MARKETMIND/1.2 (educational research app)"}


def _normalise_yahoo_news(raw, limit):
    articles = []
    for item in raw.get("news", [])[:limit]:
        content = item.get("content") or item
        canonical = content.get("canonicalUrl") or {}
        click = content.get("clickThroughUrl") or {}
        provider = content.get("provider") or {}
        title = content.get("title")
        url = canonical.get("url") or click.get("url") or content.get("link")
        if not title or not url:
            continue
        published = content.get("pubDate") or content.get("published_at")
        articles.append({"title": title, "url": url, "source": provider.get("displayName") or "Yahoo Finance",
                         "published_at": published, "language": None, "source_country": None})
    return articles


def _gdelt(company, symbol, limit):
    query = f'("{company}" OR "{symbol}")'
    params = {"query": query, "mode": "ArtList", "format": "json", "maxrecords": min(max(limit, 1), 25), "timespan": "7d", "sort": "DateDesc"}
    response = requests.get("https://api.gdeltproject.org/api/v2/doc/doc", params=params, headers=HEADERS, timeout=16)
    response.raise_for_status()
    if "json" not in response.headers.get("content-type", "").lower():
        raise ValueError("GDELT returned a non-JSON response")
    raw = response.json()
    articles = []
    for item in raw.get("articles", []):
        if not item.get("title") or not item.get("url"):
            continue
        articles.append({"title": item.get("title"), "url": item.get("url"),
                         "source": item.get("domain") or item.get("sourceCountry"),
                         "published_at": item.get("seendate"), "language": item.get("language"),
                         "source_country": item.get("sourceCountry")})
    return query, articles


def _yahoo_news(company, symbol, limit):
    query = f"{company} {symbol}".strip()
    response = requests.get("https://query1.finance.yahoo.com/v1/finance/search",
                            params={"q": query, "quotesCount": 0, "newsCount": min(max(limit, 1), 20)},
                            headers=HEADERS, timeout=14)
    response.raise_for_status()
    raw = response.json()
    return _normalise_yahoo_news(raw, limit)


def _google_news_rss(company, symbol, limit):
    query = f"{company} {symbol}".strip()
    encoded_query = quote_plus(query)
    url = f"https://news.google.com/rss/search?q={encoded_query}&hl=en-US&gl=US&ceid=US:en"
    response = requests.get(url, headers=HEADERS, timeout=14)
    response.raise_for_status()
    try:
        root = ET.fromstring(response.text)
    except (ET.ParseError, TypeError, ValueError) as exc:
        raise ValueError(f"Google News RSS returned malformed XML: {str(exc)[:180]}") from exc

    articles = []
    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        if not title or not link:
            continue
        published = (item.findtext("pubDate") or "").strip() or None
        source_element = item.find("source")
        source = (source_element.text or "").strip() if source_element is not None else None
        articles.append({"title": title, "url": link, "source": source or "Google News RSS",
                         "published_at": published, "language": "en", "source_country": "US"})
        if len(articles) >= limit:
            break
    return articles


def search_news(company, symbol, limit=8, force_refresh=False):
    key = f"{company}|{symbol}".lower()
    now = time.time()
    cached = _cache.get(key)
    if not force_refresh and cached and now - cached["at"] < 180:
        return {**cached["data"], "cached": True}

    errors = []
    successful_responses = 0
    query = f'("{company}" OR "{symbol}")'
    try:
        query, articles = _gdelt(company, symbol, limit)
        successful_responses += 1
        if articles:
            data = {"query": query, "source": "GDELT DOC 2.0", "status": "LIVE_NEWS_AVAILABLE", "is_live": True,
                    "articles": articles, "count": len(articles), "window": "7 days",
                    "retrieved_at": datetime.now(timezone.utc).isoformat(), "provider_chain": ["GDELT DOC 2.0"],
                    "warning": "GDELT coverage is broad but not exhaustive; headlines are leads, not verified facts."}
            _cache[key] = {"at": now, "data": data}
            return data
        errors.append({"provider": "GDELT DOC 2.0", "error": "Successful response contained zero articles"})
    except Exception as exc:
        errors.append({"provider": "GDELT DOC 2.0", "error": str(exc)[:220]})

    try:
        articles = _yahoo_news(company, symbol, limit)
        successful_responses += 1
        if articles:
            data = {"query": query, "source": "Yahoo Finance Search News", "status": "LIVE_NEWS_AVAILABLE", "is_live": True,
                    "articles": articles, "count": len(articles), "window": "provider-defined recent coverage",
                    "retrieved_at": datetime.now(timezone.utc).isoformat(),
                    "provider_chain": ["GDELT DOC 2.0", "Yahoo Finance Search News"], "provider_errors": errors,
                    "warning": "Yahoo Finance search results are third-party headlines; verify claims against primary sources."}
            _cache[key] = {"at": now, "data": data}
            return data
        errors.append({"provider": "Yahoo Finance Search News", "error": "Successful response contained zero articles"})
        status = "NO_ARTICLES_FOUND" if all("zero articles" in e["error"] for e in errors) else "PROVIDER_UNAVAILABLE"
    except Exception as exc:
        errors.append({"provider": "Yahoo Finance Search News", "error": str(exc)[:220]})
    try:
        articles = _google_news_rss(company, symbol, limit)
        successful_responses += 1
        if articles:
            data = {"query": query, "source": "Google News RSS", "status": "LIVE_NEWS_AVAILABLE", "is_live": True,
                    "articles": articles, "count": len(articles), "window": "Google News RSS recent coverage",
                    "retrieved_at": datetime.now(timezone.utc).isoformat(),
                    "provider_chain": ["GDELT DOC 2.0", "Yahoo Finance Search News", "Google News RSS"],
                    "provider_errors": errors,
                    "warning": "Google News RSS links to third-party coverage; verify claims against primary sources."}
            _cache[key] = {"at": now, "data": data}
            return data
        errors.append({"provider": "Google News RSS", "error": "Successful response contained zero usable articles"})
    except Exception as exc:
        errors.append({"provider": "Google News RSS", "error": str(exc)[:220]})

    status = "NO_ARTICLES_FOUND" if successful_responses > 0 else "PROVIDER_UNAVAILABLE"
    data = {"query": query, "source": "GDELT DOC 2.0 + Yahoo Finance Search News + Google News RSS", "status": status,
            "is_live": False, "articles": [], "count": 0, "window": "7 days / provider-defined",
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "provider_chain": ["GDELT DOC 2.0", "Yahoo Finance Search News", "Google News RSS"],
            "provider_errors": errors,
            "warning": "Live news providers did not supply articles. This does not establish that no relevant news exists."}
    _cache[key] = {"at": now, "data": data}
    return data
