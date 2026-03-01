"""
pages/00_Landing.py
════════════════════════════════════════════════════════════════
P0 · Global Market Map — the new entry point.

Renders landing.html (flat SVG world map with clickable index
dots) via st.components.v1.html().

Listens for postMessage from the iframe:
  { type:'AVITO_CONTEXT', indices:[...], sectors:[...] }

On receiving it, stores to st.session_state and switches to
the Context page (00a_Context.py).
════════════════════════════════════════════════════════════════
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

import json
import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(
    page_title="AVITO · Global Markets",
    page_icon="⬡",
    layout="wide",
    initial_sidebar_state="collapsed",
)

from core.page_setup import apply; apply()
from core.context_data import get_indices, get_sectors, get_commodity_flags

# ── load template ──────────────────────────────────────────────
_LANDING = pathlib.Path(__file__).parent.parent / "assets" / "landing.html"

def _inject(html, key, val):
    import json
    return html.replace(f"__{key}__", json.dumps(val, default=str))

html = _LANDING.read_text(encoding="utf-8")
html = _inject(html, "INDICES",         get_indices())
html = _inject(html, "SECTORS",         get_sectors())
html = _inject(html, "COMMODITY_FLAGS", get_commodity_flags())

# ── render ─────────────────────────────────────────────────────
# Inject a bridge script that forwards postMessage to Streamlit
# via URL hash change (Streamlit detects this via st.query_params)
bridge = """
<script>
window.addEventListener('message', function(e){
  try {
    const d = typeof e.data === 'string' ? JSON.parse(e.data) : e.data;
    if(d && d.type === 'AVITO_CONTEXT'){
      // encode context into URL hash for Streamlit to read
      const enc = encodeURIComponent(JSON.stringify(d));
      window.parent.location.hash = 'ctx=' + enc;
    }
    if(d && d.type === 'AVITO_NAV' && d.page === 'dashboard'){
      const enc = encodeURIComponent(JSON.stringify(d));
      window.parent.location.hash = 'nav=' + enc;
    }
  } catch(err){}
});
</script>
"""
html = html.replace("</body>", bridge + "</body>")

components.html(html, height=920, scrolling=False)

# ── detect hash change via query param workaround ──────────────
# Streamlit doesn't expose window.location.hash directly.
# We use a small JS snippet that writes to a hidden Streamlit
# text_input via the Streamlit component setValue mechanism,
# allowing us to read the selection in the next rerun.

st.markdown("""
<script>
// Poll for hash changes and push to Streamlit via URL param
(function(){
  let last = '';
  setInterval(function(){
    const h = window.location.hash;
    if(h && h !== last && h.startsWith('#ctx=')){
      last = h;
      const params = new URLSearchParams(window.location.search);
      const ctx = decodeURIComponent(h.replace('#ctx=',''));
      // Navigate to context page via Streamlit's own router
      const url = new URL(window.location.href);
      url.searchParams.set('avito_ctx', ctx);
      url.hash = '';
      window.location.href = url.href;
    }
  }, 300);
})();
</script>
""", unsafe_allow_html=True)

# ── read context from query params if set ─────────────────────
params = st.query_params
if "avito_ctx" in params:
    try:
        ctx = json.loads(params["avito_ctx"])
        st.session_state["avito_context"] = ctx
        st.switch_page("pages/00a_Context.py")
    except Exception:
        pass
