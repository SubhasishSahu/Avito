"""
Agent_Trader -- Harvest Runner
Data source: NSE India official APIs (nseindia.com)
  - Price history  : /api/historical/cm/equity?symbol=X&series=EQ&from=&to=
  - Quote/fundam.  : /api/quote-equity?symbol=X
  - Index history  : /api/historical/indicesHistory?indexType=NIFTY+50&from=&to=

No API key required. NSE does not block cloud/datacenter IP ranges.

Analytics computed locally: RSI, MACD, Beta, CAGR, VaR, Alpha, Max Drawdown.

Fix history:
  BUG_1-9  (see previous comments -- yfinance/curl_cffi stack)
  BUG_10   yfinance rate-limited at IP level on GitHub Actions
           -> switched to NSE India official API, no rate limit
"""
import os
import sys
import logging
import warnings
import uuid
import time
from datetime import datetime, timedelta

import pandas as pd
import numpy as np
import requests

import github_store as gs

warnings.filterwarnings("ignore")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Nifty50 Universe: exactly 50 unique stocks, sector-mapped
# ---------------------------------------------------------------------------
NIFTY50 = {
    # Financial Services -- 10
    "HDFCBANK":   {"name": "HDFC Bank",              "sector": "Financial Services"},
    "ICICIBANK":  {"name": "ICICI Bank",             "sector": "Financial Services"},
    "KOTAKBANK":  {"name": "Kotak Mahindra Bank",    "sector": "Financial Services"},
    "AXISBANK":   {"name": "Axis Bank",              "sector": "Financial Services"},
    "SBIN":       {"name": "State Bank of India",    "sector": "Financial Services"},
    "BAJFINANCE": {"name": "Bajaj Finance",          "sector": "Financial Services"},
    "BAJAJFINSV": {"name": "Bajaj Finserv",          "sector": "Financial Services"},
    "HDFCLIFE":   {"name": "HDFC Life Insurance",    "sector": "Financial Services"},
    "SBILIFE":    {"name": "SBI Life Insurance",     "sector": "Financial Services"},
    "INDUSINDBK": {"name": "IndusInd Bank",          "sector": "Financial Services"},
    # IT -- 6
    "TCS":        {"name": "Tata Consultancy",       "sector": "IT"},
    "INFY":       {"name": "Infosys",                "sector": "IT"},
    "HCLTECH":    {"name": "HCL Technologies",       "sector": "IT"},
    "WIPRO":      {"name": "Wipro",                  "sector": "IT"},
    "TECHM":      {"name": "Tech Mahindra",          "sector": "IT"},
    "LTIM":       {"name": "LTIMindtree",            "sector": "IT"},
    # Oil & Gas -- 6
    "RELIANCE":   {"name": "Reliance Industries",    "sector": "Oil & Gas"},
    "ONGC":       {"name": "ONGC",                   "sector": "Oil & Gas"},
    "BPCL":       {"name": "BPCL",                   "sector": "Oil & Gas"},
    "COALINDIA":  {"name": "Coal India",             "sector": "Oil & Gas"},
    "POWERGRID":  {"name": "Power Grid Corp",        "sector": "Oil & Gas"},
    "NTPC":       {"name": "NTPC",                   "sector": "Oil & Gas"},
    # Consumer -- 8
    "HINDUNILVR": {"name": "Hindustan Unilever",     "sector": "Consumer"},
    "ITC":        {"name": "ITC",                    "sector": "Consumer"},
    "NESTLEIND":  {"name": "Nestle India",           "sector": "Consumer"},
    "BRITANNIA":  {"name": "Britannia Industries",   "sector": "Consumer"},
    "TATACONSUM": {"name": "Tata Consumer Products", "sector": "Consumer"},
    "TITAN":      {"name": "Titan Company",          "sector": "Consumer"},
    "ASIANPAINT": {"name": "Asian Paints",           "sector": "Consumer"},
    "ZOMATO":     {"name": "Zomato",                 "sector": "Consumer"},
    # Auto -- 6
    "MARUTI":     {"name": "Maruti Suzuki",          "sector": "Auto"},
    "BAJAJ-AUTO": {"name": "Bajaj Auto",             "sector": "Auto"},
    "HEROMOTOCO": {"name": "Hero MotoCorp",          "sector": "Auto"},
    "EICHERMOT":  {"name": "Eicher Motors",          "sector": "Auto"},
    "M&M":        {"name": "Mahindra & Mahindra",    "sector": "Auto"},
    "TATAMOTORS": {"name": "Tata Motors",            "sector": "Auto"},
    # Pharma -- 5
    "SUNPHARMA":  {"name": "Sun Pharmaceutical",     "sector": "Pharma"},
    "DRREDDY":    {"name": "Dr Reddys Labs",         "sector": "Pharma"},
    "CIPLA":      {"name": "Cipla",                  "sector": "Pharma"},
    "DIVISLAB":   {"name": "Divis Laboratories",     "sector": "Pharma"},
    "APOLLOHOSP": {"name": "Apollo Hospitals",       "sector": "Pharma"},
    # Metals -- 4
    "TATASTEEL":  {"name": "Tata Steel",             "sector": "Metals"},
    "JSWSTEEL":   {"name": "JSW Steel",              "sector": "Metals"},
    "HINDALCO":   {"name": "Hindalco Industries",    "sector": "Metals"},
    "ADANIENT":   {"name": "Adani Enterprises",      "sector": "Metals"},
    # Infrastructure -- 2
    "LT":         {"name": "Larsen and Toubro",      "sector": "Infrastructure"},
    "ADANIPORTS": {"name": "Adani Ports",            "sector": "Infrastructure"},
    # Cement -- 2
    "ULTRACEMCO": {"name": "UltraTech Cement",       "sector": "Cement"},
    "GRASIM":     {"name": "Grasim Industries",      "sector": "Cement"},
    # Telecom -- 1
    "BHARTIARTL": {"name": "Bharti Airtel",          "sector": "Telecom"},
}

assert len(NIFTY50) == 50, f"NIFTY50 has {len(NIFTY50)} stocks -- expected exactly 50"

THROTTLE_SECS = 0.4


# ---------------------------------------------------------------------------
# NSE HTTP session
# NSE requires browser-like headers + cookie handshake on first request.
# ---------------------------------------------------------------------------

NSE_BASE = "https://www.nseindia.com"

_NSE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/121.0.0.0 Safari/537.36"
    ),
    "Accept":          "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer":         "https://www.nseindia.com/",
    "Connection":      "keep-alive",
}

_session = None


def _get_session():
    global _session
    if _session is not None:
        return _session
    s = requests.Session()
    s.headers.update(_NSE_HEADERS)
    try:
        r = s.get(NSE_BASE, timeout=15)
        r.raise_for_status()
        log.info(f"NSE cookie handshake OK ({len(s.cookies)} cookies)")
    except Exception as e:
        log.warning(f"NSE cookie handshake failed: {e} -- continuing anyway")
    _session = s
    return _session


def _nse_get(path, params=None, retries=3):
    s = _get_session()
    url = f"{NSE_BASE}{path}"
    for attempt in range(1, retries + 1):
        try:
            r = s.get(url, params=params, timeout=20)
            if r.status_code == 401:
                log.debug("NSE 401 -- refreshing session cookies")
                s.get(NSE_BASE, timeout=15)
                r = s.get(url, params=params, timeout=20)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            log.debug(f"NSE GET attempt {attempt} failed ({url}): {e}")
            if attempt < retries:
                time.sleep(2 ** attempt)
    return None


# ---------------------------------------------------------------------------
# Price history
# ---------------------------------------------------------------------------

def _fetch_prices_nse(symbol, label):
    end_dt   = datetime.today()
    start_dt = end_dt - timedelta(days=3 * 365 + 30)

    params = {
        "symbol": symbol,
        "series": "EQ",
        "from":   start_dt.strftime("%d-%m-%Y"),
        "to":     end_dt.strftime("%d-%m-%Y"),
    }
    data = _nse_get("/api/historical/cm/equity", params=params)

    if not data:
        log.warning(f"  {label}: NSE returned no data")
        return None

    rows = data.get("data", [])
    if not rows:
        log.warning(f"  {label}: empty data array")
        return None

    try:
        df = pd.DataFrame(rows)
        ts_col    = next((c for c in df.columns if "TIMESTAMP" in c.upper()), None)
        close_col = next((c for c in df.columns if "CLOSING" in c.upper()), None)
        if ts_col is None or close_col is None:
            log.warning(f"  {label}: unexpected columns {list(df.columns)[:8]}")
            return None

        df[ts_col]    = pd.to_datetime(df[ts_col])
        df[close_col] = pd.to_numeric(df[close_col], errors="coerce")
        df = df.dropna(subset=[ts_col, close_col]).sort_values(ts_col)
        prices = df.set_index(ts_col)[close_col]
        prices.index.name = "Date"
        prices.name = symbol

        log.info(f"  {label}: {len(prices)} rows from NSE")
        return prices if len(prices) >= 20 else None

    except Exception as e:
        log.warning(f"  {label}: parse error -- {e}")
        return None


# ---------------------------------------------------------------------------
# Nifty50 index history for beta / alpha
# ---------------------------------------------------------------------------

def _fetch_index_prices_nse():
    end_dt   = datetime.today()
    start_dt = end_dt - timedelta(days=3 * 365 + 30)

    params = {
        "indexType": "NIFTY 50",
        "from":      start_dt.strftime("%d-%m-%Y"),
        "to":        end_dt.strftime("%d-%m-%Y"),
    }
    data = _nse_get("/api/historical/indicesHistory", params=params)

    if not data:
        log.warning("  Nifty50 index: NSE returned no data")
        return None

    try:
        records = (
            data.get("data", {}).get("indexCloseOnlineRecords")
            or data.get("data", [])
        )
        if not records:
            log.warning("  Nifty50 index: empty records")
            return None

        df = pd.DataFrame(records)
        ts_col  = next((c for c in df.columns if "TIMESTAMP" in c.upper()), None)
        val_col = next((c for c in df.columns if "CLOSE" in c.upper()), None)
        if ts_col is None or val_col is None:
            log.warning(f"  Nifty50 index: unexpected columns {list(df.columns)[:8]}")
            return None

        df[ts_col]  = pd.to_datetime(df[ts_col])
        df[val_col] = pd.to_numeric(df[val_col], errors="coerce")
        df = df.dropna().sort_values(ts_col)
        idx = df.set_index(ts_col)[val_col]
        log.info(f"  Nifty50 index: {len(idx)} rows from NSE")
        return idx

    except Exception as e:
        log.warning(f"  Nifty50 index parse error: {e}")
        return None


# ---------------------------------------------------------------------------
# Fundamentals
# ---------------------------------------------------------------------------

def _fetch_fundamentals_nse(symbol):
    data = _nse_get("/api/quote-equity", params={"symbol": symbol})
    if not data:
        return {}
    try:
        md = data.get("metadata",   {}) or {}
        pi = data.get("priceInfo",  {}) or {}
        return {
            "pe":        round(float(md.get("pdSymbolPe", 0) or 0), 2),
            "pb":        0.0,
            "div_yield": 0.0,
            "mkt_cap":   md.get("pdFfMktCapCr"),
            "52w_high":  (pi.get("weekHighLow") or {}).get("max"),
            "52w_low":   (pi.get("weekHighLow") or {}).get("min"),
            "sector":    md.get("pdSectorPe", ""),
            "industry":  "",
        }
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------

def _compute_rsi(prices, period=14):
    if len(prices) < period + 1:
        return None
    delta = prices.diff()
    gain  = delta.clip(lower=0).rolling(period).mean()
    loss  = (-delta.clip(upper=0)).rolling(period).mean()
    rs    = gain / loss.replace(0, float("nan"))
    rsi   = 100 - (100 / (1 + rs))
    val   = rsi.iloc[-1]
    return round(float(val), 2) if not np.isnan(val) else None


def _compute_macd(prices):
    if len(prices) < 26:
        return None
    ema12  = prices.ewm(span=12, adjust=False).mean()
    ema26  = prices.ewm(span=26, adjust=False).mean()
    macd   = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    lm, ls = macd.iloc[-1], signal.iloc[-1]
    if np.isnan(lm) or np.isnan(ls):
        return None
    return "bullish" if lm > ls else "bearish"


def _compute_beta(stock_ret, idx_ret):
    aligned = pd.concat([stock_ret, idx_ret], axis=1).dropna()
    if len(aligned) < 30:
        return None
    cov = aligned.cov()
    var = aligned.iloc[:, 1].var()
    return round(float(cov.iloc[0, 1] / var), 3) if var else None


def _compute_cagr(prices, years=3):
    days = years * 252
    if len(prices) < days * 0.8:
        return None
    start = prices.iloc[-min(days, len(prices))]
    end   = prices.iloc[-1]
    if start <= 0:
        return None
    return round(float(((end / start) ** (1 / (min(len(prices), days) / 252)) - 1) * 100), 2)


def _compute_var(returns, confidence=0.95):
    if len(returns) < 30:
        return None
    return round(float(np.percentile(returns.dropna(), (1 - confidence) * 100)) * 100, 3)


def _compute_max_drawdown(prices):
    if len(prices) < 2:
        return None
    return round(float(((prices - prices.cummax()) / prices.cummax()).min()) * 100, 2)


def _compute_alpha(stock_ret, idx_ret, beta):
    if beta is None or len(stock_ret) < 30:
        return None
    aligned = pd.concat([stock_ret, idx_ret], axis=1).dropna()
    return round(
        (float(aligned.iloc[:, 0].mean()) * 252
         - beta * float(aligned.iloc[:, 1].mean()) * 252) * 100, 2
    )


# ---------------------------------------------------------------------------
# Universe helpers
# ---------------------------------------------------------------------------

def get_peer_tickers(tickers):
    sectors = {NIFTY50[t]["sector"] for t in tickers if t in NIFTY50}
    peers   = {t for t, info in NIFTY50.items() if info["sector"] in sectors}
    peers.update(tickers)
    result = [t for t in peers if t in NIFTY50]
    log.info(f"Holdings: {len(tickers)} | Sectors: {sectors} | With peers: {len(result)}")
    return result


# ---------------------------------------------------------------------------
# Main harvest
# ---------------------------------------------------------------------------

def harvest(tickers=None):
    run_id  = str(uuid.uuid4())[:8]
    started = datetime.utcnow()
    log.info(f"Harvest started -- run_id: {run_id}")
    log.info("Data source: NSE India official API (no rate limits)")

    universe = get_peer_tickers(tickers) if tickers else list(NIFTY50.keys())
    log.info(f"Universe: {len(universe)} stocks")

    log.info("Fetching Nifty50 index from NSE...")
    idx_prices = _fetch_index_prices_nse()
    idx_ret    = idx_prices.pct_change().dropna() if idx_prices is not None else None
    if idx_ret is None:
        log.warning("Could not fetch index -- beta/alpha will be None for all stocks")

    snapshot     = []
    fundamentals = {}
    success      = 0
    failed       = []

    for i, ticker in enumerate(universe, 1):
        meta = NIFTY50.get(ticker, {})
        log.info(f"[{i}/{len(universe)}] {ticker}")

        prices = _fetch_prices_nse(ticker, ticker)

        if prices is None or len(prices) < 20:
            log.warning(f"  {ticker}: insufficient data -- skipping")
            failed.append(ticker)
            time.sleep(THROTTLE_SECS)
            continue

        ret    = prices.pct_change().dropna()
        beta   = _compute_beta(ret, idx_ret)         if idx_ret is not None else None
        alpha  = _compute_alpha(ret, idx_ret, beta)  if idx_ret is not None else None
        sma50  = round(float(prices.rolling(50).mean().iloc[-1]),  2) if len(prices) >= 50  else None
        sma200 = round(float(prices.rolling(200).mean().iloc[-1]), 2) if len(prices) >= 200 else None
        price  = round(float(prices.iloc[-1]), 2)
        ret_1y = None
        if len(prices) >= 252:
            p1y    = prices.iloc[-252]
            ret_1y = round(float((price - p1y) / p1y) * 100, 2) if p1y > 0 else None

        snapshot.append({
            "ticker":       ticker,
            "name":         meta.get("name", ticker),
            "sector":       meta.get("sector", "Unknown"),
            "price":        price,
            "rsi":          _compute_rsi(prices),
            "macd":         _compute_macd(prices),
            "beta_3y":      beta,
            "alpha":        alpha,
            "cagr_3y":      _compute_cagr(prices, 3),
            "cagr_1y":      _compute_cagr(prices, 1),
            "ret_1y":       ret_1y,
            "var_95":       _compute_var(ret),
            "max_dd":       _compute_max_drawdown(prices),
            "sma50":        sma50,
            "sma200":       sma200,
            "above_sma50":  price > sma50  if sma50  else None,
            "above_sma200": price > sma200 if sma200 else None,
            "52w_high":     round(float(prices.rolling(252).max().iloc[-1]), 2) if len(prices) >= 252 else None,
            "52w_low":      round(float(prices.rolling(252).min().iloc[-1]), 2) if len(prices) >= 252 else None,
            "harvested_at": datetime.utcnow().isoformat(),
        })

        if ticker not in fundamentals:
            fundamentals[ticker] = _fetch_fundamentals_nse(ticker)

        success += 1
        time.sleep(THROTTLE_SECS)

    log.info("Writing encrypted data to GitHub db/...")
    gs.write("snapshot", {
        "generated_at": datetime.utcnow().isoformat(),
        "run_id":       run_id,
        "count":        len(snapshot),
        "stocks":       snapshot,
    }, f"harvest snapshot: {success} stocks")
    gs.write("fundamentals", {
        "generated_at": datetime.utcnow().isoformat(),
        "data":         fundamentals,
    })
    gs.write_metadata(success, [s["ticker"] for s in snapshot], run_id)

    duration = round((datetime.utcnow() - started).total_seconds(), 1)
    summary  = {
        "run_id":   run_id,
        "success":  success,
        "failed":   len(failed),
        "duration": duration,
        "status":   "ok" if not failed else "partial",
    }
    log.info(f"Harvest complete: {success} ok, {len(failed)} failed, {duration}s")
    return summary


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    log.info("=== Agent_Trader Harvest Runner ===")
    log.info("Data source: NSE India official API")

    conn = gs.test_connection()
    for k, v in conn.items():
        log.info(f"  {k}: {v}")

    if not all(
        "OK" in str(v) or "accessible" in str(v) or "valid" in str(v) or "found" in str(v)
        for v in conn.values()
    ):
        log.error("Connectivity check failed -- aborting")
        sys.exit(1)

    tickers = None
    trigger = gs.read("holdings_trigger")
    if trigger and "tickers" in trigger:
        tickers = trigger["tickers"]
        log.info(f"Targeted harvest -- {len(tickers)} holdings")
    else:
        log.info("No trigger -- full Nifty50 harvest")

    summary = harvest(tickers)
    log.info(f"Done: {summary}")

    if summary["success"] == 0:
        log.error("Zero stocks harvested -- marking as failed")
        sys.exit(1)
