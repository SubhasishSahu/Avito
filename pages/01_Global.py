"""
pages/01_Global.py — Tab 1: Global Financial Intelligence
Static, independent page. No navigation, no session state dependencies.
Renders global.html with live RSS news injected.
"""
import sys, pathlib, json
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(
    page_title="AVITO · Global",
    page_icon="⬡",
    layout="wide",
    initial_sidebar_state="collapsed",
)

from core.page_setup import apply; apply()

@st.cache_data(ttl=1800)
def load_news():
    try:
        from core.rss_loader import fetch_news
        return fetch_news()
    except Exception:
        # Fallback news when RSS is unavailable
        return [
            {"title": "RBI holds repo rate at 6.5%; accommodative stance maintained",
             "summary": "Reserve Bank of India's Monetary Policy Committee kept rates unchanged amid easing inflation and growth concerns.",
             "source": "RBI", "published": "03 Mar 2026",
             "tags": ["Banking", "RBI", "Rates"]},
            {"title": "Nifty IT index surges 1.8% led by TCS and Infosys on strong US deal wins",
             "summary": "IT sector outperforms broader market after major contract announcements from top-tier Indian software exporters.",
             "source": "ET Markets", "published": "03 Mar 2026",
             "tags": ["IT", "TCS", "Infosys"]},
            {"title": "FII outflow at ₹4,200 crore over 3 sessions; DII buying cushions fall",
             "summary": "Foreign institutional investors continue net selling while domestic funds absorb pressure at lower levels.",
             "source": "Moneycontrol", "published": "03 Mar 2026",
             "tags": ["FII", "Markets", "Banking"]},
            {"title": "Brent crude slips to $81 on demand concerns; OMC stocks rise",
             "summary": "Lower oil prices provide relief to oil marketing companies and reduce India's import burden.",
             "source": "Reuters", "published": "03 Mar 2026",
             "tags": ["Energy", "Crude Oil", "OMC"]},
            {"title": "HDFC Bank Q3 net profit up 2.2%; NIM stable at 3.4%",
             "summary": "India's largest private bank reports modest profit growth with asset quality remaining stable.",
             "source": "HDFC Bank", "published": "02 Mar 2026",
             "tags": ["Banking", "HDFC", "Results"]},
            {"title": "Tata Motors domestic sales rise 8% YoY; EV segment grows 42%",
             "summary": "Automaker reports strong volume growth driven by commercial vehicles and electric vehicle adoption.",
             "source": "BSE Filing", "published": "02 Mar 2026",
             "tags": ["Auto", "EV", "Tata"]},
            {"title": "Copper prices decline 0.8% on weak China PMI data; metals under pressure",
             "summary": "Industrial metals retreat as China's manufacturing PMI disappoints, signalling slower demand.",
             "source": "LME", "published": "02 Mar 2026",
             "tags": ["Metals", "Copper", "China"]},
            {"title": "Sun Pharma receives USFDA approval for key biosimilar product",
             "summary": "Regulatory clearance opens up $2 billion US market for India's largest pharmaceutical company.",
             "source": "USFDA", "published": "01 Mar 2026",
             "tags": ["Pharma", "Sun Pharma", "FDA"]},
            {"title": "Coal India production hits record 950MT; power sector demand stable",
             "summary": "State-run miner beats annual production target, ensuring energy security for Indian power plants.",
             "source": "Coal India", "published": "01 Mar 2026",
             "tags": ["Energy", "Coal", "Utilities"]},
            {"title": "India manufacturing PMI at 56.3 in Feb; strongest in 5 months",
             "summary": "S&P Global PMI data shows robust expansion in Indian manufacturing with new order growth accelerating.",
             "source": "S&P Global", "published": "01 Mar 2026",
             "tags": ["Macro", "PMI", "Manufacturing"]},
            {"title": "Reliance Jio IPO timeline: FY27 listing possible, DRHP prep underway",
             "summary": "India's most valuable telecom subsidiary moving toward public listing as Reliance monetises digital assets.",
             "source": "Bloomberg", "published": "28 Feb 2026",
             "tags": ["Telecom", "Reliance", "IPO"]},
            {"title": "USD/INR holds at 84.18; RBI intervention limits downside",
             "summary": "Rupee stabilises as central bank manages volatility through spot and forward market operations.",
             "source": "RBI", "published": "28 Feb 2026",
             "tags": ["Currency", "RBI", "USD"]},
        ]

news = load_news()

_TPL = pathlib.Path(__file__).parent.parent / "assets" / "global.html"
html = _TPL.read_text(encoding="utf-8")
html = html.replace("__NEWS__", json.dumps(news, default=str, ensure_ascii=False))

components.html(html, height=10000, scrolling=False)
