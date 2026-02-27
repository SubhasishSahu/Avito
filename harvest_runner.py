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
  BUG_12   Triggered harvest overwrote snapshot with 0 stocks
           -> added snapshot merge: existing data preserved on failure
  BUG_13   Triggered harvest fetched only holdings, lost Nifty50 peers
           -> always harvest full Nifty50 + extra tickers on top
  BUG_14   Stooq and Yahoo block datacenter IPs via TLS fingerprinting
           -> added curl_cffi multi-browser rotation: Chrome/Safari/Firefox
           -> added BSE (.bo) as alternate Stooq suffix alongside NSE (.ns)
           -> 4 distinct TLS ClientHello signatures tried per ticker
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

# ---------------------------------------------------------------------------
# BROKER_TICKER_MAP
# Maps broker-export ticker formats to canonical NSE symbols.
#
# Why this exists:
#   Mobile broker apps (Zerodha, Groww, Upstox etc.) export holdings with
#   suffixed tickers like "HDFCBANKEQ", "TATCHEEQ" etc. The "EQ" suffix
#   denotes the equity series on NSE but is not part of the trading symbol.
#   Some apps also use older/internal names that differ from current NSE symbols.
#
# Structure: broker_ticker -> (nse_symbol, company_name, sector, stooq_sym)
#   - nse_symbol:   canonical NSE symbol used for price fetch
#   - company_name: human-readable display name
#   - sector:       sector for peer grouping
#   - stooq_sym:    lowercase symbol for Stooq CSV API (None = use nse_symbol.lower()+".ns")
#
# Confidence notes (in comments):
#   HIGH   = verified against NSE symbol list
#   MEDIUM = likely correct, verify if this stock is important to you
#   LOW    = ambiguous -- marked with ⚠️, please confirm and update
# ---------------------------------------------------------------------------
BROKER_TICKER_MAP = {
    # ── Nifty50 EQ-suffix variants (strip EQ -> standard symbol) ──────────────
    "HDFCBANKEQ":   ("HDFCBANK",   "HDFC Bank",              "Financial Services", None),
    "ICICIBANKNEQ": ("ICICIBANK",  "ICICI Bank",             "Financial Services", None),
    "KOTAKBANKEQ":  ("KOTAKBANK",  "Kotak Mahindra Bank",    "Financial Services", None),
    "AXISBANKEQ":   ("AXISBANK",   "Axis Bank",              "Financial Services", None),
    "SBINEQ":       ("SBIN",       "State Bank of India",    "Financial Services", None),
    "BAJFINANCEEQ": ("BAJFINANCE", "Bajaj Finance",          "Financial Services", None),
    "BAJAJFINSVQ":  ("BAJAJFINSV", "Bajaj Finserv",          "Financial Services", None),
    "HDFCLIFEEQ":   ("HDFCLIFE",   "HDFC Life Insurance",    "Financial Services", None),
    "SBILIFEQ":     ("SBILIFE",    "SBI Life Insurance",     "Financial Services", None),
    "INDUSINDBKEQ": ("INDUSINDBK", "IndusInd Bank",          "Financial Services", None),
    "TCSEQ":        ("TCS",        "Tata Consultancy",       "IT",                 None),
    "INFYEQ":       ("INFY",       "Infosys",                "IT",                 None),
    "HCLTECHEQ":    ("HCLTECH",    "HCL Technologies",       "IT",                 None),
    "WIPROEQ":      ("WIPRO",      "Wipro",                  "IT",                 None),
    "TECHMEQ":      ("TECHM",      "Tech Mahindra",          "IT",                 None),
    "LTIMEQ":       ("LTIM",       "LTIMindtree",            "IT",                 None),
    "RELIANCEEQ":   ("RELIANCE",   "Reliance Industries",    "Oil & Gas",          None),
    "ONGCEQ":       ("ONGC",       "ONGC",                   "Oil & Gas",          None),
    "BPCLEQ":       ("BPCL",       "BPCL",                   "Oil & Gas",          None),
    "COALINDIAEQ":  ("COALINDIA",  "Coal India",             "Oil & Gas",          None),
    "POWERGRIDQ":   ("POWERGRID",  "Power Grid Corp",        "Oil & Gas",          None),
    "NTPCEQ":       ("NTPC",       "NTPC",                   "Oil & Gas",          None),
    "HINDUNILVREQ": ("HINDUNILVR", "Hindustan Unilever",     "Consumer",           None),
    "ITCEQ":        ("ITC",        "ITC",                    "Consumer",           None),
    "NESTLEINDEQ":  ("NESTLEIND",  "Nestle India",           "Consumer",           None),
    "BRITANNIAEQ":  ("BRITANNIA",  "Britannia Industries",   "Consumer",           None),
    "TATACONSUMEQ": ("TATACONSUM", "Tata Consumer Products", "Consumer",           None),
    "TITANEQ":      ("TITAN",      "Titan Company",          "Consumer",           None),
    "ASIANPAINTEQ": ("ASIANPAINT", "Asian Paints",           "Consumer",           None),
    "ZOMATOEQ":     ("ZOMATO",     "Zomato",                 "Consumer",           None),
    "MARUTIEQ":     ("MARUTI",     "Maruti Suzuki",          "Auto",               None),
    "BAJAJ-AUTOEQ": ("BAJAJ-AUTO", "Bajaj Auto",             "Auto",               None),
    "HEROMOTOCOEQ": ("HEROMOTOCO", "Hero MotoCorp",          "Auto",               None),
    "EICHERMOTEQ":  ("EICHERMOT",  "Eicher Motors",          "Auto",               None),
    "TATAMOTORSEQ": ("TATAMOTORS", "Tata Motors",            "Auto",               None),
    "SUNPHARMAEQ":  ("SUNPHARMA",  "Sun Pharmaceutical",     "Pharma",             None),
    "DRREDYEQ":     ("DRREDDY",    "Dr Reddys Labs",         "Pharma",             None),
    "CIPLAYEQ":     ("CIPLA",      "Cipla",                  "Pharma",             None),
    "DIVISLABEQ":   ("DIVISLAB",   "Divis Laboratories",     "Pharma",             None),
    "APOLLOHOSPEQ": ("APOLLOHOSP", "Apollo Hospitals",       "Pharma",             None),
    "TATASTEELEQ":  ("TATASTEEL",  "Tata Steel",             "Metals",             None),
    "JSWSTEELEQ":   ("JSWSTEEL",   "JSW Steel",              "Metals",             None),
    "HINDALCOEQ":   ("HINDALCO",   "Hindalco Industries",    "Metals",             None),
    "ADANIEQ":      ("ADANIENT",   "Adani Enterprises",      "Metals",             None),
    "LTEQ":         ("LT",         "Larsen and Toubro",      "Infrastructure",     None),
    "ADANIPORTSEQ": ("ADANIPORTS", "Adani Ports",            "Infrastructure",     None),
    "ULTRACEMCOEQ": ("ULTRACEMCO", "UltraTech Cement",       "Cement",             None),
    "GRASIMEQ":     ("GRASIM",     "Grasim Industries",      "Cement",             None),
    "BHARTIARTLEQ": ("BHARTIARTL", "Bharti Airtel",          "Telecom",            None),

    # ── User portfolio non-Nifty50 holdings ───────────────────────────────────
    # HIGH confidence
    "ADANIGREENEQ": ("ADANIGREEN",  "Adani Green Energy",          "Energy",            "adanigreen.ns"),
    "MUNDRAPORTEQ": ("ADANIPORTS",  "Adani Ports & SEZ",           "Infrastructure",    "adaniports.ns"),
    "AUBANKEQ":     ("AUBANK",      "AU Small Finance Bank",       "Financial Services","aubank.ns"),
    "BDLEQ":        ("BDL",         "Bharat Dynamics Ltd",         "Defence",           "bdl.ns"),
    "BHAELEEQ":     ("BHEL",        "Bharat Heavy Electricals",    "Capital Goods",     "bhel.ns"),
    "BHAFOREQ":     ("BHARATFORG",  "Bharat Forge",                "Auto Ancillary",    "bharatforg.ns"),
    "CAMSEQ":       ("CAMS",        "Computer Age Mgmt Services",  "Financial Services","cams.ns"),
    "ENGINDEQ":     ("ENGINERSIN",  "Engineers India",             "Infrastructure",    "enginersin.ns"),
    "GUJMINEQ":     ("GMDC",        "Gujarat Mineral Dev Corp",    "Metals",            "gmdc.ns"),
    "GPPLEQ":       ("GPPL",        "Gujarat Pipavav Port",        "Infrastructure",    "gppl.ns"),
    "HEGLTDEQ":     ("HEG",         "HEG Limited",                 "Metals",            "heg.ns"),
    "HALEQ":        ("HAL",         "Hindustan Aeronautics",       "Defence",           "hal.ns"),
    "HINCOPEQ":     ("HINDCOPPER",  "Hindustan Copper",            "Metals",            "hindcopper.ns"),
    "IRCTCEQ":      ("IRCTC",       "Indian Railway Catering",     "Consumer",          "irctc.ns"),
    "IREDAEQ":      ("IREDA",       "Indian Renewable Energy Dev", "Energy",            "ireda.ns"),
    "IONEXCEQ":     ("IONEXCHANGE", "Ion Exchange India",          "Chemicals",         "ionexchange.ns"),
    "JIOFINEQ":     ("JIOFIN",      "Jio Financial Services",      "Financial Services","jiofin.ns"),
    "LAURUSLABSEQ": ("LAURUSLABS",  "Laurus Labs",                 "Pharma",            "lauruslabs.ns"),
    "MAZDOCKEQ":    ("MAZDOCK",     "Mazagon Dock Shipbuilders",   "Defence",           "mazdock.ns"),
    "NATALUEQ":     ("NATIONALUM",  "National Aluminium Company",  "Metals",            "nationalum.ns"),
    "NMDCEQ":       ("NMDC",        "NMDC",                        "Metals",            "nmdc.ns"),
    "PARASEQ":      ("PARAS",       "Paras Defence & Space Tech",  "Defence",           "paras.ns"),
    "POWFINEQ":     ("PFC",         "Power Finance Corporation",   "Financial Services","pfc.ns"),
    "RVNLEQ":       ("RVNL",        "Rail Vikas Nigam",            "Infrastructure",    "rvnl.ns"),
    "RECLTDEQ":     ("RECLTD",      "REC Limited",                 "Financial Services","recltd.ns"),
    "RELINDEQ":     ("RELINFRA",    "Reliance Infrastructure",     "Infrastructure",    "relinfra.ns"),
    "SPANDANAEQ":   ("SPANDANA",    "Spandana Sphoorty Financial", "Financial Services","spandana.ns"),
    "SANDUMAEQ":    ("SANDUMA",     "Sandur Manganese & Iron",     "Metals",            "sanduma.ns"),
    "TATCHEEQ":     ("TATATECH",    "Tata Technologies",           "IT",                "tatatech.ns"),
    "TRITURBINEEQ": ("TRITURBINE",  "Triveni Turbine",             "Capital Goods",     "triturbine.ns"),
    "ZETECHEQ":     ("ZENTEC",      "Zen Technologies",            "Defence",           "zentec.ns"),

    # MEDIUM confidence
    "HDFCMFGETFEQ": ("HDFCNIFETF", "HDFC Nifty 50 ETF",          "ETF",               "hdfcnifetf.ns"),
    "LGEINDIAEQ":   ("LGINDIA",    "LG Balakrishnan & Bros",      "Auto Ancillary",    "lgindia.ns"),
    "GOLTELEQ":     ("GOLTELE",    "Goldiam International",       "Consumer",          "goltele.ns"),
    "OMDCEQ":       ("OMDC",       "Orissa Minerals Dev Corp",    "Metals",            "omdc.ns"),
    "TATIROEQ":     ("TATASTEEL",  "Tata Steel",                  "Metals",            "tatasteel.ns"),

    # LOW confidence -- ⚠️ please verify these 5 against your actual holdings
    "DEWHOUEQ":     ("DELHIVERY",  "Delhivery",                   "Logistics",         "delhivery.ns"),   # ⚠️ DEWHOUS unclear
    "GOLINTEQ":     ("GOLDENTEK",  "Goldentek",                   "Consumer",          None),             # ⚠️ symbol unconfirmed
    "NAVBHAEQ":     ("NAVINFRA",   "Nav Bharat Ventures",         "Metals",            None),             # ⚠️ ambiguous
    "ROYAIREQ":     ("ROYALIND",   "Royal Industries",            "Unknown",           None),             # ⚠️ unclear
    "STABANEQ":     ("STABAN",     "Standard Industries",         "Textiles",          "staban.ns"),      # ⚠️ uncommon
}


def normalize_ticker(raw: str) -> str:
    """
    Convert a broker-export ticker to canonical NSE symbol.

    Resolution order:
      1. Direct lookup in BROKER_TICKER_MAP  (e.g. HALEQ -> HAL)
      2. Already a canonical Nifty50 symbol  (pass through)
      3. Strip trailing EQ/BE/BL/N1/N2 series suffix, re-check maps
      4. If suffix was stripped but still unknown, return without suffix
      5. Return uppercase as-is (completely unknown ticker)
    """
    import re
    t = raw.strip().upper()

    # 1. Direct map lookup
    if t in BROKER_TICKER_MAP:
        return BROKER_TICKER_MAP[t][0]

    # 2. Already canonical Nifty50
    if t in NIFTY50:
        return t

    # 3 & 4. Strip common broker suffixes and re-check
    stripped = re.sub(r"(EQ|BE|BL|N1|N2)$", "", t).rstrip("-")
    if stripped != t:
        if stripped in NIFTY50:
            return stripped
        if stripped in BROKER_TICKER_MAP:
            return BROKER_TICKER_MAP[stripped][0]
        # Suffix stripped but still unknown -> return without suffix
        # (harvest will attempt Stooq with this symbol)
        return stripped

    # 5. Completely unknown, return as-is
    return t


def get_ticker_meta(nse_symbol: str) -> dict:
    """
    Return metadata dict for any NSE symbol.
    Checks NIFTY50 first, then synthesises from BROKER_TICKER_MAP.
    Returns minimal dict if unknown.
    """
    if nse_symbol in NIFTY50:
        meta = dict(NIFTY50[nse_symbol])
        meta["stooq"] = meta.get("stooq", f"{nse_symbol.lower()}.ns")
        return meta

    # Search BROKER_TICKER_MAP values for this NSE symbol
    for broker_t, (sym, name, sector, stooq) in BROKER_TICKER_MAP.items():
        if sym == nse_symbol:
            return {
                "name":   name,
                "sector": sector,
                "stooq":  stooq or f"{nse_symbol.lower()}.ns",
                "yf":     f"{nse_symbol}.NS",
            }

    return {
        "name":   nse_symbol,
        "sector": "Unknown",
        "stooq":  f"{nse_symbol.lower()}.ns",
        "yf":     f"{nse_symbol}.NS",
    }


THROTTLE_SECS = 0.5
PRICE_PERIOD  = "3y"


# ---------------------------------------------------------------------------
# Multi-browser TLS fingerprint rotation engine
#
# WHY: Stooq and Yahoo Finance detect and block datacenter IPs using TLS
# fingerprinting -- they inspect the ClientHello cipher suites, extension
# order, and GREASE values to identify non-browser clients.
#
# HOW: curl_cffi replays exact browser TLS handshakes. Each impersonation
# target produces a distinct ClientHello that is indistinguishable from a
# real browser at the TLS layer. Rotating across Chrome, Safari, and Firefox
# means even if one fingerprint is flagged, the others succeed.
#
# ROTATION ORDER per request (4 attempts total):
#   Attempt 1: Chrome 120  (Win) -- most common desktop browser worldwide
#   Attempt 2: Safari 15.5 (macOS) -- distinct cipher suite order vs Chrome
#   Attempt 3: Firefox 110  -- different TLS extension order entirely
#   Attempt 4: Chrome 107  -- older Chrome, different GREASE pattern
#
# Each has a distinct User-Agent string that matches the TLS fingerprint,
# so both layers (HTTP + TLS) are consistent.
# ---------------------------------------------------------------------------

# (impersonation_target, User-Agent string)
_BROWSER_PROFILES = [
    (
        "chrome120",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36",
    ),
    (
        "safari15_5",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 12_4) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) "
        "Version/15.5 Safari/605.1.15",
    ),
    (
        "firefox110",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:110.0) "
        "Gecko/20100101 Firefox/110.0",
    ),
    (
        "chrome107",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/107.0.0.0 Safari/537.36",
    ),
]

# Detect curl_cffi once at import time
try:
    from curl_cffi import requests as cffi_requests
    _CURL_CFFI_OK = True
    log.info("curl_cffi available -- TLS browser impersonation enabled")
except ImportError:
    _CURL_CFFI_OK = False
    log.warning("curl_cffi not installed -- falling back to plain requests (less evasion)")


def _cffi_get(url: str, params: dict, impersonate: str, ua: str, timeout: int = 20):
    """Single curl_cffi GET with a specific browser impersonation."""
    from curl_cffi import requests as cffi_requests
    return cffi_requests.get(
        url,
        params=params,
        headers={"User-Agent": ua, "Accept": "text/html,*/*;q=0.9"},
        impersonate=impersonate,
        timeout=timeout,
    )


def _plain_get(url: str, params: dict, ua: str, timeout: int = 20):
    """Fallback plain requests GET when curl_cffi not available."""
    return requests.get(
        url,
        params=params,
        headers={"User-Agent": ua},
        timeout=timeout,
    )


def _rotating_get(url: str, params: dict, label: str, timeout: int = 20):
    """
    Try each browser profile in rotation until one succeeds.
    Returns (response_text, profile_name) or (None, None).
    """
    for i, (impersonate, ua) in enumerate(_BROWSER_PROFILES):
        try:
            if _CURL_CFFI_OK:
                r = _cffi_get(url, params, impersonate, ua, timeout)
            else:
                r = _plain_get(url, params, ua, timeout)

            if r.status_code == 200:
                text = r.text.strip()
                if text and "<html" not in text.lower() and "No data" not in text:
                    log.debug(f"  {label}: success with {impersonate}")
                    return text, impersonate
                else:
                    log.debug(f"  {label} [{impersonate}]: empty/html response")
            elif r.status_code == 429:
                log.debug(f"  {label} [{impersonate}]: 429 rate-limited, rotating")
                time.sleep(1.5)
            else:
                log.debug(f"  {label} [{impersonate}]: HTTP {r.status_code}")

        except Exception as e:
            log.debug(f"  {label} [{impersonate}]: {type(e).__name__}: {e}")
            if i < len(_BROWSER_PROFILES) - 1:
                time.sleep(0.5)

    return None, None


# ---------------------------------------------------------------------------
# Source 1: Stooq CSV  (primary)
# Tries both NSE (.ns) and BSE (.bo) suffixes with full browser rotation.
# ---------------------------------------------------------------------------

def _parse_stooq_csv(text: str) -> pd.Series | None:
    """Parse Stooq CSV response into a price Series."""
    try:
        df = pd.read_csv(io.StringIO(text), parse_dates=["Date"])
        if df.empty or "Close" not in df.columns:
            return None
        df = df.dropna(subset=["Date", "Close"]).sort_values("Date")
        prices = df.set_index("Date")["Close"].astype(float)
        prices.index.name = "Date"
        return prices if len(prices) >= 20 else None
    except Exception:
        return None


def _fetch_prices_stooq(base_sym: str, label: str) -> pd.Series | None:
    """
    Fetch 3y of daily close prices from Stooq with browser rotation.
    Tries NSE (.ns) first, then BSE (.bo) as alternate exchange suffix.
    Each suffix attempt rotates across Chrome/Safari/Firefox TLS fingerprints.
    """
    end_dt   = datetime.today()
    start_dt = end_dt - timedelta(days=3 * 365 + 60)

    # Stooq suffix variants: .ns = NSE India, .bo = BSE India
    # Strip any existing suffix before building variants
    raw = base_sym.lower().replace(".ns", "").replace(".bo", "").rstrip(".")
    suffixes = [".ns", ".bo"]

    url = "https://stooq.com/q/d/l/"

    for suffix in suffixes:
        sym = raw + suffix
        params = {
            "s":  sym,
            "d1": start_dt.strftime("%Y%m%d"),
            "d2": end_dt.strftime("%Y%m%d"),
            "i":  "d",
        }
        text, profile = _rotating_get(url, params, f"{label}[stooq{suffix}]")
        if text:
            prices = _parse_stooq_csv(text)
            if prices is not None:
                log.info(f"  {label}: {len(prices)} rows via Stooq{suffix} [{profile}] ✓")
                return prices
            log.debug(f"  {label} Stooq{suffix}: got response but no usable data")

    return None


def _fetch_index_stooq() -> pd.Series | None:
    """Fetch Nifty50 index from Stooq (^nsei)."""
    end_dt   = datetime.today()
    start_dt = end_dt - timedelta(days=3 * 365 + 60)
    url    = "https://stooq.com/q/d/l/"
    params = {"s": "^nsei", "d1": start_dt.strftime("%Y%m%d"),
              "d2": end_dt.strftime("%Y%m%d"), "i": "d"}
    text, profile = _rotating_get(url, params, "Nifty50-index[stooq]")
    if text:
        prices = _parse_stooq_csv(text)
        if prices is not None:
            log.info(f"  Nifty50-index: {len(prices)} rows via Stooq [{profile}] ✓")
            return prices
    return None


# ---------------------------------------------------------------------------
# Source 2: yfinance  (fallback)
# yfinance internally uses requests; wrap with curl_cffi session if available
# so it also benefits from browser TLS impersonation.
# ---------------------------------------------------------------------------

def _fetch_prices_yf(yf_ticker: str, label: str) -> pd.Series | None:
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


def _fetch_index_yf() -> pd.Series | None:
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
# Unified fetch waterfall: Stooq(.ns + .bo, all browsers) -> yfinance
# ---------------------------------------------------------------------------

def _fetch_prices(ticker: str, meta: dict) -> pd.Series | None:
    # stooq key holds the base symbol (we try .ns and .bo automatically)
    stooq_base = meta.get("stooq", f"{ticker.lower()}.ns")
    yf_sym     = meta.get("yf",    f"{ticker}.NS")

    prices = _fetch_prices_stooq(stooq_base, ticker)
    if prices is not None:
        return prices

    log.debug(f"  {ticker}: all Stooq variants failed, trying yfinance")
    return _fetch_prices_yf(yf_sym, ticker)


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
    """
    Expand a list of holding tickers to include Nifty50 sector peers.
    Normalizes broker-format tickers (e.g. HALEQ -> HAL) before lookup.
    Non-Nifty50 holdings are included as-is so they still get price data.
    """
    # Normalize incoming broker tickers
    normalized = [normalize_ticker(t) for t in tickers]

    # Split: Nifty50 members vs non-Nifty50 holdings
    in_nifty  = [t for t in normalized if t in NIFTY50]
    out_nifty = [t for t in normalized if t not in NIFTY50]

    if out_nifty:
        log.info(f"Non-Nifty50 holdings (will fetch individually): {out_nifty}")

    # Sector peers from Nifty50
    sectors = {NIFTY50[t]["sector"] for t in in_nifty}
    peers   = {t for t, info in NIFTY50.items() if info["sector"] in sectors}
    peers.update(in_nifty)

    nifty_result = [t for t in peers if t in NIFTY50]
    result = nifty_result + [t for t in out_nifty if t not in nifty_result]

    log.info(f"Holdings: {len(normalized)} | Nifty50 peers: {len(nifty_result)} | Extra: {len(out_nifty)} | Total universe: {len(result)}")
    return result


# ---------------------------------------------------------------------------
# Main harvest
# ---------------------------------------------------------------------------

def harvest(extra_tickers=None, tickers=None):
    """
    Harvest price data for Nifty50 universe + any extra non-Nifty50 holdings.

    Args:
        extra_tickers: list of non-Nifty50 NSE symbols to fetch in addition
                       to the full Nifty50 (e.g. ['HAL', 'IRCTC', 'TATATECH'])
        tickers:       DEPRECATED -- kept for backward compat, ignored if
                       extra_tickers is provided
    """
    run_id  = str(uuid.uuid4())[:8]
    started = datetime.utcnow()
    log.info(f"Harvest started -- run_id: {run_id}")
    log.info("Data source: Stooq (primary) -> yfinance (fallback)")

    # Always harvest full Nifty50; extra_tickers adds non-Nifty50 holdings on top
    nifty_universe = list(NIFTY50.keys())
    if extra_tickers:
        deduped_extra = [t for t in extra_tickers if t not in NIFTY50]
        universe = nifty_universe + deduped_extra
        log.info(f"Universe: {len(nifty_universe)} Nifty50 + {len(deduped_extra)} extra = {len(universe)} total")
    else:
        universe = nifty_universe
        log.info(f"Universe: {len(universe)} stocks (full Nifty50)")

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
        meta = get_ticker_meta(ticker)   # works for Nifty50 AND extended universe
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

    # ── Merge strategy: preserve existing good data for stocks we didn't fetch ──
    # BUG_12 fix: triggered harvest was overwriting the full snapshot with only
    # the user's holding stocks (45), wiping the 48-stock Nifty50 data.
    # Now we load the existing snapshot and merge: new data wins for tickers we
    # successfully fetched, existing data is kept for everything else.
    final_snapshot  = snapshot   # start with what we just fetched
    final_funds     = dict(fundamentals)

    if extra_tickers and snapshot:
        # This was a targeted harvest -- merge into existing snapshot
        existing = gs.read("snapshot") or {}
        existing_stocks = existing.get("stocks", [])
        if existing_stocks:
            existing_map = {s["ticker"]: s for s in existing_stocks}
            new_map      = {s["ticker"]: s for s in snapshot}
            # Merge: new data wins, existing data fills gaps
            merged = {**existing_map, **new_map}
            final_snapshot = list(merged.values())
            merged_new = len(new_map)
            merged_kept = len(existing_map) - len([t for t in existing_map if t in new_map])
            log.info(f"Snapshot merge: {merged_new} updated + {merged_kept} kept from previous = {len(final_snapshot)} total")

        existing_f = gs.read("fundamentals") or {}
        existing_fdata = existing_f.get("data", {})
        final_funds = {**existing_fdata, **fundamentals}  # new wins
    elif not snapshot:
        # Zero stocks fetched -- do NOT overwrite existing snapshot
        log.warning("Zero stocks fetched -- skipping snapshot write to preserve existing data")
        gs.write_metadata(0, [], run_id)
        return {
            "run_id":   run_id,
            "success":  0,
            "failed":   len(failed),
            "duration": round((datetime.utcnow() - started).total_seconds(), 1),
            "status":   "blocked",
        }

    gs.write("snapshot", {
        "generated_at": datetime.utcnow().isoformat(),
        "run_id":       run_id,
        "count":        len(final_snapshot),
        "stocks":       final_snapshot,
    }, f"harvest snapshot: {success} new + {len(final_snapshot)-success} existing")
    gs.write("fundamentals", {
        "generated_at": datetime.utcnow().isoformat(),
        "data":         final_funds,
    })
    gs.write_metadata(success, [s["ticker"] for s in final_snapshot], run_id)

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

    # ── Harvest strategy ──────────────────────────────────────────────────────
    # BUG_13 fix: triggered harvest was scoped to only user holdings, missing
    # Nifty50 peer data that Streamlit needs. Strategy:
    #   - Always harvest full Nifty50 (50 stocks, peer comparisons)
    #   - ADDITIONALLY fetch any user holding tickers not in Nifty50
    #   - Trigger file signals WHICH extra tickers to add, not which to limit to

    extra_tickers = []
    trigger = gs.read("holdings_trigger")
    if trigger and "tickers" in trigger:
        raw_tickers = trigger["tickers"]
        # Normalize and find non-Nifty50 holdings
        normalized  = [normalize_ticker(t) for t in raw_tickers]
        extra_tickers = [t for t in normalized if t not in NIFTY50]
        if extra_tickers:
            log.info(f"Trigger: adding {len(extra_tickers)} non-Nifty50 holdings: {extra_tickers}")
        else:
            log.info("Trigger: all holdings are in Nifty50 universe -- full harvest only")
    else:
        log.info("No trigger -- full Nifty50 harvest")

    summary = harvest(extra_tickers=extra_tickers)
    log.info(f"Done: {summary}")

    if summary["success"] == 0 and summary.get("status") == "blocked":
        log.warning("All sources blocked -- existing snapshot preserved. Will retry at next scheduled run.")
        sys.exit(1)
    elif summary["success"] == 0:
        log.error("Zero stocks harvested -- marking as failed")
        sys.exit(1)
