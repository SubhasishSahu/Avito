"""
pages/00a_Context.py — P0a · Market Context

Reads context from session_state OR from _avito query param
(whichever arrived — switch_page preserves session_state so
this is belt + suspenders).
"""
import sys, pathlib, json
import urllib.parse
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(
    page_title="AVITO · Context",
    page_icon="⬡",
    layout="wide",
    initial_sidebar_state="collapsed",
)

from core.page_setup import apply; apply()
from core.context_data import get_sectors, get_commodity_flags
from core.rss_loader import fetch_news

def _parse_param(raw: str) -> dict | None:
    for attempt in (raw, urllib.parse.unquote(raw)):
        try:
            obj = json.loads(attempt)
            if isinstance(obj, dict):
                return obj
        except Exception:
            continue
    return None

# ── Step 1: Restore context from URL if present ───────────────
params = st.query_params

if "_avito" in params:
    ctx_from_url = _parse_param(params["_avito"])
    if ctx_from_url and ctx_from_url.get("indices"):
        st.session_state["avito_context"]    = ctx_from_url
        st.session_state["avito_indices"]    = ctx_from_url.get("indices", [])
        st.session_state["avito_sectors"]    = ctx_from_url.get("sectors", [])
        st.session_state["avito_members"]    = ctx_from_url.get("members", [])
        st.session_state["avito_has_oil"]    = ctx_from_url.get("has_oil", False)
        st.session_state["avito_has_metals"] = ctx_from_url.get("has_metals", False)
    st.query_params.clear()

# ── Step 2: Guard ──────────────────────────────────────────────
if "avito_context" not in st.session_state:
    st.switch_page("pages/00_Landing.py")
    st.stop()

ctx = st.session_state["avito_context"]

# ── Step 3: Smart filter logic ────────────────────────────────
has_oil    = ctx.get("has_oil",    "COM_OIL"    in ctx.get("indices", []))
has_metals = ctx.get("has_metals", "COM_METALS" in ctx.get("indices", []))
sel_sectors = ctx.get("sectors", [])

if has_oil and not sel_sectors:
    st.session_state["avito_sectors"]     = ["Energy"]
    st.session_state["avito_filter_mode"] = "oil"
elif has_metals and not sel_sectors:
    st.session_state["avito_sectors"]     = ["Metals", "Mining"]
    st.session_state["avito_filter_mode"] = "metals"
elif sel_sectors:
    st.session_state["avito_sectors"]     = sel_sectors
    st.session_state["avito_filter_mode"] = "sectors"
else:
    st.session_state["avito_sectors"]     = []
    st.session_state["avito_filter_mode"] = "default"

# ── Step 4: Fetch news ─────────────────────────────────────────
@st.cache_data(ttl=1800)
def load_news():
    return fetch_news()

news = load_news()

# ── Step 5: Render context HTML ───────────────────────────────
_TPL = pathlib.Path(__file__).parent.parent / "assets" / "context.html"

def _inject(html: str, key: str, val) -> str:
    return html.replace(f"__{key}__", json.dumps(val, default=str))

html = _TPL.read_text(encoding="utf-8")
html = _inject(html, "CONTEXT",          ctx)
html = _inject(html, "NEWS",             news)
html = _inject(html, "SECTORS",          get_sectors())
html = _inject(html, "COMMODITY_FLAGS",  get_commodity_flags())

# Override context.html broken postMessage nav with reliable URL-param nav
nav_override = """
<script>
function goBack() {
  try {
    var base = window.parent.location.href.split('?')[0].split('#')[0];
    window.parent.location.href = base;
  } catch(e) { history.back(); }
}
function goDashboard() {
  // Native st.button below handles actual navigation — this is visual only
}
</script>
"""
html = html.replace("</body>", nav_override + "\n</body>")

components.html(html, height=900, scrolling=False)

# ── Step 6: Native nav buttons ────────────────────────────────
filter_mode = st.session_state.get("avito_filter_mode", "default")
btn_labels  = {
    "oil":     "⚡ Open Dashboard → Nifty50 Oil & Gas",
    "metals":  "⚙ Open Dashboard → Nifty50 Metals",
    "sectors": "▤ Open Dashboard → {} filter".format(
                   ", ".join(st.session_state.get("avito_sectors", [])[:2])),
    "default": "◎ Open Dashboard → Default Nifty50 View",
}

c_back, c_open = st.columns([1, 3])
with c_back:
    if st.button("← Back to Map", use_container_width=True):
        st.switch_page("pages/00_Landing.py")
with c_open:
    if st.button(
        btn_labels.get(filter_mode, "Open Dashboard →"),
        use_container_width=True,
        type="primary",
    ):
        st.switch_page("pages/01_Overview.py")
