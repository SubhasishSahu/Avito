"""
pages/00a_Context.py
════════════════════════════════════════════════════════════════
P0a · Market Context page

Smart dashboard routing:
  - Crude Oil selected → filter Nifty50 to Energy/Oil&Gas stocks
  - Metals selected    → filter to Metals sector
  - Sectors selected   → pass those sector filters
  - Nothing specific   → default Nifty50 view
════════════════════════════════════════════════════════════════
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

# ── Guard ─────────────────────────────────────────────────
if "avito_context" not in st.session_state:
    st.switch_page("pages/00_Landing.py")

ctx = st.session_state["avito_context"]

# ── Check navigation params from iframe ───────────────────
params = st.query_params
if params.get("_nav") == "landing":
    st.query_params.clear()
    st.switch_page("pages/00_Landing.py")

if params.get("_nav") == "dashboard":
    try:
        nav_ctx = json.loads(params.get("_ctx", "{}"))
        st.session_state["avito_context"] = nav_ctx
        st.session_state["avito_sectors"] = nav_ctx.get("sectors", [])
        st.session_state["avito_indices"] = nav_ctx.get("indices", [])
    except Exception:
        pass
    st.query_params.clear()
    st.switch_page("pages/01_Overview.py")

# ── Compute smart dashboard filter ────────────────────────
has_oil    = ctx.get("has_oil", "COM_OIL" in ctx.get("indices", []))
has_metals = ctx.get("has_metals", "COM_METALS" in ctx.get("indices", []))
sel_sectors = ctx.get("sectors", [])

if has_oil and not sel_sectors:
    # Crude oil selected → Energy sector stocks
    st.session_state["avito_sectors"] = ["Energy"]
    st.session_state["avito_filter_mode"] = "oil"
elif has_metals and not sel_sectors:
    st.session_state["avito_sectors"] = ["Metals", "Mining"]
    st.session_state["avito_filter_mode"] = "metals"
elif sel_sectors:
    st.session_state["avito_sectors"] = sel_sectors
    st.session_state["avito_filter_mode"] = "sectors"
else:
    # Default — show all Nifty50
    st.session_state["avito_sectors"] = []
    st.session_state["avito_filter_mode"] = "default"

# ── Fetch news ─────────────────────────────────────────────
@st.cache_data(ttl=1800)
def load_news():
    return fetch_news()
news = load_news()

# ── Render context HTML ────────────────────────────────────
_TPL = pathlib.Path(__file__).parent.parent / "assets" / "context.html"

def _inject(html, key, val):
    return html.replace(f"__{key}__", json.dumps(val, default=str))

html = _TPL.read_text(encoding="utf-8")
html = _inject(html, "CONTEXT",         ctx)
html = _inject(html, "NEWS",            news)
html = _inject(html, "SECTORS",         get_sectors())
html = _inject(html, "COMMODITY_FLAGS", get_commodity_flags())

# bridge — same URL param nav
bridge = """
<script>
function goBack(){
  try{
    const url=new URL(window.parent.location.href);
    url.searchParams.set('_nav','landing');
    url.searchParams.delete('_ctx');
    window.parent.location.replace(url.toString());
  }catch(e){}
}
function goDashboard(){
  const payload={
    type:'AVITO_NAV',page:'dashboard',
    indices:(typeof CONTEXT!=='undefined'?CONTEXT.indices:[]),
    sectors:[...(window._activeSectors||[])],
  };
  try{
    const url=new URL(window.parent.location.href);
    url.searchParams.set('_nav','dashboard');
    url.searchParams.set('_ctx',encodeURIComponent(JSON.stringify(payload)));
    window.parent.location.replace(url.toString());
  }catch(e){}
}
</script>"""
html = html.replace("</body>", bridge + "</body>")

components.html(html, height=900, scrolling=False)

# ── Native nav buttons ────────────────────────────────────
c1, c2 = st.columns([1, 3])
with c1:
    if st.button("← Back to Map", use_container_width=True):
        st.switch_page("pages/00_Landing.py")
with c2:
    filter_mode = st.session_state.get("avito_filter_mode", "default")
    btn_labels = {
        "oil":     "Open Dashboard → Nifty50 Oil & Gas Filter",
        "metals":  "Open Dashboard → Nifty50 Metals Filter",
        "sectors": f"Open Dashboard → {', '.join(st.session_state.get('avito_sectors',[])[:2])} filter",
        "default": "Open Dashboard → Default Nifty50 View",
    }
    if st.button(btn_labels.get(filter_mode, "Open Dashboard →"),
                 use_container_width=True, type="primary"):
        st.switch_page("pages/01_Overview.py")
