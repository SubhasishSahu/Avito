"""
pages/00a_Context.py
════════════════════════════════════════════════════════════════
P0a · Market Context — news + commodity flags.

Reads avito_context from session_state (set by 00_Landing.py).
Fetches RSS news, filters by selected sectors.
User can refine sector filters, then click "Open Dashboard".
════════════════════════════════════════════════════════════════
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

import json
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

# ── guard: must have context ───────────────────────────────────
if "avito_context" not in st.session_state:
    st.switch_page("pages/00_Landing.py")

ctx = st.session_state["avito_context"]

# ── fetch news (cached 30 min) ─────────────────────────────────
@st.cache_data(ttl=1800)
def load_news():
    return fetch_news()

news = load_news()

# ── load template ──────────────────────────────────────────────
_CTX_HTML = pathlib.Path(__file__).parent.parent / "assets" / "context.html"

def _inject(html, key, val):
    return html.replace(f"__{key}__", json.dumps(val, default=str))

html = _CTX_HTML.read_text(encoding="utf-8")
html = _inject(html, "CONTEXT",        ctx)
html = _inject(html, "NEWS",           news)
html = _inject(html, "SECTORS",        get_sectors())
html = _inject(html, "COMMODITY_FLAGS",get_commodity_flags())

# ── bridge: handle nav messages from iframe ────────────────────
bridge = """
<script>
window.addEventListener('message', function(e){
  try {
    const d = typeof e.data === 'string' ? JSON.parse(e.data) : e.data;
    if(!d) return;
    if(d.type === 'AVITO_NAV' && d.page === 'landing'){
      window.parent.location.hash = 'go=landing';
      const url = new URL(window.parent.location.href);
      url.searchParams.set('avito_nav','landing');
      url.hash = '';
      window.parent.location.href = url.href;
    }
    if(d.type === 'AVITO_NAV' && d.page === 'dashboard'){
      const enc = encodeURIComponent(JSON.stringify(d));
      const url = new URL(window.parent.location.href);
      url.searchParams.set('avito_nav','dashboard');
      url.searchParams.set('avito_ctx', enc);
      url.hash = '';
      window.parent.location.href = url.href;
    }
  } catch(err){}
});
</script>
"""
html = html.replace("</body>", bridge + "</body>")

components.html(html, height=920, scrolling=False)

# ── handle navigation from iframe ─────────────────────────────
params = st.query_params
if params.get("avito_nav") == "landing":
    st.query_params.clear()
    st.switch_page("pages/00_Landing.py")

if params.get("avito_nav") == "dashboard":
    try:
        nav_ctx = json.loads(params.get("avito_ctx","{}"))
        st.session_state["avito_context"] = nav_ctx
        # store active sector filters for dashboard pages
        st.session_state["avito_sectors"] = nav_ctx.get("sectors", [])
        st.session_state["avito_indices"] = nav_ctx.get("indices", [])
    except Exception:
        pass
    st.query_params.clear()
    st.switch_page("pages/01_Overview.py")
