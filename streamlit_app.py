"""
streamlit_app.py — AVITO entry point

Handles _avito param that may arrive here if the user's browser navigates
to root "/" instead of the specific landing page URL.
Otherwise routes directly to landing.
"""
import json
import urllib.parse
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

def _parse(raw: str) -> dict | None:
    for s in (raw, urllib.parse.unquote(raw)):
        try:
            obj = json.loads(s)
            if isinstance(obj, dict):
                return obj
        except Exception:
            continue
    return None

params = st.query_params

if "_avito" in params:
    ctx = _parse(params["_avito"])
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
        st.switch_page("pages/00_Landing.py")
else:
    st.switch_page("pages/00_Landing.py")
