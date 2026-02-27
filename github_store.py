"""
Agent_Trader -- GitHub Store
Fernet encryption/decryption + GitHub Contents API read/write.
All data stored in SubhasishSahu/Avito/db/ as encrypted .enc files.

Encryption:  Fernet (AES-128-CBC + HMAC-SHA256)
Key source:  FERNET_KEY environment variable / Colab secret / Streamlit secret
GitHub API:  Contents API -- GET to read, PUT to write
"""
import os
import json
import base64
import requests
import logging
from datetime import datetime
from cryptography.fernet import Fernet, InvalidToken

log = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────────
GITHUB_API   = "https://api.github.com"
RAW_BASE     = "https://raw.githubusercontent.com"
REPO         = os.environ.get("GITHUB_REPO",   "SubhasishSahu/Avito")
BRANCH       = os.environ.get("GITHUB_BRANCH", "master")
DB_FOLDER    = "db"

# File registry -- logical name → filename in db/
DB_FILES = {
    "snapshot":         "snapshot.enc",
    "fundamentals":     "fundamentals.enc",
    "portfolio":        "portfolio.enc",
    "metadata":         "metadata.enc",
    "news":             "news.enc",
    "holdings_trigger": "holdings_trigger.enc",
}


# ── Fernet helpers ─────────────────────────────────────────────────────────────

def _get_fernet() -> Fernet:
    """Load Fernet instance from environment. Raises if key missing or invalid."""
    key = os.environ.get("FERNET_KEY", "").strip()
    if not key:
        # Try Colab userdata
        try:
            from google.colab import userdata
            key = userdata.get("FERNET_KEY", "").strip()
        except Exception:
            pass
    if not key:
        raise EnvironmentError(
            "FERNET_KEY not found. Set it in:\n"
            "  - GitHub Actions secrets\n"
            "  - Streamlit Cloud secrets\n"
            "  - Colab: Tools → Secrets → FERNET_KEY"
        )
    try:
        return Fernet(key.encode())
    except Exception as e:
        raise ValueError(f"FERNET_KEY is invalid: {e}")


def encrypt(data: dict | list) -> bytes:
    """Serialize dict/list to JSON then encrypt to bytes."""
    f = _get_fernet()
    raw = json.dumps(data, ensure_ascii=False, default=str).encode("utf-8")
    return f.encrypt(raw)


def decrypt(encrypted_bytes: bytes) -> dict | list:
    """Decrypt bytes and deserialize JSON. Raises InvalidToken if key wrong."""
    f = _get_fernet()
    try:
        raw = f.decrypt(encrypted_bytes)
        return json.loads(raw.decode("utf-8"))
    except InvalidToken:
        raise InvalidToken(
            "Decryption failed -- FERNET_KEY does not match the encrypted data. "
            "Ensure the same key is used for both encrypt and decrypt."
        )


# ── GitHub API helpers ─────────────────────────────────────────────────────────

def _get_token() -> str:
    """Load GitHub token from environment or Colab secrets."""
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if not token:
        try:
            from google.colab import userdata
            token = userdata.get("GITHUB_TOKEN", "").strip()
        except Exception:
            pass
    if not token:
        raise EnvironmentError(
            "GITHUB_TOKEN not found. Set it in Streamlit/Colab secrets."
        )
    return token


def _headers() -> dict:
    return {
        "Authorization": f"token {_get_token()}",
        "Accept": "application/vnd.github.v3+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _file_path(name: str) -> str:
    """Convert logical name to repo path e.g. snapshot → db/snapshot.enc"""
    filename = DB_FILES.get(name, f"{name}.enc")
    return f"{DB_FOLDER}/{filename}"


def _get_sha(path: str) -> str | None:
    """Get current SHA of a file (needed for update). Returns None if not exists."""
    url = f"{GITHUB_API}/repos/{REPO}/contents/{path}"
    r = requests.get(url, headers=_headers(), params={"ref": BRANCH}, timeout=15)
    if r.status_code == 200:
        return r.json().get("sha")
    return None


# ── Public read/write API ──────────────────────────────────────────────────────

def write(name: str, data: dict | list, commit_message: str = None) -> bool:
    """
    Encrypt data and write to GitHub db/ folder.
    Creates file if not exists, updates if exists.

    Args:
        name: logical name -- 'snapshot', 'portfolio', 'holdings_trigger', etc.
        data: dict or list to encrypt and store
        commit_message: optional custom commit message

    Returns:
        True on success, False on failure
    """
    path = _file_path(name)
    encrypted = encrypt(data)
    content_b64 = base64.b64encode(encrypted).decode("utf-8")
    sha = _get_sha(path)

    msg = commit_message or f"db: update {name} -- {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}"

    payload = {
        "message": msg,
        "content": content_b64,
        "branch":  BRANCH,
    }
    if sha:
        payload["sha"] = sha  # required for updates

    url = f"{GITHUB_API}/repos/{REPO}/contents/{path}"
    r = requests.put(url, headers=_headers(), json=payload, timeout=30)

    if r.status_code in (200, 201):
        action = "updated" if sha else "created"
        log.info(f"✅ GitHub write: {path} {action}")
        return True
    else:
        # Provide actionable error detail
        try:
            err_json = r.json()
            err_msg  = err_json.get("message", r.text[:300])
        except Exception:
            err_msg = r.text[:300]

        if r.status_code == 401:
            log.error(
                f"❌ GitHub write 401 Unauthorized: token invalid or missing. "
                f"Streamlit Cloud needs a Personal Access Token (PAT) with "
                f"repo scope, not the GitHub Actions GITHUB_TOKEN. "
                f"Create one at github.com/settings/tokens and add it to "
                f"Streamlit Cloud → App Settings → Secrets as GITHUB_TOKEN."
            )
        elif r.status_code == 403:
            log.error(
                f"❌ GitHub write 403 Forbidden: token lacks write permission. "
                f"Ensure the PAT has 'Contents: Read and Write' (fine-grained) "
                f"or 'repo' scope (classic). Error: {err_msg}"
            )
        elif r.status_code == 404:
            log.error(
                f"❌ GitHub write 404: repo or path not found. "
                f"Check GITHUB_REPO='{REPO}' and that db/ folder exists. "
                f"Error: {err_msg}"
            )
        else:
            log.error(f"❌ GitHub write failed: HTTP {r.status_code} -- {err_msg}")
        return False


def read(name: str) -> dict | list | None:
    """
    Read and decrypt a file from GitHub db/ folder.
    Uses raw GitHub URL -- no auth needed for public repo.

    Args:
        name: logical name -- 'snapshot', 'portfolio', 'metadata', etc.

    Returns:
        Decrypted dict/list, or None if file not found
    """
    path = _file_path(name)
    url  = f"{RAW_BASE}/{REPO}/{BRANCH}/{path}"

    try:
        r = requests.get(url, timeout=15)
        if r.status_code == 404:
            log.warning(f"File not found in GitHub: {path}")
            return None
        if r.status_code != 200:
            log.error(f"GitHub read failed: {r.status_code} for {path}")
            return None
        return decrypt(r.content)
    except InvalidToken:
        log.error(f"Decryption failed for {path} -- key mismatch")
        return None
    except Exception as e:
        log.error(f"GitHub read error for {path}: {e}")
        return None


def read_metadata() -> dict:
    """Read metadata.enc -- returns empty dict if not found."""
    return read("metadata") or {}


def write_metadata(stocks_harvested: int, tickers: list, run_id: str = None) -> bool:
    """Write harvest metadata to metadata.enc."""
    import uuid
    meta = {
        "last_harvest":      datetime.utcnow().isoformat(),
        "stocks_harvested":  stocks_harvested,
        "tickers":           tickers,
        "run_id":            run_id or str(uuid.uuid4())[:8],
        "repo":              REPO,
        "branch":            BRANCH,
    }
    return write("metadata", meta, f"harvest metadata: {stocks_harvested} stocks")


def file_exists(name: str) -> bool:
    """Check if a logical file exists in db/ folder."""
    path = _file_path(name)
    return _get_sha(path) is not None


def list_db_files() -> list:
    """List all files currently in the db/ folder."""
    url = f"{GITHUB_API}/repos/{REPO}/contents/{DB_FOLDER}"
    r = requests.get(url, headers=_headers(), params={"ref": BRANCH}, timeout=15)
    if r.status_code == 200:
        return [f["name"] for f in r.json() if isinstance(f, dict)]
    return []


# ── Convenience test ───────────────────────────────────────────────────────────

def test_connection() -> dict:
    """
    Test encryption and GitHub connectivity.
    Safe to run -- writes nothing, reads nothing sensitive.
    """
    results = {}

    # Test 1: Fernet key
    try:
        f = _get_fernet()
        test_enc = f.encrypt(b"ping")
        test_dec = f.decrypt(test_enc)
        results["fernet"] = "✅ Key valid -- encrypt/decrypt OK"
    except Exception as e:
        results["fernet"] = f"❌ {e}"

    # Test 2: GitHub token
    try:
        token = _get_token()
        results["github_token"] = f"✅ Token found -- starts with {token[:4]}"
    except Exception as e:
        results["github_token"] = f"❌ {e}"

    # Test 3: Repo access
    try:
        url = f"{GITHUB_API}/repos/{REPO}"
        r = requests.get(url, headers=_headers(), timeout=10)
        if r.status_code == 200:
            results["repo_access"] = f"✅ Repo accessible: {REPO}"
        else:
            results["repo_access"] = f"❌ Repo returned {r.status_code}"
    except Exception as e:
        results["repo_access"] = f"❌ {e}"

    # Test 4: db/ folder
    try:
        files = list_db_files()
        results["db_folder"] = f"✅ db/ folder found -- {len(files)} files: {files}"
    except Exception as e:
        results["db_folder"] = f"❌ {e}"

    return results
