"""
core/page_setup.py
Shared Streamlit configuration applied to every page.
Hides all Streamlit chrome and removes every margin/padding
that would cause the iframe component to be clipped or scrolled.
"""
import streamlit as st

# Target every wrapper Streamlit 1.40 injects around components:
#   stVerticalBlock → stVerticalBlockBorderWrapper → element-container
#   → stCustomComponentV1 → iframe
CHROME_CSS = """
<style>
  /* Hide all Streamlit chrome */
  #MainMenu, header, footer { visibility: hidden; }
  [data-testid="stToolbar"] { display: none; }

  /* Remove ALL padding and margin from the page shell */
  .block-container {
    padding: 0 !important;
    margin: 0 !important;
    max-width: 100% !important;
  }

  /* App background */
  [data-testid="stAppViewContainer"] { background: #070a0d; }
  [data-testid="stAppViewBlockContainer"] {
    padding: 0 !important;
    margin: 0 !important;
  }

  /* Hide sidebar completely */
  [data-testid="stSidebar"] { display: none !important; }
  [data-testid="collapsedControl"] { display: none !important; }

  /* Remove ALL margins from the component wrapper chain */
  .element-container {
    margin: 0 !important;
    padding: 0 !important;
  }
  [data-testid="stCustomComponentV1"] {
    margin: 0 !important;
    padding: 0 !important;
    display: block !important;
  }

  /* Remove vertical block gaps */
  [data-testid="stVerticalBlock"] {
    gap: 0 !important;
  }
  [data-testid="stVerticalBlockBorderWrapper"] {
    margin: 0 !important;
    padding: 0 !important;
  }

  /* The iframe itself — fill available space */
  [data-testid="stCustomComponentV1"] iframe {
    display: block !important;
    border: none !important;
  }

  /* Force the components.html iframe to fill the full viewport height */
  [data-testid="stCustomComponentV1"] iframe {
    height: 100vh !important;
    min-height: 100vh !important;
  }
</style>
"""


def apply() -> None:
    """Hide Streamlit chrome. Call at the top of every page."""
    st.markdown(CHROME_CSS, unsafe_allow_html=True)
