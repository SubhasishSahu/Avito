"""
Agent_Trader -- Harvest Runner
Data source strategy (waterfall, first success wins per ticker):
  1. Stooq CSV  -- stooq.com serves .NS historical data, no IP blocking,
                   no auth, no cookies. Works from any datacenter IP.
  2. yfinance   -- fallback; works when Yahoo isn't rate-limiting
                   (reliable at off-peak hours / midnight IST).

Analytics: RSI, MACD, Beta, CAGR, VaR, Alpha, Max Drawdown (all local).

Fix history:
  BUG_1-9  yfinance/curl_cffi stack issues
  BUG_10   Yahoo rate-limits GitHub Actions IPs -> added NSE as primary
  BUG_11   NSE also blocks datacenter IPs during market hours
           -> switched to Stooq (primary) + yfinance (fallback)
           Stooq is a Polish financial aggregator that mirrors global
           exchange data including NSE (.NS suffix) with no IP filtering.
"""
import os
import sys
import logging
import warnings
import uuid
import time
import io
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

# Silence noisy loggers
for _lib in ("yfinance", "urllib3", "peewee"):
    logging.getLogger(_lib).setLevel(logging.ERROR)


# ---------------------------------------------------------------------------
# Nifty50 Universe: exactly 50 unique stocks, sector-mapped
# stooq_sym: lowercase symbol for Stooq API  (e.g. "hdfcbank.ns")
# yf_sym:    NSE symbol for yfinance fallback  (e.g. "HDFCBANK.NS")
# ---------------------------------------------------------------------------
NIFTY50 = {
    # Financial Services -- 10
    "HDFCBANK":   {"name": "HDFC Bank",              "sector": "Financial Services", "stooq": "hdfcbank.ns",   "yf": "HDFCBANK.NS"},
    "ICICIBANK":  {"name": "ICICI Bank",             "sector": "Financial Services", "stooq": "icicibank.ns",  "yf": "ICICIBANK.NS"},
    "KOTAKBANK":  {"name": "Kotak Mahindra Bank",    "sector": "Financial Services", "stooq": "kotakbank.ns",  "yf": "KOTAKBANK.NS"},
    "AXISBANK":   {"name": "Axis Bank",              "sector": "Financial Services", "stooq": "axisbank.ns",   "yf": "AXISBANK.NS"},
    "SBIN":       {"name": "State Bank of India",    "sector": "Financial Services", "stooq": "sbin.ns",       "yf": "SBIN.NS"},
    "BAJFINANCE": {"name": "Bajaj Finance",          "sector": "Financial Services", "stooq": "bajfinance.ns", "yf": "BAJFINANCE.NS"},
    "BAJAJFINSV": {"name": "Bajaj Finserv",          "sector": "Financial Services", "stooq": "bajajfinsv.ns", "yf": "BAJAJFINSV.NS"},
    "HDFCLIFE":   {"name": "HDFC Life Insurance",    "sector": "Financial Services", "stooq": "hdfclife.ns",   "yf": "HDFCLIFE.NS"},
    "SBILIFE":    {"name": "SBI Life Insurance",     "sector": "Financial Services", "stooq": "sbilife.ns",    "yf": "SBILIFE.NS"},
    "INDUSINDBK": {"name": "IndusInd Bank",          "sector": "Financial Services", "stooq": "indusindbk.ns", "yf": "INDUSINDBK.NS"},
    # IT -- 6
    "TCS":        {"name": "Tata Consultancy",       "sector": "IT",                 "stooq": "tcs.ns",        "yf": "TCS.NS"},
    "INFY":       {"name": "Infosys",                "sector": "IT",                 "stooq": "infy.ns",       "yf": "INFY.NS"},
    "HCLTECH":    {"name": "HCL Technologies",       "sector": "IT",                 "stooq": "hcltech.ns",    "yf": "HCLTECH.NS"},
    "WIPRO":      {"name": "Wipro",                  "sector": "IT",                 "stooq": "wipro.ns",      "yf": "WIPRO.NS"},
    "TECHM":      {"name": "Tech Mahindra",          "sector": "IT",                 "stooq": "techm.ns",      "yf": "TECHM.NS"},
    "LTIM":       {"name": "LTIMindtree",            "sector": "IT",                 "stooq": "ltim.ns",       "yf": "LTIM.NS"},
    # Oil & Gas -- 6
    "RELIANCE":   {"name": "Reliance Industries",    "sector": "Oil & Gas",          "stooq": "reliance.ns",   "yf": "RELIANCE.NS"},
    "ONGC":       {"name": "ONGC",                   "sector": "Oil & Gas",          "stooq": "ongc.ns",       "yf": "ONGC.NS"},
    "BPCL":       {"name": "BPCL",                   "sector": "Oil & Gas",          "stooq": "bpcl.ns",       "yf": "BPCL.NS"},
    "COALINDIA":  {"name": "Coal India",             "sector": "Oil & Gas",          "stooq": "coalindia.ns",  "yf": "COALINDIA.NS"},
    "POWERGRID":  {"name": "Power Grid Corp",        "sector": "Oil & Gas",          "stooq": "powergrid.ns",  "yf": "POWERGRID.NS"},
    "NTPC":       {"name": "NTPC",                   "sector": "Oil & Gas",          "stooq": "ntpc.ns",       "yf": "NTPC.NS"},
    # Consumer -- 8
    "HINDUNILVR": {"name": "Hindustan Unilever",     "sector": "Consumer",           "stooq": "hindunilvr.ns", "yf": "HINDUNILVR.NS"},
    "ITC":        {"name": "ITC",                    "sector": "Consumer",           "stooq": "itc.ns",        "yf": "ITC.NS"},
    "NESTLEIND":  {"name": "Nestle India",           "sector": "Consumer",           "stooq": "nestleind.ns",  "yf": "NESTLEIND.NS"},
    "BRITANNIA":  {"name": "Britannia Industries",   "sector": "Consumer",           "stooq": "britannia.ns",  "yf": "BRITANNIA.NS"},
    "TATACONSUM": {"name": "Tata Consumer Products", "sector": "Consumer",           "stooq": "tataconsum.ns", "yf": "TATACONSUM.NS"},
    "TITAN":      {"name": "Titan Company",          "sector": "Consumer",           "stooq": "titan.ns",      "yf": "TITAN.NS"},
    "ASIANPAINT": {"name": "Asian Paints",           "sector": "Consumer",           "stooq": "asianpaint.ns", "yf": "ASIANPAINT.NS"},
    "ZOMATO":     {"name": "Zomato",                 "sector": "Consumer",           "stooq": "zomato.ns",     "yf": "ZOMATO.NS"},
    # Auto -- 6
    "MARUTI":     {"name": "Maruti Suzuki",          "sector": "Auto",               "stooq": "maruti.ns",     "yf": "MARUTI.NS"},
    "BAJAJ-AUTO": {"name": "Bajaj Auto",             "sector": "Auto",               "stooq": "bajaj-auto.ns", "yf": "BAJAJ-AUTO.NS"},
    "HEROMOTOCO": {"name": "Hero MotoCorp",          "sector": "Auto",               "stooq": "heromotoco.ns", "yf": "HEROMOTOCO.NS"},
    "EICHERMOT":  {"name": "Eicher Motors",          "sector": "Auto",               "stooq": "eichermot.ns",  "yf": "EICHERMOT.NS"},
    "M&M":        {"name": "Mahindra & Mahindra",    "sector": "Auto",               "stooq": "m&m.ns",        "yf": "M&M.NS"},
    "TATAMOTORS": {"name": "Tata Motors",            "sector": "Auto",               "stooq": "tatamotors.ns", "yf": "TATAMOTORS.NS"},
    # Pharma -- 5
    "SUNPHARMA":  {"name": "Sun Pharmaceutical",     "sector": "Pharma",             "stooq": "sunpharma.ns",  "yf": "SUNPHARMA.NS"},
    "DRREDDY":    {"name": "Dr Reddys Labs",         "sector": "Pharma",             "stooq": "drreddy.ns",    "yf": "DRREDDY.NS"},
    "CIPLA":      {"name": "Cipla",                  "sector": "Pharma",             "stooq": "cipla.ns",      "yf": "CIPLA.NS"},
    "DIVISLAB":   {"name": "Divis Laboratories",     "sector": "Pharma",             "stooq": "divislab.ns",   "yf": "DIVISLAB.NS"},
    "APOLLOHOSP": {"name": "Apollo Hospitals",       "sector": "Pharma",             "stooq": "apollohosp.ns", "yf": "APOLLOHOSP.NS"},
    # Metals -- 4
    "TATASTEEL":  {"name": "Tata Steel",             "sector": "Metals",             "stooq": "tatasteel.ns",  "yf": "TATASTEEL.NS"},
    "JSWSTEEL":   {"name": "JSW Steel",              "sector": "Metals",             "stooq": "jswsteel.ns",   "yf": "JSWSTEEL.NS"},
    "HINDALCO":   {"name": "Hindalco Industries",    "sector": "Metals",             "stooq": "hindalco.ns",   "yf": "HINDALCO.NS"},
    "ADANIENT":   {"name": "Adani Enterprises",      "sector": "Metals",             "stooq": "adanient.ns",   "yf": "ADANIENT.NS"},
    # Infrastructure -- 2
    "LT":         {"name": "Larsen and Toubro",      "sector": "Infrastructure",     "stooq": "lt.ns",         "yf": "LT.NS"},
    "ADANIPORTS": {"name": "Adani Ports",            "sector": "Infrastructure",     "stooq": "adaniports.ns", "yf": "ADANIPORTS.NS"},
    # Cement -- 2
    "ULTRACEMCO": {"name": "UltraTech Cement",       "sector": "Cement",             "stooq": "ultracemco.ns", "yf": "ULTRACEMCO.NS"},
    "GRASIM":     {"name": "Grasim Industries",      "sector": "Cement",             "stooq": "grasim.ns",     "yf": "GRASIM.NS"},
    # Telecom -- 1
    "BHARTIARTL": {"name": "Bharti Airtel",          "sector": "Telecom",            "stooq": "bhartiartl.ns", "yf": "BHARTIARTL.NS"},
}

assert len(NIFTY50) == 50, f"NIFTY50 has {len(NIFTY50)} stocks -- expected exactly 50"

THROTTLE_SECS = 0.5
PRICE_PERIOD  = "3y"   # for yfinance fallback


# ---------------------------------------------------------------------------
# Source 1: Stooq CSV
# Simple GET, returns CSV, no auth, no cookies, no IP blocking.
# URL: https://stooq.com/q/d/l/?s=SYMBOL&i=d  (d = daily)
# ---------------------------------------------------------------------------

_STOOQ_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/121.0.0.0 Safari/537.36"
    )
}

_stooq_session = None


def _get_stooq_session():
    global _stooq_session
    if _stooq_session is None:
        _stooq_session = requests.Session()
        _stooq_session.headers.update(_STOOQ_HEADERS)
    return _stooq_session


def _fetch_prices_stooq(stooq_sym: str, label: str):
    """
    Fetch ~3y of daily close prices from Stooq.
    Returns pd.Series or None.
    """
    s = _get_stooq_session()
    end_dt   = datetime.today()
    start_dt = end_dt - timedelta(days=3 * 365 + 60)

    url = "https://stooq.com/q/d/l/"
    params = {
        "s":  stooq_sym,
        "d1": start_dt.strftime("%Y%m%d"),
        "d2": end_dt.strftime("%Y%m%d"),
        "i":  "d",
    }

    for attempt in range(1, 4):
        try:
            r = s.get(url, params=params, timeout=20)
            r.raise_for_status()

            text = r.text.strip()
            # Stooq returns "No data" or similar for unknown symbols
            if len(text) < 50 or "No data" in text or "<html" in text.lower():
                log.debug(f"  {label} Stooq: no usable data in response")
                return None

            df = pd.read_csv(io.StringIO(text), parse_dates=["Date"])
            if df.empty or "Close" not in df.columns:
                return None

            df = df.dropna(subset=["Date", "Close"]).sort_values("Date")
            prices = df.set_index("Date")["Close"].astype(float)
            prices.index.name = "Date"

            if len(prices) >= 20:
                log.info(f"  {label}: {len(prices)} rows via Stooq ✓")
                return prices

        except Exception as e:
            log.debug(f"  {label} Stooq attempt {attempt}: {e}")
            if attempt < 3:
                time.sleep(2 ** attempt)

    return None


def _fetch_index_stooq():
    """Fetch Nifty50 index history from Stooq (^nsei)."""
    return _fetch_prices_stooq("^nsei", "Nifty50-index")


# ---------------------------------------------------------------------------
# Source 2: yfinance fallback
# Works reliably at off-peak hours; kept as fallback.
# ---------------------------------------------------------------------------

def _fetch_prices_yf(yf_ticker: str, label: str):
    try:
        import yfinance as yf
        hist = yf.Ticker(yf_ticker).history(
            period=PRICE_PERIOD, auto_adjust=True, actions=False, timeout=25
        )
        if hist is not None and not hist.empty and len(hist) > 10:
            prices = hist["Close"].squeeze()
            log.info(f"  {label}: {len(prices)} rows via yfinance ✓")
            return prices
    except Exception as e:
        log.debug(f"  {label} yfinance: {e}")
    return None


def _fetch_index_yf():
    """Fetch Nifty50 index via yfinance fallback."""
    try:
        import yfinance as yf
        hist = yf.Ticker("^NSEI").history(
            period=PRICE_PERIOD, auto_adjust=True, actions=False, timeout=25
        )
        if hist is not None and not hist.empty:
            return hist["Close"].squeeze()
    except Exception as e:
        log.debug(f"  Nifty50-index yfinance: {e}")
    return None


# ---------------------------------------------------------------------------
# Unified fetch with waterfall: Stooq -> yfinance
# ---------------------------------------------------------------------------

def _fetch_prices(ticker: str, meta: dict) -> pd.Series | None:
    stooq_sym = meta.get("stooq", f"{ticker.lower()}.ns")
    yf_sym    = meta.get("yf",    f"{ticker}.NS")

    prices = _fetch_prices_stooq(stooq_sym, ticker)
    if prices is not None:
        return prices

    log.debug(f"  {ticker}: Stooq failed, trying yfinance")
    prices = _fetch_prices_yf(yf_sym, ticker)
    return prices


def _fetch_index() -> pd.Series | None:
    idx = _fetch_index_stooq()
    if idx is not None:
        return idx
    log.debug("  Index: Stooq failed, trying yfinance")
    return _fetch_index_yf()


# ---------------------------------------------------------------------------
# Analytics (unchanged)
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
    log.info("Data source: Stooq (primary) -> yfinance (fallback)")

    universe = get_peer_tickers(tickers) if tickers else list(NIFTY50.keys())
    log.info(f"Universe: {len(universe)} stocks")

    log.info("Fetching Nifty50 index...")
    idx_prices = _fetch_index()
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

        prices = _fetch_prices(ticker, meta)

        if prices is None or len(prices) < 20:
            log.warning(f"  {ticker}: no data from any source -- skipping")
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

        # Fundamentals: try yfinance (more detailed); graceful on failure
        if ticker not in fundamentals:
            fundamentals[ticker] = _fetch_fundamentals(meta.get("yf", f"{ticker}.NS"))

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


def _fetch_fundamentals(yf_sym: str) -> dict:
    """PE, PB etc. from yfinance -- best-effort, returns {} on any error."""
    try:
        import yfinance as yf
        info = yf.Ticker(yf_sym).info or {}
        return {
            "pe":        round(float(info.get("trailingPE",    0) or 0), 2),
            "pb":        round(float(info.get("priceToBook",   0) or 0), 2),
            "div_yield": round((info.get("dividendYield", 0) or 0) * 100, 2),
            "mkt_cap":   info.get("marketCap"),
            "52w_high":  info.get("fiftyTwoWeekHigh"),
            "52w_low":   info.get("fiftyTwoWeekLow"),
        }
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    log.info("=== Agent_Trader Harvest Runner ===")
    log.info("Data: Stooq (primary) -> yfinance (fallback)")

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
