"""
Agent_Trader -- Pipeline Dry Run / Diagnostic Tool
===================================================
Tests the entire harvest pipeline end-to-end using only 3 stocks.
Safe: writes to db/dryrun.enc only, never touches snapshot.enc.

Run locally:   python dry_run.py
Run on Actions: triggered by dry_run.yml workflow

Exit codes:
  0 = all tests passed, pipeline is healthy
  1 = one or more tests failed (see FAIL lines for fix instructions)
"""
import os
import sys
import json
import time
import io
import base64
import requests
import traceback
from datetime import datetime, timedelta

# ── Inject Streamlit/Actions env ──────────────────────────────────────────────
# When running locally, you can set these in your shell:
#   export FERNET_KEY="..."
#   export GITHUB_TOKEN="..."
#   export FMP_API_KEY="..."   (optional but needed for FMP test)

RESULTS  = []   # list of (test_name, passed, message)
WARNINGS = []

def record(name, passed, msg="", fix=""):
    icon = "✅ PASS" if passed else "❌ FAIL"
    line = f"  {icon}  {name}"
    if msg:
        line += f"\n         {msg}"
    if not passed and fix:
        line += f"\n         FIX: {fix}"
    RESULTS.append((name, passed, line))
    print(line)

def warn(msg):
    WARNINGS.append(msg)
    print(f"  ⚠️  WARN  {msg}")

print()
print("=" * 60)
print("  Agent_Trader Pipeline Dry Run")
print(f"  {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
print("=" * 60)
print()


# ────────────────────────────────────────────────────────────────
# TEST 1: Secrets / environment variables
# ────────────────────────────────────────────────────────────────
print("── TEST 1: Secrets ──────────────────────────────────────────")

FERNET_KEY   = os.environ.get("FERNET_KEY", "").strip()
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "").strip()
GITHUB_REPO  = os.environ.get("GITHUB_REPO", "SubhasishSahu/Avito").strip()
GITHUB_BRANCH= os.environ.get("GITHUB_BRANCH", "master").strip()
FMP_API_KEY  = os.environ.get("FMP_API_KEY", "").strip()

record("FERNET_KEY set",   bool(FERNET_KEY),
       f"starts with: {FERNET_KEY[:8]}..." if FERNET_KEY else "",
       "Add FERNET_KEY to GitHub Secrets and Streamlit Secrets")

record("GITHUB_TOKEN set", bool(GITHUB_TOKEN),
       f"starts with: {GITHUB_TOKEN[:4]}..." if GITHUB_TOKEN else "",
       "Add GITHUB_TOKEN (PAT with Contents: Read+Write) to GitHub Secrets")

record("GITHUB_REPO set",  bool(GITHUB_REPO),
       f"repo: {GITHUB_REPO}")

if FMP_API_KEY:
    record("FMP_API_KEY set", True, f"starts with: {FMP_API_KEY[:6]}...")
else:
    warn("FMP_API_KEY not set -- FMP source will be skipped (get free key at financialmodelingprep.com)")


# ────────────────────────────────────────────────────────────────
# TEST 2: Encryption round-trip
# ────────────────────────────────────────────────────────────────
print()
print("── TEST 2: Encryption ───────────────────────────────────────")

try:
    from cryptography.fernet import Fernet, InvalidToken
    f = Fernet(FERNET_KEY.encode() if FERNET_KEY else Fernet.generate_key())
    payload = {"test": "dry_run", "ts": datetime.utcnow().isoformat()}
    encrypted = f.encrypt(json.dumps(payload).encode())
    decrypted = json.loads(f.decrypt(encrypted).decode())
    assert decrypted["test"] == "dry_run"
    record("Fernet encrypt/decrypt", True,
           f"round-trip OK ({len(encrypted)} bytes encrypted)")
except Exception as e:
    record("Fernet encrypt/decrypt", False, str(e),
           "Check FERNET_KEY is a valid base64 Fernet key (44 chars)")


# ────────────────────────────────────────────────────────────────
# TEST 3: GitHub API connectivity + read/write
# ────────────────────────────────────────────────────────────────
print()
print("── TEST 3: GitHub API ───────────────────────────────────────")

GITHUB_API = "https://api.github.com"
gh_headers = {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github.v3+json",
}

try:
    r = requests.get(f"{GITHUB_API}/repos/{GITHUB_REPO}",
                     headers=gh_headers, timeout=10)
    if r.status_code == 200:
        record("GitHub repo accessible", True,
               f"repo: {GITHUB_REPO}, default branch: {r.json().get('default_branch')}")
    elif r.status_code == 401:
        record("GitHub repo accessible", False, "401 Unauthorized",
               "GITHUB_TOKEN is invalid or expired. Create a new PAT at github.com/settings/tokens")
    elif r.status_code == 404:
        record("GitHub repo accessible", False, "404 Not Found",
               f"Check GITHUB_REPO='{GITHUB_REPO}' is correct and token has access")
    else:
        record("GitHub repo accessible", False, f"HTTP {r.status_code}: {r.text[:100]}")
except Exception as e:
    record("GitHub repo accessible", False, str(e), "Network issue reaching api.github.com")

# Test write: write a tiny test file and then delete it
try:
    from cryptography.fernet import Fernet
    _f  = Fernet(FERNET_KEY.encode() if FERNET_KEY else Fernet.generate_key())
    _enc = base64.b64encode(_f.encrypt(json.dumps({"dryrun": True}).encode())).decode()
    test_path = "db/dryrun_test.enc"
    url = f"{GITHUB_API}/repos/{GITHUB_REPO}/contents/{test_path}"

    # Create
    payload = {
        "message": "dry_run: test write (auto-deleted)",
        "content": _enc,
        "branch":  GITHUB_BRANCH,
    }
    r = requests.put(url, headers=gh_headers, json=payload, timeout=15)
    if r.status_code in (200, 201):
        sha = r.json()["content"]["sha"]
        record("GitHub write (create)", True, f"wrote {test_path}")

        # Delete it immediately
        del_payload = {"message": "dry_run: cleanup test file", "sha": sha, "branch": GITHUB_BRANCH}
        r2 = requests.delete(url, headers=gh_headers, json=del_payload, timeout=15)
        record("GitHub write (delete)", r2.status_code in (200, 201), f"deleted {test_path}")
    elif r.status_code == 401:
        record("GitHub write (create)", False, "401 Unauthorized",
               "PAT needs 'Contents: Read and Write' permission. "
               "The GITHUB_TOKEN from Actions env won't work -- use a PAT from github.com/settings/tokens")
    elif r.status_code == 403:
        record("GitHub write (create)", False, "403 Forbidden",
               "Token lacks write permission. Ensure PAT has 'Contents: Read and Write' for this repo.")
    else:
        record("GitHub write (create)", False, f"HTTP {r.status_code}: {r.text[:200]}")
except Exception as e:
    record("GitHub write", False, str(e))


# ────────────────────────────────────────────────────────────────
# TEST 4: Data source probes (1 stock each, exact response logged)
# ────────────────────────────────────────────────────────────────
print()
print("── TEST 4: Data Source Probes ───────────────────────────────")
print("   (probing each source with HDFCBANK -- one request each)")
print()

TEST_SYMBOL = "HDFCBANK"
BSE_SCRIP   = "500180"   # HDFCBANK BSE scrip code
end_dt      = datetime.today()
start_dt    = end_dt - timedelta(days=30)

# ── 4a. BSE India direct API ─────────────────────────────────────
print("  [BSE India direct API]")
try:
    bse_sess = requests.Session()
    bse_sess.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer":    "https://www.bseindia.com",
        "Accept":     "application/json, text/plain, */*",
        "Origin":     "https://www.bseindia.com",
    })
    r = bse_sess.get(
        "https://api.bseindia.com/BseIndiaAPI/api/StockReachGraph/w",
        params={"scripcode": BSE_SCRIP, "flag": "1",
                "fromdate": start_dt.strftime("%Y%m%d"),
                "todate":   end_dt.strftime("%Y%m%d"),
                "seriesid": "EQ"},
        timeout=15)
    print(f"    HTTP {r.status_code} | Server: {r.headers.get('Server','?')[:30]} | CF-Ray: {r.headers.get('CF-Ray','none')}")
    print(f"    Body[:200]: {r.text[:200].replace(chr(10),' ')}")
    if r.status_code == 200:
        try:
            data = r.json()
            rows = data.get("Data") or data.get("data") or []
            if rows:
                record("BSE India API", True, f"{len(rows)} data points for HDFCBANK (scrip {BSE_SCRIP})")
            else:
                record("BSE India API", False,
                       f"HTTP 200 but empty. Keys: {list(data.keys())}",
                       "BSE API structure may have changed -- check bseindia.com network tab")
        except Exception as je:
            record("BSE India API", False, f"JSON parse error: {je} | body: {r.text[:100]}")
    elif r.status_code == 403:
        record("BSE India API", False, "403 Forbidden",
               "Add stronger Referer/Origin headers or test jugaad-trader wrapper")
    else:
        record("BSE India API", False, f"HTTP {r.status_code}: {r.text[:150]}")
except Exception as e:
    record("BSE India API", False, f"{type(e).__name__}: {e}",
           "Network-level block. BSE API may not be reachable from GitHub Actions IPs.")

# ── 4b. jugaad-trader (BSE Python wrapper) ───────────────────────
print()
print("  [jugaad-trader]")
try:
    from jugaad_trader.stockdata import StockDataBse
    df = StockDataBse.stock_data_raw(BSE_SCRIP, start_dt.strftime("%Y%m%d"), end_dt.strftime("%Y%m%d"))
    if df is not None and not df.empty:
        record("jugaad-trader", True, f"{len(df)} rows for HDFCBANK")
    else:
        record("jugaad-trader", False, "Empty response",
               "jugaad-trader wraps the same BSE API -- if BSE API fails, this will too")
except ImportError:
    record("jugaad-trader", False, "Not installed",
           "Add jugaad-trader==0.2.17 to requirements.txt")
except Exception as e:
    record("jugaad-trader", False, f"{type(e).__name__}: {e}")

# ── 4c. Stooq ────────────────────────────────────────────────────
print()
print("  [Stooq]")
try:
    r = requests.get("https://stooq.com/q/d/l/",
                     params={"s": f"{TEST_SYMBOL.lower()}.ns",
                             "d1": start_dt.strftime("%Y%m%d"),
                             "d2": end_dt.strftime("%Y%m%d"), "i": "d"},
                     headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_2_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15"},
                     timeout=15)
    body = r.text[:200].replace("\n", " ").strip()
    print(f"    HTTP {r.status_code} | Server: {r.headers.get('Server','?')[:20]} | CF-Ray: {r.headers.get('CF-Ray','none')}")
    print(f"    Body[:200]: {body}")
    if r.status_code == 200 and r.text.strip().startswith("Date,"):
        import pandas as pd
        record("Stooq", True, f"{len(pd.read_csv(io.StringIO(r.text)))} rows")
    elif "No data" in r.text:
        record("Stooq", False,
               f"'No data' -- permanent Apache IP block for Azure/AWS/GCP ranges. "
               "Browser rotation ineffective (IP-based, not fingerprint-based).",
               "Expected failure. BSE India API is the replacement.")
    else:
        record("Stooq", False, f"HTTP {r.status_code} | {body[:100]}")
except Exception as e:
    record("Stooq", False, f"{type(e).__name__}: {e}")

# ── 4d. yfinance query1 ──────────────────────────────────────────
print()
print("  [yfinance/query1]")
try:
    import yfinance as yf
    hist = yf.Ticker(f"{TEST_SYMBOL}.NS").history(period="5d", timeout=15)
    if hist is not None and not hist.empty:
        record("yfinance/query1", True, f"{len(hist)} rows | latest: {hist['Close'].iloc[-1]:.2f}")
    else:
        record("yfinance/query1", False, "Empty response",
               "Rate limited. GitHub Actions shared IPs exhaust Yahoo's pool quickly.")
except Exception as e:
    err = str(e)
    if "429" in err or "RateLimit" in err:
        record("yfinance/query1", False,
               "YFRateLimitError -- Yahoo rate-limits GitHub Actions shared IPs. "
               "No safe time window -- the IP pool is always busy.",
               "Use BSE India API as primary. yfinance is unreliable from Actions.")
    else:
        record("yfinance/query1", False, f"{type(e).__name__}: {err[:150]}")

# ── 4e. Yahoo query2 subdomain ────────────────────────────────────
print()
print("  [Yahoo query2 subdomain]")
try:
    sess2 = requests.Session()
    sess2.headers.update({"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_2_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15"})
    url = f"https://query2.finance.yahoo.com/v8/finance/chart/{TEST_SYMBOL}.NS"
    r = sess2.get(url, params={"interval": "1d", "range": "5d", "includePrePost": "false"}, timeout=15)
    print(f"    HTTP {r.status_code} | Server: {r.headers.get('Server','?')[:30]}")
    if r.status_code == 200:
        closes = r.json().get("chart",{}).get("result",[{}])[0].get("indicators",{}).get("quote",[{}])[0].get("close",[])
        closes = [c for c in closes if c is not None]
        if closes:
            record("Yahoo/query2", True, f"{len(closes)} closes | latest: {closes[-1]:.2f}")
        else:
            record("Yahoo/query2", False, "HTTP 200 but no close prices")
    elif r.status_code == 429:
        record("Yahoo/query2", False,
               "429 -- query2 also rate-limited (same IP-level limit as query1)",
               "Both Yahoo subdomains share the same IP rate limit counter.")
    else:
        record("Yahoo/query2", False, f"HTTP {r.status_code}: {r.text[:150]}")
except Exception as e:
    record("Yahoo/query2", False, f"{type(e).__name__}: {e}")


# ────────────────────────────────────────────────────────────────
# TEST 5: Mini harvest (3 stocks, full analytics, write dryrun.enc)
# ────────────────────────────────────────────────────────────────
print()
print("── TEST 5: Mini Harvest (3 stocks) ──────────────────────────")

MINI_STOCKS = ["HDFCBANK", "TCS", "RELIANCE"]

try:
    import harvest_runner as hr

    # Check which source will actually work based on test 4 results
    fmp_ok    = any(n == "FMP data source"    and p for n, p, _ in RESULTS)
    stooq_ok  = any(n == "Stooq data source"  and p for n, p, _ in RESULTS)
    yf_ok     = any(n == "yfinance data source" and p for n, p, _ in RESULTS)

    if not (fmp_ok or stooq_ok or yf_ok):
        record("Mini harvest", False,
               "All data sources failed -- no point running mini harvest",
               "Fix at least one data source above first")
    else:
        working = "FMP" if fmp_ok else ("Stooq" if stooq_ok else "yfinance")
        print(f"  Using {working} as working source")

        mini_snapshot = []
        for sym in MINI_STOCKS:
            meta   = hr.get_ticker_meta(sym)
            prices = hr._fetch_prices(sym, meta)
            if prices is not None and len(prices) >= 20:
                ret    = prices.pct_change().dropna()
                rsi    = hr._compute_rsi(prices)
                macd   = hr._compute_macd(prices)
                cagr1y = hr._compute_cagr(prices, 1)
                mini_snapshot.append({
                    "ticker": sym,
                    "price":  round(float(prices.iloc[-1]), 2),
                    "rows":   len(prices),
                    "rsi":    rsi,
                    "macd":   macd,
                    "cagr_1y": cagr1y,
                })
                print(f"  ✅ {sym}: price={prices.iloc[-1]:.2f}, RSI={rsi}, MACD={macd}, rows={len(prices)}")
            else:
                print(f"  ❌ {sym}: no data")

        record("Mini harvest", len(mini_snapshot) > 0,
               f"{len(mini_snapshot)}/{len(MINI_STOCKS)} stocks fetched successfully")

        # Write to dryrun.enc (safe -- never overwrites snapshot.enc)
        if mini_snapshot and GITHUB_TOKEN and FERNET_KEY:
            ok = hr.gs.write(
                "dryrun",
                {"generated_at": datetime.utcnow().isoformat(),
                 "stocks": mini_snapshot},
                "dry_run: mini harvest test"
            )
            record("Write dryrun.enc", ok,
                   "wrote db/dryrun.enc (safe -- not snapshot.enc)" if ok else "write failed")

except ImportError:
    record("Mini harvest", False,
           "Could not import harvest_runner",
           "Ensure harvest_runner.py is in the same directory as dry_run.py")
except Exception as e:
    record("Mini harvest", False, f"{type(e).__name__}: {e}\n{traceback.format_exc()[:300]}")


# ────────────────────────────────────────────────────────────────
# FINAL SUMMARY
# ────────────────────────────────────────────────────────────────
print()
print("=" * 60)
print("  SUMMARY")
print("=" * 60)

passed = [(n, p, m) for n, p, m in RESULTS if p]
failed = [(n, p, m) for n, p, m in RESULTS if not p]

print(f"\n  Passed: {len(passed)}/{len(RESULTS)}")
if WARNINGS:
    print(f"  Warnings: {len(WARNINGS)}")
for w in WARNINGS:
    print(f"    ⚠️  {w}")

if failed:
    print(f"\n  Failed tests:")
    for n, _, m in failed:
        print()
        print(m)  # full message with FIX instruction
    print()
    print("  ⛔ Pipeline NOT ready. Fix the failed tests above.")
    sys.exit(1)
else:
    print("\n  ✅ All tests passed. Pipeline is healthy.")
    print("  The full harvest should succeed.")
    sys.exit(0)
