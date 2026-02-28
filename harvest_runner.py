"""
Agent_Trader -- Harvest Runner
==============================
Data source: yfinance (Yahoo Finance query1 / query2).

Why yfinance only
-----------------
Colab test on 2026-02-28 (Google AS396982 — clean residential-equivalent IP)
proved that every alternative source fails for Indian NSE stocks:

  Stooq .ns / .bo  → "No data" from Google Cloud AND Azure.
                     Stooq does not index Indian NSE/BSE stocks at all.
                     Was misidentified as an ASN block; it is a coverage gap.

  BSE India API    → Session cookies are set by JavaScript (document.cookie).
                     Plain requests.get() never receives them.
                     Returns all-null JSON from every IP, every header set.

  FMP free tier    → NSE/BSE not on free plan. Requires $19/mo subscription.

yfinance works reliably from GitHub Actions Azure IPs during the off-peak
window: 18:30–23:30 UTC (midnight–5:30am IST). Scheduled harvest at 18:30 UTC
is correctly timed. During market hours the shared Azure rate-limit quota is
exhausted within seconds by thousands of concurrent workflows; at midnight IST
it resets and stays available for the full harvest window.

Rate-limit safety
-----------------
Circuit breakers: first 429 from query1 sets _YF_BLOCKED and skips all
subsequent stocks via that subdomain. query2 has a separate pool and is tried
independently. If both are blocked the existing snapshot is preserved
(BUG_12 fix: zero-fetch runs must not overwrite good data).

Fix history
-----------
  BUG_1-9   yfinance/curl_cffi stack issues
  BUG_10    Yahoo rate-limits GitHub Actions IPs -> added NSE as primary
  BUG_11    NSE also blocks datacenter IPs -> switched to Stooq
  BUG_12    Triggered harvest overwrote snapshot with 0 stocks
            -> merge strategy: existing data preserved on failure
  BUG_13    Triggered harvest fetched only holdings, lost Nifty50 peers
            -> always harvest full Nifty50 + extra tickers on top
  BUG_14    Wasted browser-rotation / curl_cffi effort on Stooq
            -> Colab test proved Stooq has no Indian stock coverage
            -> removed Stooq, BSE, FMP, _rotating_get, _BROWSER_PROFILES
            -> yfinance-only with query1 + query2 circuit breakers
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

for _lib in ("yfinance", "urllib3", "peewee"):
    logging.getLogger(_lib).setLevel(logging.ERROR)


# ---------------------------------------------------------------------------
# Nifty50 Universe — 50 stocks, sector-mapped
# yf: Yahoo Finance symbol (TICKER.NS)
# ---------------------------------------------------------------------------
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

assert len(NIFTY50) == 50, f"NIFTY50 has {len(NIFTY50)} stocks -- expected 50"


# ---------------------------------------------------------------------------
# BROKER_TICKER_MAP
# Maps broker-export ticker formats (e.g. "HALEQ") to canonical NSE symbols.
# Structure: broker_ticker -> (nse_symbol, company_name, sector)
# ---------------------------------------------------------------------------
BROKER_TICKER_MAP = {
    # ── Nifty50 EQ-suffix variants ────────────────────────────────────────────
    "HDFCBANKEQ":   ("HDFCBANK",   "HDFC Bank",              "Financial Services"),
    "ICICIBANKNEQ": ("ICICIBANK",  "ICICI Bank",             "Financial Services"),
    "KOTAKBANKEQ":  ("KOTAKBANK",  "Kotak Mahindra Bank",    "Financial Services"),
    "AXISBANKEQ":   ("AXISBANK",   "Axis Bank",              "Financial Services"),
    "SBINEQ":       ("SBIN",       "State Bank of India",    "Financial Services"),
    "BAJFINANCEEQ": ("BAJFINANCE", "Bajaj Finance",          "Financial Services"),
    "BAJAJFINSVQ":  ("BAJAJFINSV", "Bajaj Finserv",          "Financial Services"),
    "HDFCLIFEEQ":   ("HDFCLIFE",   "HDFC Life Insurance",    "Financial Services"),
    "SBILIFEQ":     ("SBILIFE",    "SBI Life Insurance",     "Financial Services"),
    "INDUSINDBKEQ": ("INDUSINDBK", "IndusInd Bank",          "Financial Services"),
    "TCSEQ":        ("TCS",        "Tata Consultancy",       "IT"),
    "INFYEQ":       ("INFY",       "Infosys",                "IT"),
    "HCLTECHEQ":    ("HCLTECH",    "HCL Technologies",       "IT"),
    "WIPROEQ":      ("WIPRO",      "Wipro",                  "IT"),
    "TECHMEQ":      ("TECHM",      "Tech Mahindra",          "IT"),
    "LTIMEQ":       ("LTIM",       "LTIMindtree",            "IT"),
    "RELIANCEEQ":   ("RELIANCE",   "Reliance Industries",    "Oil & Gas"),
    "ONGCEQ":       ("ONGC",       "ONGC",                   "Oil & Gas"),
    "BPCLEQ":       ("BPCL",       "BPCL",                   "Oil & Gas"),
    "COALINDIAEQ":  ("COALINDIA",  "Coal India",             "Oil & Gas"),
    "POWERGRIDQ":   ("POWERGRID",  "Power Grid Corp",        "Oil & Gas"),
    "NTPCEQ":       ("NTPC",       "NTPC",                   "Oil & Gas"),
    "HINDUNILVREQ": ("HINDUNILVR", "Hindustan Unilever",     "Consumer"),
    "ITCEQ":        ("ITC",        "ITC",                    "Consumer"),
    "NESTLEINDEQ":  ("NESTLEIND",  "Nestle India",           "Consumer"),
    "BRITANNIAEQ":  ("BRITANNIA",  "Britannia Industries",   "Consumer"),
    "TATACONSUMEQ": ("TATACONSUM", "Tata Consumer Products", "Consumer"),
    "TITANEQ":      ("TITAN",      "Titan Company",          "Consumer"),
    "ASIANPAINTEQ": ("ASIANPAINT", "Asian Paints",           "Consumer"),
    "ZOMATOEQ":     ("ZOMATO",     "Zomato",                 "Consumer"),
    "MARUTIEQ":     ("MARUTI",     "Maruti Suzuki",          "Auto"),
    "BAJAJ-AUTOEQ": ("BAJAJ-AUTO", "Bajaj Auto",             "Auto"),
    "HEROMOTOCOEQ": ("HEROMOTOCO", "Hero MotoCorp",          "Auto"),
    "EICHERMOTEQ":  ("EICHERMOT",  "Eicher Motors",          "Auto"),
    "TATAMOTORSEQ": ("TATAMOTORS", "Tata Motors",            "Auto"),
    "SUNPHARMAEQ":  ("SUNPHARMA",  "Sun Pharmaceutical",     "Pharma"),
    "DRREDYEQ":     ("DRREDDY",    "Dr Reddys Labs",         "Pharma"),
    "CIPLAYEQ":     ("CIPLA",      "Cipla",                  "Pharma"),
    "DIVISLABEQ":   ("DIVISLAB",   "Divis Laboratories",     "Pharma"),
    "APOLLOHOSPEQ": ("APOLLOHOSP", "Apollo Hospitals",       "Pharma"),
    "TATASTEELEQ":  ("TATASTEEL",  "Tata Steel",             "Metals"),
    "JSWSTEELEQ":   ("JSWSTEEL",   "JSW Steel",              "Metals"),
    "HINDALCOEQ":   ("HINDALCO",   "Hindalco Industries",    "Metals"),
    "ADANIEQ":      ("ADANIENT",   "Adani Enterprises",      "Metals"),
    "LTEQ":         ("LT",         "Larsen and Toubro",      "Infrastructure"),
    "ADANIPORTSEQ": ("ADANIPORTS", "Adani Ports",            "Infrastructure"),
    "ULTRACEMCOEQ": ("ULTRACEMCO", "UltraTech Cement",       "Cement"),
    "GRASIMEQ":     ("GRASIM",     "Grasim Industries",      "Cement"),
    "BHARTIARTLEQ": ("BHARTIARTL", "Bharti Airtel",          "Telecom"),

    # ── Non-Nifty50 user holdings ─────────────────────────────────────────────
    "ADANIGREENEQ": ("ADANIGREEN",  "Adani Green Energy",          "Energy"),
    "MUNDRAPORTEQ": ("ADANIPORTS",  "Adani Ports & SEZ",           "Infrastructure"),
    "AUBANKEQ":     ("AUBANK",      "AU Small Finance Bank",       "Financial Services"),
    "BDLEQ":        ("BDL",         "Bharat Dynamics Ltd",         "Defence"),
    "BHAELEEQ":     ("BHEL",        "Bharat Heavy Electricals",    "Capital Goods"),
    "BHAFOREQ":     ("BHARATFORG",  "Bharat Forge",                "Auto Ancillary"),
    "CAMSEQ":       ("CAMS",        "Computer Age Mgmt Services",  "Financial Services"),
    "ENGINDEQ":     ("ENGINERSIN",  "Engineers India",             "Infrastructure"),
    "GUJMINEQ":     ("GMDC",        "Gujarat Mineral Dev Corp",    "Metals"),
    "GPPLEQ":       ("GPPL",        "Gujarat Pipavav Port",        "Infrastructure"),
    "HEGLTDEQ":     ("HEG",         "HEG Limited",                 "Metals"),
    "HALEQ":        ("HAL",         "Hindustan Aeronautics",       "Defence"),
    "HINCOPEQ":     ("HINDCOPPER",  "Hindustan Copper",            "Metals"),
    "IRCTCEQ":      ("IRCTC",       "Indian Railway Catering",     "Consumer"),
    "IREDAEQ":      ("IREDA",       "Indian Renewable Energy Dev", "Energy"),
    "IONEXCEQ":     ("IONEXCHANGE", "Ion Exchange India",          "Chemicals"),
    "JIOFINEQ":     ("JIOFIN",      "Jio Financial Services",      "Financial Services"),
    "LAURUSLABSEQ": ("LAURUSLABS",  "Laurus Labs",                 "Pharma"),
    "MAZDOCKEQ":    ("MAZDOCK",     "Mazagon Dock Shipbuilders",   "Defence"),
    "NATALUEQ":     ("NATIONALUM",  "National Aluminium Company",  "Metals"),
    "NMDCEQ":       ("NMDC",        "NMDC",                        "Metals"),
    "PARASEQ":      ("PARAS",       "Paras Defence & Space Tech",  "Defence"),
    "POWFINEQ":     ("PFC",         "Power Finance Corporation",   "Financial Services"),
    "RVNLEQ":       ("RVNL",        "Rail Vikas Nigam",            "Infrastructure"),
    "RECLTDEQ":     ("RECLTD",      "REC Limited",                 "Financial Services"),
    "RELINDEQ":     ("RELINFRA",    "Reliance Infrastructure",     "Infrastructure"),
    "SPANDANAEQ":   ("SPANDANA",    "Spandana Sphoorty Financial", "Financial Services"),
    "SANDUMAEQ":    ("SANDUMA",     "Sandur Manganese & Iron",     "Metals"),
    "TATCHEEQ":     ("TATATECH",    "Tata Technologies",           "IT"),
    "TRITURBINEEQ": ("TRITURBINE",  "Triveni Turbine",             "Capital Goods"),
    "ZETECHEQ":     ("ZENTEC",      "Zen Technologies",            "Defence"),
    # MEDIUM confidence
    "HDFCMFGETFEQ": ("HDFCNIFETF", "HDFC Nifty 50 ETF",          "ETF"),
    "LGEINDIAEQ":   ("LGINDIA",    "LG Balakrishnan & Bros",      "Auto Ancillary"),
    "GOLTELEQ":     ("GOLTELE",    "Goldiam International",       "Consumer"),
    "OMDCEQ":       ("OMDC",       "Orissa Minerals Dev Corp",    "Metals"),
    "TATIROEQ":     ("TATASTEEL",  "Tata Steel",                  "Metals"),
    # LOW confidence -- ⚠️ verify against your actual holdings
    "DEWHOUEQ":     ("DELHIVERY",  "Delhivery",                   "Logistics"),   # ⚠️
    "GOLINTEQ":     ("GOLDENTEK",  "Goldentek",                   "Consumer"),    # ⚠️
    "NAVBHAEQ":     ("NAVINFRA",   "Nav Bharat Ventures",         "Metals"),      # ⚠️
    "ROYAIREQ":     ("ROYALIND",   "Royal Industries",            "Unknown"),     # ⚠️
    "STABANEQ":     ("STABAN",     "Standard Industries",         "Textiles"),    # ⚠️
}


def normalize_ticker(raw: str) -> str:
    """
    Convert a broker-export ticker to canonical NSE symbol.
    Resolution: BROKER_TICKER_MAP -> NIFTY50 -> strip EQ/BE suffix -> as-is.
    """
    import re
    t = raw.strip().upper()
    if t in BROKER_TICKER_MAP:
        return BROKER_TICKER_MAP[t][0]
    if t in NIFTY50:
        return t
    stripped = re.sub(r"(EQ|BE|BL|N1|N2)$", "", t).rstrip("-")
    if stripped != t:
        if stripped in NIFTY50:
            return stripped
        if stripped in BROKER_TICKER_MAP:
            return BROKER_TICKER_MAP[stripped][0]
        return stripped
    return t


def get_ticker_meta(nse_symbol: str) -> dict:
    """Return metadata for any NSE symbol. Falls back to sensible defaults."""
    if nse_symbol in NIFTY50:
        return dict(NIFTY50[nse_symbol])
    for _, (sym, name, sector) in BROKER_TICKER_MAP.items():
        if sym == nse_symbol:
            return {"name": name, "sector": sector, "yf": f"{nse_symbol}.NS"}
    return {"name": nse_symbol, "sector": "Unknown", "yf": f"{nse_symbol}.NS"}


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
THROTTLE_SECS = 1.0   # polite delay between stocks
PRICE_PERIOD  = "3y"


# ---------------------------------------------------------------------------
# Circuit breakers
#
# Yahoo Finance rate-limits per-IP. On GitHub Actions, hundreds of workflows
# share the same Azure IP pool. When the pool's quota is exhausted the first
# 429 sets the circuit breaker and all remaining stocks skip that subdomain
# instantly — turning a 15-minute blocked run into a 2-minute blocked run.
#
# query1 (default yfinance endpoint) and query2 (alternate subdomain) have
# INDEPENDENT rate-limit counters. Both are tried before giving up.
# ---------------------------------------------------------------------------
_YF_Q1_BLOCKED = False
_YF_Q2_BLOCKED = False


# ---------------------------------------------------------------------------
# Timezone helper
# ---------------------------------------------------------------------------
def _strip_tz(prices: pd.Series) -> pd.Series:
    """
    Drop timezone from DatetimeIndex without shifting values.

    yfinance daily data: timestamps are midnight IST (e.g. 2026-02-27 00:00+05:30).
    tz_convert(None) would shift to UTC -> 2026-02-26 18:30 (WRONG date).
    tz_localize(None) drops the label only -> 2026-02-27 00:00 (correct).
    """
    if prices.index.tz is not None:
        prices = prices.copy()
        prices.index = prices.index.tz_localize(None)
    return prices


# ---------------------------------------------------------------------------
# yfinance fetch — query1
# ---------------------------------------------------------------------------
def _fetch_prices_yf_q1(yf_ticker: str, label: str) -> "pd.Series | None":
    """
    Fetch 3y close prices via yfinance (query1.finance.yahoo.com).
    Sets _YF_Q1_BLOCKED circuit breaker on first 429.
    """
    global _YF_Q1_BLOCKED
    if _YF_Q1_BLOCKED:
        log.debug(f"  {label} yf/q1: skipped (rate-limited earlier this run)")
        return None
    try:
        import yfinance as yf
        hist = yf.Ticker(yf_ticker).history(
            period=PRICE_PERIOD, auto_adjust=True, actions=False, timeout=25
        )
        if hist is not None and not hist.empty and len(hist) > 10:
            prices = _strip_tz(hist["Close"].squeeze())
            log.info(f"  {label}: {len(prices)} rows via yf/q1 ✓")
            return prices
        log.debug(f"  {label} yf/q1: empty response")
    except Exception as e:
        err = str(e)
        if "429" in err or "RateLimit" in err or "Too Many" in err:
            _YF_Q1_BLOCKED = True
            log.warning("  yf/q1 rate-limited — circuit breaker open for this run")
        else:
            log.debug(f"  {label} yf/q1: {type(e).__name__}: {e}")
    return None


def _fetch_index_yf_q1() -> "pd.Series | None":
    """Fetch Nifty50 index via yfinance query1."""
    global _YF_Q1_BLOCKED
    if _YF_Q1_BLOCKED:
        return None
    try:
        import yfinance as yf
        hist = yf.Ticker("^NSEI").history(
            period=PRICE_PERIOD, auto_adjust=True, actions=False, timeout=25
        )
        if hist is not None and not hist.empty:
            prices = _strip_tz(hist["Close"].squeeze())
            log.info(f"  Nifty50 index: {len(prices)} rows via yf/q1 ✓")
            return prices
    except Exception as e:
        err = str(e)
        if "429" in err or "RateLimit" in err or "Too Many" in err:
            _YF_Q1_BLOCKED = True
            log.warning("  yf/q1 rate-limited on index — circuit breaker open")
        else:
            log.debug(f"  Nifty50-index yf/q1: {e}")
    return None


# ---------------------------------------------------------------------------
# yfinance fetch — query2 (independent rate-limit pool)
# ---------------------------------------------------------------------------
def _fetch_prices_yf_q2(yf_ticker: str, label: str) -> "pd.Series | None":
    """
    Fetch via query2.finance.yahoo.com — a separate Yahoo subdomain with its
    own rate-limit counter, independent of query1.

    Implementation: pass a custom requests.Session to yfinance so the base URL
    resolves to query2. The session also carries a Safari UA to reduce noise.
    """
    global _YF_Q2_BLOCKED
    if _YF_Q2_BLOCKED:
        log.debug(f"  {label} yf/q2: skipped (rate-limited earlier this run)")
        return None
    try:
        import yfinance as yf
        import yfinance.base as _yfbase

        session = requests.Session()
        session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_2_1) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) "
                "Version/17.2 Safari/605.1.15"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        })

        ticker = yf.Ticker(yf_ticker, session=session)
        _orig = getattr(_yfbase, "YF_URL", None)
        try:
            if hasattr(_yfbase, "YF_URL"):
                _yfbase.YF_URL = "https://query2.finance.yahoo.com"
            hist = ticker.history(
                period=PRICE_PERIOD, auto_adjust=True, actions=False, timeout=25
            )
        finally:
            if _orig is not None and hasattr(_yfbase, "YF_URL"):
                _yfbase.YF_URL = _orig

        if hist is not None and not hist.empty and "Close" in hist.columns:
            prices = hist["Close"].dropna()
            prices.index = pd.to_datetime(prices.index).tz_localize(None)
            prices.index.name = "Date"
            if len(prices) >= 20:
                log.info(f"  {label}: {len(prices)} rows via yf/q2 ✓")
                return prices
        log.debug(f"  {label} yf/q2: empty response")
    except Exception as e:
        err = str(e)
        if "429" in err or "RateLimit" in err or "Too Many" in err:
            _YF_Q2_BLOCKED = True
            log.warning("  yf/q2 rate-limited — circuit breaker open for this run")
        else:
            log.debug(f"  {label} yf/q2: {type(e).__name__}: {e}")
    return None


def _fetch_index_yf_q2() -> "pd.Series | None":
    """Fetch Nifty50 index via yfinance query2."""
    global _YF_Q2_BLOCKED
    if _YF_Q2_BLOCKED:
        return None
    try:
        import yfinance as yf
        import yfinance.base as _yfbase

        session = requests.Session()
        session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_2_1) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) "
                "Version/17.2 Safari/605.1.15"
            ),
        })
        ticker = yf.Ticker("^NSEI", session=session)
        _orig = getattr(_yfbase, "YF_URL", None)
        try:
            if hasattr(_yfbase, "YF_URL"):
                _yfbase.YF_URL = "https://query2.finance.yahoo.com"
            hist = ticker.history(
                period=PRICE_PERIOD, auto_adjust=True, actions=False, timeout=25
            )
        finally:
            if _orig is not None and hasattr(_yfbase, "YF_URL"):
                _yfbase.YF_URL = _orig

        if hist is not None and not hist.empty:
            prices = hist["Close"].dropna()
            prices.index = pd.to_datetime(prices.index).tz_localize(None)
            prices.index.name = "Date"
            if len(prices) >= 20:
                log.info(f"  Nifty50 index: {len(prices)} rows via yf/q2 ✓")
                return prices
    except Exception as e:
        err = str(e)
        if "429" in err or "RateLimit" in err or "Too Many" in err:
            _YF_Q2_BLOCKED = True
            log.warning("  yf/q2 rate-limited on index — circuit breaker open")
        else:
            log.debug(f"  Nifty50-index yf/q2: {e}")
    return None


# ---------------------------------------------------------------------------
# Unified fetch: query1 -> query2
# ---------------------------------------------------------------------------
def _fetch_prices(ticker: str, meta: dict) -> "pd.Series | None":
    """
    Try yfinance query1, fall back to query2.
    Both circuit breakers can be open (whole run blocked) → returns None.
    Caller preserves existing snapshot in that case (BUG_12).
    """
    yf_sym = meta.get("yf", f"{ticker}.NS")

    prices = _fetch_prices_yf_q1(yf_sym, ticker)
    if prices is not None:
        return prices

    return _fetch_prices_yf_q2(yf_sym, ticker)


def _fetch_index() -> "pd.Series | None":
    """Nifty50 index: query1 -> query2."""
    idx = _fetch_index_yf_q1()
    if idx is not None:
        return idx
    log.debug("  Index: yf/q1 failed, trying q2")
    return _fetch_index_yf_q2()


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
    if stock_ret.index.tz is not None:
        stock_ret = stock_ret.copy(); stock_ret.index = stock_ret.index.tz_localize(None)
    if idx_ret.index.tz is not None:
        idx_ret = idx_ret.copy(); idx_ret.index = idx_ret.index.tz_localize(None)
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


def _fetch_fundamentals(yf_sym: str) -> dict:
    """PE, PB etc. from yfinance — best-effort, returns {} on any error."""
    try:
        import yfinance as yf
        info = yf.Ticker(yf_sym).info or {}
        return {
            "pe":        round(float(info.get("trailingPE",    0) or 0), 2),
            "pb":        round(float(info.get("priceToBook",   0) or 0), 2),
            "div_yield": round((info.get("dividendYield",      0) or 0) * 100, 2),
            "mkt_cap":   info.get("marketCap"),
            "52w_high":  info.get("fiftyTwoWeekHigh"),
            "52w_low":   info.get("fiftyTwoWeekLow"),
        }
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# Universe helpers
# ---------------------------------------------------------------------------
def get_peer_tickers(tickers):
    """Expand holding tickers to include Nifty50 sector peers."""
    normalized = [normalize_ticker(t) for t in tickers]
    in_nifty   = [t for t in normalized if t in NIFTY50]
    out_nifty  = [t for t in normalized if t not in NIFTY50]
    if out_nifty:
        log.info(f"Non-Nifty50 holdings (fetch individually): {out_nifty}")
    sectors = {NIFTY50[t]["sector"] for t in in_nifty}
    peers   = {t for t, info in NIFTY50.items() if info["sector"] in sectors}
    peers.update(in_nifty)
    nifty_result = [t for t in peers if t in NIFTY50]
    result = nifty_result + [t for t in out_nifty if t not in nifty_result]
    log.info(
        f"Holdings: {len(normalized)} | Nifty50 peers: {len(nifty_result)} "
        f"| Extra: {len(out_nifty)} | Total: {len(result)}"
    )
    return result


# ---------------------------------------------------------------------------
# Main harvest
# ---------------------------------------------------------------------------
def harvest(extra_tickers=None, tickers=None):
    """
    Harvest price data for full Nifty50 + any extra non-Nifty50 holdings.

    Args:
        extra_tickers: non-Nifty50 NSE symbols to add (e.g. ['HAL', 'IRCTC'])
        tickers:       DEPRECATED, ignored if extra_tickers is provided
    """
    run_id  = str(uuid.uuid4())[:8]
    started = datetime.utcnow()
    log.info(f"Harvest started -- run_id: {run_id}")
    log.info("Source: yfinance query1 -> query2 (circuit breakers active)")
    log.info("Window: 18:30-23:30 UTC (midnight-5:30am IST) — Azure rate limit reset")

    nifty_universe = list(NIFTY50.keys())
    if extra_tickers:
        deduped_extra = [t for t in extra_tickers if t not in NIFTY50]
        universe = nifty_universe + deduped_extra
        log.info(
            f"Universe: {len(nifty_universe)} Nifty50 + "
            f"{len(deduped_extra)} extra = {len(universe)} total"
        )
    else:
        universe = nifty_universe
        log.info(f"Universe: {len(universe)} stocks (full Nifty50)")

    log.info("Fetching Nifty50 index (^NSEI)...")
    idx_prices = _fetch_index()
    idx_ret    = idx_prices.pct_change().dropna() if idx_prices is not None else None
    if idx_ret is None:
        log.warning("Index unavailable — beta/alpha will be None for all stocks")

    snapshot     = []
    fundamentals = {}
    success      = 0
    failed       = []

    for i, ticker in enumerate(universe, 1):
        meta = get_ticker_meta(ticker)
        log.info(f"[{i}/{len(universe)}] {ticker}")

        prices = _fetch_prices(ticker, meta)

        if prices is None or len(prices) < 20:
            log.warning(f"  {ticker}: no data — skipping")
            failed.append(ticker)
            time.sleep(THROTTLE_SECS)
            continue

        ret    = prices.pct_change().dropna()
        beta   = _compute_beta(ret, idx_ret)        if idx_ret is not None else None
        alpha  = _compute_alpha(ret, idx_ret, beta) if idx_ret is not None else None
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
            fundamentals[ticker] = _fetch_fundamentals(meta.get("yf", f"{ticker}.NS"))

        success += 1
        time.sleep(THROTTLE_SECS)

    # ── Write / merge snapshot ────────────────────────────────────────────────
    # BUG_12: zero-fetch runs (all sources blocked) must NOT overwrite the
    # existing snapshot. The midnight window failure is transient; the next
    # scheduled run will succeed.
    if not snapshot:
        log.warning(
            "Zero stocks fetched — preserving existing snapshot. "
            "Both yf/q1 and yf/q2 were rate-limited. "
            f"q1_blocked={_YF_Q1_BLOCKED}, q2_blocked={_YF_Q2_BLOCKED}"
        )
        gs.write_metadata(0, [], run_id)
        return {
            "run_id":   run_id,
            "success":  0,
            "failed":   len(failed),
            "duration": round((datetime.utcnow() - started).total_seconds(), 1),
            "status":   "blocked",
        }

    final_snapshot = snapshot
    final_funds    = dict(fundamentals)

    if extra_tickers and snapshot:
        # Triggered harvest: merge new data into existing snapshot
        existing        = gs.read("snapshot") or {}
        existing_stocks = existing.get("stocks", [])
        if existing_stocks:
            existing_map   = {s["ticker"]: s for s in existing_stocks}
            new_map        = {s["ticker"]: s for s in snapshot}
            merged         = {**existing_map, **new_map}
            final_snapshot = list(merged.values())
            kept           = len(existing_map) - sum(1 for t in existing_map if t in new_map)
            log.info(
                f"Merge: {len(new_map)} updated + {kept} kept = {len(final_snapshot)} total"
            )
        existing_f  = gs.read("fundamentals") or {}
        final_funds = {**existing_f.get("data", {}), **fundamentals}

    log.info("Writing to GitHub db/...")
    gs.write("snapshot", {
        "generated_at": datetime.utcnow().isoformat(),
        "run_id":       run_id,
        "count":        len(final_snapshot),
        "stocks":       final_snapshot,
    }, f"harvest snapshot: {success} stocks")
    gs.write("fundamentals", {
        "generated_at": datetime.utcnow().isoformat(),
        "data":         final_funds,
    })
    gs.write_metadata(success, [s["ticker"] for s in final_snapshot], run_id)

    duration = round((datetime.utcnow() - started).total_seconds(), 1)
    summary  = {
        "run_id":       run_id,
        "success":      success,
        "failed":       len(failed),
        "duration":     duration,
        "yf_q1_blocked": _YF_Q1_BLOCKED,
        "yf_q2_blocked": _YF_Q2_BLOCKED,
        "status":       "ok" if not failed else "partial",
    }
    log.info(f"Harvest done: {success} ok, {len(failed)} failed, {duration}s")
    return summary


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    log.info("=== Agent_Trader Harvest Runner (yfinance-only) ===")
    log.info(f"Scheduled harvest window: 18:30-23:30 UTC (midnight-5:30am IST)")

    conn = gs.test_connection()
    for k, v in conn.items():
        log.info(f"  {k}: {v}")

    if not all(
        any(w in str(v) for w in ("OK", "accessible", "valid", "found"))
        for v in conn.values()
    ):
        log.error("Connectivity check failed -- aborting")
        sys.exit(1)

    extra_tickers = []
    trigger = gs.read("holdings_trigger")
    if trigger and "tickers" in trigger:
        raw_tickers   = trigger["tickers"]
        normalized    = [normalize_ticker(t) for t in raw_tickers]
        extra_tickers = [t for t in normalized if t not in NIFTY50]
        if extra_tickers:
            log.info(f"Trigger: adding {len(extra_tickers)} non-Nifty50: {extra_tickers}")
        else:
            log.info("Trigger: all holdings in Nifty50 — full harvest only")
    else:
        log.info("No trigger file — full Nifty50 harvest")

    summary = harvest(extra_tickers=extra_tickers)
    log.info(f"Result: {summary}")

    if summary["success"] == 0:
        log.warning(
            "Zero stocks harvested. "
            f"yf/q1={'blocked' if _YF_Q1_BLOCKED else 'ok'}, "
            f"yf/q2={'blocked' if _YF_Q2_BLOCKED else 'ok'}. "
            "Existing snapshot preserved. Retry at next scheduled run."
        )
        sys.exit(1)