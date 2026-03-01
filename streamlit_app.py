"""
streamlit_app.py  —  AVITO entry point
Routes directly to the Global Market Map (landing page).
"""
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

st.switch_page("pages/00_Landing.py")
