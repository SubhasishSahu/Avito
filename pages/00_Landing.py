"""
pages/00_Landing.py — P0 · Global Market Map

Navigation fix summary (definitive v5):
  The go() JS function navigates the parent window to its CURRENT URL
  (which is the landing page URL) + ?_avito=<JSON>.
  This avoids constructing the page path manually, which fails on
  Streamlit Community Cloud due to slug-based URL routing.
  
  Python reads the param on rerun and switches to 00a_Context.py.
"""
import sys, pathlib, json
import urllib.parse
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

def _parse_avito(raw: str) -> dict | None:
    """Parse _avito param. Streamlit auto-decodes URL encoding but
    double-encoding can occur. Try both raw and unquoted."""
    for attempt in (raw, urllib.parse.unquote(raw)):
        try:
            obj = json.loads(attempt)
            if isinstance(obj, dict):
                return obj
        except Exception:
            continue
    return None

# ── Read navigation signal FIRST ──────────────────────────────
params = st.query_params

if "_avito" in params:
    ctx = _parse_avito(params["_avito"])
    if ctx and ctx.get("indices"):
        st.session_state["avito_context"]    = ctx
        st.session_state["avito_indices"]    = ctx.get("indices", [])
        st.session_state["avito_sectors"]    = ctx.get("sectors", [])
        st.session_state["avito_members"]    = ctx.get("members", [])
        st.session_state["avito_has_oil"]    = ctx.get("has_oil", False)
        st.session_state["avito_has_metals"] = ctx.get("has_metals", False)
        st.query_params.clear()
        st.switch_page("pages/00a_Context.py")
    else:
        st.query_params.clear()

# ── Inject data into landing HTML ──────────────────────────────
_TPL = pathlib.Path(__file__).parent.parent / "assets" / "landing.html"

def _inject(html: str, key: str, val) -> str:
    return html.replace(f"__{key}__", json.dumps(val, default=str))

html = _TPL.read_text(encoding="utf-8")
html = _inject(html, "INDICES",         get_indices())
html = _inject(html, "SECTORS",         get_sectors())
html = _inject(html, "COMMODITY_FLAGS", get_commodity_flags())

components.html(html, height=900, scrolling=False)

# ── Native fallback ────────────────────────────────────────────
with st.expander("⬡ Manual navigation (if map click doesn't work)", expanded=False):
    all_clusters   = get_indices()
    cluster_labels = {c["id"]: f"{c['label']}  ({c['city']})" for c in all_clusters}
    all_sectors    = get_sectors()
    sector_labels  = {s["id"]: f"{s['icon']} {s['label']}" for s in all_sectors}

    with st.form("fallback_form"):
        sel_idx = st.multiselect(
            "Market regions",
            options=list(cluster_labels.keys()),
            format_func=lambda x: cluster_labels[x],
            default=["INDIA"],
        )
        sel_sec = st.multiselect(
            "Sector filter (blank = all Nifty50)",
            options=list(sector_labels.keys()),
            format_func=lambda x: sector_labels[x],
        )
        submitted = st.form_submit_button("Open Dashboard →", type="primary")

    if submitted and sel_idx:
        all_map = {c["id"]: c for c in all_clusters}
        members = [m["id"] for cid in sel_idx
                   for m in all_map.get(cid, {}).get("members", [])]
        ctx = {
            "indices":    sel_idx,
            "sectors":    sel_sec,
            "members":    members,
            "ts":         0,
            "via":        "fallback",
            "has_oil":    "COM_OIL"    in sel_idx,
            "has_metals": "COM_METALS" in sel_idx,
        }
        st.session_state["avito_context"]    = ctx
        st.session_state["avito_indices"]    = sel_idx
        st.session_state["avito_sectors"]    = sel_sec
        st.session_state["avito_members"]    = members
        st.switch_page("pages/00a_Context.py")
