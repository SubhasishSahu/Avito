“””
Agent_Trader — Harvest Runner
Fetches yfinance data for user’s holdings + sector peers.
Computes analytics — beta, RSI, MACD, CAGR, VaR.
Encrypts everything and writes to GitHub db/ folder.

Triggered by:

- GitHub Actions cron (Mon-Fri 07:00 IST)
- GitHub Actions push to db/holdings_trigger.enc
- GitHub Actions workflow_dispatch (manual)
- Google Colab cell (ad-hoc / debug)

SECURITY: Never prints raw data or secrets to stdout.
GitHub Actions logs are public for public repos.
“””
import os
import sys
import json
import logging
import warnings
import uuid
from datetime import datetime, timedelta

import pandas as pd
import numpy as np
import yfinance as yf

import github_store as gs

warnings.filterwarnings(“ignore”)
logging.basicConfig(
level=logging.INFO,
format=”%(asctime)s [%(levelname)s] %(message)s”,
datefmt=”%H:%M:%S”,
)
log = logging.getLogger(**name**)

# Suppress yfinance internal noise

logging.getLogger(“yfinance”).setLevel(logging.ERROR)
logging.getLogger(“urllib3”).setLevel(logging.ERROR)

# ── Nifty50 Universe + Sector Map ──────────────────────────────────────────────

NIFTY50 = {
# Financial Services
“HDFCBANK”:    {“name”: “HDFC Bank”,              “sector”: “Financial Services”, “yf”: “HDFCBANK.NS”},
“ICICIBANK”:   {“name”: “ICICI Bank”,             “sector”: “Financial Services”, “yf”: “ICICIBANK.NS”},
“KOTAKBANK”:   {“name”: “Kotak Mahindra Bank”,    “sector”: “Financial Services”, “yf”: “KOTAKBANK.NS”},
“AXISBANK”:    {“name”: “Axis Bank”,              “sector”: “Financial Services”, “yf”: “AXISBANK.NS”},
“SBIN”:        {“name”: “State Bank of India”,    “sector”: “Financial Services”, “yf”: “SBIN.NS”},
“BAJFINANCE”:  {“name”: “Bajaj Finance”,          “sector”: “Financial Services”, “yf”: “BAJFINANCE.NS”},
“BAJAJFINSV”:  {“name”: “Bajaj Finserv”,          “sector”: “Financial Services”, “yf”: “BAJAJFINSV.NS”},
“HDFCLIFE”:    {“name”: “HDFC Life Insurance”,    “sector”: “Financial Services”, “yf”: “HDFCLIFE.NS”},
“SBILIFE”:     {“name”: “SBI Life Insurance”,     “sector”: “Financial Services”, “yf”: “SBILIFE.NS”},
“SHRIRAMFIN”:  {“name”: “Shriram Finance”,        “sector”: “Financial Services”, “yf”: “SHRIRAMFIN.NS”},
# IT
“TCS”:         {“name”: “Tata Consultancy”,       “sector”: “IT”,                 “yf”: “TCS.NS”},
“INFY”:        {“name”: “Infosys”,                “sector”: “IT”,                 “yf”: “INFY.NS”},
“HCLTECH”:     {“name”: “HCL Technologies”,       “sector”: “IT”,                 “yf”: “HCLTECH.NS”},
“WIPRO”:       {“name”: “Wipro”,                  “sector”: “IT”,                 “yf”: “WIPRO.NS”},
“TECHM”:       {“name”: “Tech Mahindra”,          “sector”: “IT”,                 “yf”: “TECHM.NS”},
# Oil & Gas / Energy
“RELIANCE”:    {“name”: “Reliance Industries”,    “sector”: “Oil & Gas”,          “yf”: “RELIANCE.NS”},
“ONGC”:        {“name”: “ONGC”,                   “sector”: “Oil & Gas”,          “yf”: “ONGC.NS”},
“BPCL”:        {“name”: “BPCL”,                   “sector”: “Oil & Gas”,          “yf”: “BPCL.NS”},
“COALINDIA”:   {“name”: “Coal India”,             “sector”: “Oil & Gas”,          “yf”: “COALINDIA.NS”},
“POWERGRID”:   {“name”: “Power Grid Corp”,        “sector”: “Oil & Gas”,          “yf”: “POWERGRID.NS”},
“NTPC”:        {“name”: “NTPC”,                   “sector”: “Oil & Gas”,          “yf”: “NTPC.NS”},
# Consumer
“HINDUNILVR”:  {“name”: “Hindustan Unilever”,     “sector”: “Consumer”,           “yf”: “HINDUNILVR.NS”},
“ITC”:         {“name”: “ITC”,                    “sector”: “Consumer”,           “yf”: “ITC.NS”},
“NESTLEIND”:   {“name”: “Nestle India”,           “sector”: “Consumer”,           “yf”: “NESTLEIND.NS”},
“BRITANNIA”:   {“name”: “Britannia Industries”,   “sector”: “Consumer”,           “yf”: “BRITANNIA.NS”},
“TATACONSUM”:  {“name”: “Tata Consumer Products”, “sector”: “Consumer”,           “yf”: “TATACONSUM.NS”},
“TITAN”:       {“name”: “Titan Company”,          “sector”: “Consumer”,           “yf”: “TITAN.NS”},
# Auto
“MARUTI”:      {“name”: “Maruti Suzuki”,          “sector”: “Auto”,               “yf”: “MARUTI.NS”},
“BAJAJ-AUTO”:  {“name”: “Bajaj Auto”,             “sector”: “Auto”,               “yf”: “BAJAJ-AUTO.NS”},
“HEROMOTOCO”:  {“name”: “Hero MotoCorp”,          “sector”: “Auto”,               “yf”: “HEROMOTOCO.NS”},
“EICHERMOT”:   {“name”: “Eicher Motors”,          “sector”: “Auto”,               “yf”: “EICHERMOT.NS”},
“M&M”:         {“name”: “Mahindra & Mahindra”,    “sector”: “Auto”,               “yf”: “M&M.NS”},
“TATAMOTORS”:  {“name”: “Tata Motors”,            “sector”: “Auto”,               “yf”: “TATAMOTORS.NS”},
# Pharma / Healthcare
“SUNPHARMA”:   {“name”: “Sun Pharmaceutical”,     “sector”: “Pharma”,             “yf”: “SUNPHARMA.NS”},
“DRREDDY”:     {“name”: “Dr Reddy’s Labs”,        “sector”: “Pharma”,             “yf”: “DRREDDY.NS”},
“CIPLA”:       {“name”: “Cipla”,                  “sector”: “Pharma”,             “yf”: “CIPLA.NS”},
“DIVISLAB”:    {“name”: “Divi’s Laboratories”,    “sector”: “Pharma”,             “yf”: “DIVISLAB.NS”},
“APOLLOHOSP”:  {“name”: “Apollo Hospitals”,       “sector”: “Pharma”,             “yf”: “APOLLOHOSP.NS”},
# Metals
“TATASTEEL”:   {“name”: “Tata Steel”,             “sector”: “Metals”,             “yf”: “TATASTEEL.NS”},
“JSWSTEEL”:    {“name”: “JSW Steel”,              “sector”: “Metals”,             “yf”: “JSWSTEEL.NS”},
“HINDALCO”:    {“name”: “Hindalco Industries”,    “sector”: “Metals”,             “yf”: “HINDALCO.NS”},
“ADANIENT”:    {“name”: “Adani Enterprises”,      “sector”: “Metals”,             “yf”: “ADANIENT.NS”},
# Infra / Cement
“LT”:          {“name”: “Larsen & Toubro”,        “sector”: “Infrastructure”,     “yf”: “LT.NS”},
“ADANIPORTS”:  {“name”: “Adani Ports”,            “sector”: “Infrastructure”,     “yf”: “ADANIPORTS.NS”},
“ULTRACEMCO”:  {“name”: “UltraTech Cement”,       “sector”: “Cement”,             “yf”: “ULTRACEMCO.NS”},
“GRASIM”:      {“name”: “Grasim Industries”,      “sector”: “Cement”,             “yf”: “GRASIM.NS”},
# Telecom
“BHARTIARTL”:  {“name”: “Bharti Airtel”,          “sector”: “Telecom”,            “yf”: “BHARTIARTL.NS”},
# Diversified
“WIPRO”:       {“name”: “Wipro”,                  “sector”: “IT”,                 “yf”: “WIPRO.NS”},
“INDUSINDBK”:  {“name”: “IndusInd Bank”,          “sector”: “Financial Services”, “yf”: “INDUSINDBK.NS”},
“ASIANPAINT”:  {“name”: “Asian Paints”,           “sector”: “Consumer”,           “yf”: “ASIANPAINT.NS”},
“ZOMATO”:      {“name”: “Zomato”,                 “sector”: “Consumer”,           “yf”: “ZOMATO.NS”},
}

NIFTY50_INDEX_YF = “^NSEI”
PRICE_PERIOD     = “3y”
PRICE_INTERVAL   = “1d”
THROTTLE_SECS    = 1.2   # polite delay between yfinance calls

# ── Analytics helpers ──────────────────────────────────────────────────────────

def _compute_rsi(prices: pd.Series, period: int = 14) -> float | None:
if len(prices) < period + 1:
return None
delta = prices.diff()
gain  = delta.clip(lower=0).rolling(period).mean()
loss  = (-delta.clip(upper=0)).rolling(period).mean()
rs    = gain / loss.replace(0, float(“nan”))
rsi   = 100 - (100 / (1 + rs))
val   = rsi.iloc[-1]
return round(float(val), 2) if not np.isnan(val) else None

def _compute_macd(prices: pd.Series) -> str | None:
if len(prices) < 26:
return None
ema12 = prices.ewm(span=12, adjust=False).mean()
ema26 = prices.ewm(span=26, adjust=False).mean()
macd  = ema12 - ema26
signal = macd.ewm(span=9, adjust=False).mean()
last_macd   = macd.iloc[-1]
last_signal = signal.iloc[-1]
if np.isnan(last_macd) or np.isnan(last_signal):
return None
return “bullish” if last_macd > last_signal else “bearish”

def _compute_beta(stock_returns: pd.Series, index_returns: pd.Series) -> float | None:
aligned = pd.concat([stock_returns, index_returns], axis=1).dropna()
if len(aligned) < 30:
return None
cov = aligned.cov()
var = aligned.iloc[:, 1].var()
if var == 0:
return None
beta = cov.iloc[0, 1] / var
return round(float(beta), 3)

def _compute_cagr(prices: pd.Series, years: int = 3) -> float | None:
days = years * 252
if len(prices) < days * 0.8:
return None
start = prices.iloc[-min(days, len(prices))]
end   = prices.iloc[-1]
if start <= 0:
return None
actual_years = min(len(prices), days) / 252
cagr = (end / start) ** (1 / actual_years) - 1
return round(float(cagr) * 100, 2)

def _compute_var(returns: pd.Series, confidence: float = 0.95) -> float | None:
if len(returns) < 30:
return None
var = float(np.percentile(returns.dropna(), (1 - confidence) * 100))
return round(var * 100, 3)

def _compute_max_drawdown(prices: pd.Series) -> float | None:
if len(prices) < 2:
return None
roll_max = prices.cummax()
drawdown = (prices - roll_max) / roll_max
return round(float(drawdown.min()) * 100, 2)

def _compute_alpha(stock_returns: pd.Series, index_returns: pd.Series, beta: float) -> float | None:
if beta is None or len(stock_returns) < 30:
return None
aligned = pd.concat([stock_returns, index_returns], axis=1).dropna()
stock_ann = float(aligned.iloc[:, 0].mean()) * 252
index_ann = float(aligned.iloc[:, 1].mean()) * 252
alpha = stock_ann - (beta * index_ann)
return round(alpha * 100, 2)

# ── Price fetch ────────────────────────────────────────────────────────────────

def _make_session() -> requests.Session:
“””
Browser-like requests session.
GitHub Actions IPs are blocked by Yahoo Finance when using default
yfinance headers. A Chrome User-Agent bypasses this fingerprinting.
“””
session = requests.Session()
session.headers.update({
“User-Agent”: (
“Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) “
“AppleWebKit/537.36 (KHTML, like Gecko) “
“Chrome/120.0.0.0 Safari/537.36”
),
“Accept”:          “*/*”,
“Accept-Language”: “en-US,en;q=0.9”,
“Accept-Encoding”: “gzip, deflate, br”,
“Referer”:         “https://finance.yahoo.com”,
“Origin”:          “https://finance.yahoo.com”,
})
return session

def _fetch_prices(yf_ticker: str, ticker: str,
session: requests.Session = None) -> pd.Series | None:
“””
Fetch price series using Ticker.history() with browser session.
Fallback chain: .NS 3y → .NS max → .BO 3y
“””
import time
if session is None:
session = _make_session()

```
fallbacks = [
    (yf_ticker,                       PRICE_PERIOD),
    (yf_ticker,                       "max"),
    (yf_ticker.replace(".NS", ".BO"), PRICE_PERIOD),
]

for attempt, (t, period) in enumerate(fallbacks, 1):
    try:
        ticker_obj = yf.Ticker(t, session=session)
        hist = ticker_obj.history(
            period=period,
            auto_adjust=True,
            actions=False,
            timeout=30,
        )
        if hist is not None and not hist.empty and len(hist) > 10:
            close = hist["Close"].squeeze()
            log.info(f"  {ticker}: {len(close)} rows (attempt {attempt})")
            return close
    except Exception as e:
        log.debug(f"  {ticker} attempt {attempt} failed: {e}")
    time.sleep(1.5)

log.warning(f"  {ticker}: no price data after {len(fallbacks)} attempts")
return None
```

def _fetch_fundamentals(yf_ticker: str) -> dict:
“”“Fetch fundamentals safely.”””
try:
info = yf.Ticker(yf_ticker).info or {}
return {
“pe”:       round(info.get(“trailingPE”, 0) or 0, 2),
“pb”:       round(info.get(“priceToBook”, 0) or 0, 2),
“div_yield”:round((info.get(“dividendYield”, 0) or 0) * 100, 2),
“mkt_cap”:  info.get(“marketCap”),
“52w_high”: info.get(“fiftyTwoWeekHigh”),
“52w_low”:  info.get(“fiftyTwoWeekLow”),
“sector”:   info.get(“sector”, “”),
“industry”: info.get(“industry”, “”),
}
except Exception:
return {}

# ── Core harvest ───────────────────────────────────────────────────────────────

def get_peer_tickers(tickers: list) -> list:
“””
Given a list of user’s tickers, return them + all sector peers.
E.g. HDFCBANK → all Financial Services stocks added.
“””
import time
sectors = set()
for t in tickers:
if t in NIFTY50:
sectors.add(NIFTY50[t][“sector”])

```
peers = set(tickers)
for ticker, info in NIFTY50.items():
    if info["sector"] in sectors:
        peers.add(ticker)

result = [t for t in peers if t in NIFTY50]
log.info(f"Holdings: {len(tickers)} | Sectors: {sectors} | With peers: {len(result)}")
return result
```

def harvest(tickers: list = None) -> dict:
“””
Main harvest function.
If tickers=None → harvest all 50 Nifty stocks.
If tickers given → harvest those + sector peers.

```
Returns summary dict (no raw data — safe to log).
"""
import time

run_id   = str(uuid.uuid4())[:8]
started  = datetime.utcnow()
log.info(f"Harvest started — run_id: {run_id}")

# Determine universe
if tickers:
    universe = get_peer_tickers(tickers)
else:
    universe = list(NIFTY50.keys())

log.info(f"Universe: {len(universe)} stocks")

# Fetch Nifty50 index for beta/alpha
log.info("Fetching Nifty50 index...")
try:
    idx_obj   = yf.Ticker(NIFTY50_INDEX_YF, session=shared_session)
    idx_hist  = idx_obj.history(period=PRICE_PERIOD, auto_adjust=True,
                                actions=False, timeout=30)
    idx_close = idx_hist["Close"].squeeze()
    idx_ret   = idx_close.pct_change().dropna()
    log.info(f"  Index: {len(idx_close)} rows")
except Exception as e:
    log.warning(f"  Index fetch failed: {e}")
    idx_close = None
    idx_ret   = None

# Shared browser session — created once, reused for all 50 stocks
shared_session = _make_session()
log.info("Browser session initialised")

# Harvest each stock
snapshot     = []
fundamentals = {}
success      = 0
failed       = []

for i, ticker in enumerate(universe, 1):
    meta = NIFTY50.get(ticker, {})
    yf_t = meta.get("yf", f"{ticker}.NS")

    log.info(f"[{i}/{len(universe)}] {ticker}")

    prices = _fetch_prices(yf_t, ticker, session=shared_session)

    if prices is None or len(prices) < 20:
        failed.append(ticker)
        time.sleep(THROTTLE_SECS)
        continue

    returns = prices.pct_change().dropna()

    # Analytics
    beta     = _compute_beta(returns, idx_ret) if idx_ret is not None else None
    alpha    = _compute_alpha(returns, idx_ret, beta) if idx_ret is not None else None
    cagr_3y  = _compute_cagr(prices, 3)
    cagr_1y  = _compute_cagr(prices, 1)
    var_95   = _compute_var(returns)
    max_dd   = _compute_max_drawdown(prices)
    rsi      = _compute_rsi(prices)
    macd     = _compute_macd(prices)

    # SMA
    sma50  = round(float(prices.rolling(50).mean().iloc[-1]),  2) if len(prices) >= 50  else None
    sma200 = round(float(prices.rolling(200).mean().iloc[-1]), 2) if len(prices) >= 200 else None
    price  = round(float(prices.iloc[-1]), 2)

    # 1yr return
    ret_1y = None
    if len(prices) >= 252:
        p_now  = prices.iloc[-1]
        p_1y   = prices.iloc[-252]
        ret_1y = round(float((p_now - p_1y) / p_1y) * 100, 2) if p_1y > 0 else None

    stock_entry = {
        "ticker":       ticker,
        "name":         meta.get("name", ticker),
        "sector":       meta.get("sector", "Unknown"),
        "yf_ticker":    yf_t,
        "price":        price,
        "rsi":          rsi,
        "macd":         macd,
        "beta_3y":      beta,
        "alpha":        alpha,
        "cagr_3y":      cagr_3y,
        "cagr_1y":      cagr_1y,
        "ret_1y":       ret_1y,
        "var_95":       var_95,
        "max_dd":       max_dd,
        "sma50":        sma50,
        "sma200":       sma200,
        "above_sma50":  price > sma50  if sma50  else None,
        "above_sma200": price > sma200 if sma200 else None,
        "52w_high":     round(float(prices.rolling(252).max().iloc[-1]), 2) if len(prices) >= 252 else None,
        "52w_low":      round(float(prices.rolling(252).min().iloc[-1]), 2) if len(prices) >= 252 else None,
        "harvested_at": datetime.utcnow().isoformat(),
    }
    snapshot.append(stock_entry)

    # Fundamentals (slower — only fetch if not already done)
    if ticker not in fundamentals:
        fund = _fetch_fundamentals(yf_t)
        fundamentals[ticker] = fund

    success += 1
    time.sleep(THROTTLE_SECS)

# Write to GitHub
log.info(f"Writing encrypted data to GitHub db/...")

snapshot_payload = {
    "generated_at": datetime.utcnow().isoformat(),
    "run_id":       run_id,
    "count":        len(snapshot),
    "stocks":       snapshot,
}
gs.write("snapshot",     snapshot_payload, f"harvest snapshot: {success} stocks")
gs.write("fundamentals", {"generated_at": datetime.utcnow().isoformat(), "data": fundamentals})
gs.write_metadata(success, [s["ticker"] for s in snapshot], run_id)

duration = (datetime.utcnow() - started).total_seconds()
summary = {
    "run_id":    run_id,
    "success":   success,
    "failed":    len(failed),
    "duration":  round(duration, 1),
    "status":    "ok" if not failed else "partial",
}
# SECURITY: log only counts, never raw data
log.info(f"Harvest complete: {success} ok, {len(failed)} failed, {duration:.0f}s")
return summary
```

# ── Entry point ────────────────────────────────────────────────────────────────

if **name** == “**main**”:
“””
Called by GitHub Actions or Colab.
If db/holdings_trigger.enc exists → targeted harvest.
Otherwise → full Nifty50 harvest.
“””
log.info(”=== Agent_Trader Harvest Runner ===”)

```
# Test connectivity first
conn = gs.test_connection()
for k, v in conn.items():
    log.info(f"  {k}: {v}")

all_ok = all("✅" in str(v) for v in conn.values())
if not all_ok:
    log.error("Connectivity check failed — aborting harvest")
    sys.exit(1)

# Check for targeted trigger
tickers = None
trigger = gs.read("holdings_trigger")
if trigger and "tickers" in trigger:
    tickers = trigger["tickers"]
    log.info(f"Targeted harvest triggered — {len(tickers)} holdings: {tickers}")
else:
    log.info("No trigger found — running full Nifty50 harvest")

summary = harvest(tickers)
log.info(f"Done: {summary}")

if summary["status"] not in ("ok", "partial"):
    sys.exit(1)
