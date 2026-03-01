"""
pages/06_Holdings.py
════════════════════════════════════════════════════════════════
P6 · Holdings Editor
The only page that writes back to GitHub.

Three input modes:
  1. Type / paste symbols
  2. Upload .xlsx / .csv file
  3. AI image scan (calls Anthropic API)

On save → core/github_writer.write_holdings() encrypts and
pushes to db/holdings_trigger.enc on GitHub.
════════════════════════════════════════════════════════════════
"""
import sys
import pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

import json
import base64
import streamlit as st

st.set_page_config(
    page_title="AVITO · Holdings Editor",
    page_icon="⬡",
    layout="wide",
    initial_sidebar_state="collapsed",
)

from core.page_setup import apply; apply()
from core.data_loader import SYMBOL_META, DEFAULT_HOLDINGS, resolve_symbol  # type: ignore
from core.github_writer import write_holdings

# ── local symbol resolver (fallback if not exported from data_loader) ──
try:
    from core.data_loader import resolve_symbol
except ImportError:
    def resolve_symbol(raw: str) -> dict | None:
        clean = raw.strip().upper().replace(".", "").replace(" ", "")
        if clean in SYMBOL_META:
            return {"symbol": clean, **SYMBOL_META[clean], "status": "verified"}
        # fuzzy: check if raw lowercased matches any name
        for sym, meta in SYMBOL_META.items():
            if raw.strip().lower() in meta["name"].lower():
                return {"symbol": sym, **meta, "status": "verified"}
        return {"symbol": clean, "name": raw.strip(), "sector": "Unknown",
                "cap": "?", "status": "unknown"}

# ══════════════════════════════════════════════════════════════
# SESSION STATE
# ══════════════════════════════════════════════════════════════
if "holdings" not in st.session_state:
    st.session_state.holdings = [
        {"symbol": s, **SYMBOL_META.get(s, {"name": s, "sector": "Unknown", "cap": "?"}),
         "status": "verified" if s in SYMBOL_META else "unknown"}
        for s in DEFAULT_HOLDINGS
    ]
if "save_result" not in st.session_state:
    st.session_state.save_result = None

# ══════════════════════════════════════════════════════════════
# THEME — inject mainframe CSS into native Streamlit elements
# ══════════════════════════════════════════════════════════════
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=IBM+Plex+Sans:wght@300;400;500&display=swap');

body, .stApp { background: #070a0d !important; color: #b8cce0; font-family: 'IBM Plex Sans', sans-serif; }

/* Page header */
.pg-tag  { font-family: 'IBM Plex Mono', monospace; font-size: 10px; letter-spacing: .16em;
           text-transform: uppercase; color: #3d5570; margin-bottom: 4px; }
.pg-title{ font-size: 22px; font-weight: 300; color: #b8cce0; letter-spacing: -.02em; }
.pg-sub  { font-size: 12px; color: #6a8aa8; margin-top: 3px; margin-bottom: 20px; }

/* Cards */
.card { background: #0b0f14; border: 1px solid #1a2535; border-radius: 8px;
        padding: 16px 18px; margin-bottom: 14px; }
.c-label { font-family: 'IBM Plex Mono', monospace; font-size: 9px; letter-spacing: .14em;
           text-transform: uppercase; color: #3d5570; margin-bottom: 10px; }

/* Streamlit overrides */
div[data-testid="stTextInput"] input,
div[data-testid="stTextArea"] textarea {
  background: #0f1520 !important; border: 1px solid #243044 !important;
  border-radius: 6px !important; color: #b8cce0 !important;
  font-family: 'IBM Plex Mono', monospace !important; font-size: 12px !important;
}
div[data-testid="stButton"] button {
  background: #00e5a0 !important; color: #000 !important; border: none !important;
  font-family: 'IBM Plex Mono', monospace !important; font-weight: 600 !important;
  letter-spacing: .08em !important; border-radius: 6px !important;
}
div[data-testid="stButton"] button[kind="secondary"] {
  background: transparent !important; border: 1px solid #243044 !important;
  color: #6a8aa8 !important;
}
div[data-testid="stFileUploader"] {
  background: #0f1520 !important; border: 1px dashed #243044 !important;
  border-radius: 8px !important;
}
.stDataFrame { background: #0b0f14 !important; }
div[data-testid="stSelectbox"] > div { background: #0f1520 !important; border-color: #243044 !important; }
div[data-testid="stAlert"] { border-radius: 6px !important; }

/* Mode tabs */
.mode-tab {
  display: inline-block; padding: 7px 18px; cursor: pointer;
  font-family: 'IBM Plex Mono', monospace; font-size: 10px; letter-spacing: .08em;
  border-radius: 5px; margin-right: 6px; border: 1px solid #1a2535;
  text-transform: uppercase; color: #6a8aa8; background: #0f1520;
}
.mode-tab.active { background: rgba(0,229,160,.08); border-color: rgba(0,229,160,.3); color: #00e5a0; }

/* Holdings table */
.h-table { width: 100%; border-collapse: collapse; font-size: 11px; }
.h-table th { font-family: 'IBM Plex Mono', monospace; font-size: 8px; letter-spacing: .1em;
              text-transform: uppercase; color: #3d5570; padding: 7px 10px;
              text-align: left; border-bottom: 1px solid #1a2535; font-weight: 400; }
.h-table td { padding: 7px 10px; border-bottom: 1px solid rgba(26,37,53,.5); }
.h-table tr:hover td { background: rgba(255,255,255,.015); }
.sym-v { font-family: 'IBM Plex Mono', monospace; color: #00e5a0; }
.sym-u { font-family: 'IBM Plex Mono', monospace; color: #ff4757; }
.tag-xs { display: inline-block; padding: 1px 7px; border-radius: 2px;
          font-family: 'IBM Plex Mono', monospace; font-size: 8px; }
.tg { background: rgba(0,229,160,.08); color: #00e5a0; }
.tr2{ background: rgba(255,71,87,.08); color: #ff4757; }
.ta { background: rgba(245,166,35,.1); color: #f5a623; }
.tb { background: rgba(56,182,255,.1); color: #38b6ff; }

/* Save banner */
.save-ok   { background: rgba(0,229,160,.08); border: 1px solid rgba(0,229,160,.3);
             border-radius: 6px; padding: 10px 14px; font-family: 'IBM Plex Mono', monospace;
             font-size: 11px; color: #00e5a0; margin-bottom: 14px; }
.save-err  { background: rgba(255,71,87,.08); border: 1px solid rgba(255,71,87,.3);
             border-radius: 6px; padding: 10px 14px; font-family: 'IBM Plex Mono', monospace;
             font-size: 11px; color: #ff4757; margin-bottom: 14px; }
.save-mock { background: rgba(245,166,35,.08); border: 1px solid rgba(245,166,35,.3);
             border-radius: 6px; padding: 10px 14px; font-family: 'IBM Plex Mono', monospace;
             font-size: 11px; color: #f5a623; margin-bottom: 14px; }
</style>
""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════
# HEADER
# ══════════════════════════════════════════════════════════════
st.markdown("""
<div class="pg-tag">// P6 · Holdings Editor</div>
<div class="pg-title">Voice · Type · Image Scan</div>
<div class="pg-sub">Update existing holdings or onboard a new portfolio. Changes write to <code>holdings_trigger.enc</code> on GitHub.</div>
""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════
# SAVE RESULT BANNER
# ══════════════════════════════════════════════════════════════
if st.session_state.save_result:
    res = st.session_state.save_result
    if res.get("ok") and res.get("mock"):
        st.markdown(f'<div class="save-mock">⚠ MOCK SAVE — would write {res["symbols_written"]} symbols. Set FERNET_KEY + GITHUB_TOKEN secrets for live write.</div>', unsafe_allow_html=True)
    elif res.get("ok"):
        st.markdown(f'<div class="save-ok">✓ Saved {res["symbols_written"]} symbols to holdings_trigger.enc on GitHub</div>', unsafe_allow_html=True)
    else:
        st.markdown(f'<div class="save-err">✗ Save failed: {res.get("error","Unknown error")}</div>', unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════
# TWO-COLUMN LAYOUT
# ══════════════════════════════════════════════════════════════
col_left, col_right = st.columns([1, 1.8], gap="medium")

# ── LEFT: current holdings ──────────────────────────────────
with col_left:
    verified   = [h for h in st.session_state.holdings if h["status"] == "verified"]
    unverified = [h for h in st.session_state.holdings if h["status"] == "unknown"]

    st.markdown(f"""
    <div class="card">
      <div class="c-label">// Current Holdings</div>
      <div style="display:flex;gap:10px;margin-bottom:12px">
        <span class="tag-xs tg">{len(verified)} verified</span>
        <span class="tag-xs tr2">{len(unverified)} unknown</span>
        <span class="tag-xs tb" style="margin-left:auto">{len(st.session_state.holdings)} total</span>
      </div>
    </div>
    """, unsafe_allow_html=True)

    if st.session_state.holdings:
        # Render holdings as HTML table
        rows_html = ""
        for h in st.session_state.holdings:
            sym_cls = "sym-v" if h["status"] == "verified" else "sym-u"
            tag_cls = "tg" if h["status"] == "verified" else "tr2"
            tag_txt = "✓ NSE" if h["status"] == "verified" else "✗ Unknown"
            rows_html += f"""<tr>
              <td class="{sym_cls}">{h['symbol']}</td>
              <td style="color:#6a8aa8;font-size:10px">{h.get('name','')}</td>
              <td style="color:#3d5570;font-size:10px">{h.get('sector','')}</td>
              <td><span class="tag-xs {tag_cls}">{tag_txt}</span></td>
            </tr>"""

        st.markdown(f"""
        <div style="max-height:480px;overflow-y:auto;scrollbar-width:thin;scrollbar-color:#243044 transparent">
          <table class="h-table">
            <thead><tr><th>Symbol</th><th>Name</th><th>Sector</th><th>Status</th></tr></thead>
            <tbody>{rows_html}</tbody>
          </table>
        </div>
        """, unsafe_allow_html=True)

    # Action buttons
    st.markdown("<br>", unsafe_allow_html=True)
    btn_col1, btn_col2, btn_col3 = st.columns(3)

    with btn_col1:
        if st.button("✓ Save to GitHub", use_container_width=True):
            symbols = [h["symbol"] for h in st.session_state.holdings]
            result  = write_holdings(symbols)
            st.session_state.save_result = result
            st.rerun()

    with btn_col2:
        if st.button("✕ Remove Unknown", use_container_width=True):
            st.session_state.holdings = [h for h in st.session_state.holdings if h["status"] == "verified"]
            st.session_state.save_result = None
            st.rerun()

    with btn_col3:
        if st.button("⟳ Reset", use_container_width=True):
            st.session_state.holdings = [
                {"symbol": s, **SYMBOL_META.get(s, {"name": s, "sector": "Unknown", "cap": "?"}),
                 "status": "verified" if s in SYMBOL_META else "unknown"}
                for s in DEFAULT_HOLDINGS
            ]
            st.session_state.save_result = None
            st.rerun()

# ── RIGHT: input modes ──────────────────────────────────────
with col_right:
    tab1, tab2, tab3 = st.tabs(["✎ Type / Voice", "⊞ Upload File", "📷 Image Scan"])

    # ── TAB 1: TYPE ─────────────────────────────────────────
    with tab1:
        st.markdown('<div class="c-label">// Enter NSE symbols — comma or newline separated</div>', unsafe_allow_html=True)

        raw_input = st.text_area(
            label="symbols",
            label_visibility="collapsed",
            placeholder="HDFCBANK, TCS, RELIANCE\nBAJFINANCE\nHAL",
            height=120,
            key="sym_input",
        )

        st.markdown('<div class="c-label" style="margin-top:6px">// Or use quick-add single symbol</div>', unsafe_allow_html=True)
        qa_col1, qa_col2 = st.columns([3, 1])
        with qa_col1:
            quick_sym = st.text_input("quick", label_visibility="collapsed",
                                      placeholder="e.g. HDFCBANK", key="quick_sym")
        with qa_col2:
            if st.button("ADD", use_container_width=True):
                if quick_sym.strip():
                    resolved = resolve_symbol(quick_sym)
                    if not any(h["symbol"] == resolved["symbol"] for h in st.session_state.holdings):
                        st.session_state.holdings.append(resolved)
                    st.rerun()

        if st.button("VERIFY & ADD ALL", use_container_width=True):
            parts = [p.strip() for p in raw_input.replace("\n", ",").split(",") if p.strip()]
            added = 0
            for part in parts:
                resolved = resolve_symbol(part)
                if not any(h["symbol"] == resolved["symbol"] for h in st.session_state.holdings):
                    st.session_state.holdings.append(resolved)
                    added += 1
            st.session_state.save_result = None
            st.success(f"Added {added} new symbols. {len([h for h in st.session_state.holdings if h['status']=='unknown'])} unknown (red).")
            st.rerun()

        st.markdown("""
        <div class="card" style="margin-top:14px">
          <div class="c-label">// Voice Tips — fuzzy matching</div>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
            <div>
              <div style="font-family:'IBM Plex Mono',monospace;font-size:8px;color:#00e5a0;letter-spacing:.1em;margin-bottom:8px">SAY / TYPE</div>
              <div style="font-family:'IBM Plex Mono',monospace;font-size:10px;color:#6a8aa8;line-height:2.1">
                HDFC Bank<br>Infosys<br>Bajaj Finance<br>Reliance Industries<br>HAL
              </div>
            </div>
            <div>
              <div style="font-family:'IBM Plex Mono',monospace;font-size:8px;color:#3d5570;letter-spacing:.1em;margin-bottom:8px">RESOLVES TO</div>
              <div style="font-family:'IBM Plex Mono',monospace;font-size:10px;color:#f5a623;line-height:2.1">
                HDFCBANK<br>INFY<br>BAJFINANCE<br>RELIANCE<br>HAL
              </div>
            </div>
          </div>
        </div>
        """, unsafe_allow_html=True)

    # ── TAB 2: FILE UPLOAD ──────────────────────────────────
    with tab2:
        st.markdown('<div class="c-label">// Upload .xlsx, .xls, or .csv holdings file</div>', unsafe_allow_html=True)
        st.markdown('<div style="font-family:\'IBM Plex Mono\',monospace;font-size:9px;color:#3d5570;margin-bottom:10px">File must have a column named <code>Symbol</code>, <code>Ticker</code>, or <code>Scrip</code></div>', unsafe_allow_html=True)

        uploaded = st.file_uploader(
            "Upload file", type=["xlsx", "xls", "csv"],
            label_visibility="collapsed"
        )

        if uploaded:
            try:
                import pandas as pd
                if uploaded.name.endswith(".csv"):
                    df = pd.read_csv(uploaded)
                else:
                    df = pd.read_excel(uploaded)

                st.markdown(f'<div style="font-family:\'IBM Plex Mono\',monospace;font-size:9px;color:#00e5a0;margin:8px 0">✓ Loaded {len(df)} rows · {len(df.columns)} columns</div>', unsafe_allow_html=True)

                # Preview
                with st.expander("⊞ Preview file contents"):
                    st.dataframe(df.head(20), use_container_width=True,
                                 hide_index=True)

                # Find symbol column
                sym_col = next(
                    (c for c in df.columns if any(k in c.lower() for k in ["symbol","ticker","scrip","stock"])),
                    None
                )

                if sym_col:
                    st.markdown(f'<div style="font-family:\'IBM Plex Mono\',monospace;font-size:9px;color:#38b6ff;margin:6px 0">Found symbol column: <strong>{sym_col}</strong></div>', unsafe_allow_html=True)

                    if st.button("⊕ Import Symbols from File", use_container_width=True):
                        added = 0
                        for raw in df[sym_col].dropna().astype(str):
                            if raw.strip():
                                resolved = resolve_symbol(raw)
                                if not any(h["symbol"] == resolved["symbol"] for h in st.session_state.holdings):
                                    st.session_state.holdings.append(resolved)
                                    added += 1
                        st.session_state.save_result = None
                        st.success(f"Imported {added} new symbols from file.")
                        st.rerun()
                else:
                    st.warning("No Symbol/Ticker/Scrip column found. Available columns: " + ", ".join(df.columns.tolist()))

            except Exception as e:
                st.error(f"Could not read file: {e}")

    # ── TAB 3: IMAGE SCAN ───────────────────────────────────
    with tab3:
        st.markdown("""
        <div class="c-label">// New Customer Portfolio Scan</div>
        <div style="font-family:'IBM Plex Mono',monospace;font-size:9px;color:#3d5570;margin-bottom:10px;line-height:1.7">
          Upload a broker screenshot · statement · watchlist photo.<br>
          AI extracts all stock symbols and imports them in one step.
        </div>
        """, unsafe_allow_html=True)

        img_file = st.file_uploader(
            "Upload image", type=["png", "jpg", "jpeg", "webp"],
            label_visibility="collapsed", key="img_upload"
        )

        if img_file:
            st.image(img_file, caption=img_file.name, use_column_width=True)

            if st.button("✦ Extract Stocks with AI", use_container_width=True):
                with st.spinner("Analysing portfolio image…"):
                    try:
                        # Prepare base64
                        img_bytes = img_file.read()
                        img_b64   = base64.b64encode(img_bytes).decode()
                        mime      = img_file.type or "image/jpeg"

                        # Call Anthropic API
                        import requests as req
                        api_key = st.secrets.get("ANTHROPIC_API_KEY", "")

                        if not api_key:
                            raise ValueError("ANTHROPIC_API_KEY not set in secrets — using demo data")

                        resp = req.post(
                            "https://api.anthropic.com/v1/messages",
                            headers={
                                "x-api-key": api_key,
                                "anthropic-version": "2023-06-01",
                                "content-type": "application/json",
                            },
                            json={
                                "model": "claude-sonnet-4-20250514",
                                "max_tokens": 800,
                                "messages": [{
                                    "role": "user",
                                    "content": [
                                        {"type": "image", "source": {
                                            "type": "base64",
                                            "media_type": mime,
                                            "data": img_b64,
                                        }},
                                        {"type": "text", "text": (
                                            "Extract all Indian stock symbols/names from this image "
                                            "(broker screenshot, portfolio statement, or watchlist). "
                                            "Return ONLY JSON: "
                                            '{\"stocks\":[{\"symbol\":\"HDFCBANK\",\"name\":\"HDFC Bank\",\"confidence\":0.95},...]} '
                                            "No markdown, no explanation."
                                        )},
                                    ],
                                }],
                            },
                            timeout=30,
                        )
                        resp.raise_for_status()
                        text = resp.json()["content"][0]["text"]
                        clean = text.replace("```json", "").replace("```", "").strip()
                        extracted = json.loads(clean).get("stocks", [])

                    except Exception as e:
                        # Demo fallback
                        st.warning(f"API unavailable ({e}) — showing demo extraction")
                        extracted = [
                            {"symbol": "HDFCBANK", "name": "HDFC Bank",      "confidence": 0.98},
                            {"symbol": "TCS",      "name": "TCS",             "confidence": 0.97},
                            {"symbol": "RELIANCE", "name": "Reliance",        "confidence": 0.99},
                            {"symbol": "INFY",     "name": "Infosys",         "confidence": 0.96},
                            {"symbol": "BAJFINANCE","name": "Bajaj Finance",  "confidence": 0.94},
                        ]

                if extracted:
                    st.markdown(f'<div style="font-family:\'IBM Plex Mono\',monospace;font-size:9px;color:#00e5a0;margin:8px 0">✓ Detected {len(extracted)} stocks from image</div>', unsafe_allow_html=True)

                    # Show detected stocks with confidence
                    det_html = ""
                    for s in extracted:
                        conf = s.get("confidence", 0.8)
                        conf_col = "#00e5a0" if conf > 0.85 else "#f5a623"
                        det_html += f"""<tr>
                          <td style="font-family:'IBM Plex Mono',monospace;color:#00e5a0">{s['symbol']}</td>
                          <td style="font-size:10px;color:#6a8aa8">{s.get('name','')}</td>
                          <td style="font-family:'IBM Plex Mono',monospace;font-size:9px;color:{conf_col}">{int(conf*100)}%</td>
                        </tr>"""

                    st.markdown(f"""
                    <div style="max-height:220px;overflow-y:auto;margin:8px 0">
                      <table class="h-table">
                        <thead><tr><th>Symbol</th><th>Name</th><th>Confidence</th></tr></thead>
                        <tbody>{det_html}</tbody>
                      </table>
                    </div>
                    """, unsafe_allow_html=True)

                    if st.button("⊕ Import All to Holdings", use_container_width=True):
                        added = 0
                        for s in extracted:
                            resolved = resolve_symbol(s["symbol"])
                            if not any(h["symbol"] == resolved["symbol"] for h in st.session_state.holdings):
                                st.session_state.holdings.append(resolved)
                                added += 1
                        st.session_state.save_result = None
                        st.success(f"Imported {added} stocks from image scan.")
                        st.rerun()
                else:
                    st.warning("No stocks detected in image. Try a clearer screenshot.")
