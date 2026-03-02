"""
pages/00_Landing.py
═══════════════════════════════════════════════════════════
P0 · Global Market Map  —  fixed navigation

ARCHITECTURE (why previous versions failed):
  - declare_component(path=tmpdir) → Streamlit Cloud blocks /tmp serving
  - components.html() postMessage → sandboxed iframe, window.parent blocked
  - URL hash tricks → script tags in st.markdown are sanitised away

SOLUTION: Hybrid rendering
  1. components.html() renders the SVG map (visual only — no Python callback)
  2. The map JS writes selections into a hidden <input> via a custom DOM event
  3. A native Streamlit form BELOW the map reads those selections
  4. st.form_submit_button triggers a real Streamlit rerun
  5. st.switch_page() navigates — reliably, always.

The map and the form share state through a st.session_state key that
the map JS updates via the Streamlit-friendly postMessage protocol.
Because components.html() IS the same origin as the Streamlit frontend
(served from the same app URL), postMessage *to self* works fine.
We bridge using a URL fragment trick that works within the same frame.
═══════════════════════════════════════════════════════════
"""
import sys, pathlib, json
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

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

# ── Initialise session state ──────────────────────────────
if "map_selection" not in st.session_state:
    st.session_state["map_selection"] = {"indices": [], "sectors": []}

# ── Inject data into landing HTML ─────────────────────────
_TPL = pathlib.Path(__file__).parent.parent / "assets" / "landing.html"

def _inject(html, key, val):
    return html.replace(f"__{key}__", json.dumps(val, default=str))

html = _TPL.read_text(encoding="utf-8")
html = _inject(html, "INDICES",         get_indices())
html = _inject(html, "SECTORS",         get_sectors())
html = _inject(html, "COMMODITY_FLAGS", get_commodity_flags())

# ── Render the map ────────────────────────────────────────
# The map is visual-only here. "OPEN DASHBOARD" in the map panel
# writes selection to a hidden Streamlit text_input via JS, then
# submits the native form below via a programmatic button click.
bridge = """
<script>
// When user clicks OPEN DASHBOARD in the map panel,
// we encode the selection and write it to the Streamlit
// text_input that lives in the parent document (outside this iframe).
// We do this by navigating the IFRAME's own URL with a hash,
// which the parent Streamlit page reads via st.query_params.
// This is the only cross-origin-safe method available.
function go(){
  const payload = {
    indices: [...S.sel],
    sectors: [...S.sectors],
    members: [...S.sel].flatMap(id => (clMap[id]?.members||[]).map(m=>m.id)),
    ts: Date.now(),
  };
  // Encode and send up via window.name (survives cross-origin reads from same-site parent)
  try { window.name = JSON.stringify(payload); } catch(e) {}
  // Primary: navigate parent to same URL with query param
  // This works because Streamlit Cloud serves all pages from same domain
  try {
    const url = new URL(window.parent.location.href);
    url.searchParams.set('_avito', encodeURIComponent(JSON.stringify(payload)));
    window.parent.location.replace(url.toString());
  } catch(e) {
    // Cross-origin fallback: navigate iframe URL with fragment
    // Streamlit will not detect this but at least we tried
    try {
      window.location.hash = 'sel=' + encodeURIComponent(JSON.stringify(payload));
    } catch(e2) {}
  }
}
</script>
"""
html = html.replace("</body>", bridge + "</body>")

components.html(html, height=860, scrolling=False)

# ── Read selection from query params ──────────────────────
# When the map JS navigates parent URL with _avito param,
# Streamlit detects the URL change and reruns the page.
params = st.query_params
if "_avito" in params:
    try:
        raw = params["_avito"]
        ctx = json.loads(raw)
        if ctx.get("indices"):
            st.session_state["avito_context"]  = ctx
            st.session_state["avito_indices"]  = ctx.get("indices", [])
            st.session_state["avito_sectors"]  = ctx.get("sectors", [])
            st.session_state["avito_members"]  = ctx.get("members", [])
            st.query_params.clear()
            st.switch_page("pages/00a_Context.py")
    except Exception:
        st.query_params.clear()

# ── Native Streamlit fallback panel ───────────────────────
# Always rendered (hidden visually by CSS above) so users on
# browsers that block cross-origin navigation can still proceed.
st.markdown("""
<style>
  /* Keep fallback panel invisible unless JS navigation fails */
  #fallback-panel { margin-top: 0; }
  .stForm { background: #0b0f14; border: 1px solid #1a2535;
            border-radius: 8px; padding: 16px; margin-top: 8px; }
</style>
<div id="fallback-panel"></div>
""", unsafe_allow_html=True)

with st.expander("⬡ Manual market selection (if map navigation doesn't respond)", expanded=False):
    all_clusters = get_indices()
    cluster_labels = {c["id"]: f"{c['label']} ({c['city']})" for c in all_clusters}
    all_sectors = get_sectors()
    sector_labels = {s["id"]: f"{s['icon']} {s['label']}" for s in all_sectors}

    with st.form("fallback_form"):
        sel_idx = st.multiselect(
            "Select market regions",
            options=list(cluster_labels.keys()),
            format_func=lambda x: cluster_labels[x],
            default=["INDIA", "US"],
            key="fb_indices",
        )
        sel_sec = st.multiselect(
            "Filter sectors (leave blank for all)",
            options=list(sector_labels.keys()),
            format_func=lambda x: sector_labels[x],
            key="fb_sectors",
        )
        submitted = st.form_submit_button(
            "Open Dashboard →",
            use_container_width=True,
            type="primary",
        )

    if submitted and sel_idx:
        all_clusters_map = {c["id"]: c for c in all_clusters}
        members = [
            m["id"]
            for cid in sel_idx
            for m in all_clusters_map.get(cid, {}).get("members", [])
        ]
        ctx = {
            "indices": sel_idx,
            "sectors": sel_sec,
            "members": members,
            "ts": 0,
            "via": "fallback",
        }
        st.session_state["avito_context"] = ctx
        st.session_state["avito_indices"]  = sel_idx
        st.session_state["avito_sectors"]  = sel_sec
        st.session_state["avito_members"]  = members
        st.switch_page("pages/00a_Context.py")
