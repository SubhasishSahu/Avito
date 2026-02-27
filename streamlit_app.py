"""
Agent_Trader -- Portfolio Dashboard
Streamlit Community Cloud deployment.

Repo:   SubhasishSahu/Avito
Branch: master
File:   streamlit_app.py

Secrets required (Streamlit Cloud → App → Settings → Secrets):
    FERNET_KEY    = "EwpdRz6PVPNrqbtqjUzmK4SMKFDowQ-y2hFt_inEA7c="
    GITHUB_TOKEN  = "ghp_xxxx"
    GITHUB_REPO   = "SubhasishSahu/Avito"
    GITHUB_BRANCH = "master"
"""
import os
import json
import time
import warnings
from datetime import datetime

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import requests

warnings.filterwarnings("ignore")

# ── Inject Streamlit secrets into environment ──────────────────────────────────
for key in ["FERNET_KEY", "GITHUB_TOKEN", "GITHUB_REPO", "GITHUB_BRANCH", "FMP_API_KEY"]:
    if key in st.secrets and key not in os.environ:
        os.environ[key] = st.secrets[key]

import github_store as gs

# ── Page config ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Agent_Trader -- Portfolio Intelligence",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Theme colours ──────────────────────────────────────────────────────────────
GREEN  = "#00C48C"
RED    = "#FF5C5C"
BLUE   = "#3B82F6"
YELLOW = "#F59E0B"
GREY   = "#6B7280"

# ── Helpers ────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=300)   # cache 5 min
def load_snapshot() -> dict | None:
    return gs.read("snapshot")

@st.cache_data(ttl=300)
def load_fundamentals() -> dict | None:
    return gs.read("fundamentals")

@st.cache_data(ttl=60)
def load_metadata() -> dict:
    return gs.read_metadata()


def colour_pnl(val):
    """Return green or red CSS colour string based on sign."""
    try:
        return f"color: {GREEN}" if float(val) >= 0 else f"color: {RED}"
    except Exception:
        return ""


def fmt_pct(val) -> str:
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return "--"
    return f"{val:+.2f}%"


def fmt_inr(val) -> str:
    if val is None:
        return "--"
    try:
        v = float(val)
        if v >= 1e7:
            return f"₹{v/1e7:.2f} Cr"
        if v >= 1e5:
            return f"₹{v/1e5:.2f} L"
        return f"₹{v:,.2f}"
    except Exception:
        return "--"


def ticker_suggestions(raw: str) -> str:
    """
    Normalise broker-export tickers to canonical NSE symbols.
    Delegates to harvest_runner.normalize_ticker() which covers:
      - EQ-suffix variants (HDFCBANKEQ -> HDFCBANK)
      - Broker internal names (MUNDRAPORTEQ -> ADANIPORTS)
      - 41 user portfolio non-Nifty50 holdings (HALEQ -> HAL, etc.)
      - Generic EQ/BE/BL suffix stripping as fallback
    """
    try:
        import harvest_runner as hr
        return hr.normalize_ticker(raw)
    except Exception:
        # Fallback if harvest_runner not importable in Streamlit context
        import re
        t = raw.strip().upper()
        return re.sub(r"(EQ|BE|BL|N1|N2)$", "", t).rstrip("-") or t


def parse_excel(uploaded_file) -> pd.DataFrame | None:
    """
    Parse uploaded holdings file. Flexible column detection.
    Expected columns: Ticker, Shares/Qty/Quantity, AvgCost/Buy Price/Cost
    """
    try:
        if uploaded_file.name.endswith(".csv"):
            df = pd.read_csv(uploaded_file)
        else:
            df = pd.read_excel(uploaded_file)
    except Exception as e:
        st.error(f"Could not read file: {e}")
        return None

    df.columns = [c.strip() for c in df.columns]

    # Column alias maps
    ticker_aliases = ["Ticker", "Symbol", "Stock", "TICKER", "SYMBOL"]
    qty_aliases    = ["Shares", "Qty", "Quantity", "Units", "SHARES", "QTY"]
    cost_aliases   = ["AvgCost", "Avg Cost", "Buy Price", "Cost", "Price",
                      "Average Cost", "AVGCOST", "AVG COST"]

    def find_col(aliases):
        for a in aliases:
            if a in df.columns:
                return a
        return None

    t_col = find_col(ticker_aliases)
    q_col = find_col(qty_aliases)
    c_col = find_col(cost_aliases)

    if not t_col:
        st.error(f"No Ticker column found. Columns in file: {list(df.columns)}\n"
                 f"Expected one of: {ticker_aliases}")
        return None
    if not q_col:
        st.error(f"No Qty column found. Expected one of: {qty_aliases}")
        return None
    if not c_col:
        st.warning("No Avg Cost column found -- P&L calculations will be skipped.")

    # Build clean dataframe
    result = pd.DataFrame()
    result["Ticker"]   = df[t_col].apply(lambda x: ticker_suggestions(str(x)))
    result["Qty"]      = pd.to_numeric(df[q_col], errors="coerce").fillna(0)
    result["AvgCost"]  = pd.to_numeric(df[c_col], errors="coerce").fillna(0) if c_col else 0
    result["Sector"]   = df.get("Sector", "")
    result = result[result["Qty"] > 0].reset_index(drop=True)
    return result


def trigger_harvest(tickers: list):
    """Write holdings_trigger.enc to GitHub → fires GitHub Actions harvest."""
    payload = {
        "tickers":    tickers,
        "triggered_at": datetime.utcnow().isoformat(),
        "source":     "streamlit_upload",
    }
    ok = gs.write(
        "holdings_trigger",
        payload,
        f"trigger: harvest for {len(tickers)} holdings"
    )
    return ok


def enrich_holdings(holdings_df: pd.DataFrame, snapshot: dict) -> pd.DataFrame:
    """Join user holdings with pre-harvested analytics."""
    stocks_map = {s["ticker"]: s for s in snapshot.get("stocks", [])}
    rows = []
    for _, row in holdings_df.iterrows():
        ticker = row["Ticker"]
        s      = stocks_map.get(ticker, {})
        price  = s.get("price", None)
        qty    = row["Qty"]
        cost   = row["AvgCost"]

        invested   = qty * cost  if cost  else None
        mkt_val    = qty * price if price else None
        pnl        = mkt_val - invested if (mkt_val and invested) else None
        pnl_pct    = (pnl / invested * 100) if (pnl is not None and invested) else None

        rows.append({
            "Ticker":     ticker,
            "Name":       s.get("name", ticker),
            "Sector":     s.get("sector", row.get("Sector", "Unknown")),
            "Qty":        int(qty),
            "Avg Cost":   cost,
            "CMP":        price,
            "Invested":   invested,
            "Mkt Value":  mkt_val,
            "P&L":        pnl,
            "P&L %":      pnl_pct,
            "Beta":       s.get("beta_3y"),
            "RSI":        s.get("rsi"),
            "MACD":       s.get("macd"),
            "CAGR 3Y":    s.get("cagr_3y"),
            "CAGR 1Y":    s.get("cagr_1y"),
            "VaR 95%":    s.get("var_95"),
            "Max DD":     s.get("max_dd"),
            "Alpha":      s.get("alpha"),
            "SMA50":      s.get("sma50"),
            "SMA200":     s.get("sma200"),
            "In Universe": ticker in stocks_map,
        })
    return pd.DataFrame(rows)


# ── Sidebar ────────────────────────────────────────────────────────────────────

def render_sidebar(metadata: dict):
    with st.sidebar:
        st.image("https://raw.githubusercontent.com/SubhasishSahu/Avito/master/db/.gitkeep",
                 width=40, output_format="auto") if False else None
        st.title("📈 Agent_Trader")
        st.caption("Portfolio Intelligence Dashboard")
        st.divider()

        # Data freshness
        last_h = metadata.get("last_harvest")
        if last_h:
            try:
                dt    = datetime.fromisoformat(last_h)
                age_h = (datetime.utcnow() - dt).total_seconds() / 3600
                colour = GREEN if age_h < 26 else YELLOW if age_h < 48 else RED
                st.markdown(f"**Last Harvest**")
                st.markdown(f":{colour.lstrip('#')}[{dt.strftime('%d %b %Y %H:%M')} UTC]")
                st.caption(f"{age_h:.1f} hours ago")
            except Exception:
                st.caption("Last harvest: unknown")
        else:
            st.warning("No harvest data yet. Trigger harvest below.")

        st.divider()

        # Manual harvest trigger
        st.markdown("**⚡ Trigger Harvest**")
        st.caption("Fires after Excel upload or manually here")
        if st.button("🔄 Trigger Full Harvest", use_container_width=True):
            with st.spinner("Triggering..."):
                ok = trigger_harvest(list(
                    {s["ticker"] for s in (load_snapshot() or {}).get("stocks", [])}
                ))
            if ok:
                st.success("Harvest triggered via GitHub Actions")
                st.caption("Data updates in ~5 minutes")
            else:
                st.error("Trigger failed -- check GITHUB_TOKEN")

        st.divider()
        stocks_count = metadata.get("stocks_harvested", 0)
        st.metric("Stocks in DB", stocks_count)
        st.caption(f"Run ID: {metadata.get('run_id', '--')}")


# ── Tab renderers ──────────────────────────────────────────────────────────────

def tab_portfolio(enriched: pd.DataFrame):
    st.subheader("📋 Holdings Overview")

    # Top metrics
    total_invested = enriched["Invested"].sum()
    total_value    = enriched["Mkt Value"].sum()
    total_pnl      = enriched["P&L"].sum()
    total_pnl_pct  = (total_pnl / total_invested * 100) if total_invested else 0

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Invested",   fmt_inr(total_invested))
    c2.metric("Market Value",     fmt_inr(total_value))
    c3.metric("Total P&L",        fmt_inr(total_pnl),
              delta=f"{total_pnl_pct:+.2f}%")
    c4.metric("Holdings",         len(enriched))

    st.divider()

    # Holdings table
    display_cols = ["Ticker", "Name", "Sector", "Qty", "Avg Cost",
                    "CMP", "Mkt Value", "P&L", "P&L %"]
    disp = enriched[display_cols].copy()
    disp["Avg Cost"]  = disp["Avg Cost"].apply(lambda x: f"₹{x:,.2f}" if x else "--")
    disp["CMP"]       = disp["CMP"].apply(lambda x:      f"₹{x:,.2f}" if x else "--")
    disp["Mkt Value"] = disp["Mkt Value"].apply(fmt_inr)
    disp["P&L"]       = disp["P&L"].apply(fmt_inr)
    disp["P&L %"]     = disp["P&L %"].apply(fmt_pct)

    st.dataframe(
        disp.style.applymap(colour_pnl, subset=["P&L %", "P&L"]),
        use_container_width=True,
        hide_index=True,
    )

    # Flag unrecognised tickers
    unknown = enriched[~enriched["In Universe"]]["Ticker"].tolist()
    if unknown:
        st.warning(f"Tickers not in Nifty50 universe (no peer data): {unknown}")


def tab_risk(enriched: pd.DataFrame):
    st.subheader("⚠️ Risk Analysis")

    # Portfolio-level beta (weighted)
    total_val = enriched["Mkt Value"].sum() or 1
    enriched["Weight"] = enriched["Mkt Value"] / total_val
    port_beta = (enriched["Beta"] * enriched["Weight"]).sum()
    port_var  = (enriched["VaR 95%"] * enriched["Weight"]).sum()
    port_dd   = enriched["Max DD"].min()

    c1, c2, c3 = st.columns(3)
    beta_colour = "normal" if 0.8 <= port_beta <= 1.2 else "inverse"
    c1.metric("Portfolio Beta",    f"{port_beta:.2f}", help="Weighted avg vs Nifty50")
    c2.metric("Portfolio VaR 95%", f"{port_var:.2f}%",
              help="Max daily loss at 95% confidence")
    c3.metric("Worst Stock Max DD", f"{port_dd:.2f}%",
              help="Worst drawdown across holdings")

    st.divider()

    # Per-stock risk table
    risk_cols = ["Ticker", "Sector", "Beta", "VaR 95%", "Max DD", "Alpha"]
    risk_df   = enriched[risk_cols].copy()
    risk_df["Beta"]    = risk_df["Beta"].apply(lambda x: f"{x:.2f}" if x else "--")
    risk_df["VaR 95%"] = risk_df["VaR 95%"].apply(lambda x: f"{x:.2f}%" if x else "--")
    risk_df["Max DD"]  = risk_df["Max DD"].apply(lambda x: f"{x:.2f}%" if x else "--")
    risk_df["Alpha"]   = risk_df["Alpha"].apply(lambda x: f"{x:+.2f}%" if x else "--")

    st.dataframe(risk_df, use_container_width=True, hide_index=True)

    # Beta bar chart
    beta_data = enriched[enriched["Beta"].notna()].copy()
    if not beta_data.empty:
        fig = px.bar(
            beta_data.sort_values("Beta"),
            x="Ticker", y="Beta",
            color="Beta",
            color_continuous_scale=["green", "yellow", "red"],
            title="Beta vs Nifty50 -- Per Stock",
        )
        fig.add_hline(y=1, line_dash="dash", line_color="grey",
                      annotation_text="Market Beta = 1")
        st.plotly_chart(fig, use_container_width=True)


def tab_sector(enriched: pd.DataFrame):
    st.subheader("🏭 Sector Exposure")

    sec_group = enriched.groupby("Sector").agg(
        Invested   = ("Invested",  "sum"),
        Mkt_Value  = ("Mkt Value", "sum"),
        PnL        = ("P&L",       "sum"),
        Count      = ("Ticker",    "count"),
    ).reset_index()
    sec_group["PnL %"] = (sec_group["PnL"] / sec_group["Invested"] * 100).round(2)

    c1, c2 = st.columns(2)

    with c1:
        fig = px.pie(sec_group, values="Mkt_Value", names="Sector",
                     title="Portfolio by Market Value",
                     color_discrete_sequence=px.colors.qualitative.Set3)
        fig.update_traces(textposition="inside", textinfo="percent+label")
        st.plotly_chart(fig, use_container_width=True)

    with c2:
        fig = px.bar(sec_group.sort_values("PnL %"),
                     x="Sector", y="PnL %",
                     color="PnL %",
                     color_continuous_scale=["red", "yellow", "green"],
                     title="Sector P&L %")
        fig.add_hline(y=0, line_dash="dash", line_color="grey")
        st.plotly_chart(fig, use_container_width=True)

    st.dataframe(sec_group, use_container_width=True, hide_index=True)


def tab_peers(enriched: pd.DataFrame, snapshot: dict):
    st.subheader("🔍 Peer Comparison")

    if not snapshot:
        st.info("No snapshot data available. Trigger a harvest first.")
        return

    all_stocks = {s["ticker"]: s for s in snapshot.get("stocks", [])}
    holdings_tickers = enriched["Ticker"].tolist()

    selected = st.selectbox("Select your holding to compare vs peers:",
                            options=holdings_tickers)
    if not selected:
        return

    holding_sector = enriched[enriched["Ticker"] == selected]["Sector"].iloc[0]
    peers = [s for s in snapshot.get("stocks", [])
             if s.get("sector") == holding_sector]

    if not peers:
        st.info(f"No peer data for sector: {holding_sector}")
        return

    peers_raw = pd.DataFrame(peers)
    col_map = {
        "ticker": "Ticker", "name": "Name", "cagr_1y": "CAGR 1Y%",
        "cagr_3y": "CAGR 3Y%", "rsi": "RSI", "beta_3y": "Beta",
        "max_dd": "Max DD%", "var_95": "VaR 95%", "alpha": "Alpha%"
    }
    avail_cols = [c for c in col_map if c in peers_raw.columns]
    peers_df = peers_raw[avail_cols].copy()
    peers_df.columns = [col_map[c] for c in avail_cols]

    # Highlight selected ticker
    def highlight_selected(row):
        return ["background-color: #1e3a5f" if row["Ticker"] == selected
                else "" for _ in row]

    st.caption(f"Sector: **{holding_sector}** -- {len(peers)} stocks")
    st.dataframe(
        peers_df.style.apply(highlight_selected, axis=1),
        use_container_width=True, hide_index=True
    )

    # Peer CAGR comparison chart
    fig = px.bar(
        peers_df.dropna(subset=["CAGR 1Y%"]).sort_values("CAGR 1Y%"),
        x="Ticker", y="CAGR 1Y%",
        color="Ticker",
        title=f"{holding_sector} -- 1Y CAGR Peer Comparison",
    )
    st.plotly_chart(fig, use_container_width=True)


def tab_momentum(enriched: pd.DataFrame):
    st.subheader("📊 Momentum Signals")

    mom_df = enriched[["Ticker", "Name", "RSI", "MACD",
                        "CMP", "SMA50", "SMA200"]].copy()

    # RSI signal
    def rsi_signal(v):
        if v is None: return "--"
        if v > 70: return "🔴 Overbought"
        if v < 30: return "🟢 Oversold"
        return "⚪ Neutral"

    mom_df["RSI Signal"] = mom_df["RSI"].apply(rsi_signal)
    mom_df["MACD Signal"] = mom_df["MACD"].apply(
        lambda x: "🟢 Bullish" if x == "bullish" else ("🔴 Bearish" if x == "bearish" else "--")
    )
    mom_df["vs SMA50"]  = mom_df.apply(
        lambda r: "✅ Above" if (r["CMP"] and r["SMA50"] and r["CMP"] > r["SMA50"])
                  else "❌ Below" if (r["CMP"] and r["SMA50"]) else "--", axis=1
    )
    mom_df["vs SMA200"] = mom_df.apply(
        lambda r: "✅ Above" if (r["CMP"] and r["SMA200"] and r["CMP"] > r["SMA200"])
                  else "❌ Below" if (r["CMP"] and r["SMA200"]) else "--", axis=1
    )

    display = mom_df[["Ticker", "RSI", "RSI Signal", "MACD Signal",
                       "vs SMA50", "vs SMA200"]]
    st.dataframe(display, use_container_width=True, hide_index=True)

    # RSI gauge chart
    rsi_data = mom_df[mom_df["RSI"].notna()].copy()
    if not rsi_data.empty:
        fig = go.Figure()
        for _, row in rsi_data.iterrows():
            colour = RED if row["RSI"] > 70 else GREEN if row["RSI"] < 30 else BLUE
            fig.add_trace(go.Bar(
                name=row["Ticker"], x=[row["Ticker"]], y=[row["RSI"]],
                marker_color=colour
            ))
        fig.add_hline(y=70, line_dash="dash", line_color=RED,
                      annotation_text="Overbought (70)")
        fig.add_hline(y=30, line_dash="dash", line_color=GREEN,
                      annotation_text="Oversold (30)")
        fig.update_layout(title="RSI -- Your Holdings", showlegend=False)
        st.plotly_chart(fig, use_container_width=True)


def tab_fundamentals(enriched: pd.DataFrame, fundamentals: dict | None):
    st.subheader("📐 Fundamental Analysis")

    if not fundamentals:
        st.info("No fundamentals data. Trigger a harvest to fetch PE, PB, dividend yield.")
        return

    fund_data = fundamentals.get("data", {})
    rows = []
    for _, row in enriched.iterrows():
        t    = row["Ticker"]
        fund = fund_data.get(t, {})
        rows.append({
            "Ticker":    t,
            "Sector":    row["Sector"],
            "PE":        fund.get("pe"),
            "PB":        fund.get("pb"),
            "Div Yield": fund.get("div_yield"),
            "52W High":  fund.get("52w_high"),
            "52W Low":   fund.get("52w_low"),
            "Mkt Cap":   fund.get("mkt_cap"),
        })

    df = pd.DataFrame(rows)

    # Sector median PE for comparison
    sec_pe = df.groupby("Sector")["PE"].median().rename("Sector Median PE")
    df     = df.join(sec_pe, on="Sector")
    df["PE vs Sector"] = df.apply(
        lambda r: f"{((r['PE']/r['Sector Median PE'])-1)*100:+.1f}%"
        if (r["PE"] and r["Sector Median PE"]) else "--", axis=1
    )

    display = df[["Ticker", "Sector", "PE", "Sector Median PE",
                  "PE vs Sector", "PB", "Div Yield", "Mkt Cap"]].copy()
    display["Mkt Cap"]   = display["Mkt Cap"].apply(fmt_inr)
    display["Div Yield"] = display["Div Yield"].apply(
        lambda x: f"{x:.2f}%" if x else "--"
    )
    st.dataframe(display, use_container_width=True, hide_index=True)


def tab_correlation(enriched: pd.DataFrame, snapshot: dict):
    st.subheader("🔗 Holdings Correlation")
    st.caption("Correlation of 1-year daily returns between your holdings")

    holdings = enriched["Ticker"].tolist()

    if len(holdings) < 2:
        st.info("Upload at least 2 holdings to see correlation.")
        return

    # Pull return series from snapshot (use CAGR 1Y as proxy if price series unavailable)
    # For a real correlation matrix we'd need price history -- show what we have
    cagr_data = enriched[["Ticker", "CAGR 1Y"]].set_index("Ticker")
    beta_data  = enriched[["Ticker", "Beta"]].set_index("Ticker")

    st.info("Full correlation matrix requires per-stock price history -- "
            "showing CAGR 1Y and Beta as proxies below. "
            "Full correlation will be available in Sprint 3.")

    c1, c2 = st.columns(2)
    with c1:
        fig = px.bar(enriched.dropna(subset=["CAGR 1Y"]).sort_values("CAGR 1Y"),
                     x="Ticker", y="CAGR 1Y",
                     color="CAGR 1Y",
                     color_continuous_scale=["red", "yellow", "green"],
                     title="1Y CAGR -- Your Holdings")
        fig.add_hline(y=0, line_dash="dash", line_color="grey")
        st.plotly_chart(fig, use_container_width=True)

    with c2:
        fig = px.scatter(enriched.dropna(subset=["Beta", "CAGR 1Y"]),
                         x="Beta", y="CAGR 1Y",
                         text="Ticker", color="Sector",
                         title="Risk vs Return (Beta vs CAGR 1Y)")
        fig.add_vline(x=1, line_dash="dash", line_color="grey")
        fig.add_hline(y=0, line_dash="dash", line_color="grey")
        st.plotly_chart(fig, use_container_width=True)


def tab_news():
    st.subheader("📰 Market News")
    news = gs.read("news")
    if not news:
        st.info("No news data available. Trigger a harvest to fetch latest news.")
        return
    items = news if isinstance(news, list) else news.get("items", [])
    if not items:
        st.info("No news items in database.")
        return
    for item in items[:20]:
        with st.expander(f"📰 {item.get('title', 'No title')}", expanded=False):
            st.caption(f"{item.get('source', '')} -- {item.get('published', '')}")
            st.markdown(item.get("summary", ""))
            if item.get("url"):
                st.markdown(f"[Read full article →]({item['url']})")


# ── Main app ───────────────────────────────────────────────────────────────────

def main():
    metadata = load_metadata()
    render_sidebar(metadata)

    st.title("📈 Agent_Trader -- Portfolio Intelligence")
    st.caption("Upload your holdings Excel to see 8-dimension portfolio analysis")

    # ── Upload section ──────────────────────────────────────────────────────────
    with st.expander("📤 Upload Holdings", expanded=True):
        col_up, col_fmt = st.columns([2, 1])
        with col_up:
            uploaded = st.file_uploader(
                "Upload your holdings file",
                type=["xlsx", "xls", "csv"],
                help="Required columns: Ticker | Shares/Qty | AvgCost/Buy Price"
            )
        with col_fmt:
            st.markdown("**Expected format:**")
            st.dataframe(pd.DataFrame({
                "Ticker":  ["HDFCBANK", "TCS", "RELIANCE"],
                "Qty":     [100, 50, 75],
                "AvgCost": [1650, 3400, 2750],
                "Sector":  ["Financial Services", "IT", "Oil & Gas"],
            }), use_container_width=True, hide_index=True)

    # ── Load snapshot ───────────────────────────────────────────────────────────
    snapshot     = load_snapshot()
    fundamentals = load_fundamentals()

    if not snapshot:
        st.warning(
            "⚠️ No harvest data found in GitHub db/ folder.\n\n"
            "**Steps to fix:**\n"
            "1. Go to GitHub → Avito → Actions → Agent_Trader Harvest\n"
            "2. Click **Run workflow** → Run\n"
            "3. Wait ~5 minutes → refresh this page"
        )

        # Show connection diagnostics
        with st.expander("🔧 Connection Diagnostics"):
            with st.spinner("Testing..."):
                conn = gs.test_connection()
            for k, v in conn.items():
                st.write(f"`{k}`: {v}")
        return

    # ── No file uploaded -- show snapshot summary ────────────────────────────────
    if uploaded is None:
        stocks = snapshot.get("stocks", [])
        gen_at = snapshot.get("generated_at", "")

        st.info(
            f"✅ Harvest data loaded -- **{len(stocks)} stocks** in database\n\n"
            f"Generated: `{gen_at[:19] if gen_at else 'unknown'}` UTC\n\n"
            "Upload your holdings Excel above to start portfolio analysis."
        )

        # Show snapshot preview
        with st.expander("👀 Snapshot Preview (last 10 stocks)"):
            df_all = pd.DataFrame(stocks)
            # Defensive: only request columns that actually exist in snapshot
            wanted = ["ticker", "name", "sector", "price", "rsi", "macd",
                      "beta_3y", "cagr_1y", "cagr_3y"]
            available = [c for c in wanted if c in df_all.columns]
            if available:
                preview = df_all[available].tail(10)
                st.dataframe(preview, use_container_width=True, hide_index=True)
            else:
                # Fallback: show whatever columns are present
                st.dataframe(df_all.tail(10), use_container_width=True, hide_index=True)
                st.caption(f"Available columns: {list(df_all.columns)}")
        return

    # ── Parse uploaded file ─────────────────────────────────────────────────────
    holdings_df = parse_excel(uploaded)
    if holdings_df is None or holdings_df.empty:
        st.error("Could not parse holdings file. Check format and try again.")
        return

    st.success(f"✅ Parsed {len(holdings_df)} holdings from {uploaded.name}")

    # Check for new tickers vs last trigger
    current_tickers = sorted(holdings_df["Ticker"].tolist())
    prev_trigger    = gs.read("holdings_trigger") or {}
    prev_tickers    = sorted(prev_trigger.get("tickers", []))

    new_tickers = [t for t in current_tickers if t not in prev_tickers]
    if new_tickers:
        st.info(f"🆕 New tickers detected: **{new_tickers}**\n\n"
                "Triggering harvest for these stocks + sector peers...")
        with st.spinner("Writing trigger to GitHub..."):
            ok = trigger_harvest(current_tickers)
        if ok:
            st.success(
                "✅ Harvest triggered via GitHub Actions.\n\n"
                "New stock data will be ready in ~5 minutes. "
                "Refresh the page after the Actions run completes."
            )
        else:
            st.error(
                "❌ Failed to write trigger to GitHub.\n\n"
                "**Most likely cause:** The `GITHUB_TOKEN` in Streamlit Cloud secrets "
                "is the GitHub Actions token, which only works inside Actions — "
                "not from external apps.\n\n"
                "**Fix:** Create a Personal Access Token (PAT) at "
                "[github.com/settings/tokens](https://github.com/settings/tokens) "
                "with **Contents: Read & Write** permission for this repo, "
                "then replace `GITHUB_TOKEN` in "
                "Streamlit Cloud → App → Settings → Secrets with the new PAT.\n\n"
                "The dashboard will still work with existing snapshot data."
            )
    elif set(current_tickers) != set(prev_tickers):
        with st.spinner("Updating trigger file..."):
            trigger_harvest(current_tickers)

    # ── Enrich holdings with analytics ─────────────────────────────────────────
    enriched = enrich_holdings(holdings_df, snapshot)

    if enriched.empty:
        st.error("No matching stocks found in snapshot. Trigger a harvest first.")
        return

    # ── 8 Tabs ──────────────────────────────────────────────────────────────────
    tabs = st.tabs([
        "📋 Portfolio",
        "⚠️ Risk",
        "🏭 Sector",
        "🔍 Peers",
        "📊 Momentum",
        "📐 Fundamentals",
        "🔗 Correlation",
        "📰 News",
    ])

    with tabs[0]: tab_portfolio(enriched)
    with tabs[1]: tab_risk(enriched)
    with tabs[2]: tab_sector(enriched)
    with tabs[3]: tab_peers(enriched, snapshot)
    with tabs[4]: tab_momentum(enriched)
    with tabs[5]: tab_fundamentals(enriched, fundamentals)
    with tabs[6]: tab_correlation(enriched, snapshot)
    with tabs[7]: tab_news()


if __name__ == "__main__":
    main()
