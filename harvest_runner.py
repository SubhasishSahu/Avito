"""
Agent_Trader -- Harvest Runner
Fetches yfinance data for user holdings + Nifty50 sector peers.
Computes analytics: beta, RSI, MACD, CAGR, VaR, alpha.
Encrypts and writes to GitHub db/ folder.

Fixes applied:
  - curl_cffi TLS impersonation replaces requests session (Yahoo blocks raw requests)
  - Exactly 50 unique Nifty50 stocks (removed SHRIRAMFIN duplicate, fixed count)
  - shared_session created before index fetch
  - session passed to fundamentals fetch
  - zero-stock harvest exits with code 1
"""
import os
import sys
import logging
import warnings
import uuid
import time
from datetime import datetime

import pandas as pd
import numpy as np
import yfinance as yf

import github_store as gs

warnings.filterwarnings("ignore")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)
logging.getLogger("yfinance").setLevel(logging.ERROR)
logging.getLogger("urllib3").setLevel(logging.ERROR)


# -- Nifty50 Universe: exactly 50 unique stocks, sector-mapped --
NIFTY50 = {
    # Financial Services -- 10
    "HDFCBANK":   {"name": "HDFC Bank",              "sector": "Financial Services", "yf": "HDFCBANK.NS"},
    "ICICIBANK":  {"name": "ICICI Bank",             "sector": "Financial Services", "yf": "ICICIBANK.NS"},
    "KOTAKBANK":  {"name": "Kotak Mahindra Bank",    "sector": "Financial Services", "yf": "KOTAKBANK.NS"},
    "AXISBANK":   {"name": "Axis Bank",              "sector": "Financial Services", "yf": "AXISBANK.NS"},
    "SBIN":       {"name": "State Bank of India",    "sector": "Financial Services", "yf": "SBIN.NS"},
    "BAJFINANCE": {"name": "Bajaj Finance",          "sector": "Financial Services", "yf": "BAJFINANCE.NS"},
    "BAJAJFINSV": {"name": "Bajaj Finserv",          "sector": "Financial Services", "yf": "BAJAJFINSV.NS"},
    "HDFCLIFE":   {"name": "HDFC Life Insurance",    "sector": "Financial Services", "yf": "HDFCLIFE.NS"},
    "SBILIFE":    {"name": "SBI Life Insurance",     "sector": "Financial Services", "yf": "SBILIFE.NS"},
    "INDUSINDBK": {"name": "IndusInd Bank",          "sector": "Financial Services", "yf": "INDUSINDBK.NS"},
    # IT -- 6
    "TCS":        {"name": "Tata Consultancy",       "sector": "IT",                 "yf": "TCS.NS"},
    "INFY":       {"name": "Infosys",                "sector": "IT",                 "yf": "INFY.NS"},
    "HCLTECH":    {"name": "HCL Technologies",       "sector": "IT",                 "yf": "HCLTECH.NS"},
    "WIPRO":      {"name": "Wipro",                  "sector": "IT",                 "yf": "WIPRO.NS"},
    "TECHM":      {"name": "Tech Mahindra",          "sector": "IT",                 "yf": "TECHM.NS"},
    "LTIM":       {"name": "LTIMindtree",            "sector": "IT",                 "yf": "LTIM.NS"},
    # Oil & Gas -- 6
    "RELIANCE":   {"name": "Reliance Industries",    "sector": "Oil & Gas",          "yf": "RELIANCE.NS"},
    "ONGC":       {"name": "ONGC",                   "sector": "Oil & Gas",          "yf": "ONGC.NS"},
    "BPCL":       {"name": "BPCL",                   "sector": "Oil & Gas",          "yf": "BPCL.NS"},
    "COALINDIA":  {"name": "Coal India",             "sector": "Oil & Gas",          "yf": "COALINDIA.NS"},
    "POWERGRID":  {"name": "Power Grid Corp",        "sector": "Oil & Gas",          "yf": "POWERGRID.NS"},
    "NTPC":       {"name": "NTPC",                   "sector": "Oil & Gas",          "yf": "NTPC.NS"},
    # Consumer -- 8
    "HINDUNILVR": {"name": "Hindustan Unilever",     "sector": "Consumer",           "yf": "HINDUNILVR.NS"},
    "ITC":        {"name": "ITC",                    "sector": "Consumer",           "yf": "ITC.NS"},
    "NESTLEIND":  {"name": "Nestle India",           "sector": "Consumer",           "yf": "NESTLEIND.NS"},
    "BRITANNIA":  {"name": "Britannia Industries",   "sector": "Consumer",           "yf": "BRITANNIA.NS"},
    "TATACONSUM": {"name": "Tata Consumer Products", "sector": "Consumer",           "yf": "TATACONSUM.NS"},
    "TITAN":      {"name": "Titan Company",          "sector": "Consumer",           "yf": "TITAN.NS"},
    "ASIANPAINT": {"name": "Asian Paints",           "sector": "Consumer",           "yf": "ASIANPAINT.NS"},
    "ZOMATO":     {"name": "Zomato",                 "sector": "Consumer",           "yf": "ZOMATO.NS"},
    # Auto -- 6
    "MARUTI":     {"name": "Maruti Suzuki",          "sector": "Auto",               "yf": "MARUTI.NS"},
    "BAJAJ-AUTO": {"name": "Bajaj Auto",             "sector": "Auto",               "yf": "BAJAJ-AUTO.NS"},
    "HEROMOTOCO": {"name": "Hero MotoCorp",          "sector": "Auto",               "yf": "HEROMOTOCO.NS"},
    "EICHERMOT":  {"name": "Eicher Motors",          "sector": "Auto",               "yf": "EICHERMOT.NS"},
    "M&M":        {"name": "Mahindra & Mahindra",    "sector": "Auto",               "yf": "M&M.NS"},
    "TATAMOTORS": {"name": "Tata Motors",            "sector": "Auto",               "yf": "TATAMOTORS.NS"},
    # Pharma -- 5
    "SUNPHARMA":  {"name": "Sun Pharmaceutical",     "sector": "Pharma",             "yf": "SUNPHARMA.NS"},
    "DRREDDY":    {"name": "Dr Reddys Labs",         "sector": "Pharma",             "yf": "DRREDDY.NS"},
    "CIPLA":      {"name": "Cipla",                  "sector": "Pharma",             "yf": "CIPLA.NS"},
    "DIVISLAB":   {"name": "Divis Laboratories",     "sector": "Pharma",             "yf": "DIVISLAB.NS"},
    "APOLLOHOSP": {"name": "Apollo Hospitals",       "sector": "Pharma",             "yf": "APOLLOHOSP.NS"},
    # Metals -- 4
    "TATASTEEL":  {"name": "Tata Steel",             "sector": "Metals",             "yf": "TATASTEEL.NS"},
    "JSWSTEEL":   {"name": "JSW Steel",              "sector": "Metals",             "yf": "JSWSTEEL.NS"},
    "HINDALCO":   {"name": "Hindalco Industries",    "sector": "Metals",             "yf": "HINDALCO.NS"},
    "ADANIENT":   {"name": "Adani Enterprises",      "sector": "Metals",             "yf": "ADANIENT.NS"},
    # Infrastructure -- 2
    "LT":         {"name": "Larsen and Toubro",      "sector": "Infrastructure",     "yf": "LT.NS"},
    "ADANIPORTS": {"name": "Adani Ports",            "sector": "Infrastructure",     "yf": "ADANIPORTS.NS"},
    # Cement -- 2
    "ULTRACEMCO": {"name": "UltraTech Cement",       "sector": "Cement",             "yf": "ULTRACEMCO.NS"},
    "GRASIM":     {"name": "Grasim Industries",      "sector": "Cement",             "yf": "GRASIM.NS"},
    # Telecom -- 1
    "BHARTIARTL": {"name": "Bharti Airtel",          "sector": "Telecom",            "yf": "BHARTIARTL.NS"},
}

assert len(NIFTY50) == 50, f"NIFTY50 has {len(NIFTY50)} stocks -- expected exactly 50"

NIFTY50_INDEX_YF = "^NSEI"
PRICE_PERIOD     = "3y"
THROTTLE_SECS    = 1.0


# -- Analytics --

def _compute_rsi(prices: pd.Series, period: int = 14):
    if len(prices) < period + 1:
        return None
    delta = prices.diff()
    gain  = delta.clip(lower=0).rolling(period).mean()
    loss  = (-delta.clip(upper=0)).rolling(period).mean()
    rs    = gain / loss.replace(0, float("nan"))
    rsi   = 100 - (100 / (1 + rs))
    val   = rsi.iloc[-1]
    return round(float(val), 2) if not np.isnan(val) else None


def _compute_macd(prices: pd.Series):
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


def _compute_beta(stock_ret: pd.Series, idx_ret: pd.Series):
    aligned = pd.concat([stock_ret, idx_ret], axis=1).dropna()
    if len(aligned) < 30:
        return None
    cov = aligned.cov()
    var = aligned.iloc[:, 1].var()
    return round(float(cov.iloc[0, 1] / var), 3) if var else None


def _compute_cagr(prices: pd.Series, years: int = 3):
    days = years * 252
    if len(prices) < days * 0.8:
        return None
    start = prices.iloc[-min(days, len(prices))]
    end   = prices.iloc[-1]
    if start <= 0:
        return None
    return round(float(((end / start) ** (1 / (min(len(prices), days) / 252)) - 1) * 100), 2)


def _compute_var(returns: pd.Series, confidence: float = 0.95):
    if len(returns) < 30:
        return None
    return round(float(np.percentile(returns.dropna(), (1 - confidence) * 100)) * 100, 3)


def _compute_max_drawdown(prices: pd.Series):
    if len(prices) < 2:
        return None
    return round(float(((prices - prices.cummax()) / prices.cummax()).min()) * 100, 2)


def _compute_alpha(stock_ret: pd.Series, idx_ret: pd.Series, beta):
    if beta is None or len(stock_ret) < 30:
        return None
    aligned = pd.concat([stock_ret, idx_ret], axis=1).dropna()
    return round((float(aligned.iloc[:, 0].mean()) * 252 - beta * float(aligned.iloc[:, 1].mean()) * 252) * 100, 2)


# -- Session: curl_cffi TLS impersonation --

def _make_session():
    """
    curl_cffi impersonates Chrome at TLS level -- bypasses Yahoo Finance
    JA3 fingerprinting that blocks standard Python requests on GitHub Actions.
    yfinance detects curl_cffi sessions automatically and uses them correctly.
    Falls back to requests.Session if curl_cffi not installed.
    """
    try:
        from curl_cffi import requests as cffi_requests
        session = cffi_requests.Session(impersonate="chrome")
        log.info("Session: curl_cffi Chrome impersonation active")
        return session
    except ImportError:
        import requests as req
        session = req.Session()
        session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://finance.yahoo.com",
        })
        log.warning("Session: curl_cffi not found, using requests (may be blocked)")
        return session


def _fetch_prices(yf_ticker: str, label: str, session):
    """
    Fetch close prices via Ticker.history().
    Fallback: .NS 3y -> .NS max -> .BO 3y
    """
    for attempt, (t, period) in enumerate([
        (yf_ticker,                       PRICE_PERIOD),
        (yf_ticker,                       "max"),
        (yf_ticker.replace(".NS", ".BO"), PRICE_PERIOD),
    ], 1):
        try:
            hist = yf.Ticker(t, session=session).history(
                period=period, auto_adjust=True, actions=False, timeout=30
            )
            if hist is not None and not hist.empty and len(hist) > 10:
                close = hist["Close"].squeeze()
                log.info(f"  {label}: {len(close)} rows (attempt {attempt})")
                return close
        except Exception as e:
            log.debug(f"  {label} attempt {attempt}: {e}")
        time.sleep(1.0)
    log.warning(f"  {label}: no data after 3 attempts")
    return None


def _fetch_fundamentals(yf_ticker: str, session):
    try:
        info = yf.Ticker(yf_ticker, session=session).info or {}
        return {
            "pe":        round(info.get("trailingPE",    0) or 0, 2),
            "pb":        round(info.get("priceToBook",   0) or 0, 2),
            "div_yield": round((info.get("dividendYield", 0) or 0) * 100, 2),
            "mkt_cap":   info.get("marketCap"),
            "52w_high":  info.get("fiftyTwoWeekHigh"),
            "52w_low":   info.get("fiftyTwoWeekLow"),
            "sector":    info.get("sector",   ""),
            "industry":  info.get("industry", ""),
        }
    except Exception:
        return {}


# -- Core --

def get_peer_tickers(tickers: list) -> list:
    sectors = {NIFTY50[t]["sector"] for t in tickers if t in NIFTY50}
    peers   = {t for t, info in NIFTY50.items() if info["sector"] in sectors}
    peers.update(tickers)
    result = [t for t in peers if t in NIFTY50]
    log.info(f"Holdings: {len(tickers)} | Sectors: {sectors} | With peers: {len(result)}")
    return result


def harvest(tickers: list = None) -> dict:
    run_id  = str(uuid.uuid4())[:8]
    started = datetime.utcnow()
    log.info(f"Harvest started -- run_id: {run_id}")

    universe = get_peer_tickers(tickers) if tickers else list(NIFTY50.keys())
    log.info(f"Universe: {len(universe)} stocks")

    # Create session FIRST -- before any yfinance call
    session = _make_session()

    # Nifty50 index for beta/alpha
    log.info("Fetching Nifty50 index...")
    idx_ret = None
    try:
        idx_hist = yf.Ticker(NIFTY50_INDEX_YF, session=session).history(
            period=PRICE_PERIOD, auto_adjust=True, actions=False, timeout=30
        )
        idx_ret = idx_hist["Close"].squeeze().pct_change().dropna()
        log.info(f"  Index: {len(idx_ret)+1} rows")
    except Exception as e:
        log.warning(f"  Index fetch failed: {e}")

    snapshot     = []
    fundamentals = {}
    success      = 0
    failed       = []

    for i, ticker in enumerate(universe, 1):
        meta = NIFTY50.get(ticker, {})
        yf_t = meta.get("yf", f"{ticker}.NS")
        log.info(f"[{i}/{len(universe)}] {ticker}")

        prices = _fetch_prices(yf_t, ticker, session)

        if prices is None or len(prices) < 20:
            failed.append(ticker)
            time.sleep(THROTTLE_SECS)
            continue

        ret     = prices.pct_change().dropna()
        beta    = _compute_beta(ret, idx_ret)            if idx_ret is not None else None
        alpha   = _compute_alpha(ret, idx_ret, beta)     if idx_ret is not None else None
        sma50   = round(float(prices.rolling(50).mean().iloc[-1]),  2) if len(prices) >= 50  else None
        sma200  = round(float(prices.rolling(200).mean().iloc[-1]), 2) if len(prices) >= 200 else None
        price   = round(float(prices.iloc[-1]), 2)
        ret_1y  = None
        if len(prices) >= 252:
            p1y = prices.iloc[-252]
            ret_1y = round(float((price - p1y) / p1y) * 100, 2) if p1y > 0 else None

        snapshot.append({
            "ticker":       ticker,
            "name":         meta.get("name", ticker),
            "sector":       meta.get("sector", "Unknown"),
            "yf_ticker":    yf_t,
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
            fundamentals[ticker] = _fetch_fundamentals(yf_t, session)

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


# -- Entry point --

if __name__ == "__main__":
    log.info("=== Agent_Trader Harvest Runner ===")

    conn = gs.test_connection()
    for k, v in conn.items():
        log.info(f"  {k}: {v}")

    if not all("OK" in str(v) or "accessible" in str(v) or "valid" in str(v) or "found" in str(v) for v in conn.values()):
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
