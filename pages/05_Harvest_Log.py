import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

import streamlit as st
st.set_page_config(page_title="AVITO", page_icon="⬡", layout="wide", initial_sidebar_state="collapsed")

from core.page_setup import apply; apply()
from core.data_loader import get_harvest_meta, get_run_history, get_nifty_series, get_snapshot, get_signals
from core.renderer import render_dashboard

@st.cache_data(ttl=300)
def load():
    meta     = get_harvest_meta()
    runs     = get_run_history()
    nifty    = get_nifty_series()
    snapshot = get_snapshot()
    signals  = get_signals(snapshot)
    return meta, runs, nifty, snapshot, signals

meta, runs, nifty, snapshot, signals = load()
render_dashboard("harvest", meta, runs, nifty, snapshot, signals)
