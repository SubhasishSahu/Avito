"""
streamlit_app.py — AVITO entry point

FIX: The old version unconditionally called st.switch_page('pages/00_Landing.py').
This stripped any incoming query params (?_avito=...) that the landing map's
go() function attached to the URL. The navigation payload was silently lost,
causing the "Open Dashboard" button to bounce back to the landing page forever.

NEW BEHAVIOUR:
  - If ?_avito param present → context from the map → go to 00a_Context
  - If ?_ctx param present   → coming from context page → go to 01_Overview
  - Otherwise                → show landing map (normal entry)
"""
import json
import streamlit as st

st.set_page_config(
    page_title="AVITO · Portfolio Intelligence",
    page_icon="⬡",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
  #MainMenu, header, footer { visibility: hidden; }
  .block-container { padding: 0 !important; max-width: 100% !important; }
  [data-testid="stAppViewContainer"] { background: #070a0d; }
  [data-testid="stSidebar"] { display: none; }
</style>
""", unsafe_allow_html=True)

params = st.query_params

# ── Route: map selection arriving via full-page navigation ──
if "_avito" in params:
    try:
        ctx = json.loads(params["_avito"])
        if ctx.get("indices"):
            st.session_state["avito_context"]    = ctx
            st.session_state["avito_indices"]    = ctx.get("indices", [])
            st.session_state["avito_sectors"]    = ctx.get("sectors", [])
            st.session_state["avito_members"]    = ctx.get("members", [])
            st.session_state["avito_has_oil"]    = ctx.get("has_oil", False)
            st.session_state["avito_has_metals"] = ctx.get("has_metals", False)
            st.query_params.clear()
            st.switch_page("pages/00a_Context.py")
    except Exception:
        st.query_params.clear()

# ── Route: "Open Dashboard" from context page ──
elif "_ctx" in params:
    try:
        ctx = json.loads(params["_ctx"])
        st.session_state["avito_context"] = ctx
        st.session_state["avito_sectors"] = ctx.get("sectors", [])
        st.session_state["avito_indices"] = ctx.get("indices", [])
        st.query_params.clear()
        st.switch_page("pages/01_Overview.py")
    except Exception:
        st.query_params.clear()

# ── Default: show the landing map ──
else:
    st.switch_page("pages/00_Landing.py")
