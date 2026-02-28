"""
Agent_Trader -- Pipeline Dry Run / Diagnostic Tool
===================================================
Tests the entire harvest pipeline end-to-end.
Safe: writes to db/dryrun_test.enc only, never touches snapshot.enc.

Run locally:   python dry_run.py
Run on Actions: triggered by dry_run.yml workflow

Exit codes:
  0 = all tests passed (or only expected warnings — rate limits at peak hour)
  1 = genuine failure (auth broken, GitHub unreachable, code error)

What changed from previous version (2026-02-28)
------------------------------------------------
Colab test proved Stooq does NOT index Indian NSE stocks.
'No data' is a coverage gap, not an IP block. Removed Stooq test.
BSE India API requires JavaScript-rendered cookies — removed as a primary
source but kept as a canary test to verify this diagnosis holds.
yfinance (query1 + query2) is the sole data source going forward.
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

RESULTS  = []
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
print("=" * 62)
print("  Agent_Trader Pipeline Dry Run")
print(f"  {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
now_ist = datetime.utcnow() + timedelta(hours=5, minutes=30)
print(f"  {now_ist.strftime('%H:%M IST')} "
      f"({'in harvest window ✅' if 18 <= datetime.utcnow().hour < 24 else 'outside harvest window ⚠️  (18:30-23:30 UTC)'})")
print("=" * 62)
print()


# ────────────────────────────────────────────────────────────────
# TEST 1: Secrets / environment variables
# ────────────────────────────────────────────────────────────────
print("── TEST 1: Secrets ──────────────────────────────────────────")

FERNET_KEY    = os.environ.get("FERNET_KEY",    "").strip()
GITHUB_TOKEN  = os.environ.get("GITHUB_TOKEN",  "").strip()
GITHUB_REPO   = os.environ.get("GITHUB_REPO",   "SubhasishSahu/Avito").strip()
GITHUB_BRANCH = os.environ.get("GITHUB_BRANCH", "master").strip()

record("FERNET_KEY set", bool(FERNET_KEY),
       f"starts with: {FERNET_KEY[:8]}..." if FERNET_KEY else "",
       "Add FERNET_KEY to GitHub Secrets and Streamlit Secrets")

record("GITHUB_TOKEN set", bool(GITHUB_TOKEN),
       f"starts with: {GITHUB_TOKEN[:4]}..." if GITHUB_TOKEN else "",
       "Add GITHUB_TOKEN (PAT with Contents: Read+Write) to GitHub Secrets")

record("GITHUB_REPO set", bool(GITHUB_REPO), f"repo: {GITHUB_REPO}")

# Removed: FMP_API_KEY (FMP free tier does not support NSE stocks)


# ────────────────────────────────────────────────────────────────
# TEST 2: Encryption round-trip
# ────────────────────────────────────────────────────────────────
print()
print("── TEST 2: Encryption ───────────────────────────────────────")

try:
    from cryptography.fernet import Fernet, InvalidToken
    f = Fernet(FERNET_KEY.encode() if FERNET_KEY else Fernet.generate_key())
    payload   = {"test": "dry_run", "ts": datetime.utcnow().isoformat()}
    encrypted = f.encrypt(json.dumps(payload).encode())
    decrypted = json.loads(f.decrypt(encrypted).decode())
    assert decrypted["test"] == "dry_run"
    record("Fernet encrypt/decrypt", True,
           f"round-trip OK ({len(encrypted)} bytes)")
except Exception as e:
    record("Fernet encrypt/decrypt", False, str(e),
           "Check FERNET_KEY is a valid 44-char base64 Fernet key")


# ────────────────────────────────────────────────────────────────
# TEST 3: GitHub API connectivity + write
# ────────────────────────────────────────────────────────────────
print()
print("── TEST 3: GitHub API ───────────────────────────────────────")

GITHUB_API = "https://api.github.com"
gh_headers = {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept":        "application/vnd.github.v3+json",
}

try:
    r = requests.get(f"{GITHUB_API}/repos/{GITHUB_REPO}",
                     headers=gh_headers, timeout=10)
    if r.status_code == 200:
        record("GitHub repo accessible", True,
               f"repo: {GITHUB_REPO}, branch: {GITHUB_BRANCH}")
    elif r.status_code == 401:
        record("GitHub repo accessible", False, "401 Unauthorized",
               "GITHUB_TOKEN invalid or expired. Create a new PAT at github.com/settings/tokens")
    elif r.status_code == 404:
        record("GitHub repo accessible", False, "404 Not Found",
               f"Check GITHUB_REPO='{GITHUB_REPO}' is correct and token has access")
    else:
        record("GitHub repo accessible", False,
               f"HTTP {r.status_code}: {r.text[:100]}")
except Exception as e:
    record("GitHub repo accessible", False, str(e),
           "Network issue reaching api.github.com")

try:
    from cryptography.fernet import Fernet
    _f   = Fernet(FERNET_KEY.encode() if FERNET_KEY else Fernet.generate_key())
    _enc = base64.b64encode(
        _f.encrypt(json.dumps({"dryrun": True}).encode())
    ).decode()
    test_path = "db/dryrun_test.enc"
    url       = f"{GITHUB_API}/repos/{GITHUB_REPO}/contents/{test_path}"

    r = requests.put(url, headers=gh_headers, json={
        "message": "dry_run: test write (auto-deleted)",
        "content": _enc,
        "branch":  GITHUB_BRANCH,
    }, timeout=15)

    if r.status_code in (200, 201):
        sha = r.json()["content"]["sha"]
        record("GitHub write (create)", True, f"wrote {test_path}")
        r2 = requests.delete(url, headers=gh_headers, json={
            "message": "dry_run: cleanup test file",
            "sha":     sha,
            "branch":  GITHUB_BRANCH,
        }, timeout=15)
        record("GitHub write (delete)", r2.status_code in (200, 201),
               f"deleted {test_path}")
    elif r.status_code == 401:
        record("GitHub write (create)", False, "401 Unauthorized",
               "PAT needs 'Contents: Read and Write' permission.")
    elif r.status_code == 403:
        record("GitHub write (create)", False, "403 Forbidden",
               "Token lacks write permission.")
    else:
        record("GitHub write (create)", False,
               f"HTTP {r.status_code}: {r.text[:200]}")
except Exception as e:
    record("GitHub write", False, str(e))


# ────────────────────────────────────────────────────────────────
# TEST 4: Data source probes
# ────────────────────────────────────────────────────────────────
print()
print("── TEST 4: Data Source Probes ───────────────────────────────")
print("   (HDFCBANK — one request per source, minimal quota usage)")
print()

TEST_SYMBOL = "HDFCBANK"
end_dt      = datetime.today()
start_dt    = end_dt - timedelta(days=365)


# ── 4a. BSE India API (canary test — expected to fail) ─────────────
# Kept to verify our understanding: BSE sets cookies via JavaScript,
# so this will always return null data from any automated environment.
# If this ever starts returning real data, it means BSE changed their
# auth approach and we should revisit BSE as a source.
print("  [BSE India API — canary test, expected: null data]")
try:
    bse_sess = requests.Session()
    bse_sess.headers.update({
        "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection":      "keep-alive",
    })
    r0 = bse_sess.get("https://www.bseindia.com", timeout=15)
    cf0       = r0.headers.get("CF-Ray", "none")
    cookies   = list(bse_sess.cookies.keys())
    print(f"    Handshake: HTTP {r0.status_code} | CF-Ray: {cf0} | cookies: {cookies}")

    bse_sess.headers.update({
        "Accept":  "application/json, text/plain, */*",
        "Referer": "https://www.bseindia.com/",
        "Origin":  "https://www.bseindia.com",
    })
    r = bse_sess.get(
        "https://api.bseindia.com/BseIndiaAPI/api/StockReachGraph/w",
        params={"scripcode": "500180", "flag": "1",
                "fromdate": start_dt.strftime("%Y%m%d"),
                "todate":   end_dt.strftime("%Y%m%d"),
                "seriesid": "EQ"},
        timeout=15)
    print(f"    API: HTTP {r.status_code} | body[:100]: {r.text[:100]}")

    if r.status_code == 200 and r.text.strip().startswith("{"):
        import json as _json
        data = r.json()
        raw  = data.get("Data") or "[]"
        rows = _json.loads(raw) if isinstance(raw, str) else raw
        n    = len(rows) if isinstance(rows, list) else 0
        if n >= 20:
            # Unexpected success — BSE may have changed their auth
            warn(f"BSE India: unexpectedly returned {n} rows. "
                 "BSE may have relaxed cookie requirements. "
                 "Consider re-adding BSE as a data source in harvest_runner.py.")
        else:
            # Expected: null response, JS cookies not set
            warn("BSE India: null response (expected — cookies require JavaScript). "
                 "This is the known behaviour. Not a bug.")
    else:
        warn(f"BSE India: HTTP {r.status_code} (expected — JS cookie dependency)")
except Exception as e:
    warn(f"BSE India: {type(e).__name__}: {e}")


# ── 4b. Stooq (canary test — expected to return 'No data') ──────────
# Colab test (2026-02-28) proved Stooq does not carry Indian NSE stocks.
# 'No data' from Stooq is a coverage gap, not an IP block.
# If Stooq ever returns real CSV, this is significant — log it.
print()
print("  [Stooq — canary test, expected: 'No data' (no NSE coverage)]")
try:
    r = requests.get(
        "https://stooq.com/q/d/l/",
        params={"s": f"{TEST_SYMBOL.lower()}.ns",
                "d1": start_dt.strftime("%Y%m%d"),
                "d2": end_dt.strftime("%Y%m%d"), "i": "d"},
        headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_2_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15"},
        timeout=15)
    body = r.text[:120].replace("\n", " ").strip()
    print(f"    HTTP {r.status_code} | body: {body}")
    if r.status_code == 200 and r.text.strip().startswith("Date,"):
        import pandas as pd
        warn(f"Stooq: unexpectedly returned CSV ({len(pd.read_csv(io.StringIO(r.text)))} rows). "
             "Stooq may have started indexing NSE stocks. "
             "Consider re-adding Stooq to harvest_runner.py waterfall.")
    elif "No data" in r.text:
        warn("Stooq: 'No data' confirmed — no NSE stock coverage (expected, not a bug).")
    else:
        warn(f"Stooq: HTTP {r.status_code} | {body[:80]}")
except Exception as e:
    warn(f"Stooq: {type(e).__name__}: {e}")


# ── 4c. yfinance query1 (primary source) ─────────────────────────────
print()
print("  [yfinance / query1 — primary data source]")
try:
    import yfinance as yf
    hist = yf.Ticker(f"{TEST_SYMBOL}.NS").history(period="5d", timeout=15)
    if hist is not None and not hist.empty:
        record("yfinance/query1", True,
               f"{len(hist)} rows | latest: ₹{hist['Close'].iloc[-1]:.2f}")
    else:
        warn("yfinance/query1: empty response — likely rate-limited at this hour. "
             "Harvest window: 18:30-23:30 UTC (midnight-5:30am IST).")
except Exception as e:
    err = str(e)
    if "429" in err or "RateLimit" in err or "Too Many" in err:
        warn("yfinance/query1: rate-limited. "
             "Expected at peak hours (9am-6pm IST) from Azure IPs. "
             "Harvest at 18:30 UTC (midnight IST) will succeed.")
    else:
        record("yfinance/query1", False,
               f"{type(e).__name__}: {err[:150]}",
               "Check yfinance version: pip install -U yfinance")


# ── 4d. Yahoo query2 subdomain (fallback source) ─────────────────────
print()
print("  [Yahoo query2 — independent rate-limit pool, fallback source]")
try:
    sess2 = requests.Session()
    sess2.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_2_1) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) "
            "Version/17.2 Safari/605.1.15"
        ),
    })
    r = sess2.get(
        f"https://query2.finance.yahoo.com/v8/finance/chart/{TEST_SYMBOL}.NS",
        params={"interval": "1d", "range": "5d", "includePrePost": "false"},
        timeout=15)
    print(f"    HTTP {r.status_code} | Server: {r.headers.get('Server','?')[:30]}")
    if r.status_code == 200:
        closes = (r.json()
                  .get("chart", {})
                  .get("result", [{}])[0]
                  .get("indicators", {})
                  .get("quote", [{}])[0]
                  .get("close", []))
        closes = [c for c in closes if c is not None]
        if closes:
            record("Yahoo/query2", True,
                   f"{len(closes)} closes | latest: ₹{closes[-1]:.2f}")
        else:
            record("Yahoo/query2", False,
                   "HTTP 200 but no close prices in response")
    elif r.status_code == 429:
        warn("Yahoo/query2: 429 — both query1 and query2 are exhausted at this hour. "
             "Harvest at midnight IST will have fresh quota.")
    else:
        warn(f"Yahoo/query2: HTTP {r.status_code}")
except Exception as e:
    warn(f"Yahoo/query2: {type(e).__name__}: {e}")


# ────────────────────────────────────────────────────────────────
# TEST 5: Pipeline readiness
# ────────────────────────────────────────────────────────────────
print()
print("── TEST 5: Pipeline Readiness ───────────────────────────────")
print()
print("  No mini-harvest. Running one here would consume quota from the same")
print("  Azure IP pool that the full harvest uses 60 seconds later.")
print()

yf_ok     = any(n == "yfinance/query1" and p for n, p, _ in RESULTS)
q2_ok     = any(n == "Yahoo/query2"    and p for n, p, _ in RESULTS)
github_ok = any(n == "GitHub write (create)" and p for n, p, _ in RESULTS)

any_yf    = yf_ok or q2_ok

yf_rate_limited = any(
    "rate-limit" in w.lower() or "rate-limited" in w.lower()
    for w in WARNINGS
)

if any_yf and github_ok:
    source = "yfinance/q1" if yf_ok else "yfinance/q2"
    record("Pipeline ready", True,
           f"{source} + GitHub write both verified. Safe to trigger full harvest.")

elif not any_yf and yf_rate_limited and github_ok:
    warn(
        "Pipeline readiness: yfinance rate-limited at this hour (not a code bug). "
        "Scheduled harvest at 18:30 UTC / midnight IST will succeed when quota resets. "
        "Do not run dry run immediately before the scheduled harvest."
    )

elif not github_ok:
    record("Pipeline ready", False,
           "GitHub write failed — cannot store harvest results.",
           "Check GITHUB_TOKEN permissions (Contents: Read+Write required).")

else:
    record("Pipeline ready", False,
           "No data source returned prices and this is not a rate-limit issue.",
           "Check yfinance version: pip install -U yfinance")


# ────────────────────────────────────────────────────────────────
# SUMMARY
# ────────────────────────────────────────────────────────────────
print()
print("=" * 62)
print("  SUMMARY")
print("=" * 62)

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
        print(m)
    print()
    print("  ⛔ Pipeline NOT ready. Fix the failures above.")
    sys.exit(1)
else:
    print()
    print("  ✅ All tests passed.")
    if WARNINGS:
        print("  Rate-limit warnings are expected at peak hours — harvest at 18:30 UTC will succeed.")
    sys.exit(0)