"""
core/data_loader.py
════════════════════════════════════════════════════════════════
Single source of truth for all dashboard data.

MOCK MODE (current):
  Returns realistic synthetic data. No secrets needed.

LIVE MODE (swap later):
  1. Install:  pip install cryptography yfinance
  2. Set Streamlit secrets:  FERNET_KEY, GITHUB_TOKEN, GITHUB_REPO
  3. Replace the three loader functions below with the LIVE versions
     that are commented out at the bottom of this file.

Data contract — every function returns the same shape regardless of
whether mock or live, so the pages never need to change.
════════════════════════════════════════════════════════════════
"""
from __future__ import annotations
import random
import math
from datetime import datetime, timedelta, date
from typing import Any

# ── reproducible randomness so hot-reload doesn't flicker ──
_rng = random.Random(42)

# ══════════════════════════════════════════════════════════════
# MASTER SYMBOL REGISTRY  (shared by mock & live)
# ══════════════════════════════════════════════════════════════
SYMBOL_META: dict[str, dict] = {
    "HDFCBANK":   {"name": "HDFC Bank",                   "sector": "Banking",        "cap": "Large"},
    "ICICIBANK":  {"name": "ICICI Bank",                   "sector": "Banking",        "cap": "Large"},
    "KOTAKBANK":  {"name": "Kotak Mahindra Bank",          "sector": "Banking",        "cap": "Large"},
    "AXISBANK":   {"name": "Axis Bank",                    "sector": "Banking",        "cap": "Large"},
    "SBIN":       {"name": "State Bank of India",          "sector": "Banking",        "cap": "Large"},
    "INDUSINDBK": {"name": "IndusInd Bank",                "sector": "Banking",        "cap": "Large"},
    "AUBANK":     {"name": "AU Small Finance Bank",        "sector": "Banking",        "cap": "Mid"},
    "BAJFINANCE": {"name": "Bajaj Finance",                "sector": "NBFC",           "cap": "Large"},
    "BAJAJFINSV": {"name": "Bajaj Finserv",                "sector": "NBFC",           "cap": "Large"},
    "SPANDANA":   {"name": "Spandana Sphoorty",            "sector": "NBFC",           "cap": "Small"},
    "JIOFIN":     {"name": "Jio Financial Services",       "sector": "Finance",        "cap": "Large"},
    "PFC":        {"name": "Power Finance Corporation",    "sector": "Finance",        "cap": "Large"},
    "RECLTD":     {"name": "REC Limited",                  "sector": "Finance",        "cap": "Large"},
    "IREDA":      {"name": "IREDA",                        "sector": "Finance",        "cap": "Mid"},
    "CAMS":       {"name": "CAMS",                         "sector": "Finance",        "cap": "Mid"},
    "HDFCLIFE":   {"name": "HDFC Life Insurance",          "sector": "Insurance",      "cap": "Large"},
    "SBILIFE":    {"name": "SBI Life Insurance",           "sector": "Insurance",      "cap": "Large"},
    "TCS":        {"name": "Tata Consultancy Services",    "sector": "IT",             "cap": "Large"},
    "INFY":       {"name": "Infosys",                      "sector": "IT",             "cap": "Large"},
    "HCLTECH":    {"name": "HCL Technologies",             "sector": "IT",             "cap": "Large"},
    "WIPRO":      {"name": "Wipro",                        "sector": "IT",             "cap": "Large"},
    "TECHM":      {"name": "Tech Mahindra",                "sector": "IT",             "cap": "Large"},
    "LTIM":       {"name": "LTIMindtree",                  "sector": "IT",             "cap": "Large"},
    "TATATECH":   {"name": "Tata Technologies",            "sector": "IT",             "cap": "Mid"},
    "RELIANCE":   {"name": "Reliance Industries",          "sector": "Energy",         "cap": "Large"},
    "ONGC":       {"name": "ONGC",                         "sector": "Energy",         "cap": "Large"},
    "BPCL":       {"name": "BPCL",                         "sector": "Energy",         "cap": "Large"},
    "ADANIGREEN": {"name": "Adani Green Energy",           "sector": "Energy",         "cap": "Large"},
    "COALINDIA":  {"name": "Coal India",                   "sector": "Mining",         "cap": "Large"},
    "NMDC":       {"name": "NMDC Limited",                 "sector": "Mining",         "cap": "Mid"},
    "HINDCOPPER": {"name": "Hindustan Copper",             "sector": "Metals",         "cap": "Mid"},
    "SANDUMA":    {"name": "Sandur Manganese",             "sector": "Metals",         "cap": "Small"},
    "HEG":        {"name": "HEG Limited",                  "sector": "Industrials",    "cap": "Mid"},
    "POWERGRID":  {"name": "Power Grid Corporation",       "sector": "Utilities",      "cap": "Large"},
    "NTPC":       {"name": "NTPC",                         "sector": "Utilities",      "cap": "Large"},
    "HINDUNILVR": {"name": "Hindustan Unilever",           "sector": "FMCG",           "cap": "Large"},
    "ITC":        {"name": "ITC Limited",                  "sector": "FMCG",           "cap": "Large"},
    "NESTLEIND":  {"name": "Nestle India",                 "sector": "FMCG",           "cap": "Large"},
    "BRITANNIA":  {"name": "Britannia Industries",         "sector": "FMCG",           "cap": "Large"},
    "TATACONSUM": {"name": "Tata Consumer",                "sector": "FMCG",           "cap": "Large"},
    "TITAN":      {"name": "Titan Company",                "sector": "Consumer",       "cap": "Large"},
    "ASIANPAINT": {"name": "Asian Paints",                 "sector": "Consumer",       "cap": "Large"},
    "DELHIVERY":  {"name": "Delhivery",                    "sector": "Logistics",      "cap": "Mid"},
    "MARUTI":     {"name": "Maruti Suzuki",                "sector": "Auto",           "cap": "Large"},
    "BAJAJ-AUTO": {"name": "Bajaj Auto",                   "sector": "Auto",           "cap": "Large"},
    "HEROMOTOCO": {"name": "Hero MotoCorp",                "sector": "Auto",           "cap": "Large"},
    "EICHERMOT":  {"name": "Eicher Motors",                "sector": "Auto",           "cap": "Large"},
    "M&M":        {"name": "Mahindra & Mahindra",          "sector": "Auto",           "cap": "Large"},
    "BHARATFORG": {"name": "Bharat Forge",                 "sector": "Auto",           "cap": "Mid"},
    "SUNPHARMA":  {"name": "Sun Pharmaceutical",           "sector": "Pharma",         "cap": "Large"},
    "DRREDDY":    {"name": "Dr. Reddy's Laboratories",     "sector": "Pharma",         "cap": "Large"},
    "CIPLA":      {"name": "Cipla",                        "sector": "Pharma",         "cap": "Large"},
    "DIVISLAB":   {"name": "Divi's Laboratories",          "sector": "Pharma",         "cap": "Large"},
    "LAURUSLABS": {"name": "Laurus Labs",                  "sector": "Pharma",         "cap": "Mid"},
    "APOLLOHOSP": {"name": "Apollo Hospitals",             "sector": "Healthcare",     "cap": "Large"},
    "TATASTEEL":  {"name": "Tata Steel",                   "sector": "Metals",         "cap": "Large"},
    "JSWSTEEL":   {"name": "JSW Steel",                    "sector": "Metals",         "cap": "Large"},
    "HINDALCO":   {"name": "Hindalco Industries",          "sector": "Metals",         "cap": "Large"},
    "NATIONALUM": {"name": "National Aluminium Co.",       "sector": "Metals",         "cap": "Mid"},
    "ADANIENT":   {"name": "Adani Enterprises",            "sector": "Conglomerate",   "cap": "Large"},
    "LT":         {"name": "Larsen & Toubro",              "sector": "Infrastructure", "cap": "Large"},
    "ADANIPORTS": {"name": "Adani Ports",                  "sector": "Infrastructure", "cap": "Large"},
    "RVNL":       {"name": "Rail Vikas Nigam",             "sector": "Infrastructure", "cap": "Mid"},
    "GPPL":       {"name": "Gujarat Pipavav Port",         "sector": "Infrastructure", "cap": "Small"},
    "ENGINERSIN": {"name": "Engineers India",              "sector": "Engineering",    "cap": "Mid"},
    "BHEL":       {"name": "Bharat Heavy Electricals",     "sector": "Engineering",    "cap": "Large"},
    "TRITURBINE": {"name": "Triveni Turbine",              "sector": "Engineering",    "cap": "Small"},
    "ULTRACEMCO": {"name": "UltraTech Cement",             "sector": "Cement",         "cap": "Large"},
    "GRASIM":     {"name": "Grasim Industries",            "sector": "Cement",         "cap": "Large"},
    "BHARTIARTL": {"name": "Bharti Airtel",                "sector": "Telecom",        "cap": "Large"},
    "IRCTC":      {"name": "Indian Railway Catering",      "sector": "Travel",         "cap": "Large"},
    "HAL":        {"name": "Hindustan Aeronautics",        "sector": "Defence",        "cap": "Large"},
    "MAZDOCK":    {"name": "Mazagon Dock Shipbuilders",    "sector": "Defence",        "cap": "Mid"},
    "BDL":        {"name": "Bharat Dynamics",              "sector": "Defence",        "cap": "Mid"},
    "ZENTEC":     {"name": "Zen Technologies",             "sector": "Defence",        "cap": "Small"},
    "PARAS":      {"name": "Paras Defence",                "sector": "Defence",        "cap": "Small"},
    "RELINFRA":   {"name": "Reliance Infrastructure",      "sector": "Infrastructure", "cap": "Mid"},
}

# Default holdings (what the system currently tracks)
DEFAULT_HOLDINGS = [
    "HDFCBANK", "TCS", "RELIANCE", "BAJFINANCE", "GPPL", "IREDA", "HAL",
    "TATASTEEL", "ADANIGREEN", "BHARTIARTL", "INFY", "NTPC", "PFC",
    "RVNL", "BDL", "IRCTC", "ZENTEC", "MAZDOCK", "RECLTD", "AUBANK",
    "BAJAJFINSV", "HDFCLIFE", "SUNPHARMA", "LT", "HINDALCO", "COALINDIA",
]

# ══════════════════════════════════════════════════════════════
# HELPER — deterministic "random" for each symbol
# ══════════════════════════════════════════════════════════════
def _sym_rng(sym: str, lo: float, hi: float, seed_offset: int = 0) -> float:
    r = random.Random(hash(sym) + seed_offset)
    return lo + r.random() * (hi - lo)


# ══════════════════════════════════════════════════════════════
# PUBLIC API
# ══════════════════════════════════════════════════════════════

def _mock_get_harvest_meta() -> dict[str, Any]:
    """Last harvest run metadata (mock data)."""
    return {
        "run_id": "891201c5",
        "timestamp": "2026-03-01T01:51:14Z",
        "timestamp_ist": "01 Mar 2026 · 07:21 IST",
        "success": 77,
        "failed": 2,
        "duration_s": 498.9,
        "failed_symbols": ["ZOMATO", "TATAMOTORS"],
        "universe": 79,
        "azure_region": "westus",
        "harvest_mode": "auto",
        "yf_q1_blocked": False,
        "yf_q2_blocked": False,
        "idx_q1_blocked": False,
        "idx_q2_blocked": False,
        "db_files": ["snapshot.enc", "fundamentals.enc", "metadata.enc",
                     "holdings_trigger.enc", "dryrun.enc"],
        "github_repo": "SubhasishSahu/Avito",
        "throttle_secs": 1.2,
    }


def get_run_history() -> list[dict]:
    """Recent harvest runs."""
    return [
        {
            "run_id": "c0a860b2", "time_utc": "01:12", "time_ist": "06:42",
            "ok": 77, "failed": 12, "duration_s": 631, "region": "eastus",
            "status": "partial",
            "note": "12 delisted symbols (ZOMATO, TATAMOTORS + 10 bad tickers)",
        },
        {
            "run_id": "37dee6dc", "time_utc": "01:28", "time_ist": "06:58",
            "ok": 0, "failed": 79, "duration_s": 100, "region": "northcentralus",
            "status": "blocked",
            "note": "429 on first request — both circuit breakers tripped",
        },
        {
            "run_id": "891201c5", "time_utc": "01:42", "time_ist": "07:12",
            "ok": 77, "failed": 2, "duration_s": 499, "region": "westus",
            "status": "ok",
            "note": "Clean run — 2 delisted symbols skipped",
        },
    ]


def _mock_get_nifty_series(sessions: int = 742) -> list[dict]:
    """Simulated Nifty50 OHLCV series, newest last."""
    prices = []
    p = 15_500.0
    base_date = date(2026, 3, 1)
    trading_days: list[date] = []
    d = base_date - timedelta(days=sessions * 2)
    while len(trading_days) < sessions:
        if d.weekday() < 5:          # Mon–Fri
            trading_days.append(d)
        d += timedelta(days=1)

    r = random.Random(99)
    for i, td in enumerate(trading_days):
        trend = 0.00038
        vol = 0.011
        p *= 1 + trend + (r.random() - 0.48) * vol
        p = max(14_000, min(28_000, p))
        hi = p * (1 + r.random() * 0.008)
        lo = p * (1 - r.random() * 0.008)
        prices.append({
            "date": td.isoformat(),
            "open": round(p * (1 - r.random() * 0.003), 2),
            "high": round(hi, 2),
            "low":  round(lo, 2),
            "close": round(p, 2),
            "volume": int(r.random() * 2e9 + 5e8),
        })
    return prices


def _mock_get_snapshot() -> list[dict]:
    """Per-symbol data for all 77 harvested stocks."""
    rows = []
    for sym, meta in SYMBOL_META.items():
        base_price = _sym_rng(sym, 50, 8000)
        pct_1m     = round(_sym_rng(sym, -18, 22, 1), 1)
        pct_3m     = round(_sym_rng(sym, -25, 35, 2), 1)
        pct_1y     = round(_sym_rng(sym, -30, 80, 3), 1)
        hi52       = base_price * _sym_rng(sym, 1.05, 1.5, 4)
        lo52       = base_price * _sym_rng(sym, 0.55, 0.92, 5)
        cur        = base_price
        rsi        = round(_sym_rng(sym, 22, 82, 6))
        row_count  = 742 if meta["cap"] == "Large" else (
                     int(_sym_rng(sym, 580, 741, 7)) if meta["cap"] == "Mid"
                     else int(_sym_rng(sym, 400, 620, 8)))
        rows.append({
            "symbol":    sym,
            "name":      meta["name"],
            "sector":    meta["sector"],
            "cap":       meta["cap"],
            "price":     round(cur, 2),
            "pct_1m":    pct_1m,
            "pct_3m":    pct_3m,
            "pct_1y":    pct_1y,
            "hi_52w":    round(hi52, 2),
            "lo_52w":    round(lo52, 2),
            "rsi":       rsi,
            "row_count": row_count,
            "in_holdings": sym in DEFAULT_HOLDINGS,
        })
    return rows


def _mock_get_holdings() -> list[str]:
    """Current holdings_trigger list."""
    return list(DEFAULT_HOLDINGS)


def get_signals(snapshot: list[dict]) -> list[dict]:
    """Derive trading signals from snapshot data."""
    signals = []
    for row in snapshot:
        sym  = row["symbol"]
        rsi  = row["rsi"]
        p1m  = row["pct_1m"]
        cur  = row["price"]
        hi52 = row["hi_52w"]
        lo52 = row["lo_52w"]

        vs_hi = round((cur - hi52) / hi52 * 100, 1)
        vs_lo = round((cur - lo52) / lo52 * 100, 1)

        if rsi < 35 and p1m < -5:
            signal, strength, reason = "BUY",   3, "RSI oversold + price dip"
        elif rsi < 45 and p1m < 0:
            signal, strength, reason = "BUY",   2, "RSI low"
        elif rsi > 72:
            signal, strength, reason = "SELL",  2, "RSI overbought"
        elif rsi > 65 and p1m > 12:
            signal, strength, reason = "SELL",  3, "Extended run + high RSI"
        elif vs_hi > -3:
            signal, strength, reason = "WATCH", 2, "Near 52W high"
        elif vs_lo < 5:
            signal, strength, reason = "WATCH", 2, "Near 52W low"
        else:
            signal, strength, reason = "HOLD",  1, "Neutral"

        signals.append({**row, "signal": signal, "strength": strength,
                         "reason": reason, "vs_hi_52w": vs_hi, "vs_lo_52w": vs_lo})
    return signals


# ══════════════════════════════════════════════════════════════
# ── LIVE MODE — active with mock fallback ─────────────────────
# Attempts to read from GitHub-encrypted store.
# Falls back to mock data gracefully so the page always renders.
# ══════════════════════════════════════════════════════════════
import json as _json, base64 as _base64

def _is_live() -> bool:
    """True only when FERNET_KEY and GITHUB_TOKEN are both configured."""
    try:
        import streamlit as _st
        return bool(_st.secrets.get("FERNET_KEY") and _st.secrets.get("GITHUB_TOKEN"))
    except Exception:
        return False

def _fernet():
    import streamlit as _st
    from cryptography.fernet import Fernet
    return Fernet(_st.secrets["FERNET_KEY"].encode())

def _decrypt_json(b64_enc: str) -> Any:
    raw = _base64.b64decode(b64_enc.encode())
    return _json.loads(_fernet().decrypt(raw))

def _fetch_enc_file(path: str) -> Any:
    import requests, streamlit as _st
    token = _st.secrets["GITHUB_TOKEN"]
    repo  = _st.secrets.get("GITHUB_REPO", "SubhasishSahu/Avito")
    url   = f"https://api.github.com/repos/{repo}/contents/db/{path}"
    r = requests.get(url, headers={"Authorization": f"token {token}"}, timeout=10)
    r.raise_for_status()
    return _decrypt_json(r.json()["content"].replace("\n", ""))

# Public API — tries live GitHub fetch first, falls back to mock if unavailable.
def get_harvest_meta() -> dict:
    if _is_live():
        try:
            return _fetch_enc_file("metadata.enc")
        except Exception:
            pass
    return _mock_get_harvest_meta()

def get_snapshot() -> list:
    if _is_live():
        try:
            return _fetch_enc_file("snapshot.enc")
        except Exception:
            pass
    return _mock_get_snapshot()

def get_holdings() -> list:
    if _is_live():
        try:
            return _fetch_enc_file("holdings_trigger.enc")
        except Exception:
            pass
    return list(DEFAULT_HOLDINGS)

def get_nifty_series(sessions: int = 742) -> list:
    if _is_live():
        try:
            import yfinance as yf
            df = yf.Ticker("^NSEI").history(period="3y", interval="1d")
            return [{"date": str(r.Index.date()), "open": r.Open, "high": r.High,
                     "low": r.Low, "close": r.Close, "volume": r.Volume}
                    for r in df.itertuples()]
        except Exception:
            pass
    return _mock_get_nifty_series(sessions)
# ══════════════════════════════════════════════════════════════


# ══════════════════════════════════════════════════════════════
# SYMBOL RESOLVER  (used by P6 Holdings Editor)
# ══════════════════════════════════════════════════════════════
_NAME_MAP: dict[str, str] = {
    "hdfc bank": "HDFCBANK", "hdfc": "HDFCBANK",
    "icici bank": "ICICIBANK", "icici": "ICICIBANK",
    "kotak": "KOTAKBANK", "kotak bank": "KOTAKBANK",
    "sbi": "SBIN", "state bank": "SBIN", "state bank of india": "SBIN",
    "axis bank": "AXISBANK", "axis": "AXISBANK",
    "bajaj finance": "BAJFINANCE", "bajaj finserv": "BAJAJFINSV",
    "infosys": "INFY", "reliance": "RELIANCE", "reliance industries": "RELIANCE",
    "tcs": "TCS", "tata consultancy": "TCS",
    "wipro": "WIPRO", "hcl": "HCLTECH", "hcl technologies": "HCLTECH",
    "tech mahindra": "TECHM", "maruti": "MARUTI", "maruti suzuki": "MARUTI",
    "tata steel": "TATASTEEL", "tata motors": "TATAMOTORS",
    "hdfc life": "HDFCLIFE", "sbi life": "SBILIFE",
    "sun pharma": "SUNPHARMA", "sun pharmaceutical": "SUNPHARMA",
    "airtel": "BHARTIARTL", "bharti airtel": "BHARTIARTL",
    "ntpc": "NTPC", "power grid": "POWERGRID",
    "ongc": "ONGC", "coal india": "COALINDIA",
    "itc": "ITC", "titan": "TITAN", "asian paints": "ASIANPAINT",
    "hindustan unilever": "HINDUNILVR", "hul": "HINDUNILVR",
    "nestle": "NESTLEIND", "britannia": "BRITANNIA",
    "apollo hospitals": "APOLLOHOSP", "apollo": "APOLLOHOSP",
    "dr reddy": "DRREDDY", "dr reddys": "DRREDDY",
    "cipla": "CIPLA", "zomato": "ZOMATO",
    "adani enterprises": "ADANIENT", "adani ports": "ADANIPORTS",
    "adani green": "ADANIGREEN", "larsen": "LT", "l&t": "LT",
    "jsw steel": "JSWSTEEL", "hindalco": "HINDALCO",
    "hal": "HAL", "hindustan aeronautics": "HAL",
    "bajaj auto": "BAJAJ-AUTO", "hero": "HEROMOTOCO", "hero motocorp": "HEROMOTOCO",
    "mahindra": "M&M", "eicher": "EICHERMOT",
    "grasim": "GRASIM", "ultratech": "ULTRACEMCO",
    "nmdc": "NMDC", "irctc": "IRCTC",
    "jio financial": "JIOFIN", "jio": "JIOFIN",
    "rvnl": "RVNL", "bhel": "BHEL", "pfc": "PFC", "rec": "RECLTD",
    "ireda": "IREDA", "gppl": "GPPL", "hal": "HAL",
    "mazdock": "MAZDOCK", "bdl": "BDL", "zentec": "ZENTEC",
}


def resolve_symbol(raw: str) -> dict:
    """
    Resolve a free-form stock name or symbol to a structured record.
    Returns {"symbol":..., "name":..., "sector":..., "cap":..., "status": "verified"|"unknown"}
    """
    clean = raw.strip().upper().replace(".", "").replace(" ", "")
    if clean in SYMBOL_META:
        return {"symbol": clean, **SYMBOL_META[clean], "status": "verified"}

    lc = raw.strip().lower()
    # exact name map
    mapped = _NAME_MAP.get(lc)
    if mapped and mapped in SYMBOL_META:
        return {"symbol": mapped, **SYMBOL_META[mapped], "status": "verified"}

    # partial
    for k, v in _NAME_MAP.items():
        if lc in k or k in lc:
            if v in SYMBOL_META:
                return {"symbol": v, **SYMBOL_META[v], "status": "verified"}

    # name search in registry
    for sym, meta in SYMBOL_META.items():
        if lc in meta["name"].lower() or meta["name"].lower() in lc:
            return {"symbol": sym, **meta, "status": "verified"}

    return {
        "symbol": clean or raw.strip().upper(),
        "name": raw.strip(), "sector": "Unknown",
        "cap": "?", "status": "unknown",
    }