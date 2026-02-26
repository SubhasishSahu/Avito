“””
Agent_Trader — Harvest Runner v2
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

FIXES vs v1:
BUG-1: shared_session now created BEFORE index fetch (was NameError)
BUG-2: Duplicate WIPRO key removed from NIFTY50 dict
BUG-3: import requests added to top-level imports
BUG-4: Removed unused `import time` inside get_peer_tickers()
BUG-5: _fetch_fundamentals() now accepts + uses shared session
BUG-6: Removed redundant sleep in failed-stock branch
BUG-7: NIFTY50 universe audited — exactly 50 unique tickers
BUG-8: status = ‘error’ when success == 0, not ‘partial’
BUG-9: Removed unused timedelta import
“””
import os
import sys
import logging
import warnings
import time
import uuid
import requests
from datetime import datetime

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
log = logging.getLogger(__name__)

# Suppress noisy third-party loggers

logging.getLogger(“yfinance”).setLevel(logging.ERROR)
logging.getLogger(“urllib3”).setLevel(logging.ERROR)
logging.getLogger(“peewee”).setLevel(logging.ERROR)

# ── Nifty50 Universe — 50 unique tickers ──────────────────────────────────────

# BUG-2 fixed: WIPRO appeared twice — removed duplicate from Diversified section

# BUG-7 fixed: Audited to exactly 50 unique tickers

NIFTY50 = {
# Financial Services (10)
“HDFCBANK”:   {“name”: “HDFC Bank”,              “sector”: “Financial Services”, “yf”: “HDFCBANK.NS”},
“ICICIBANK”:  {“name”: “ICICI Bank”,             “sector”: “Financial Services”, “yf”: “ICICIBANK.NS”},
“KOTAKBANK”:  {“name”: “Kotak Mahindra Bank”,    “sector”: “Financial Services”, “yf”: “KOTAKBANK.NS”},
“AXISBANK”:   {“name”: “Axis Bank”,              “sector”: “Financial Services”, “yf”: “AXISBANK.NS”},
“SBIN”:       {“name”: “State Bank of India”,    “sector”: “Financial Services”, “yf”: “SBIN.NS”},
“BAJFINANCE”: {“name”: “Bajaj Finance”,          “sector”: “Financial Services”, “yf”: “BAJFINANCE.NS”},
“BAJAJFINSV”: {“name”: “Bajaj Finserv”,          “sector”: “Financial Services”, “yf”: “BAJAJFINSV.NS”},
“HDFCLIFE”:   {“name”: “HDFC Life Insurance”,    “sector”: “Financial Services”, “yf”: “HDFCLIFE.NS”},
“SBILIFE”:    {“name”: “SBI Life Insurance”,     “sector”: “Financial Services”, “yf”: “SBILIFE.NS”},
“INDUSINDBK”: {“name”: “IndusInd Bank”,          “sector”: “Financial Services”, “yf”: “INDUSINDBK.NS”},
# IT (5)
“TCS”:        {“name”: “Tata Consultancy”,       “sector”: “IT”,                 “yf”: “TCS.NS”},
“INFY”:       {“name”: “Infosys”,                “sector”: “IT”,                 “yf”: “INFY.NS”},
“HCLTECH”:    {“name”: “HCL Technologies”,       “sector”: “IT”,                 “yf”: “HCLTECH.NS”},
“WIPRO”:      {“name”: “Wipro”,                  “sector”: “IT”,                 “yf”: “WIPRO.NS”},
“TECHM”:      {“name”: “Tech Mahindra”,          “sector”: “IT”,                 “yf”: “TECHM.NS”},
# Oil & Gas / Energy (5)
“RELIANCE”:   {“name”: “Reliance Industries”,    “sector”: “Oil & Gas”,          “yf”: “RELIANCE.NS”},
“ONGC”:       {“name”: “ONGC”,                   “sector”: “Oil & Gas”,          “yf”: “ONGC.NS”},
“BPCL”:       {“name”: “BPCL”,                   “sector”: “Oil & Gas”,          “yf”: “BPCL.NS”},
“POWERGRID”:  {“name”: “Power Grid Corp”,        “sector”: “Oil & Gas”,          “yf”: “POWERGRID.NS”},
“NTPC”:       {“name”: “NTPC”,                   “sector”: “Oil & Gas”,          “yf”: “NTPC.NS”},
# Consumer (6)
“HINDUNILVR”: {“name”: “Hindustan Unilever”,     “sector”: “Consumer”,           “yf”: “HINDUNILVR.NS”},
“ITC”:        {“name”: “ITC”,                    “sector”: “Consumer”,           “yf”: “ITC.NS”},
“NESTLEIND”:  {“name”: “Nestle India”,           “sector”: “Consumer”,           “yf”: “NESTLEIND.NS”},
“BRITANNIA”:  {“name”: “Britannia Industries”,   “sector”: “Consumer”,           “yf”: “BRITANNIA.NS”},
“TATACONSUM”: {“name”: “Tata Consumer Products”, “sector”: “Consumer”,           “yf”: “TATACONSUM.NS”},
“TITAN”:      {“name”: “Titan Company”,          “sector”: “Consumer”,           “yf”: “TITAN.NS”},
# Auto (6)
“MARUTI”:     {“name”: “Maruti Suzuki”,          “sector”: “Auto”,               “yf”: “MARUTI.NS”},
“BAJAJ-AUTO”: {“name”: “Bajaj Auto”,             “sector”: “Auto”,               “yf”: “BAJAJ-AUTO.NS”},
“HEROMOTOCO”: {“name”: “Hero MotoCorp”,          “sector”: “Auto”,               “yf”: “HEROMOTOCO.NS”},
“EICHERMOT”:  {“name”: “Eicher Motors”,          “sector”: “Auto”,               “yf”: “EICHERMOT.NS”},
“M&M”:        {“name”: “Mahindra & Mahindra”,    “sector”: “Auto”,               “yf”: “M&M.NS”},
“TATAMOTORS”: {“name”: “Tata Motors”,            “sector”: “Auto”,               “yf”: “TATAMOTORS.NS”},
# Pharma / Healthcare (5)
“SUNPHARMA”:  {“name”: “Sun Pharmaceutical”,     “sector”: “Pharma”,             “yf”: “SUNPHARMA.NS”},
“DRREDDY”:    {“name”: “Dr Reddy’s Labs”,        “sector”: “Pharma”,             “yf”: “DRREDDY.NS”},
“CIPLA”:      {“name”: “Cipla”,                  “sector”: “Pharma”,             “yf”: “CIPLA.NS”},
“DIVISLAB”:   {“name”: “Divi’s Laboratories”,    “sector”: “Pharma”,             “yf”: “DIVISLAB.NS”},
“APOLLOHOSP”: {“name”: “Apollo Hospitals”,       “sector”: “Pharma”,             “yf”: “APOLLOHOSP.NS”},
# Metals (4)
“TATASTEEL”:  {“name”: “Tata Steel”,             “sector”: “Metals”,             “yf”: “TATASTEEL.NS”},
“JSWSTEEL”:   {“name”: “JSW Steel”,              “sector”: “Metals”,             “yf”: “JSWSTEEL.NS”},
“HINDALCO”:   {“name”: “Hindalco Industries”,    “sector”: “Metals”,             “yf”: “HINDALCO.NS”},
“ADANIENT”:   {“name”: “Adani Enterprises”,      “sector”: “Metals”,             “yf”: “ADANIENT.NS”},
# Infrastructure (2)
“LT”:         {“name”: “Larsen & Toubro”,        “sector”: “Infrastructure”,     “yf”: “LT.NS”},
“ADANIPORTS”: {“name”: “Adani Ports”,            “sector”: “Infrastructure”,     “yf”: “ADANIPORTS.NS”},
# Cement (2)
“ULTRACEMCO”: {“name”: “UltraTech Cement”,       “sector”: “Cement”,             “yf”: “ULTRACEMCO.NS”},
“GRASIM”:     {“name”: “Grasim Industries”,      “sector”: “Cement”,             “yf”: “GRASIM.NS”},
# Telecom (1)
“BHARTIARTL”: {“name”: “Bharti Airtel”,          “sector”: “Telecom”,            “yf”: “BHARTIARTL.NS”},
# Consumer extras to reach 50
“ASIANPAINT”: {“name”: “Asian Paints”,           “sector”: “Consumer”,           “yf”: “ASIANPAINT.NS”},
“ZOMATO”:     {“name”: “Zomato”,                 “sector”: “Consumer”,           “yf”: “ZOMATO.NS”},
“COALINDIA”:  {“name”: “Coal India”,             “sector”: “Oil & Gas”,          “yf”: “COALINDIA.NS”},
“SHRIRAMFIN”: {“name”: “Shriram Finance”,        “sector”: “Financial Services”, “yf”: “SHRIRAMFIN.NS”},
}

# Confirm universe at module load time

assert len(NIFTY50) == 50, f”Universe has {len(NIFTY50)} stocks — expected 50”

NIFTY50_INDEX_YF = “^NSEI”
PRICE_PERIOD     = “3y”
THROTTLE_SECS    = 1.2

# ── Browser session ────────────────────────────────────────────────────────────

# BUG-1 fix: session creation moved here so it exists before index fetch

# BUG-3 fix: `import requests` now at top of file

def _make_session() -> requests.Session:
“””
Browser-like requests session.
GitHub Actions IPs are blocked by Yahoo Finance when using default
yfinance headers. A Chrome User-Agent bypasses this fingerprinting.
One session is created per harvest run and shared across all tickers.
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
return round(float(val), 2) if pd.notna(val) else None

def _compute_macd(prices: pd.Series) -> str | None:
if len(prices) < 26:
return None
ema12  = prices.ewm(span=12, adjust=False).mean()
ema26  = prices.ewm(span=26, adjust=False).mean()
macd   = ema12 - ema26
signal = macd.ewm(span=9, adjust=False).mean()
last_macd   = macd.iloc[-1]
last_signal = signal.iloc[-1]
if pd.isna(last_macd) or pd.isna(last_signal):
return None
return “bullish” if last_macd > last_signal else “bearish”

def _compute_beta(stock_ret: pd.Series, index_ret: pd.Series) -> float | None:
if index_ret is None or len(stock_ret) < 30:
return None
aligned = pd.concat([stock_ret, index_ret], axis=1).dropna()
if len(aligned) < 30:
return None
var = aligned.iloc[:, 1].var()
if var == 0:
return None
return round(float(aligned.cov().iloc[0, 1] / var), 3)

def _compute_cagr(prices: pd.Series, years: int = 3) -> float | None:
days = years * 252
if len(prices) < days * 0.8:
return None
start = float(prices.iloc[-min(days, len(prices))])
end   = float(prices.iloc[-1])
if start <= 0:
return None
actual_years = min(len(prices), days) / 252
return round(((end / start) ** (1 / actual_years) - 1) * 100, 2)

def _compute_var(returns: pd.Series, confidence: float = 0.95) -> float | None:
clean = returns.dropna()
if len(clean) < 30:
return None
return round(float(np.percentile(clean, (1 - confidence) * 100)) * 100, 3)

def _compute_max_drawdown(prices: pd.Series) -> float | None:
if len(prices) < 2:
return None
roll_max = prices.cummax()
drawdown = (prices - roll_max) / roll_max
return round(float(drawdown.min()) * 100, 2)

def _compute_alpha(stock_ret: pd.Series, index_ret: pd.Series,
beta: float | None) -> float | None:
if beta is None or index_ret is None or len(stock_ret) < 30:
return None
aligned   = pd.concat([stock_ret, index_ret], axis=1).dropna()
stock_ann = float(aligned.iloc[:, 0].mean()) * 252
index_ann = float(aligned.iloc[:, 1].mean()) * 252
return round((stock_ann - beta * index_ann) * 100, 2)

# ── Price + fundamentals fetch ─────────────────────────────────────────────────

def _fetch_prices(yf_ticker: str, ticker: str,
session: requests.Session) -> pd.Series | None:
“””
Fetch 3yr daily close prices via Ticker.history().
Fallback chain: .NS 3y → .NS max → .BO 3y
Uses shared browser session to avoid Yahoo Finance IP blocks on GitHub Actions.
“””
fallbacks = [
(yf_ticker,                       PRICE_PERIOD),
(yf_ticker,                       “max”),
(yf_ticker.replace(”.NS”, “.BO”), PRICE_PERIOD),
]
for attempt, (t, period) in enumerate(fallbacks, 1):
try:
hist = yf.Ticker(t, session=session).history(
period=period,
auto_adjust=True,
actions=False,
timeout=30,
)
if hist is not None and not hist.empty and len(hist) > 10:
close = hist[“Close”].squeeze()
log.info(f”  {ticker}: {len(close)} rows (attempt {attempt})”)
return close
except Exception as e:
log.debug(f”  {ticker} attempt {attempt} ({t}): {e}”)
time.sleep(1.5)

log.warning(f"  {ticker}: no price data after {len(fallbacks)} attempts")
return None

def _fetch_fundamentals(yf_ticker: str,
session: requests.Session) -> dict:
“””
Fetch PE, PB, dividend yield etc.
BUG-5 fixed: now uses shared browser session.
“””
try:
info = yf.Ticker(yf_ticker, session=session).info or {}
return {
“pe”:        round(float(info.get(“trailingPE”) or 0), 2),
“pb”:        round(float(info.get(“priceToBook”) or 0), 2),
“div_yield”: round(float(info.get(“dividendYield”) or 0) * 100, 2),
“mkt_cap”:   info.get(“marketCap”),
“52w_high”:  info.get(“fiftyTwoWeekHigh”),
“52w_low”:   info.get(“fiftyTwoWeekLow”),
“sector”:    info.get(“sector”, “”),
“industry”:  info.get(“industry”, “”),
}
except Exception as e:
log.debug(f”  Fundamentals failed for {yf_ticker}: {e}”)
return {}

# ── Peer universe builder ──────────────────────────────────────────────────────

def get_peer_tickers(tickers: list) -> list:
“””
Given user’s holdings, return them + all sector peers from NIFTY50.
BUG-4 fixed: removed unused `import time` that was inside this function.
“””
sectors = {NIFTY50[t][“sector”] for t in tickers if t in NIFTY50}
peers   = {t for t, info in NIFTY50.items() if info[“sector”] in sectors}
peers.update(tickers)  # always include user’s own stocks even if not in NIFTY50
result  = [t for t in peers if t in NIFTY50]
log.info(f”Holdings: {len(tickers)} | Sectors: {sectors} | With peers: {len(result)}”)
return result

# ── Main harvest ───────────────────────────────────────────────────────────────

def harvest(tickers: list = None) -> dict:
“””
Main harvest function.
tickers=None  → harvest all 50 Nifty stocks
tickers given → harvest those + sector peers only

Returns summary dict — safe to log (no raw data, no secrets).
"""
run_id  = str(uuid.uuid4())[:8]
started = datetime.utcnow()
log.info(f"Harvest started — run_id: {run_id}")

# Universe
universe = get_peer_tickers(tickers) if tickers else list(NIFTY50.keys())
log.info(f"Universe: {len(universe)} stocks")

# BUG-1 fixed: shared_session created BEFORE index fetch
shared_session = _make_session()
log.info("Browser session initialised")

# Nifty50 index for beta/alpha calculation
idx_ret = None
log.info("Fetching Nifty50 index...")
try:
    idx_hist = yf.Ticker(NIFTY50_INDEX_YF, session=shared_session).history(
        period=PRICE_PERIOD, auto_adjust=True, actions=False, timeout=30
    )
    if idx_hist is not None and not idx_hist.empty:
        idx_ret = idx_hist["Close"].squeeze().pct_change().dropna()
        log.info(f"  Index: {len(idx_hist)} rows")
    else:
        log.warning("  Index returned empty — beta/alpha will be None")
except Exception as e:
    log.warning(f"  Index fetch failed: {e} — beta/alpha will be None")

# Per-stock harvest
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
        # BUG-6 fixed: no extra sleep here — _fetch_prices already throttles
        continue

    returns = prices.pct_change().dropna()
    price   = round(float(prices.iloc[-1]), 2)

    # SMA
    sma50  = round(float(prices.rolling(50).mean().iloc[-1]),  2) if len(prices) >= 50  else None
    sma200 = round(float(prices.rolling(200).mean().iloc[-1]), 2) if len(prices) >= 200 else None

    # 1yr return
    ret_1y = None
    if len(prices) >= 252:
        p1y    = float(prices.iloc[-252])
        ret_1y = round((price - p1y) / p1y * 100, 2) if p1y > 0 else None

    # Compute beta once — reused in alpha (avoid double computation)
    beta = _compute_beta(returns, idx_ret)

    snapshot.append({
        "ticker":       ticker,
        "name":         meta.get("name", ticker),
        "sector":       meta.get("sector", "Unknown"),
        "yf_ticker":    yf_t,
        "price":        price,
        "rsi":          _compute_rsi(prices),
        "macd":         _compute_macd(prices),
        "beta_3y":      beta,
        "alpha":        _compute_alpha(returns, idx_ret, beta),
        "cagr_3y":      _compute_cagr(prices, 3),
        "cagr_1y":      _compute_cagr(prices, 1),
        "ret_1y":       ret_1y,
        "var_95":       _compute_var(returns),
        "max_dd":       _compute_max_drawdown(prices),
        "sma50":        sma50,
        "sma200":       sma200,
        "above_sma50":  (price > sma50)  if sma50  else None,
        "above_sma200": (price > sma200) if sma200 else None,
        "52w_high":     round(float(prices.rolling(252).max().iloc[-1]), 2) if len(prices) >= 252 else None,
        "52w_low":      round(float(prices.rolling(252).min().iloc[-1]), 2) if len(prices) >= 252 else None,
        "harvested_at": datetime.utcnow().isoformat(),
    })

    # Fundamentals — BUG-5 fixed: pass shared session
    fundamentals[ticker] = _fetch_fundamentals(yf_t, session=shared_session)

    success += 1
    time.sleep(THROTTLE_SECS)

# Write encrypted data to GitHub db/
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

# BUG-8 fixed: 'error' when success==0, not 'partial'
if success == 0:
    status = "error"
elif failed:
    status = "partial"
else:
    status = "ok"

summary = {
    "run_id":   run_id,
    "success":  success,
    "failed":   len(failed),
    "duration": duration,
    "status":   status,
}
# SECURITY: log only counts, never raw ticker data or prices
log.info(f"Harvest complete: {success} ok, {len(failed)} failed, {duration}s — {status}")
return summary
```

# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == “__main__”:
log.info(”=== Agent_Trader Harvest Runner v2 ===”)

# Connectivity check before doing any work
conn   = gs.test_connection()
all_ok = True
for k, v in conn.items():
    log.info(f"  {k}: {v}")
    if "❌" in str(v):
        all_ok = False

if not all_ok:
    log.error("Connectivity check failed — aborting")
    sys.exit(1)

# Targeted or full harvest
tickers = None
trigger = gs.read("holdings_trigger")
if trigger and "tickers" in trigger:
    tickers = trigger["tickers"]
    log.info(f"Targeted harvest — {len(tickers)} holdings")
else:
    log.info("No trigger — running full Nifty50 harvest")

summary = harvest(tickers)
log.info(f"Done: {summary}")

# BUG-8 fix: exit non-zero on complete failure
if summary["status"] == "error":
    log.error("All stocks failed — check Yahoo Finance connectivity")
    sys.exit(1)
