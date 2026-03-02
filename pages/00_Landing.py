"""
pages/00_Landing.py
════════════════════════════════════════════════════════════════
P0 · Global Market Map — 80/20 split layout

Navigation: uses URL param _avito (set by JS in landing.html)
which triggers st.query_params detection on Streamlit rerun.
Fallback: native Streamlit expander with multiselect + form.
════════════════════════════════════════════════════════════════
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

# ── Read navigation signal FIRST (before rendering anything) ──
params = st.query_params
if "_avito" in params:
    try:
        ctx = json.loads(params["_avito"])
        if ctx.get("indices"):
            st.session_state["avito_context"]  = ctx
            st.session_state["avito_indices"]  = ctx.get("indices", [])
            st.session_state["avito_sectors"]  = ctx.get("sectors", [])
            st.session_state["avito_members"]  = ctx.get("members", [])
            st.session_state["avito_has_oil"]  = ctx.get("has_oil", False)
            st.session_state["avito_has_metals"]= ctx.get("has_metals", False)
            st.query_params.clear()
            st.switch_page("pages/00a_Context.py")
    except Exception:
        st.query_params.clear()

# ── Inject data into landing HTML ─────────────────────────
_TPL = pathlib.Path(__file__).parent.parent / "assets" / "landing.html"

def _inject(html, key, val):
    return html.replace(f"__{key}__", json.dumps(val, default=str))

html = _TPL.read_text(encoding="utf-8")
html = _inject(html, "INDICES",         get_indices())
html = _inject(html, "SECTORS",         get_sectors())
html = _inject(html, "COMMODITY_FLAGS", get_commodity_flags())

# ── Render map ────────────────────────────────────────────
components.html(html, height=900, scrolling=False)

# ── Native fallback (collapsed by default) ────────────────
with st.expander("⬡ Direct navigation (if map buttons don't respond)", expanded=False):
    all_clusters = get_indices()
    cluster_labels = {c["id"]: f"{c['label']}  ({c['city']})" for c in all_clusters}
    all_sectors = get_sectors()
    sector_labels = {s["id"]: f"{s['icon']} {s['label']}" for s in all_sectors}

    with st.form("fallback_form"):
        sel_idx = st.multiselect(
            "Market regions",
            options=list(cluster_labels.keys()),
            format_func=lambda x: cluster_labels[x],
            default=["INDIA"],
        )
        sel_sec = st.multiselect(
            "Sector filter (blank = all)",
            options=list(sector_labels.keys()),
            format_func=lambda x: sector_labels[x],
        )
        submitted = st.form_submit_button("Open Dashboard →", type="primary")

    if submitted and sel_idx:
        all_map = {c["id"]: c for c in all_clusters}
        members = [m["id"] for cid in sel_idx
                   for m in all_map.get(cid, {}).get("members", [])]
        ctx = {
            "indices": sel_idx, "sectors": sel_sec,
            "members": members, "ts": 0, "via": "fallback",
            "has_oil":    "COM_OIL"    in sel_idx,
            "has_metals": "COM_METALS" in sel_idx,
        }
        st.session_state["avito_context"]  = ctx
        st.session_state["avito_indices"]  = sel_idx
        st.session_state["avito_sectors"]  = sel_sec
        st.session_state["avito_members"]  = members
        st.switch_page("pages/00a_Context.py")
