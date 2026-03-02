"""
pages/00a_Context.py
═══════════════════════════════════════════════════════════
P0a · Market Context — news feed + commodity flags

Navigation fix: context.html's "Open Dashboard" and "← Map"
buttons now write to query params (same URL-navigation trick as
00_Landing.py) which triggers a real Streamlit rerun.
═══════════════════════════════════════════════════════════
"""
import sys, pathlib, json
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

# ── Guard: must arrive via landing ────────────────────────
if "avito_context" not in st.session_state:
    st.switch_page("pages/00_Landing.py")

ctx = st.session_state["avito_context"]

# ── Check for navigation signals from iframe ──────────────
# context.html fires these by navigating parent URL
params = st.query_params
if params.get("_nav") == "landing":
    st.query_params.clear()
    st.switch_page("pages/00_Landing.py")

if params.get("_nav") == "dashboard":
    try:
        raw = params.get("_ctx", "{}")
        nav_ctx = json.loads(raw)
        st.session_state["avito_context"] = nav_ctx
        st.session_state["avito_sectors"] = nav_ctx.get("sectors", [])
        st.session_state["avito_indices"] = nav_ctx.get("indices", [])
    except Exception:
        pass
    st.query_params.clear()
    st.switch_page("pages/01_Overview.py")

# ── Fetch news (cached 30 min) ────────────────────────────
@st.cache_data(ttl=1800)
def load_news():
    return fetch_news()

news = load_news()

# ── Inject and render context HTML ───────────────────────
_TPL = pathlib.Path(__file__).parent.parent / "assets" / "context.html"

def _inject(html, key, val):
    return html.replace(f"__{key}__", json.dumps(val, default=str))

html = _TPL.read_text(encoding="utf-8")
html = _inject(html, "CONTEXT",        ctx)
html = _inject(html, "NEWS",           news)
html = _inject(html, "SECTORS",        get_sectors())
html = _inject(html, "COMMODITY_FLAGS", get_commodity_flags())

# ── Navigation bridge (same URL-param technique as landing) ──
bridge = """
<script>
function goBack() {
  try {
    const url = new URL(window.parent.location.href);
    url.searchParams.set('_nav', 'landing');
    url.searchParams.delete('_ctx');
    window.parent.location.replace(url.toString());
  } catch(e) {}
}
function goDashboard() {
  const payload = {
    type: 'AVITO_NAV',
    page: 'dashboard',
    indices: (typeof CONTEXT !== 'undefined' ? CONTEXT.indices : []),
    sectors: [...(window._activeSectors || [])],
  };
  try {
    const url = new URL(window.parent.location.href);
    url.searchParams.set('_nav', 'dashboard');
    url.searchParams.set('_ctx', encodeURIComponent(JSON.stringify(payload)));
    window.parent.location.replace(url.toString());
  } catch(e) {}
}
</script>
"""
html = html.replace("</body>", bridge + "</body>")

components.html(html, height=860, scrolling=False)

# ── Native fallback nav ───────────────────────────────────
st.markdown("""
<style>.stButton>button{width:100%;font-family:monospace;font-size:11px}</style>
""", unsafe_allow_html=True)

c1, c2 = st.columns([1, 4])
with c1:
    if st.button("← Back to Map", use_container_width=True):
        st.switch_page("pages/00_Landing.py")
with c2:
    if st.button("Open Dashboard →", use_container_width=True, type="primary"):
        st.switch_page("pages/01_Overview.py")
