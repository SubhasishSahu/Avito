"""
core/rss_loader.py
Scrapes Economic Times, Moneycontrol, Reuters, BBC.
Falls back to rich mock headlines if feeds unreachable.
"""
from __future__ import annotations
import re
from datetime import datetime, timezone

_TAG_MAP: dict[str, list[str]] = {
    "rbi": ["Banking","NBFC"], "repo rate": ["Banking"], "credit": ["Banking","NBFC"],
    "npa": ["Banking"], "hdfc": ["Banking"], "sbi": ["Banking"], "icici": ["Banking"],
    "nbfc": ["NBFC"], "sebi": ["Finance"], "ipo": ["Finance"], "mutual fund": ["Finance"],
    "infosys": ["IT"], "tcs": ["IT"], "wipro": ["IT"], "hcl": ["IT"], "tech mahindra": ["IT"],
    "software": ["IT"], "outsourcing": ["IT"], "digital": ["IT"], "ai ": ["IT"],
    "crude": ["Energy"], "oil": ["Energy"], "brent": ["Energy"], "opec": ["Energy"],
    "petroleum": ["Energy"], "ongc": ["Energy"], "bpcl": ["Energy"], "natural gas": ["Energy"],
    "steel": ["Metals"], "copper": ["Metals"], "aluminium": ["Metals"], "lme": ["Metals"],
    "hindalco": ["Metals"], "jsw": ["Metals"], "tata steel": ["Metals"], "iron ore": ["Metals","Mining"],
    "automobile": ["Auto"], "ev ": ["Auto"], "maruti": ["Auto"], "electric vehicle": ["Auto"],
    "two wheeler": ["Auto"], "tata motors": ["Auto"],
    "pharma": ["Pharma"], "drug": ["Pharma"], "fda": ["Pharma"], "generic": ["Pharma"],
    "sun pharma": ["Pharma"], "cipla": ["Pharma"],
    "fmcg": ["FMCG"], "consumer goods": ["FMCG"], "hul": ["FMCG"], "itc": ["FMCG"],
    "hindustan unilever": ["FMCG"], "palm oil": ["FMCG"],
    "defence": ["Defence"], "hal ": ["Defence"], "mazagon": ["Defence"], "bdl": ["Defence"],
    "infrastructure": ["Infrastructure"], "roads": ["Infrastructure"], "larsen": ["Infrastructure"],
    "adani": ["Infrastructure","Energy"], "rvnl": ["Infrastructure"],
    "cement": ["Cement"], "ultratech": ["Cement"], "grasim": ["Cement"],
    "shipping": ["Logistics"], "freight": ["Logistics"], "delhivery": ["Logistics"],
    "baltic": ["Logistics","Metals","Energy"],
    "budget": ["Banking","Finance","Infrastructure"], "inflation": ["Banking","FMCG","Energy"],
    "gdp": ["Banking","IT","Auto"], "export": ["IT","Pharma","Metals"],
    "china": ["Metals","Pharma","IT"], "dollar": ["IT","Pharma","Energy"],
    "us fed": ["Banking","IT"], "tariff": ["IT","Pharma","Auto"],
}

_FEEDS = [
    {"name":"Economic Times Markets","url":"https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms","bias":["Banking","Finance","IT"]},
    {"name":"Economic Times Economy","url":"https://economictimes.indiatimes.com/news/economy/rssfeeds/897228639.cms","bias":["Banking","Infrastructure"]},
    {"name":"Moneycontrol","url":"https://www.moneycontrol.com/rss/latestnews.xml","bias":["Finance","Banking"]},
    {"name":"Reuters Business","url":"https://feeds.reuters.com/reuters/businessNews","bias":["Energy","Metals","IT"]},
    {"name":"BBC Business","url":"https://feeds.bbci.co.uk/news/business/rss.xml","bias":["Energy","Auto","IT"]},
]

_MOCK: list[dict] = [
    {"title":"RBI holds repo rate at 6.5%; stance remains withdrawal of accommodation","summary":"MPC voted 5-1 to hold rates citing sticky core inflation above 4% target. EMI relief unlikely before June review.","source":"Economic Times","url":"#","published":"2026-03-01","tags":["Banking","NBFC","Finance"]},
    {"title":"Nifty IT outperforms as dollar holds at ₹84.2; TCS leads","summary":"Strong dollar boosts export revenue outlook. TCS, Infosys, HCL guided for double-digit growth in Q4FY26.","source":"Moneycontrol","url":"#","published":"2026-03-01","tags":["IT"]},
    {"title":"Brent crude slips to $81 on China demand concerns; OMCs gain","summary":"Falling crude eases subsidy burden on BPCL and HPCL. ONGC exploration capex under review for FY27.","source":"Reuters","url":"#","published":"2026-03-01","tags":["Energy"]},
    {"title":"Defence capex rises 13% in revised estimates; HAL, Mazagon Dock rally","summary":"Government accelerates indigenous procurement. HAL order book at ₹94,000 cr. BDL missile programme ahead of schedule.","source":"Economic Times","url":"#","published":"2026-02-28","tags":["Defence","Engineering"]},
    {"title":"LME copper at 3-month high on Chile supply disruptions","summary":"Hindalco and NMDC benefit as copper crosses $9,000/tonne. Codelco output cut 8% on strike action.","source":"Reuters","url":"#","published":"2026-02-28","tags":["Metals","Mining"]},
    {"title":"Auto wholesale volumes up 8% YoY in Feb; rural demand drives 2W","summary":"Maruti, Hero MotoCorp strong. EV penetration at 6.2% of PV sales. Bajaj leads exports in 3W segment.","source":"Moneycontrol","url":"#","published":"2026-02-28","tags":["Auto"]},
    {"title":"SEBI tightens SME IPO disclosure norms; grey market activity to moderate","summary":"New framework requires 3-year audited financials and promoter lock-in of 5 years for SME listings.","source":"Economic Times","url":"#","published":"2026-02-27","tags":["Finance","Banking"]},
    {"title":"India pharma exports hit record $8.2bn; US generics demand stays strong","summary":"Sun Pharma, Dr Reddy's, Cipla benefit from ANDA approvals. US FDA inspection backlog clearing.","source":"Reuters","url":"#","published":"2026-02-27","tags":["Pharma"]},
    {"title":"India-US trade deal talks resume; IT sector watches services tariff","summary":"Potential changes to L1/H1B costs and services tariffs could affect IT FY27 guidance visibility.","source":"BBC Business","url":"#","published":"2026-02-26","tags":["IT","Finance"]},
    {"title":"Cement demand strong; UltraTech and Grasim raise capacity outlook to 200 MT","summary":"Housing and infra spend drives 9% YoY volume growth. Margins recovering as coal prices cool.","source":"Economic Times","url":"#","published":"2026-02-26","tags":["Cement","Infrastructure"]},
    {"title":"Palm oil falls 6% on Indonesia export tax cut; FMCG margins to improve","summary":"HUL and Britannia likely beneficiaries as edible oil input costs ease by ~₹8/kg.","source":"Moneycontrol","url":"#","published":"2026-02-25","tags":["FMCG"]},
    {"title":"Baltic Dry Index +12% on Red Sea rerouting; shipping costs elevated","summary":"Higher freight impacts steel and edible oil importers. Delhivery and logistics operators pass costs through.","source":"Reuters","url":"#","published":"2026-02-25","tags":["Logistics","Metals","FMCG"]},
    {"title":"S&P 500 correction deepens on Fed rate-hold signal; Nasdaq leads declines","summary":"Powell signals no cuts before Q3. Risk-off sentiment hits emerging markets including India. FII outflow ₹4,200 cr.","source":"BBC Business","url":"#","published":"2026-02-24","tags":["Banking","IT","Finance"]},
    {"title":"DAX hits record on German manufacturing rebound; auto exports surge","summary":"Germany PMI moves back into expansion. Positive for global auto supply chains and steel demand.","source":"Reuters","url":"#","published":"2026-02-24","tags":["Auto","Metals"]},
    {"title":"IRCTC Q3 profit up 22%; railway capex cycle intact","summary":"Passenger revenue grows 18%. Government committed to ₹2.5L cr railway capex in FY26.","source":"Economic Times","url":"#","published":"2026-02-23","tags":["Infrastructure","Finance"]},
    {"title":"OPEC+ extends output cut to Q2 2026; Brent floor seen at $78","summary":"Saudi Arabia and Russia agree to extend 2.2mbpd voluntary cut. India import bill rises by est. $3.2bn annually.","source":"Reuters","url":"#","published":"2026-02-22","tags":["Energy"]},
    {"title":"India power demand hits record 240 GW; NTPC, Power Grid capacity expansion on track","summary":"Summer peak demand will require 280 GW by May. NTPC adding 5 GW renewable capacity in FY26.","source":"Moneycontrol","url":"#","published":"2026-02-21","tags":["Utilities","Energy"]},
    {"title":"Nifty Bank underperforms as credit growth slows to 14%; NIM pressure builds","summary":"RBI data shows system credit growth at 14% vs 16% target. HDFC Bank and Axis Bank guide for margin compression.","source":"Economic Times","url":"#","published":"2026-02-20","tags":["Banking"]},
]


def _tag(text: str, bias: list[str]) -> list[str]:
    tl = text.lower()
    found: set[str] = set(bias)
    for kw, secs in _TAG_MAP.items():
        if kw in tl:
            found.update(secs)
    return sorted(found) or ["General"]


def _parse_date(dp) -> str:
    if not dp:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")
    try:
        if hasattr(dp, 'tm_year'):
            return datetime(*dp[:3]).strftime("%Y-%m-%d")
        return str(dp)[:10]
    except Exception:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def fetch_news(max_per_feed: int = 10) -> list[dict]:
    try:
        import feedparser
    except ImportError:
        return _MOCK

    articles: list[dict] = []
    for fd in _FEEDS:
        try:
            parsed = feedparser.parse(fd["url"])
            for e in parsed.entries[:max_per_feed]:
                title   = e.get("title","").strip()
                summary = re.sub(r"<[^>]+>","", e.get("summary", e.get("description",""))).strip()
                if not title:
                    continue
                articles.append({
                    "title":     title,
                    "summary":   summary[:260] + ("…" if len(summary)>260 else ""),
                    "source":    fd["name"],
                    "url":       e.get("link","#"),
                    "published": _parse_date(e.get("published_parsed") or e.get("updated_parsed")),
                    "tags":      _tag(title+" "+summary, fd["bias"]),
                })
        except Exception:
            continue

    if not articles:
        return _MOCK

    seen: set[str] = set()
    out: list[dict] = []
    for a in sorted(articles, key=lambda x: x["published"], reverse=True):
        k = a["title"][:48].lower()
        if k not in seen:
            seen.add(k)
            out.append(a)
    return out[:60]


def filter_by_sectors(articles: list[dict], sectors: list[str]) -> list[dict]:
    if not sectors:
        return articles
    s = set(sectors)
    return [a for a in articles if s.intersection(a["tags"])]
