"""
pages/03_Scanner.py — Tab 3: New Portfolio Customer Scan
Three input modes:
  1. Type / voice (Web Speech API via JS in embedded HTML)
  2. Upload Excel / CSV
  3. AI image scan (Anthropic API)

Completely independent page — no session state dependencies.
"""
import sys, pathlib, json, base64
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

import streamlit as st

st.set_page_config(
    page_title="AVITO · Scanner",
    page_icon="⬡",
    layout="wide",
    initial_sidebar_state="collapsed",
)

from core.page_setup import apply; apply()

try:
    from core.data_loader import SYMBOL_META, DEFAULT_HOLDINGS, resolve_symbol
except ImportError:
    SYMBOL_META = {}
    DEFAULT_HOLDINGS = []
    def resolve_symbol(raw):
        return {"symbol": raw.strip().upper(), "name": raw.strip(), "sector": "Unknown", "cap": "?", "status": "unknown"}

# ── Theme ──────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600;700&family=Syne:wght@400;600;700&display=swap');
body, .stApp { background:#03060b !important; color:#c0d4ea; font-family:'Syne',sans-serif; }
.stApp { background:#03060b !important; }
.block-container { padding-top:1.2rem !important; }
h1,h2,h3 { font-family:'Syne',sans-serif !important; font-weight:700 !important; }

div[data-testid="stTextInput"] input,
div[data-testid="stTextArea"] textarea {
  background:#0b1018 !important; border:1px solid #1c2c40 !important;
  border-radius:5px !important; color:#c0d4ea !important;
  font-family:'JetBrains Mono',monospace !important; font-size:12px !important;
}
div[data-testid="stButton"] > button {
  background:#00f0a0 !important; color:#000 !important; border:none !important;
  font-family:'JetBrains Mono',monospace !important; font-weight:700 !important;
  letter-spacing:.08em !important; border-radius:5px !important; font-size:11px !important;
}
div[data-testid="stButton"] > button[kind="secondary"] {
  background:transparent !important; border:1px solid #1c2c40 !important; color:#5a80a0 !important;
}
div[data-testid="stFileUploader"] { background:#0b1018 !important; border:1px dashed #1c2c40 !important; border-radius:6px !important; }
div[data-testid="stTabs"] [data-testid="stTab"] { font-family:'JetBrains Mono',monospace !important; font-size:10px !important; letter-spacing:.08em !important; }
div[data-testid="stExpander"] { background:#070b12 !important; border:1px solid #162030 !important; border-radius:6px !important; }
</style>
""", unsafe_allow_html=True)

# ── Page header ────────────────────────────────────────────
st.markdown("""
<div style="font-family:'JetBrains Mono',monospace;font-size:8px;letter-spacing:.16em;text-transform:uppercase;color:#2a3f58;margin-bottom:4px">// P3 · New Portfolio Scan</div>
<div style="font-family:'Syne',sans-serif;font-size:22px;font-weight:700;color:#c0d4ea;letter-spacing:-.01em;margin-bottom:3px">Customer Portfolio Scanner</div>
<div style="font-size:12px;color:#5a80a0;margin-bottom:20px">Voice · Upload · AI Image Scan  —  Identify and verify Indian stock holdings instantly</div>
""", unsafe_allow_html=True)

# ── Session state ─────────────────────────────────────────
if "scan_holdings" not in st.session_state:
    st.session_state.scan_holdings = []
if "scan_result" not in st.session_state:
    st.session_state.scan_result = None

# ── Layout: left = holding register, right = input modes ──
col_left, col_right = st.columns([1, 1.8], gap="large")

# ════════════════════════════════════════════════════════════
# LEFT — current scanned holdings
# ════════════════════════════════════════════════════════════
with col_left:
    verified   = [h for h in st.session_state.scan_holdings if h.get("status") == "verified"]
    unverified = [h for h in st.session_state.scan_holdings if h.get("status") != "verified"]

    st.markdown(f"""
    <div style="background:#070b12;border:1px solid #162030;border-radius:7px;padding:14px 16px;margin-bottom:14px">
      <div style="font-family:'JetBrains Mono',monospace;font-size:8px;letter-spacing:.14em;text-transform:uppercase;color:#2a3f58;margin-bottom:10px">// Scanned Holdings</div>
      <div style="display:flex;gap:10px;margin-bottom:12px">
        <span style="font-family:'JetBrains Mono',monospace;font-size:8px;padding:2px 8px;border-radius:3px;background:rgba(0,240,160,.08);border:1px solid rgba(0,240,160,.25);color:#00f0a0">{len(verified)} verified</span>
        <span style="font-family:'JetBrains Mono',monospace;font-size:8px;padding:2px 8px;border-radius:3px;background:rgba(255,61,90,.08);border:1px solid rgba(255,61,90,.25);color:#ff3d5a">{len(unverified)} unknown</span>
        <span style="margin-left:auto;font-family:'JetBrains Mono',monospace;font-size:8px;padding:2px 8px;border-radius:3px;background:rgba(61,184,255,.08);border:1px solid rgba(61,184,255,.2);color:#3db8ff">{len(st.session_state.scan_holdings)} total</span>
      </div>
    </div>
    """, unsafe_allow_html=True)

    if st.session_state.scan_holdings:
        rows_html = ""
        for h in st.session_state.scan_holdings:
            ok = h.get("status") == "verified"
            sym_col = "#00f0a0" if ok else "#ff3d5a"
            tag_cls = "background:rgba(0,240,160,.08);border:1px solid rgba(0,240,160,.25);color:#00f0a0" if ok else "background:rgba(255,61,90,.08);border:1px solid rgba(255,61,90,.25);color:#ff3d5a"
            tag_txt = "✓ NSE" if ok else "✗ Unknown"
            rows_html += f"""<tr>
              <td style="font-family:'JetBrains Mono',monospace;font-size:10px;color:{sym_col}">{h['symbol']}</td>
              <td style="color:#5a80a0;font-size:10px">{h.get('name','')}</td>
              <td style="color:#2a3f58;font-size:10px">{h.get('sector','')}</td>
              <td><span style="font-family:'JetBrains Mono',monospace;font-size:7px;padding:1px 6px;border-radius:3px;{tag_cls}">{tag_txt}</span></td>
            </tr>"""

        st.markdown(f"""
        <div style="max-height:440px;overflow-y:auto;scrollbar-width:thin;scrollbar-color:#1c2c40 transparent">
          <table style="width:100%;border-collapse:collapse;font-size:11px">
            <thead><tr>
              <th style="font-family:'JetBrains Mono',monospace;font-size:7px;letter-spacing:.1em;text-transform:uppercase;color:#2a3f58;padding:7px 8px;text-align:left;border-bottom:1px solid #162030;font-weight:400">Symbol</th>
              <th style="font-family:'JetBrains Mono',monospace;font-size:7px;letter-spacing:.1em;text-transform:uppercase;color:#2a3f58;padding:7px 8px;text-align:left;border-bottom:1px solid #162030;font-weight:400">Name</th>
              <th style="font-family:'JetBrains Mono',monospace;font-size:7px;letter-spacing:.1em;text-transform:uppercase;color:#2a3f58;padding:7px 8px;text-align:left;border-bottom:1px solid #162030;font-weight:400">Sector</th>
              <th style="font-family:'JetBrains Mono',monospace;font-size:7px;letter-spacing:.1em;text-transform:uppercase;color:#2a3f58;padding:7px 8px;text-align:left;border-bottom:1px solid #162030;font-weight:400">Status</th>
            </tr></thead>
            <tbody>{rows_html}</tbody>
          </table>
        </div>
        """, unsafe_allow_html=True)

    # Save result banner
    if st.session_state.scan_result:
        res = st.session_state.scan_result
        if res.get("ok") and res.get("mock"):
            st.markdown('<div style="background:rgba(255,184,48,.08);border:1px solid rgba(255,184,48,.25);border-radius:5px;padding:9px 12px;font-family:\'JetBrains Mono\',monospace;font-size:10px;color:#ffb830;margin-top:10px">⚠ MOCK SAVE — set FERNET_KEY + GITHUB_TOKEN to write live</div>', unsafe_allow_html=True)
        elif res.get("ok"):
            st.markdown(f'<div style="background:rgba(0,240,160,.08);border:1px solid rgba(0,240,160,.25);border-radius:5px;padding:9px 12px;font-family:\'JetBrains Mono\',monospace;font-size:10px;color:#00f0a0;margin-top:10px">✓ Saved {res.get("symbols_written",0)} symbols to GitHub</div>', unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    b1, b2, b3 = st.columns(3)
    with b1:
        if st.button("✓ Save to GitHub", use_container_width=True) and st.session_state.scan_holdings:
            try:
                from core.github_writer import write_holdings
                syms = [h["symbol"] for h in st.session_state.scan_holdings]
                st.session_state.scan_result = write_holdings(syms)
            except Exception as e:
                st.session_state.scan_result = {"ok": False, "error": str(e)}
            st.rerun()
    with b2:
        if st.button("✕ Remove Unknown", use_container_width=True):
            st.session_state.scan_holdings = [h for h in st.session_state.scan_holdings if h.get("status") == "verified"]
            st.session_state.scan_result = None
            st.rerun()
    with b3:
        if st.button("⟳ Clear All", use_container_width=True):
            st.session_state.scan_holdings = []
            st.session_state.scan_result = None
            st.rerun()

# ════════════════════════════════════════════════════════════
# RIGHT — input tabs
# ════════════════════════════════════════════════════════════
with col_right:
    tab1, tab2, tab3 = st.tabs(["✎  Type · Voice", "⊞  Upload File", "📷  AI Image Scan"])

    # ── TAB 1: TYPE / VOICE ─────────────────────────────────
    with tab1:
        st.markdown("""
        <div style="font-family:'JetBrains Mono',monospace;font-size:8px;letter-spacing:.12em;text-transform:uppercase;color:#2a3f58;margin-bottom:8px">// Type or paste NSE symbols</div>
        """, unsafe_allow_html=True)

        raw_input = st.text_area(
            "symbols", label_visibility="collapsed",
            placeholder="HDFCBANK, TCS, RELIANCE\nBAJFINANCE\nHAL\n\nOr paste from broker statement…",
            height=130, key="sym_input",
        )

        # Voice input via embedded JS
        st.markdown("""
        <div style="background:#070b12;border:1px solid #162030;border-radius:6px;padding:12px 14px;margin:10px 0">
          <div style="font-family:'JetBrains Mono',monospace;font-size:8px;letter-spacing:.12em;text-transform:uppercase;color:#2a3f58;margin-bottom:8px">// Voice Entry (Chrome)</div>
          <div style="display:flex;align-items:center;gap:10px">
            <button id="mic-btn" onclick="toggleVoice()" style="
              width:38px;height:38px;border-radius:50%;border:1px solid #1c2c40;
              background:#0b1018;color:#5a80a0;font-size:16px;cursor:pointer;
              display:flex;align-items:center;justify-content:center;flex-shrink:0">🎤</button>
            <div id="voice-out" style="font-family:'JetBrains Mono',monospace;font-size:9px;color:#5a80a0;
              flex:1;background:#0b1018;border:1px solid #162030;border-radius:4px;padding:6px 10px;min-height:32px">
              Press mic and say stock names…</div>
          </div>
          <div style="font-family:'JetBrains Mono',monospace;font-size:7.5px;color:#2a3f58;margin-top:7px;line-height:1.6">
            Say: "HDFC Bank, TCS, Reliance" → auto-resolves to NSE symbols<br>
            Works in Chrome / Edge. Paste result into text area above.
          </div>
        </div>
        <script>
        var rec=null;
        function toggleVoice(){
          var btn=document.getElementById('mic-btn');
          var out=document.getElementById('voice-out');
          if(!('webkitSpeechRecognition' in window)&&!('SpeechRecognition' in window)){
            out.textContent='Voice not supported in this browser. Use Chrome.';out.style.color='#ff3d5a';return;
          }
          if(rec){rec.stop();rec=null;btn.style.background='#0b1018';btn.style.color='#5a80a0';return;}
          rec=new(window.SpeechRecognition||window.webkitSpeechRecognition)();
          rec.lang='en-IN';rec.continuous=false;rec.interimResults=true;
          rec.onstart=()=>{btn.style.background='rgba(255,61,90,.2)';btn.style.color='#ff3d5a';out.textContent='Listening…';out.style.color='#ff3d5a';}
          rec.onresult=e=>{
            const t=Array.from(e.results).map(r=>r[0].transcript).join('');
            out.textContent='Heard: '+t;out.style.color='#ffb830';
            if(e.results[0].isFinal){
              out.textContent='✓ '+t+' → paste above and verify';
              out.style.color='#00f0a0';
              // Try to copy to clipboard
              navigator.clipboard&&navigator.clipboard.writeText(t).catch(()=>{});
              rec=null;btn.style.background='#0b1018';btn.style.color='#5a80a0';
            }
          }
          rec.onerror=()=>{out.textContent='Error. Check microphone permission.';out.style.color='#ff3d5a';rec=null;btn.style.background='#0b1018';btn.style.color='#5a80a0';}
          rec.start();
        }
        </script>
        """, unsafe_allow_html=True)

        # Quick-add
        qa1, qa2 = st.columns([3, 1])
        with qa1:
            qs = st.text_input("quick", label_visibility="collapsed", placeholder="Quick-add: e.g. HDFCBANK", key="quick_sym")
        with qa2:
            if st.button("ADD", use_container_width=True):
                if qs.strip():
                    r = resolve_symbol(qs)
                    if not any(h["symbol"] == r["symbol"] for h in st.session_state.scan_holdings):
                        st.session_state.scan_holdings.append(r)
                    st.rerun()

        if st.button("VERIFY & ADD ALL", use_container_width=True):
            parts = [p.strip() for p in raw_input.replace("\n", ",").split(",") if p.strip()]
            added = 0
            for p in parts:
                r = resolve_symbol(p)
                if not any(h["symbol"] == r["symbol"] for h in st.session_state.scan_holdings):
                    st.session_state.scan_holdings.append(r)
                    added += 1
            st.session_state.scan_result = None
            if added:
                st.success(f"Added {added} symbols. {len([h for h in st.session_state.scan_holdings if h.get('status')!='verified'])} unknown (red).")
            st.rerun()

        # Fuzzy map reference
        st.markdown("""
        <div style="background:#070b12;border:1px solid #162030;border-radius:6px;padding:10px 14px;margin-top:10px">
          <div style="font-family:'JetBrains Mono',monospace;font-size:8px;letter-spacing:.12em;text-transform:uppercase;color:#2a3f58;margin-bottom:8px">// Name → Symbol Map</div>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px">
            <div>
              <div style="font-family:'JetBrains Mono',monospace;font-size:7.5px;color:#00f0a0;margin-bottom:6px">SAY / TYPE</div>
              <div style="font-family:'JetBrains Mono',monospace;font-size:9.5px;color:#5a80a0;line-height:2.1">HDFC Bank<br>Infosys<br>Bajaj Finance<br>Reliance Industries<br>Hindustan Aeronautics</div>
            </div>
            <div>
              <div style="font-family:'JetBrains Mono',monospace;font-size:7.5px;color:#2a3f58;margin-bottom:6px">RESOLVES TO</div>
              <div style="font-family:'JetBrains Mono',monospace;font-size:9.5px;color:#ffb830;line-height:2.1">HDFCBANK<br>INFY<br>BAJFINANCE<br>RELIANCE<br>HAL</div>
            </div>
          </div>
        </div>
        """, unsafe_allow_html=True)

    # ── TAB 2: FILE UPLOAD ──────────────────────────────────
    with tab2:
        st.markdown("""
        <div style="font-family:'JetBrains Mono',monospace;font-size:8px;letter-spacing:.12em;text-transform:uppercase;color:#2a3f58;margin-bottom:5px">// Upload .xlsx, .xls, or .csv holdings file</div>
        <div style="font-family:'JetBrains Mono',monospace;font-size:9px;color:#2a3f58;margin-bottom:10px">File must have a column named Symbol, Ticker, Scrip, or Stock</div>
        """, unsafe_allow_html=True)

        uploaded = st.file_uploader("File", type=["xlsx", "xls", "csv"], label_visibility="collapsed")

        if uploaded:
            try:
                import pandas as pd
                if uploaded.name.endswith(".csv"):
                    df = pd.read_csv(uploaded)
                else:
                    df = pd.read_excel(uploaded)

                st.markdown(f'<div style="font-family:\'JetBrains Mono\',monospace;font-size:9px;color:#00f0a0;margin:8px 0">✓ Loaded {len(df)} rows · {len(df.columns)} columns</div>', unsafe_allow_html=True)

                with st.expander("Preview file"):
                    st.dataframe(df.head(20), use_container_width=True, hide_index=True)

                sym_col = next(
                    (c for c in df.columns if any(k in c.lower() for k in ["symbol","ticker","scrip","stock"])),
                    None
                )

                if sym_col:
                    st.markdown(f'<div style="font-family:\'JetBrains Mono\',monospace;font-size:9px;color:#3db8ff;margin:6px 0">Found symbol column: <strong>{sym_col}</strong></div>', unsafe_allow_html=True)
                    if st.button("⊕ Import Symbols", use_container_width=True):
                        added = 0
                        for raw in df[sym_col].dropna().astype(str):
                            if raw.strip():
                                r = resolve_symbol(raw)
                                if not any(h["symbol"] == r["symbol"] for h in st.session_state.scan_holdings):
                                    st.session_state.scan_holdings.append(r)
                                    added += 1
                        st.session_state.scan_result = None
                        st.success(f"Imported {added} symbols from file.")
                        st.rerun()
                else:
                    st.warning("No Symbol/Ticker/Scrip column found. Columns: " + ", ".join(df.columns.tolist()))

            except Exception as e:
                st.error(f"Could not read file: {e}")

    # ── TAB 3: AI IMAGE SCAN ────────────────────────────────
    with tab3:
        st.markdown("""
        <div style="font-family:'JetBrains Mono',monospace;font-size:8px;letter-spacing:.12em;text-transform:uppercase;color:#2a3f58;margin-bottom:5px">// AI Portfolio Image Extraction</div>
        <div style="font-family:'JetBrains Mono',monospace;font-size:9px;color:#2a3f58;margin-bottom:10px;line-height:1.7">
          Upload broker screenshot · statement · watchlist photo<br>
          Claude AI extracts all stock symbols in one step
        </div>
        """, unsafe_allow_html=True)

        img_file = st.file_uploader("Image", type=["png", "jpg", "jpeg", "webp"], label_visibility="collapsed", key="img_scan")

        if img_file:
            st.image(img_file, caption=img_file.name, use_column_width=True)

            if st.button("✦ Extract Stocks with AI", use_container_width=True):
                with st.spinner("Analysing portfolio image with Claude AI…"):
                    try:
                        img_bytes = img_file.getvalue()
                        img_b64   = base64.b64encode(img_bytes).decode()
                        mime      = img_file.type or "image/jpeg"

                        import requests as req
                        api_key = st.secrets.get("ANTHROPIC_API_KEY", "")

                        if not api_key:
                            raise ValueError("ANTHROPIC_API_KEY not set — showing demo extraction")

                        resp = req.post(
                            "https://api.anthropic.com/v1/messages",
                            headers={"x-api-key": api_key,
                                     "anthropic-version": "2023-06-01",
                                     "content-type": "application/json"},
                            json={
                                "model": "claude-sonnet-4-20250514",
                                "max_tokens": 800,
                                "messages": [{
                                    "role": "user",
                                    "content": [
                                        {"type": "image", "source": {"type": "base64", "media_type": mime, "data": img_b64}},
                                        {"type": "text", "text": (
                                            "Extract all Indian stock symbols/names from this image "
                                            "(broker screenshot, portfolio statement, or watchlist). "
                                            "Return ONLY JSON: "
                                            "{\"stocks\":[{\"symbol\":\"HDFCBANK\",\"name\":\"HDFC Bank\",\"confidence\":0.95},...]} "
                                            "No markdown, no explanation."
                                        )},
                                    ],
                                }],
                            }, timeout=30,
                        )
                        resp.raise_for_status()
                        text = resp.json()["content"][0]["text"]
                        clean = text.replace("```json", "").replace("```", "").strip()
                        extracted = json.loads(clean).get("stocks", [])

                    except Exception as exc:
                        st.warning(f"API unavailable ({exc}) — showing demo extraction")
                        extracted = [
                            {"symbol":"HDFCBANK",   "name":"HDFC Bank",      "confidence":0.98},
                            {"symbol":"TCS",         "name":"TCS",            "confidence":0.97},
                            {"symbol":"RELIANCE",    "name":"Reliance",       "confidence":0.99},
                            {"symbol":"INFY",        "name":"Infosys",        "confidence":0.96},
                            {"symbol":"BAJFINANCE",  "name":"Bajaj Finance",  "confidence":0.94},
                            {"symbol":"HCLTECH",     "name":"HCL Technologies","confidence":0.92},
                            {"symbol":"WIPRO",       "name":"Wipro",          "confidence":0.91},
                        ]

                if extracted:
                    st.markdown(f'<div style="font-family:\'JetBrains Mono\',monospace;font-size:9px;color:#00f0a0;margin:8px 0">✓ Detected {len(extracted)} stocks</div>', unsafe_allow_html=True)

                    rows = ""
                    for s in extracted:
                        conf = s.get("confidence", 0.8)
                        cc = "#00f0a0" if conf > 0.85 else "#ffb830"
                        rows += f"""<tr>
                          <td style="font-family:'JetBrains Mono',monospace;font-size:10px;color:#00f0a0">{s['symbol']}</td>
                          <td style="font-size:10px;color:#5a80a0">{s.get('name','')}</td>
                          <td style="font-family:'JetBrains Mono',monospace;font-size:9px;color:{cc}">{int(conf*100)}%</td>
                        </tr>"""

                    st.markdown(f"""
                    <div style="max-height:220px;overflow-y:auto;margin:8px 0">
                      <table style="width:100%;border-collapse:collapse">
                        <thead><tr>
                          <th style="font-family:'JetBrains Mono',monospace;font-size:7px;letter-spacing:.1em;text-transform:uppercase;color:#2a3f58;padding:6px 8px;text-align:left;border-bottom:1px solid #162030;font-weight:400">Symbol</th>
                          <th style="font-family:'JetBrains Mono',monospace;font-size:7px;letter-spacing:.1em;text-transform:uppercase;color:#2a3f58;padding:6px 8px;text-align:left;border-bottom:1px solid #162030;font-weight:400">Name</th>
                          <th style="font-family:'JetBrains Mono',monospace;font-size:7px;letter-spacing:.1em;text-transform:uppercase;color:#2a3f58;padding:6px 8px;text-align:left;border-bottom:1px solid #162030;font-weight:400">Confidence</th>
                        </tr></thead>
                        <tbody>{rows}</tbody>
                      </table>
                    </div>
                    """, unsafe_allow_html=True)

                    if st.button("⊕ Import All to Holdings", use_container_width=True):
                        added = 0
                        for s in extracted:
                            r = resolve_symbol(s["symbol"])
                            if not any(h["symbol"] == r["symbol"] for h in st.session_state.scan_holdings):
                                st.session_state.scan_holdings.append(r)
                                added += 1
                        st.session_state.scan_result = None
                        st.success(f"Imported {added} stocks from image scan.")
                        st.rerun()
                else:
                    st.warning("No stocks detected. Try a clearer screenshot.")
