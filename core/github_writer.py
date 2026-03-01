"""
core/github_writer.py
════════════════════════════════════════════════════════════════
Writes holdings_trigger.enc back to GitHub.
Called only from P6 Holdings Editor.

In MOCK mode  →  prints what it would write, returns success.
In LIVE mode  →  encrypts with Fernet and pushes via GitHub API.
════════════════════════════════════════════════════════════════
"""
from __future__ import annotations
import json
import base64
import os
from typing import Any


# ── detect environment ──────────────────────────────────────────
def _is_live() -> bool:
    try:
        import streamlit as st
        return (
            hasattr(st, "secrets")
            and "FERNET_KEY" in st.secrets
            and "GITHUB_TOKEN" in st.secrets
        )
    except Exception:
        return False


# ══════════════════════════════════════════════════════════════
# MOCK WRITE  (no secrets needed)
# ══════════════════════════════════════════════════════════════
def _mock_write(symbols: list[str]) -> dict:
    print(f"[MOCK] Would write {len(symbols)} symbols to holdings_trigger.enc")
    print(f"[MOCK] Symbols: {symbols}")
    return {"ok": True, "mock": True, "symbols_written": len(symbols)}


# ══════════════════════════════════════════════════════════════
# LIVE WRITE
# ══════════════════════════════════════════════════════════════
def _live_write(symbols: list[str]) -> dict:
    import requests
    import streamlit as st
    from cryptography.fernet import Fernet

    fernet    = Fernet(st.secrets["FERNET_KEY"].encode())
    token     = st.secrets["GITHUB_TOKEN"]
    repo      = st.secrets.get("GITHUB_REPO", "SubhasishSahu/Avito")
    branch    = st.secrets.get("GITHUB_BRANCH", "master")
    path      = "db/holdings_trigger.enc"

    # Encrypt
    payload   = json.dumps(symbols).encode()
    encrypted = fernet.encrypt(payload)
    b64_enc   = base64.b64encode(encrypted).decode()

    headers = {
        "Authorization": f"token {token}",
        "Accept":        "application/vnd.github.v3+json",
    }
    api_url = f"https://api.github.com/repos/{repo}/contents/{path}"

    # Get current SHA (needed for update)
    get_r = requests.get(api_url, headers=headers)
    sha   = get_r.json().get("sha") if get_r.status_code == 200 else None

    body: dict[str, Any] = {
        "message": f"dashboard: update holdings_trigger ({len(symbols)} symbols)",
        "content": b64_enc,
        "branch":  branch,
    }
    if sha:
        body["sha"] = sha

    put_r = requests.put(api_url, headers=headers, json=body)

    if put_r.status_code in (200, 201):
        return {"ok": True, "mock": False, "symbols_written": len(symbols)}
    else:
        return {
            "ok": False, "mock": False,
            "error": put_r.json().get("message", "Unknown GitHub error"),
            "status_code": put_r.status_code,
        }


# ══════════════════════════════════════════════════════════════
# PUBLIC API
# ══════════════════════════════════════════════════════════════
def write_holdings(symbols: list[str]) -> dict:
    """
    Write a list of NSE symbols to holdings_trigger.enc on GitHub.

    Returns:
        {"ok": bool, "mock": bool, "symbols_written": int}
        or on error:
        {"ok": False, "mock": False, "error": str}
    """
    if not symbols:
        return {"ok": False, "error": "Empty symbol list — nothing to write"}

    if _is_live():
        return _live_write(symbols)
    return _mock_write(symbols)
