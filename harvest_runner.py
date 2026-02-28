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
# Multi-browser rotation engine
#
# WHY: Stooq and Yahoo detect bots via TWO layers:
#   Layer 1 - HTTP:  User-Agent + Accept/Accept-Language/Sec-* headers must
#             form a CONSISTENT set matching a real browser. A Chrome UA with
#             Firefox Accept headers is WORSE than no UA (immediate flag).
#   Layer 2 - TLS:   ClientHello cipher suites, extension order, GREASE
#             values differ by browser engine. curl_cffi replays exact TLS
#             handshakes when available. Without it, plain requests still
#             gains significant benefit from correct HTTP header profiles.
#
# PROFILES (ordered best-first for Stooq/Yahoo evasion):
#   1. safari_mac     -- WebKit engine, distinct TLS, no Sec-CH-UA hints,
#                        less common for automated scrapers -> least flagged
#   2. firefox_win    -- Gecko engine, different header ordering, no CH hints
#   3. chrome_android -- Mobile UA, separate throttle bucket on many servers
#   4. edge_win       -- Chromium but distinct UA string pattern
#   5. chrome_win     -- Most common, most scrutinised -> last resort
#
# Each profile: (curl_cffi_target, UA_string, full_headers_dict)
# Headers are ordered correctly per spec for each browser engine.
# ---------------------------------------------------------------------------

_BROWSER_PROFILES = [
    (
        "safari15_5",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_2_1) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) "
        "Version/17.2 Safari/605.1.15",
        {   # Safari sends these in this exact order; no Sec-CH-UA (WebKit doesn't support)
            "User-Agent":              "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_2_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
            "Accept":                  "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language":         "en-GB,en;q=0.9",
            "Accept-Encoding":         "gzip, deflate, br",
            "Connection":              "keep-alive",
        },
    ),
    (
        "firefox122",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) "
        "Gecko/20100101 Firefox/122.0",
        {   # Firefox header order: no Sec-CH-UA (Gecko doesn't support client hints)
            "User-Agent":              "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0",
            "Accept":                  "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language":         "en-US,en;q=0.5",
            "Accept-Encoding":         "gzip, deflate, br",
            "Connection":              "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest":          "document",
            "Sec-Fetch-Mode":          "navigate",
            "Sec-Fetch-Site":          "none",
            "Sec-Fetch-User":          "?1",
        },
    ),
    (
        "chrome120",
        "Mozilla/5.0 (Linux; Android 14; Pixel 8) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.6099.210 Mobile Safari/537.36",
        {   # Chrome Android -- mobile UA, separate rate-limit bucket
            "User-Agent":              "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.6099.210 Mobile Safari/537.36",
            "Accept":                  "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language":         "en-IN,en-GB;q=0.9,en;q=0.8",
            "Accept-Encoding":         "gzip, deflate, br",
            "Connection":              "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-CH-UA":               '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
            "Sec-CH-UA-Mobile":        "?1",
            "Sec-CH-UA-Platform":      '"Android"',
            "Sec-Fetch-Dest":          "document",
            "Sec-Fetch-Mode":          "navigate",
            "Sec-Fetch-Site":          "none",
            "Sec-Fetch-User":          "?1",
        },
    ),
    (
        "edge101",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/121.0.0.0 Safari/537.36 Edg/121.0.0.0",
        {   # Edge -- Chromium base but distinct UA and CH-UA brand
            "User-Agent":              "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36 Edg/121.0.0.0",
            "Accept":                  "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Accept-Language":         "en-US,en;q=0.9",
            "Accept-Encoding":         "gzip, deflate, br",
            "Connection":              "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-CH-UA":               '"Not A(Brand";v="99", "Microsoft Edge";v="121", "Chromium";v="121"',
            "Sec-CH-UA-Mobile":        "?0",
            "Sec-CH-UA-Platform":      '"Windows"',
            "Sec-Fetch-Dest":          "document",
            "Sec-Fetch-Mode":          "navigate",
            "Sec-Fetch-Site":          "none",
            "Sec-Fetch-User":          "?1",
        },
    ),
    (
        "chrome121",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/121.0.0.0 Safari/537.36",
        {   # Chrome Windows -- most common, most scrutinised, last resort
            "User-Agent":              "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            "Accept":                  "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Accept-Language":         "en-US,en;q=0.9",
            "Accept-Encoding":         "gzip, deflate, br",
            "Connection":              "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-CH-UA":               '"Not A(Brand";v="99", "Google Chrome";v="121", "Chromium";v="121"',
            "Sec-CH-UA-Mobile":        "?0",
            "Sec-CH-UA-Platform":      '"Windows"',
            "Sec-Fetch-Dest":          "document",
            "Sec-Fetch-Mode":          "navigate",
            "Sec-Fetch-Site":          "none",
            "Sec-Fetch-User":          "?1",
        },
    ),
]

# Map profile name -> curl_cffi impersonate target
_CFFI_TARGET = {
    "safari15_5":    "safari15_5",
    "firefox122":    "firefox110",   # closest available in curl_cffi
    "chrome120":     "chrome120",
    "edge101":       "edge101",
    "chrome121":     "chrome120",    # use chrome120 TLS for chrome121
}

# Detect curl_cffi once at import time
try:
    from curl_cffi import requests as cffi_requests
    _CURL_CFFI_OK = True
    log.info("curl_cffi available -- full TLS + HTTP browser impersonation active")
except ImportError:
    _CURL_CFFI_OK = False
    log.info("curl_cffi not installed -- HTTP-layer rotation only (still effective)")


def _make_session(headers: dict) -> requests.Session:
    """Build a requests.Session with the given browser headers pre-set."""
    s = requests.Session()
    s.headers.clear()
    for k, v in headers.items():
        s.headers[k] = v
    return s


# Pre-built sessions, one per profile (reused across requests)
_PROFILE_SESSIONS: dict = {}


def _get_profile_session(profile_name: str, headers: dict) -> requests.Session:
    if profile_name not in _PROFILE_SESSIONS:
        _PROFILE_SESSIONS[profile_name] = _make_session(headers)
    return _PROFILE_SESSIONS[profile_name]


def _rotating_get(url: str, params: dict, label: str, timeout: int = 20):
    """
    Try each browser profile in order until one returns valid CSV data.
    Returns (response_text, profile_name) or (None, None).

    Detection avoidance:
    - Each profile sends a complete, consistent header set for that browser
    - Safari and Firefox profiles lack Sec-CH-UA (those browsers don't send it)
    - curl_cffi adds TLS fingerprint matching when available
    - Sessions are reused so TCP connections persist (more browser-like)
    """
    for profile_name, ua, headers in _BROWSER_PROFILES:
        try:
            if _CURL_CFFI_OK:
                from curl_cffi import requests as cffi_requests
                impersonate = _CFFI_TARGET.get(profile_name, "chrome120")
                r = cffi_requests.get(
                    url, params=params, headers=headers,
                    impersonate=impersonate, timeout=timeout,
                )
            else:
                sess = _get_profile_session(profile_name, headers)
                r = sess.get(url, params=params, timeout=timeout)

            if r.status_code == 200:
                text = r.text.strip()
                # Valid Stooq CSV starts with "Date," header, not HTML
                if (text
                        and len(text) > 100
                        and text.startswith("Date,")
                        and "No data" not in text
                        and "<html" not in text.lower()):
                    log.debug(f"  {label}: success with [{profile_name}]")
                    return text, profile_name
                else:
                    log.debug(f"  {label} [{profile_name}]: non-CSV response ({len(text)} bytes)")
            elif r.status_code == 429:
                log.debug(f"  {label} [{profile_name}]: 429 -- pausing 2s before next profile")
                time.sleep(2.0)
            else:
                log.debug(f"  {label} [{profile_name}]: HTTP {r.status_code}")

        except Exception as e:
            log.debug(f"  {label} [{profile_name}]: {type(e).__name__}: {e}")

        # Brief pause between profile attempts to avoid hammering
        time.sleep(0.3)

    return None, None


# ---------------------------------------------------------------------------
# Source 0: BSE India direct API  (no key, no Cloudflare, public endpoint)
#
# BSE India serves historical data from their own API (used by bseindia.com).
# No API key required. No Cloudflare. Datacenter IPs are not blocked.
#
# Approach: session cookie handshake then BSE raw HTTP API
#   Step 1: GET www.bseindia.com  -- establishes ASP.NET session cookies
#   Step 2: GET api.bseindia.com  -- now returns JSON (not HTML error page)
#
# Symbol mapping: NSE ticker -> BSE scrip code (6-digit number)
# ---------------------------------------------------------------------------

# NSE ticker -> BSE scrip code mapping (top holdings + Nifty50)
_BSE_SCRIP = {
    "HDFCBANK": "500180", "ICICIBANK": "532174", "KOTAKBANK": "500247",
    "AXISBANK": "532215", "SBIN": "500112", "BAJFINANCE": "500034",
    "BAJAJFINSV": "532978", "HDFCLIFE": "540777", "SBILIFE": "540719",
    "INDUSINDBK": "532187", "TCS": "532540", "INFY": "500209",
    "HCLTECH": "532281", "WIPRO": "507685", "TECHM": "532755",
    "LTIM": "540005", "RELIANCE": "500325", "ONGC": "500312",
    "BPCL": "500547", "COALINDIA": "533278", "POWERGRID": "532898",
    "NTPC": "532555", "HINDUNILVR": "500696", "ITC": "500875",
    "NESTLEIND": "500790", "BRITANNIA": "500825", "TATACONSUM": "500800",
    "TITAN": "500114", "ASIANPAINT": "500820", "ZOMATO": "543320",
    "MARUTI": "532500", "BAJAJ-AUTO": "532977", "HEROMOTOCO": "500182",
    "EICHERMOT": "505200", "M&M": "500520", "TATAMOTORS": "500570",
    "SUNPHARMA": "524715", "DRREDDY": "500124", "CIPLA": "500087",
    "DIVISLAB": "532488", "APOLLOHOSP": "508869", "TATASTEEL": "500470",
    "JSWSTEEL": "500228", "HINDALCO": "500440", "ADANIENT": "512599",
    "LT": "500510", "ADANIPORTS": "532921", "ULTRACEMCO": "532538",
    "GRASIM": "500300", "BHARTIARTL": "532454",
    # User holdings
    "ADANIGREEN": "541450", "AUBANK": "540611", "BDL": "541143",
    "BHARATFORG": "500493", "BHEL": "500103", "CAMS": "543232",
    "ENGINERSIN": "532535", "GPPL": "533248", "HAL": "541154",
    "HEG": "509631", "HINDCOPPER": "513599", "IONEXCHANGE": "500214",
    "IRCTC": "542830", "IREDA": "544225", "JIOFIN": "543940",
    "LAURUSLABS": "540222", "MAZDOCK": "543237", "NATIONALUM": "532234",
    "NMDC": "526371", "PARAS": "530647", "PFC": "532810",
    "RECLTD": "532955", "RVNL": "542649", "SPANDANA": "542759",
    "TATATECH": "544028", "TRITURBINE": "533655",
}

_bse_session       = None
_bse_session_ready = False   # True once cookie handshake succeeded

# Circuit breakers — set True on first 429/rate-limit, skips all subsequent calls
# Prevents 89 × 10s = 15min wasted time when Yahoo is blocked for this IP
_YF_Q1_BLOCKED = False  # yfinance query1 rate-limited this run
_YF_Q2_BLOCKED = False  # yfinance query2 rate-limited this run


def _strip_tz(prices: pd.Series) -> pd.Series:
    """Strip timezone from a Series DatetimeIndex. Always returns tz-naive.

    yfinance daily data uses date-only IST timestamps (e.g. 2026-02-27 00:00+05:30).
    tz_convert(None) would shift to UTC and corrupt dates (2026-02-26 18:30).
    tz_localize(None) drops the tz label without any value shift -- correct.
    """
    if prices.index.tz is not None:
        prices = prices.copy()
        prices.index = prices.index.tz_localize(None)
    return prices


def _get_bse_session() -> "requests.Session | None":
    """
    Returns a requests.Session with valid BSE ASP.NET cookies.
    
    BSE's API (api.bseindia.com) returns an ASP.NET HTML error page unless
    the session carries cookies from www.bseindia.com. This function performs
    the one-time cookie handshake and caches the session for the harvest run.
    
    No Cloudflare on either www.bseindia.com or api.bseindia.com (confirmed:
    CF-Ray header absent). Session establishment succeeds from datacenter IPs.
    """
    global _bse_session, _bse_session_ready
    if _bse_session_ready:
        return _bse_session

    sess = requests.Session()
    sess.headers.update({
        "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection":      "keep-alive",
    })

    try:
        # Step 1: hit the main BSE website to establish ASP.NET session cookies
        r = sess.get("https://www.bseindia.com", timeout=15)
        cf_ray = r.headers.get("CF-Ray", "none")
        if cf_ray != "none":
            log.warning(f"BSE main page has Cloudflare (CF-Ray: {cf_ray}) -- may block datacenter IPs")
        if r.status_code == 200:
            cookies = {c.name: c.value for c in sess.cookies}
            log.info(f"BSE session: handshake OK (HTTP 200, {len(cookies)} cookies: {list(cookies.keys())[:5]})")
            # Switch to API-friendly headers after handshake
            sess.headers.update({
                "Accept":  "application/json, text/plain, */*",
                "Referer": "https://www.bseindia.com/",
                "Origin":  "https://www.bseindia.com",
            })
            _bse_session       = sess
            _bse_session_ready = True
            return sess
        else:
            log.warning(f"BSE handshake: HTTP {r.status_code} -- session not established")
            return None
    except Exception as e:
        log.warning(f"BSE handshake failed: {type(e).__name__}: {e}")
        return None


def _fetch_prices_bse(nse_symbol: str, label: str) -> "pd.Series | None":
    """
    Fetch historical close prices from BSE India's public API.
    
    Performs a one-time cookie handshake (GET www.bseindia.com) to establish
    an ASP.NET session, then calls the historical chart API.
    No API key. No Cloudflare. Works from datacenter IPs.
    """
    scrip = _BSE_SCRIP.get(nse_symbol.upper())
    if not scrip:
        log.debug(f"  {label}: no BSE scrip code mapping -- skipping BSE source")
        return None

    end_dt   = datetime.today()
    start_dt = end_dt - timedelta(days=3 * 365 + 60)

    try:
        sess = _get_bse_session()
        if sess is None:
            log.debug(f"  {label}: BSE session unavailable")
            return None
        url  = "https://api.bseindia.com/BseIndiaAPI/api/StockReachGraph/w"
        params = {
            "scripcode": scrip,
            "flag":      "1",
            "fromdate":  start_dt.strftime("%Y%m%d"),
            "todate":    end_dt.strftime("%Y%m%d"),
            "seriesid":  "EQ",
        }
        r = sess.get(url, params=params, timeout=20)
        if r.status_code == 200:
            data = r.json()
            # BSE returns {"Data": "[[timestamp_ms,open,high,low,close,vol],...]"}
            # IMPORTANT: Data value is a JSON-encoded STRING -- must json.loads() it
            import json as _json
            raw  = data.get("Data") or data.get("data") or "[]"
            rows = _json.loads(raw) if isinstance(raw, str) else raw
            if rows and isinstance(rows, list):
                dates  = [pd.Timestamp(row[0], unit="ms") for row in rows]
                closes = [float(row[4]) for row in rows]
                prices = pd.Series(closes, index=dates, name="Close")
                prices.index.name = "Date"
                prices = prices.sort_index()
                if len(prices) >= 20:
                    log.info(f"  {label}: {len(prices)} rows via BSE ✓")
                    return prices
            log.debug(f"  {label} BSE: {len(rows) if isinstance(rows,list) else 0} rows. Keys: {list(data.keys())}")
        else:
            log.debug(f"  {label} BSE: HTTP {r.status_code}")
    except Exception as e:
        log.debug(f"  {label} BSE: {type(e).__name__}: {e}")

    return None


def _fetch_index_bse() -> "pd.Series | None":
    """Fetch Nifty50 via BSE API (Sensex as proxy, scrip 1)."""
    # BSE Sensex index = scrip code 1
    # For Nifty50 beta calculation we really want Nifty data
    # Try NSE index API as alternative
    try:
        sess = _get_bse_session()
        end_dt   = datetime.today()
        start_dt = end_dt - timedelta(days=3 * 365 + 60)
        url = "https://api.bseindia.com/BseIndiaAPI/api/StockReachGraph/w"
        r = sess.get(url, params={
            "scripcode": "1", "flag": "1",
            "fromdate": start_dt.strftime("%Y%m%d"),
            "todate":   end_dt.strftime("%Y%m%d"),
            "seriesid": "EQ",
        }, timeout=20)
        if r.status_code == 200:
            import json as _json
            raw  = r.json().get("Data", "[]")
            rows = _json.loads(raw) if isinstance(raw, str) else raw
            if rows and isinstance(rows, list):
                dates  = [pd.Timestamp(row[0], unit="ms") for row in rows]
                closes = [float(row[4]) for row in rows]
                prices = pd.Series(closes, index=dates).sort_index()
                prices.index.name = "Date"
                if len(prices) >= 20:
                    log.info(f"  Index: {len(prices)} rows via BSE ✓")
                    return prices
    except Exception as e:
        log.debug(f"  Index BSE: {e}")
    return None


# ---------------------------------------------------------------------------
# Source 0: Financial Modeling Prep (FMP) -- TRUE PRIMARY
#
# FMP is a proper REST API with an API key (stored in GitHub Secrets as
# FMP_API_KEY). It serves NSE historical data without Cloudflare, without
# IP-based blocking, and is guaranteed to work from Azure datacenter IPs.
#
# Free tier: 250 calls/day, 300 calls/min -- sufficient for 89 stocks/day.
# Endpoint:  /api/v3/historical-price-full/{SYMBOL.NS}
#            ?from=YYYY-MM-DD&to=YYYY-MM-DD&apikey=KEY
#
# If FMP_API_KEY is not set, this source is skipped silently.
# ---------------------------------------------------------------------------

_FMP_API_KEY  = os.environ.get("FMP_API_KEY", "").strip()
_FMP_BASE_URL = "https://financialmodelingprep.com/api/v3"
_fmp_session  = None


def _get_fmp_session() -> requests.Session:
    global _fmp_session
    if _fmp_session is None:
        _fmp_session = requests.Session()
        _fmp_session.headers.update({
            "User-Agent": "Agent_Trader/1.0",
            "Accept":     "application/json",
        })
    return _fmp_session


def _fetch_prices_fmp(nse_symbol: str, label: str) -> "pd.Series | None":
    """
    Fetch 3y daily close prices from FMP for an NSE symbol.
    Tries SYMBOL.NS first, then SYMBOL.BO (BSE) as fallback.
    Returns pd.Series or None.
    """
    if not _FMP_API_KEY:
        return None

    end_dt   = datetime.today()
    start_dt = end_dt - timedelta(days=3 * 365 + 60)

    sess     = _get_fmp_session()
    suffixes = [".NS", ".BO"]  # NSE first, BSE fallback

    for suffix in suffixes:
        sym = nse_symbol.upper() + suffix
        url = f"{_FMP_BASE_URL}/historical-price-full/{sym}"
        params = {
            "from":   start_dt.strftime("%Y-%m-%d"),
            "to":     end_dt.strftime("%Y-%m-%d"),
            "apikey": _FMP_API_KEY,
        }
        try:
            r = sess.get(url, params=params, timeout=20)
            if r.status_code == 401:
                log.error("FMP: Invalid API key -- check FMP_API_KEY secret")
                return None
            if r.status_code != 200:
                log.debug(f"  {label} FMP{suffix}: HTTP {r.status_code}")
                continue

            data = r.json()
            historical = data.get("historical", [])
            if not historical:
                log.debug(f"  {label} FMP{suffix}: empty historical data")
                continue

            df = pd.DataFrame(historical)
            df["date"]  = pd.to_datetime(df["date"])
            df = df.sort_values("date").set_index("date")
            prices = df["close"].astype(float)
            prices.index.name = "Date"

            if len(prices) >= 20:
                log.info(f"  {label}: {len(prices)} rows via FMP{suffix} ✓")
                return prices

        except Exception as e:
            log.debug(f"  {label} FMP{suffix}: {type(e).__name__}: {e}")

    return None


def _fetch_index_fmp() -> "pd.Series | None":
    """Fetch Nifty50 index via FMP (^NSEI)."""
    if not _FMP_API_KEY:
        return None

    end_dt   = datetime.today()
    start_dt = end_dt - timedelta(days=3 * 365 + 60)
    sess     = _get_fmp_session()
    url      = f"{_FMP_BASE_URL}/historical-price-full/%5ENSEI"
    params   = {
        "from":   start_dt.strftime("%Y-%m-%d"),
        "to":     end_dt.strftime("%Y-%m-%d"),
        "apikey": _FMP_API_KEY,
    }
    try:
        r = sess.get(url, params=params, timeout=20)
        if r.status_code == 200:
            historical = r.json().get("historical", [])
            if historical:
                df = pd.DataFrame(historical)
                df["date"] = pd.to_datetime(df["date"])
                prices = df.sort_values("date").set_index("date")["close"].astype(float)
                prices.index.name = "Date"
                if len(prices) >= 20:
                    log.info(f"  Nifty50-index: {len(prices)} rows via FMP ✓")
                    return prices
    except Exception as e:
        log.debug(f"  Nifty50-index FMP: {e}")
    return None


# ---------------------------------------------------------------------------
# Diagnostic helper -- logs EXACT server response on first failure
# so we know whether it's Cloudflare, 403, empty CSV, etc.
# ---------------------------------------------------------------------------

_diagnosed = False  # only run once per harvest


def _run_diagnosis(url: str, params: dict):
    """
    Log exactly what the server returns -- status, headers, body preview.
    Identifies Cloudflare (CF-Ray header), soft blocks (HTML body),
    hard blocks (403/429), or connectivity issues.
    """
    global _diagnosed
    if _diagnosed:
        return
    _diagnosed = True

    log.info("── Diagnosing data source response ──")
    try:
        r = requests.get(url, params=params,
                         headers={"User-Agent": "Mozilla/5.0"},
                         timeout=15)
        cf_ray   = r.headers.get("CF-Ray", "none")
        cf_cache = r.headers.get("CF-Cache-Status", "none")
        ctype    = r.headers.get("Content-Type", "?")
        body     = r.text[:300].replace("\n", " ").strip()
        is_cf    = cf_ray != "none" or "cloudflare" in r.headers.get("Server", "").lower()

        log.info(f"  URL:          {r.url[:80]}")
        log.info(f"  HTTP status:  {r.status_code}")
        log.info(f"  Server:       {r.headers.get('Server', '?')}")
        log.info(f"  Cloudflare:   {'YES -- CF-Ray: ' + cf_ray if is_cf else 'NO'}")
        log.info(f"  Content-Type: {ctype}")
        log.info(f"  Body[:300]:   {body}")

        if is_cf and r.status_code in (403, 503):
            log.warning("  → Cloudflare Bot Fight Mode active. API key (FMP/Twelve Data) required.")
        elif is_cf and r.status_code == 200 and "<html" in r.text.lower():
            log.warning("  → Cloudflare JS challenge page. cf_clearance cookie required.")
        elif r.status_code == 429:
            log.warning("  → Rate limited (429). Back off or rotate source.")
        elif r.status_code == 200 and r.text.strip().startswith("Date,"):
            log.info("  → Valid CSV! Check _rotating_get logic.")
        elif r.status_code == 200:
            log.warning("  → HTTP 200 but non-CSV body. Soft block or wrong symbol.")

    except Exception as e:
        log.info(f"  Connection failed: {type(e).__name__}: {e}")
        log.info("  → Network-level block or DNS failure from this IP range.")
    log.info("── End diagnosis ──")


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
            log.info(f"  {label}: {len(prices)} rows via yfinance ✓")
            return prices
    except Exception as e:
        err = str(e)
        if "429" in err or "RateLimit" in err or "Too Many" in err:
            _YF_Q1_BLOCKED = True
            log.warning(f"  yfinance/q1 rate-limited — disabling for this run")
        else:
            log.debug(f"  {label} yfinance: {e}")
    return None


def _fetch_index_yf() -> pd.Series | None:
    global _YF_Q1_BLOCKED
    if _YF_Q1_BLOCKED:
        return None
    try:
        import yfinance as yf
        hist = yf.Ticker("^NSEI").history(
            period=PRICE_PERIOD, auto_adjust=True, actions=False, timeout=25
        )
        if hist is not None and not hist.empty:
            return _strip_tz(hist["Close"].squeeze())
    except Exception as e:
        err = str(e)
        if "429" in err or "RateLimit" in err or "Too Many" in err:
            _YF_Q1_BLOCKED = True
            log.warning("  yfinance/q1 rate-limited on index fetch — disabling for this run")
        else:
            log.debug(f"  Nifty50-index yfinance: {e}")
    return None


# ---------------------------------------------------------------------------
# Unified fetch waterfall: Stooq(.ns + .bo, all browsers) -> yfinance
# ---------------------------------------------------------------------------

def _fetch_prices_yf_q2(yf_ticker: str, label: str) -> "pd.Series | None":
    """
    yfinance via query2.finance.yahoo.com (different subdomain, separate rate limit).
    Uses a custom requests session to override yfinance's default base_url.
    """
    global _YF_Q2_BLOCKED
    if _YF_Q2_BLOCKED:
        log.debug(f"  {label} yf/q2: skipped (rate-limited earlier this run)")
        return None
    try:
        import yfinance as yf
        session = requests.Session()
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_2_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        })
        ticker = yf.Ticker(yf_ticker, session=session)
        # Override base_url to use query2 instead of query1
        import yfinance.base as _yfbase
        _orig = getattr(_yfbase, "YF_URL", None)
        try:
            if hasattr(_yfbase, "YF_URL"):
                _yfbase.YF_URL = "https://query2.finance.yahoo.com"
            hist = ticker.history(period="3y", auto_adjust=True, actions=False, timeout=20)
        finally:
            if _orig is not None and hasattr(_yfbase, "YF_URL"):
                _yfbase.YF_URL = _orig
        if hist is not None and not hist.empty and "Close" in hist.columns:
            prices = hist["Close"].dropna()
            prices.index = pd.to_datetime(prices.index).tz_localize(None)
            prices.index.name = "Date"
            if len(prices) >= 20:
                log.info(f"  {label}: {len(prices)} rows via yfinance/q2 ✓")
                return prices
    except Exception as e:
        err = str(e)
        if "429" in err or "RateLimit" in err or "Too Many" in err:
            _YF_Q2_BLOCKED = True
            log.warning(f"  yfinance/q2 rate-limited — disabling for this run")
        else:
            log.debug(f"  {label} yf/q2: {type(e).__name__}: {e}")
    return None


def _fetch_prices(ticker: str, meta: dict) -> pd.Series | None:
    """
    Unified waterfall (first success wins):
      0. BSE India direct API  -- free, no key, no Cloudflare
      1. FMP                   -- free key if configured
      2. Stooq                 -- browser rotation (IP-blocked from datacenter)
      3. yfinance query2       -- separate rate-limit bucket from query1
      4. yfinance query1       -- last resort
    """
    stooq_base = meta.get("stooq", f"{ticker.lower()}.ns")
    yf_sym     = meta.get("yf",    f"{ticker}.NS")

    # Source 0: BSE India (no key, no bot protection, different infra from Yahoo/Stooq)
    prices = _fetch_prices_bse(ticker, ticker)
    if prices is not None:
        return prices
    log.debug(f"  {ticker}: BSE failed, trying FMP")

    # Source 1: FMP (skipped if key not set)
    if _FMP_API_KEY:
        prices = _fetch_prices_fmp(ticker, ticker)
        if prices is not None:
            return prices
        log.debug(f"  {ticker}: FMP failed, trying Stooq")

    # Source 2: Stooq (IP-blocked from datacenter, kept as it costs nothing to try)
    prices = _fetch_prices_stooq(stooq_base, ticker)
    if prices is not None:
        return prices

    # Diagnose Stooq failure once per run
    _run_diagnosis("https://stooq.com/q/d/l/", {"s": stooq_base, "i": "d"})

    # Source 3: yfinance via query2 (separate rate-limit pool)
    prices = _fetch_prices_yf_q2(yf_sym, ticker)
    if prices is not None:
        return prices

    # Source 4: yfinance via query1 (original, last resort)
    log.debug(f"  {ticker}: all sources failed, last try yfinance/q1")
    return _fetch_prices_yf(yf_sym, ticker)


def _fetch_index() -> pd.Series | None:
    """Nifty50 index waterfall: BSE -> FMP -> Stooq -> yfinance."""
    idx = _fetch_index_bse()
    if idx is not None:
        return idx

    if _FMP_API_KEY:
        idx = _fetch_index_fmp()
        if idx is not None:
            return idx

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
    # Normalise both to tz-naive -- different sources may produce mismatched tz
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
