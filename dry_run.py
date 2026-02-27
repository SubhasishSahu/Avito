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
# TEST 4: Data source probes (1 stock each, full header inspection)
# ────────────────────────────────────────────────────────────────
print()
print("── TEST 4: Data Source Probes ───────────────────────────────")
print("   (probing each source with HDFCBANK -- one request each)")
print()

TEST_SYMBOL    = "HDFCBANK"
end_dt         = datetime.today()
start_dt       = end_dt - timedelta(days=30)   # 30 days only for probe

# ── 4a. FMP ──────────────────────────────────────────────────────
print("  [FMP]")
if not FMP_API_KEY:
    warn("FMP_API_KEY not set -- skipping FMP probe")
else:
    try:
        fmp_url = f"https://financialmodelingprep.com/api/v3/historical-price-full/{TEST_SYMBOL}.NS"
        r = requests.get(fmp_url,
                         params={"from": start_dt.strftime("%Y-%m-%d"),
                                 "to":   end_dt.strftime("%Y-%m-%d"),
                                 "apikey": FMP_API_KEY},
                         headers={"User-Agent": "Agent_Trader/1.0"},
                         timeout=15)
        print(f"    HTTP {r.status_code} | Content-Type: {r.headers.get('Content-Type','?')[:50]}")

        if r.status_code == 200:
            data = r.json()
            hist = data.get("historical", [])
            if hist:
                record("FMP data source", True,
                       f"{len(hist)} rows for {TEST_SYMBOL}.NS | latest close: {hist[0].get('close')}")
                # Check quota header
                remaining = r.headers.get("X-RateLimit-Remaining", "?")
                if remaining != "?":
                    print(f"    API quota remaining: {remaining}/day")
            else:
                record("FMP data source", False,
                       f"HTTP 200 but no historical data. Response: {json.dumps(data)[:200]}",
                       f"Check symbol format -- try {TEST_SYMBOL}.BO (BSE) if .NS fails")
        elif r.status_code == 401:
            record("FMP data source", False, "401 -- API key invalid",
                   "Regenerate key at financialmodelingprep.com and update FMP_API_KEY secret")
        elif r.status_code == 403:
            record("FMP data source", False, "403 -- endpoint not available on free tier",
                   "NSE data requires the Starter plan ($19/mo). Use FMP with BSE symbols or switch to Twelve Data.")
        else:
            record("FMP data source", False,
                   f"HTTP {r.status_code}: {r.text[:200]}")
    except Exception as e:
        record("FMP data source", False, f"{type(e).__name__}: {e}")

# ── 4b. Stooq ────────────────────────────────────────────────────
print()
print("  [Stooq]")
try:
    stooq_url = "https://stooq.com/q/d/l/"
    # Try Safari UA first (most likely to work if UA-based)
    safari_headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_2_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-GB,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
    }
    r = requests.get(stooq_url,
                     params={"s": f"{TEST_SYMBOL.lower()}.ns",
                             "d1": start_dt.strftime("%Y%m%d"),
                             "d2": end_dt.strftime("%Y%m%d"),
                             "i": "d"},
                     headers=safari_headers, timeout=15)

    cf_ray    = r.headers.get("CF-Ray", "")
    cf_server = r.headers.get("Server", "")
    is_cf     = bool(cf_ray) or "cloudflare" in cf_server.lower()
    body_prev = r.text[:200].replace("\n", " ").strip()

    print(f"    HTTP {r.status_code} | Server: {cf_server[:30]} | CF-Ray: {cf_ray or 'none'}")
    print(f"    Content-Type: {r.headers.get('Content-Type', '?')[:60]}")
    print(f"    Body[:200]: {body_prev}")

    if r.status_code == 200 and r.text.strip().startswith("Date,"):
        import pandas as pd
        df = pd.read_csv(io.StringIO(r.text))
        record("Stooq data source", True,
               f"{len(df)} rows for {TEST_SYMBOL}.ns (Safari UA)")
    elif is_cf and r.status_code in (403, 503):
        record("Stooq data source", False,
               f"Cloudflare Bot Fight Mode (CF-Ray: {cf_ray})",
               "Stooq is Cloudflare-protected. FMP with API key is the reliable alternative.")
    elif is_cf and r.status_code == 200 and "<html" in r.text.lower():
        record("Stooq data source", False,
               f"Cloudflare JS challenge page (CF-Ray: {cf_ray})",
               "cf_clearance cookie required -- not feasible from GitHub Actions. Use FMP instead.")
    elif r.status_code == 200 and "No data" in r.text:
        record("Stooq data source", False,
               "HTTP 200 but 'No data' -- symbol not found or soft block",
               "Try different symbol format or check stooq.com manually")
    else:
        record("Stooq data source", False,
               f"HTTP {r.status_code} | CF: {'yes' if is_cf else 'no'} | body: {body_prev[:100]}")
except Exception as e:
    record("Stooq data source", False, f"{type(e).__name__}: {e}")

# ── 4c. yfinance ─────────────────────────────────────────────────
print()
print("  [yfinance]")
try:
    import yfinance as yf
    ticker = yf.Ticker(f"{TEST_SYMBOL}.NS")
    hist   = ticker.history(period="5d", auto_adjust=True, actions=False, timeout=15)
    if hist is not None and not hist.empty:
        record("yfinance data source", True,
               f"{len(hist)} rows for {TEST_SYMBOL}.NS | latest: {hist['Close'].iloc[-1]:.2f}")
    else:
        record("yfinance data source", False,
               "Empty response -- rate limited or blocked at this time",
               "yfinance works at midnight IST (18:30 UTC). Schedule-only is reliable.")
except Exception as e:
    err = str(e)
    if "429" in err or "Too Many" in err.lower():
        record("yfinance data source", False,
               "429 Too Many Requests -- blocked from this IP at this time",
               "yfinance only works at off-peak hours from GitHub Actions IPs")
    else:
        record("yfinance data source", False, f"{type(e).__name__}: {err[:150]}")


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
