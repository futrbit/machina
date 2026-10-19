import os
import re
import time
from pathlib import Path
from threading import Lock
from datetime import datetime, timezone

import requests
from dotenv import load_dotenv
from flask import Blueprint, jsonify, request

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env", override=False)

market_bp = Blueprint("market_data", __name__)

PROVIDER_URL = "https://www.alphavantage.co/query"
CACHE_SECONDS = 6 * 60 * 60
_cache = {}
_cache_lock = Lock()


def utc_now():
    return datetime.now(timezone.utc).isoformat()


@market_bp.get("/intelligence/api/market/health")
def market_health():
    return jsonify({
        "provider": "Alpha Vantage",
        "configured": bool(os.getenv("ALPHA_VANTAGE_API_KEY", "").strip()),
        "quote_type": "Free-tier end-of-day quote",
        "cache_seconds": CACHE_SECONDS,
        "api_key_exposed": False,
    })


@market_bp.get("/intelligence/api/market/quote")
def market_quote():
    symbol = (request.args.get("symbol") or "").strip().upper()

    if not symbol or len(symbol) > 20 or not re.fullmatch(
        r"[A-Z0-9.^_-]+", symbol
    ):
        return jsonify({
            "ok": False,
            "error": "Provide a valid ticker symbol, for example IBM.",
        }), 400

    api_key = os.getenv("ALPHA_VANTAGE_API_KEY", "").strip()
    if not api_key:
        return jsonify({
            "ok": False,
            "error": "Market data is not configured. Check the server .env file.",
        }), 503

    now = time.time()
    with _cache_lock:
        cached = _cache.get(symbol)
        if cached and now - cached["cached_at"] < CACHE_SECONDS:
            result = dict(cached["payload"])
            result["cached"] = True
            return jsonify(result)

    try:
        response = requests.get(
            PROVIDER_URL,
            params={
                "function": "GLOBAL_QUOTE",
                "symbol": symbol,
                "apikey": api_key,
            },
            timeout=15,
        )
        response.raise_for_status()
        payload = response.json()
    except requests.RequestException:
        return jsonify({
            "ok": False,
            "error": "Market-data provider could not be reached. Try again later.",
        }), 502
    except ValueError:
        return jsonify({
            "ok": False,
            "error": "Market-data provider returned an unreadable response.",
        }), 502

    # Alpha Vantage communicates many API and quota errors as JSON messages.
    if any(key in payload for key in ("Error Message", "Note", "Information")):
        return jsonify({
            "ok": False,
            "error": (
                "The provider rejected the request or its free request allowance "
                "may have been reached. Check your Alpha Vantage account and try later."
            ),
            "provider_message": "Provider did not return a quote.",
        }), 429 if "Note" in payload else 502

    quote = payload.get("Global Quote")
    if not isinstance(quote, dict) or not quote.get("05. price"):
        return jsonify({
            "ok": False,
            "error": f"No quote was returned for ticker {symbol}. Check the symbol.",
        }), 404

    result = {
        "ok": True,
        "provider": "Alpha Vantage",
        "symbol": quote.get("01. symbol", symbol),
        "price": quote.get("05. price"),
        "open": quote.get("02. open"),
        "high": quote.get("03. high"),
        "low": quote.get("04. low"),
        "volume": quote.get("06. volume"),
        "latest_trading_day": quote.get("07. latest trading day"),
        "previous_close": quote.get("08. previous close"),
        "change": quote.get("09. change"),
        "change_percent": quote.get("10. change percent"),
        "quote_type": "End-of-day quote; not live intraday pricing",
        "fetched_at_utc": utc_now(),
        "cached": False,
    }

    with _cache_lock:
        _cache[symbol] = {
            "cached_at": time.time(),
            "payload": result,
        }

    return jsonify(result)
