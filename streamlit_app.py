"""
streamlit_app.py  —  AVITO entry point
"""
import streamlit as st

st.set_page_config(
    page_title="AVITO · Portfolio Terminal",
    page_icon="⬡",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
  #MainMenu, header, footer { visibility: hidden; }
  .block-container { padding: 0 !important; max-width: 100% !important; }
  [data-testid="stAppViewContainer"] { background: #070a0d; }
</style>
""", unsafe_allow_html=True)

st.switch_page("pages/01_Overview.py")
