"""
pages/00_Landing.py
════════════════════════════════════════════════════════════════
P0 · Global Market Map

Uses st.components.v1.declare_component() instead of
components.html() so that the JS setComponentValue protocol
actually triggers a Python rerun and returns the selection.

The HTML is served from assets/ via a tiny temp-dir trick:
we write a symlink/copy to a temp dir and declare_component
points at it. On Community Cloud this works because the
component HTML is served from the same origin as the app.
════════════════════════════════════════════════════════════════
"""
import sys, pathlib, json, tempfile, shutil, os
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

import streamlit as st

st.set_page_config(
    page_title="AVITO · Global Markets",
    page_icon="⬡",
    layout="wide",
    initial_sidebar_state="collapsed",
)

from core.page_setup import apply; apply()
from core.context_data import get_indices, get_sectors, get_commodity_flags

# ── prepare injected HTML ─────────────────────────────────────
_TEMPLATE = pathlib.Path(__file__).parent.parent / "assets" / "landing.html"

def _inject(html, key, val):
    return html.replace(f"__{key}__", json.dumps(val, default=str))

html = _TEMPLATE.read_text(encoding="utf-8")
html = _inject(html, "INDICES",         get_indices())
html = _inject(html, "SECTORS",         get_sectors())
html = _inject(html, "COMMODITY_FLAGS", get_commodity_flags())

# ── write to temp component directory ────────────────────────
# declare_component needs a directory with index.html
# We cache the directory path in session_state so it survives reruns
if "comp_dir" not in st.session_state:
    tmp = tempfile.mkdtemp(prefix="avito_landing_")
    st.session_state["comp_dir"] = tmp

comp_dir = st.session_state["comp_dir"]
index_path = os.path.join(comp_dir, "index.html")

# Always write fresh so data injection stays current
with open(index_path, "w", encoding="utf-8") as f:
    f.write(html)

# ── declare the component ─────────────────────────────────────
import streamlit.components.v1 as components

# declare_component returns a callable; calling it renders the component
# and returns whatever value JS sent via setComponentValue
_landing_component = components.declare_component(
    "avito_landing",
    path=comp_dir,
)

result = _landing_component(key="landing_map", default=None, height=920)

# ── handle result ─────────────────────────────────────────────
# result is None until user clicks "OPEN DASHBOARD →"
# then it becomes the payload dict: {indices, sectors, members, ts}
if result is not None:
    try:
        # result may be a dict already or a JSON string
        ctx = result if isinstance(result, dict) else json.loads(result)
        if ctx.get("indices"):          # only proceed if real selection
            st.session_state["avito_context"] = ctx
            st.session_state["avito_sectors"] = ctx.get("sectors", [])
            st.session_state["avito_indices"] = ctx.get("indices", [])
            st.session_state["avito_members"] = ctx.get("members", [])
            st.switch_page("pages/00a_Context.py")
    except Exception as exc:
        st.error(f"Navigation error: {exc}")
