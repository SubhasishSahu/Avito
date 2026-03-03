"""
AVITO — Entry point
Routes to the Global Intelligence page.
"""
import streamlit as st

st.set_page_config(
    page_title="AVITO",
    page_icon="⬡",
    layout="wide",
    initial_sidebar_state="collapsed",
)
st.switch_page("pages/01_Global.py")
