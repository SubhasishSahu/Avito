"""
core/page_setup.py
Shared Streamlit configuration applied to every page.
"""
import streamlit as st


CHROME_CSS = """
<style>
  #MainMenu, header, footer { visibility: hidden; }
  .block-container { padding: 0 !important; max-width: 100% !important; }
  [data-testid="stAppViewContainer"] { background: #070a0d; }
  [data-testid="stSidebar"] { display: none; }
</style>
"""


def apply() -> None:
    """Hide Streamlit chrome. Call at the top of every page."""
    st.markdown(CHROME_CSS, unsafe_allow_html=True)
