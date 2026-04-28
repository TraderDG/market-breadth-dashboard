"""
app.py — Bloomberg Terminal-style Market Breadth Dashboard (Streamlit)
"""

import json
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import requests
import streamlit as st

# ─── PAGE CONFIG ─────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Market Breadth | Bloomberg Style",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── BLOOMBERG THEME ──────────────────────────────────────────────────────────

BLOOMBERG_CSS = """
<style>
/* Bloomberg Terminal Colors */
:root {
    --bb-bg:       #0a0a0a;
    --bb-panel:    #111111;
    --bb-border:   #2a2a2a;
    --bb-orange:   #FF6600;
    --bb-green:    #00FF41;
    --bb-red:      #FF3333;
    --bb-yellow:   #FFD700;
    --bb-cyan:     #00BFFF;
    --bb-white:    #E0E0E0;
    --bb-gray:     #666666;
    --bb-mono:     'Courier New', monospace;
}

/* Dark background everywhere */
.stApp, .stApp > header { background-color: var(--bb-bg) !important; }
.stSidebar { background-color: #080808 !important; border-right: 1px solid var(--bb-border); }
.stSidebar * { color: var(--bb-white) !important; }

/* Remove Streamlit branding */
#MainMenu, footer, header { visibility: hidden; }

/* All text */
*, p, label, div { color: var(--bb-white) !important; }
.metric-label { color: var(--bb-gray) !important; font-size: 11px !important; }

/* Tabs → Bloomberg nav bar */
.stTabs [data-baseweb="tab-list"] {
    background: var(--bb-panel) !important;
    border-bottom: 1px solid var(--bb-orange) !important;
    gap: 0 !important;
    padding: 0 !important;
}
.stTabs [data-baseweb="tab"] {
    background: transparent !important;
    color: var(--bb-gray) !important;
    border: none !important;
    border-right: 1px solid var(--bb-border) !important;
    padding: 6px 16px !important;
    font-family: var(--bb-mono) !important;
    font-size: 12px !important;
    text-transform: uppercase !important;
    letter-spacing: 1px !important;
}
.stTabs [aria-selected="true"] {
    background: var(--bb-orange) !important;
    color: #000 !important;
}

/* Selectbox / inputs */
.stSelectbox > div > div, .stDateInput > div > div {
    background: var(--bb-panel) !important;
    border: 1px solid var(--bb-border) !important;
    color: var(--bb-white) !important;
}

/* Metrics row */
[data-testid="metric-container"] {
    background: var(--bb-panel) !important;
    border: 1px solid var(--bb-border) !important;
    border-top: 2px solid var(--bb-orange) !important;
    padding: 8px 12px !important;
    border-radius: 2px !important;
}
[data-testid="stMetricValue"] {
    font-family: var(--bb-mono) !important;
    font-size: 22px !important;
    color: var(--bb-yellow) !important;
}
[data-testid="stMetricDelta"] { font-size: 12px !important; }

/* Page title bar */
.bb-title {
    background: var(--bb-orange);
    color: #000 !important;
    font-family: var(--bb-mono);
    font-size: 14px;
    font-weight: bold;
    padding: 4px 12px;
    margin-bottom: 8px;
    letter-spacing: 2px;
}

/* Section headers */
.bb-section {
    font-family: var(--bb-mono);
    font-size: 11px;
    color: var(--bb-orange) !important;
    text-transform: uppercase;
    letter-spacing: 2px;
    border-bottom: 1px solid var(--bb-border);
    padding-bottom: 4px;
    margin: 12px 0 6px 0;
}

/* DataFrame / tables */
.stDataFrame { background: var(--bb-panel) !important; }
</style>
"""

st.markdown(BLOOMBERG_CSS, unsafe_allow_html=True)

# ─── CONFIG ───────────────────────────────────────────────────────────────────

API_BASE = "http://localhost:8000"
INDICES = ["VNINDEX", "VN30", "VN100"]
SECTOR_NAMES = ["VNENE", "VNCOND", "VNCONS", "VNFIN", "VNHEAL",
                "VNIND", "VNIT", "VNMAT", "VNREAL", "VNUTI"]
SECTOR_LABELS = {
    "VNENE": "Energy", "VNCOND": "Cons.Disc", "VNCONS": "Cons.Stap",
    "VNFIN": "Financials", "VNHEAL": "Healthcare", "VNIND": "Industrials",
    "VNIT": "Info Tech", "VNMAT": "Materials", "VNREAL": "Real Estate",
    "VNUTI": "Utilities",
}

BB_GREEN  = "#00FF41"
BB_RED    = "#FF3333"
BB_ORANGE = "#FF6600"
BB_YELLOW = "#FFD700"
BB_CYAN   = "#00BFFF"
BB_GRAY   = "#444444"
BB_BG     = "#0a0a0a"
BB_PANEL  = "#111111"

PLOT_LAYOUT = dict(
    paper_bgcolor=BB_PANEL,
    plot_bgcolor=BB_BG,
    font=dict(family="Courier New", size=11, color="#E0E0E0"),
    margin=dict(l=50, r=20, t=30, b=40),
    legend=dict(
        bgcolor="rgba(0,0,0,0.5)",
        bordercolor="#333",
        borderwidth=1,
        font=dict(size=10),
    ),
    xaxis=dict(gridcolor="#1a1a1a", zerolinecolor="#2a2a2a"),
    yaxis=dict(gridcolor="#1a1a1a", zerolinecolor="#2a2a2a"),
    hovermode="x unified",
)

# ─── API HELPERS ──────────────────────────────────────────────────────────────

@st.cache_data(ttl=300)
def fetch(endpoint: str, params: dict) -> pd.DataFrame:
    """Call API and return DataFrame."""
    try:
        r = requests.get(f"{API_BASE}{endpoint}", params=params, timeout=10)
        r.raise_for_status()
        data = r.json().get("data", [])
        if not data:
            return pd.DataFrame()
        df = pd.DataFrame(data)
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date").sort_index()
        return df
    except Exception as e:
        st.error(f"API error: {e}")
        return pd.DataFrame()


def color_val(v, threshold=0):
    return BB_GREEN if v >= threshold else BB_RED


# ─── CHART BUILDERS ───────────────────────────────────────────────────────────

def line_chart(
    df: pd.DataFrame,
    cols: list[str],
    colors: list[str],
    title: str = "",
    yaxis_title: str = "",
    secondary_col: str = None,
    fill_zero: bool = False,
) -> go.Figure:
    """Generic multi-line Plotly chart."""
    fig = go.Figure()
    for col, color in zip(cols, colors):
        if col not in df.columns:
            continue
        kwargs = dict(fill="tozeroy", fillcolor=f"rgba({_hex_rgb(color)},0.08)") if fill_zero else {}
        fig.add_trace(go.Scatter(
            x=df.index, y=df[col],
            name=col, line=dict(color=color, width=1.5),
            **kwargs,
        ))
    if secondary_col and secondary_col in df.columns:
        fig.add_trace(go.Scatter(
            x=df.index, y=df[secondary_col],
            name=secondary_col,
            line=dict(color=BB_GRAY, width=1, dash="dot"),
            yaxis="y2",
        ))
        fig.update_layout(
            yaxis2=dict(overlaying="y", side="right", gridcolor="#1a1a1a",
                        showgrid=False, color="#E0E0E0"),
        )
    fig.update_layout(**PLOT_LAYOUT, title=dict(text=title, font=dict(size=12, color=BB_ORANGE)))
    fig.update_layout(yaxis_title=yaxis_title, height=350)
    return fig


def bar_chart(df: pd.DataFrame, col: str, title: str = "") -> go.Figure:
    """Colored bar chart (green/red by sign)."""
    if col not in df.columns:
        return go.Figure()
    series = df[col].dropna()
    colors = [BB_GREEN if v >= 0 else BB_RED for v in series]
    fig = go.Figure(go.Bar(x=series.index, y=series, marker_color=colors, name=col))
    fig.update_layout(**PLOT_LAYOUT, title=dict(text=title, font=dict(size=12, color=BB_ORANGE)), height=300)
    return fig


def dual_axis_chart(
    df: pd.DataFrame,
    left_cols: list[str],
    right_cols: list[str],
    left_colors: list[str],
    right_colors: list[str],
    title: str = "",
) -> go.Figure:
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    for col, color in zip(left_cols, left_colors):
        if col in df.columns:
            fig.add_trace(
                go.Scatter(x=df.index, y=df[col], name=col, line=dict(color=color, width=1.5)),
                secondary_y=False,
            )
    for col, color in zip(right_cols, right_colors):
        if col in df.columns:
            fig.add_trace(
                go.Scatter(x=df.index, y=df[col], name=col, line=dict(color=color, width=1, dash="dash")),
                secondary_y=True,
            )
    fig.update_layout(**PLOT_LAYOUT, title=dict(text=title, font=dict(size=12, color=BB_ORANGE)), height=380)
    fig.update_yaxes(gridcolor="#1a1a1a", zerolinecolor="#2a2a2a")
    return fig


def heatmap_chart(df: pd.DataFrame, title: str = "") -> go.Figure:
    """Sector performance heatmap."""
    # Last 20 trading days
    df_tail = df.tail(20)
    # Only price columns
    price_cols = [c for c in df_tail.columns if c in SECTOR_NAMES]
    if not price_cols:
        return go.Figure()
    pct = df_tail[price_cols].pct_change() * 100

    labels = [SECTOR_LABELS.get(c, c) for c in price_cols]
    z = pct.T.values

    fig = go.Figure(go.Heatmap(
        z=z,
        x=pct.index.strftime("%m/%d"),
        y=labels,
        colorscale=[[0, "#CC0000"], [0.5, "#111111"], [1, "#00AA33"]],
        zmid=0,
        text=z.round(1),
        texttemplate="%{text}%",
        textfont=dict(size=9),
        showscale=True,
        colorbar=dict(tickfont=dict(size=9)),
    ))
    fig.update_layout(**PLOT_LAYOUT, title=dict(text=title, font=dict(size=12, color=BB_ORANGE)), height=350)
    return fig


def gauge_chart(value: float, title: str, min_val=0, max_val=100) -> go.Figure:
    color = BB_GREEN if value > 50 else BB_RED if value < 30 else BB_YELLOW
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=value,
        title=dict(text=title, font=dict(size=11, color=BB_ORANGE)),
        number=dict(font=dict(size=20, color=color, family="Courier New")),
        gauge=dict(
            axis=dict(range=[min_val, max_val], tickfont=dict(size=9)),
            bar=dict(color=color),
            bgcolor=BB_PANEL,
            bordercolor=BB_GRAY,
            steps=[
                dict(range=[0, 30], color="#330000"),
                dict(range=[30, 70], color="#1a1a00"),
                dict(range=[70, 100], color="#003300"),
            ],
        ),
    ))
    fig.update_layout(paper_bgcolor=BB_PANEL, font_color="#E0E0E0",
                      height=200, margin=dict(l=20, r=20, t=40, b=10))
    return fig


def _hex_rgb(hex_color: str) -> str:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"{r},{g},{b}"


# ─── SIDEBAR ─────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown('<div class="bb-title">⟨ CONTROLS ⟩</div>', unsafe_allow_html=True)

    selected_index = st.selectbox("INDEX", INDICES, index=0)

    date_presets = {
        "1M": 30, "3M": 90, "6M": 180,
        "1Y": 365, "2Y": 730, "5Y": 1825, "MAX": 9999,
    }
    preset = st.radio("PERIOD", list(date_presets.keys()), index=4, horizontal=True)
    days = date_presets[preset]
    end_dt = datetime.now()
    start_dt = end_dt - timedelta(days=days)
    start_str = start_dt.strftime("%Y-%m-%d")
    end_str = end_dt.strftime("%Y-%m-%d")

    st.markdown("---")
    st.markdown('<div class="bb-section">DISPLAY</div>', unsafe_allow_html=True)
    show_vnindex_overlay = st.checkbox("VNINDEX Overlay", value=True)
    show_ema = st.checkbox("EMA Lines", value=True)

    st.markdown("---")
    st.markdown(
        f"<span style='font-size:10px;color:#444;font-family:Courier'>API: {API_BASE}</span>",
        unsafe_allow_html=True,
    )

params = dict(index=selected_index, start=start_str, end=end_str)

# ─── HEADER ──────────────────────────────────────────────────────────────────

st.markdown(
    f'<div class="bb-title">◈ MARKET BREADTH DASHBOARD — {selected_index} '
    f'| {start_str} → {end_str}</div>',
    unsafe_allow_html=True,
)

# ─── VNINDEX OVERLAY DATA ─────────────────────────────────────────────────────

@st.cache_data(ttl=300)
def get_vnindex(start, end):
    return fetch("/vnindex", {"start": start, "end": end})

vn_df = get_vnindex(start_str, end_str)

# ─── TABS ─────────────────────────────────────────────────────────────────────

tabs = st.tabs([
    "📈 OVERVIEW", "👥 PARTICIPATION", "📦 VOL BREADTH",
    "📊 VOLUME", "⚡ MOMENTUM", "📉 TREND", "🏭 SECTOR"
])

# ══════════════════════════════════════════════════════════════════════════════
# TAB 1: MARKET OVERVIEW
# ══════════════════════════════════════════════════════════════════════════════
with tabs[0]:
    df_mo = fetch("/market-overview", params)

    if df_mo.empty:
        st.warning("No market overview data. Run data_builder.py first.")
    else:
        # KPI row
        ad_col  = f"ADLines_{selected_index}"
        net_col = f"NetAdvances_{selected_index}"
        adr_col = f"ADRatio_{selected_index}"

        col1, col2, col3, col4 = st.columns(4)
        if ad_col in df_mo.columns:
            last_ad = df_mo[ad_col].dropna().iloc[-1] if not df_mo[ad_col].dropna().empty else 0
            prev_ad = df_mo[ad_col].dropna().iloc[-2] if len(df_mo[ad_col].dropna()) > 1 else last_ad
            col1.metric("AD LINE", f"{last_ad:,.0f}", f"{last_ad - prev_ad:+,.0f}")
        if net_col in df_mo.columns:
            last_net = df_mo[net_col].dropna().iloc[-1] if not df_mo[net_col].dropna().empty else 0
            col2.metric("NET ADVANCES", f"{last_net:+,.0f}",
                        delta_color="normal" if last_net >= 0 else "inverse")
        if adr_col in df_mo.columns:
            last_adr = df_mo[adr_col].dropna().iloc[-1] if not df_mo[adr_col].dropna().empty else 1
            col3.metric("A/D RATIO", f"{last_adr:.2f}", f"{'Bullish' if last_adr > 1 else 'Bearish'}")
        col4.metric("INDEX", selected_index, "")

        # AD Line chart
        st.markdown('<div class="bb-section">ADVANCE-DECLINE LINE</div>', unsafe_allow_html=True)
        ad_cols  = [c for c in [ad_col, f"ADLines_{selected_index}_EMA_10"] if c in df_mo.columns]
        ad_colors = [BB_CYAN, BB_ORANGE][:len(ad_cols)]

        if show_vnindex_overlay and not vn_df.empty:
            fig = dual_axis_chart(
                pd.concat([df_mo, vn_df], axis=1),
                left_cols=ad_cols, left_colors=ad_colors,
                right_cols=["VNINDEX"], right_colors=[BB_GRAY],
                title="AD Line vs VNINDEX",
            )
        else:
            fig = line_chart(df_mo, ad_cols, ad_colors, title="Advance-Decline Line")
        st.plotly_chart(fig, use_container_width=True)

        # Net Advances bar
        st.markdown('<div class="bb-section">DAILY NET ADVANCES</div>', unsafe_allow_html=True)
        if net_col in df_mo.columns:
            st.plotly_chart(bar_chart(df_mo, net_col, "Daily Net Advances"), use_container_width=True)

        # AD Ratio line
        st.markdown('<div class="bb-section">A/D RATIO</div>', unsafe_allow_html=True)
        if adr_col in df_mo.columns:
            fig_adr = line_chart(df_mo, [adr_col], [BB_YELLOW], title="Advance/Decline Ratio")
            fig_adr.add_hline(y=1, line_dash="dash", line_color=BB_GRAY, annotation_text="1.0")
            st.plotly_chart(fig_adr, use_container_width=True)


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2: PARTICIPATION
# ══════════════════════════════════════════════════════════════════════════════
with tabs[1]:
    df_part = fetch("/participation", params)

    if df_part.empty:
        st.warning("No participation data.")
    else:
        adv_col = f"PctAdvancing_{selected_index}"
        dec_col = f"PctDeclining_{selected_index}"

        # Gauges
        col1, col2, col3 = st.columns(3)
        if adv_col in df_part.columns:
            last_adv = df_part[adv_col].dropna().iloc[-1] if not df_part[adv_col].dropna().empty else 0
            col1.plotly_chart(gauge_chart(last_adv, "% ADVANCING"), use_container_width=True)
            col2.metric("% ADVANCING", f"{last_adv:.1f}%")
        if dec_col in df_part.columns:
            last_dec = df_part[dec_col].dropna().iloc[-1] if not df_part[dec_col].dropna().empty else 0
            col3.metric("% DECLINING", f"{last_dec:.1f}%")

        # Time series
        st.markdown('<div class="bb-section">PARTICIPATION OVER TIME</div>', unsafe_allow_html=True)
        fig_p = line_chart(
            df_part,
            cols=[adv_col, dec_col],
            colors=[BB_GREEN, BB_RED],
            title=f"% Stocks Advancing/Declining — {selected_index}",
            yaxis_title="%",
        )
        fig_p.add_hline(y=50, line_dash="dash", line_color=BB_GRAY, annotation_text="50%")
        st.plotly_chart(fig_p, use_container_width=True)

        # Rolling 20-day average
        if adv_col in df_part.columns:
            st.markdown('<div class="bb-section">20-DAY ROLLING AVERAGE</div>', unsafe_allow_html=True)
            roll_df = df_part[[adv_col, dec_col]].rolling(20).mean()
            roll_df.columns = [c + "_MA20" for c in roll_df.columns]
            fig_r = line_chart(
                roll_df,
                cols=[adv_col + "_MA20", dec_col + "_MA20"],
                colors=[BB_GREEN, BB_RED],
                title="Participation (20-Day MA)",
            )
            st.plotly_chart(fig_r, use_container_width=True)


# ══════════════════════════════════════════════════════════════════════════════
# TAB 3: VOLUME BREADTH
# ══════════════════════════════════════════════════════════════════════════════
with tabs[2]:
    df_vb = fetch("/volume-breadth", params)

    if df_vb.empty:
        st.warning("No volume breadth data.")
    else:
        ud_col  = f"UDVolumeRatio_{selected_index}"
        net_col = f"NetVolume_{selected_index}"
        cvi_col = f"CumulativeVolumeIndex_{selected_index}"

        # KPIs
        col1, col2, col3 = st.columns(3)
        for col_ui, key, label in [(col1, ud_col, "U/D VOL RATIO"),
                                    (col2, net_col, "NET VOLUME"),
                                    (col3, cvi_col, "CUM VOL INDEX")]:
            if key in df_vb.columns:
                v = df_vb[key].dropna().iloc[-1] if not df_vb[key].dropna().empty else 0
                col_ui.metric(label, f"{v:,.2f}")

        # Up/Down Ratio
        st.markdown('<div class="bb-section">UP/DOWN VOLUME RATIO</div>', unsafe_allow_html=True)
        if ud_col in df_vb.columns:
            fig_ud = line_chart(df_vb, [ud_col], [BB_CYAN], title="Up/Down Volume Ratio")
            fig_ud.add_hline(y=1, line_dash="dash", line_color=BB_GRAY, annotation_text="1.0")
            st.plotly_chart(fig_ud, use_container_width=True)

        # Net Volume bars
        st.markdown('<div class="bb-section">NET VOLUME</div>', unsafe_allow_html=True)
        if net_col in df_vb.columns:
            st.plotly_chart(bar_chart(df_vb, net_col, "Net Volume (Up - Down)"), use_container_width=True)

        # CVI line
        st.markdown('<div class="bb-section">CUMULATIVE VOLUME INDEX</div>', unsafe_allow_html=True)
        if cvi_col in df_vb.columns:
            if show_vnindex_overlay and not vn_df.empty:
                fig = dual_axis_chart(
                    pd.concat([df_vb, vn_df], axis=1),
                    left_cols=[cvi_col], left_colors=[BB_ORANGE],
                    right_cols=["VNINDEX"], right_colors=[BB_GRAY],
                    title="Cumulative Volume Index vs VNINDEX",
                )
            else:
                fig = line_chart(df_vb, [cvi_col], [BB_ORANGE], title="Cumulative Volume Index")
            st.plotly_chart(fig, use_container_width=True)


# ══════════════════════════════════════════════════════════════════════════════
# TAB 4: VOLUME (OBV Breadth)
# ══════════════════════════════════════════════════════════════════════════════
with tabs[3]:
    idx_for_vol = selected_index if selected_index in ("VNINDEX", "VN30") else "VNINDEX"
    df_vol = fetch("/volume", {"index": idx_for_vol, "start": start_str, "end": end_str})

    if df_vol.empty:
        st.warning(f"OBV Breadth not available for {selected_index}. Showing VNINDEX.")
    else:
        obv_col = f"OBVBreadth_{idx_for_vol}"
        col1, col2 = st.columns([3, 1])
        if obv_col in df_vol.columns:
            last_obv = df_vol[obv_col].dropna().iloc[-1] if not df_vol[obv_col].dropna().empty else 0
            prev_obv = df_vol[obv_col].dropna().iloc[-2] if len(df_vol[obv_col].dropna()) > 1 else last_obv
            col2.metric("OBV BREADTH", f"{last_obv:,.0f}", f"{last_obv - prev_obv:+,.0f}")

        st.markdown('<div class="bb-section">OBV BREADTH (On-Balance Volume)</div>', unsafe_allow_html=True)
        if show_vnindex_overlay and not vn_df.empty:
            fig = dual_axis_chart(
                pd.concat([df_vol, vn_df], axis=1),
                left_cols=[obv_col], left_colors=[BB_CYAN],
                right_cols=["VNINDEX"], right_colors=[BB_GRAY],
                title=f"OBV Breadth vs VNINDEX — {idx_for_vol}",
            )
        else:
            fig = line_chart(df_vol, [obv_col], [BB_CYAN], title="OBV Breadth")
        st.plotly_chart(fig, use_container_width=True)

        st.markdown(
            '<div style="font-size:10px;color:#444;font-family:Courier">'
            'Formula: Cumulative Sum of sign(Advances - Declines) × TotalVolume'
            '</div>',
            unsafe_allow_html=True,
        )


# ══════════════════════════════════════════════════════════════════════════════
# TAB 5: MOMENTUM
# ══════════════════════════════════════════════════════════════════════════════
with tabs[4]:
    df_mom = fetch("/momentum", params)

    if df_mom.empty:
        st.warning("No momentum data.")
    else:
        mco_col  = f"McClellanOsc_{selected_index}"
        mcor_col = f"McClellanOsc_ratio_{selected_index}"
        nhnl_col = f"NHNLRatio_{selected_index}"
        nh_col   = f"New_High_52_{selected_index}_week"
        nl_col   = f"New_Low_52_{selected_index}_week"

        # McClellan Oscillator
        st.markdown('<div class="bb-section">McCLELLAN OSCILLATOR</div>', unsafe_allow_html=True)
        mc_col = mco_col if mco_col in df_mom.columns else mcor_col
        if mc_col in df_mom.columns:
            last_mc = df_mom[mc_col].dropna().iloc[-1] if not df_mom[mc_col].dropna().empty else 0
            c1, c2, c3 = st.columns(3)
            c1.metric("McCLELLAN OSC", f"{last_mc:.1f}",
                      "Bullish" if last_mc > 0 else "Bearish")
            # Overbought/oversold zones
            fig_mc = bar_chart(df_mom, mc_col, f"McClellan Oscillator — {selected_index}")
            fig_mc.add_hrect(y0=100, y1=fig_mc.data[0].y.max() if len(fig_mc.data) > 0 else 200,
                             fillcolor="rgba(255,0,0,0.05)", line_width=0)
            fig_mc.add_hrect(y0=fig_mc.data[0].y.min() if len(fig_mc.data) > 0 else -200, y1=-100,
                             fillcolor="rgba(0,255,0,0.05)", line_width=0)
            fig_mc.add_hline(y=100, line_dash="dash", line_color="#FF3333", annotation_text="OB")
            fig_mc.add_hline(y=-100, line_dash="dash", line_color=BB_GREEN, annotation_text="OS")
            st.plotly_chart(fig_mc, use_container_width=True)

        # New Highs / New Lows
        st.markdown('<div class="bb-section">NEW HIGHS − NEW LOWS (52-Week)</div>', unsafe_allow_html=True)
        nh_key = f"New_High_52_{selected_index}_week"
        nl_key = f"New_Low_52_{selected_index}_week"
        if nh_key in df_mom.columns or nl_key in df_mom.columns:
            nh_nl_cols   = [c for c in [nh_key, nl_key] if c in df_mom.columns]
            nh_nl_colors = [BB_GREEN, BB_RED][:len(nh_nl_cols)]
            st.plotly_chart(
                line_chart(df_mom, nh_nl_cols, nh_nl_colors, title="New Highs / New Lows"),
                use_container_width=True,
            )

        # NH/NL Ratio
        if nhnl_col in df_mom.columns:
            st.markdown('<div class="bb-section">NH/NL RATIO</div>', unsafe_allow_html=True)
            fig_nhnl = line_chart(df_mom, [nhnl_col], [BB_YELLOW], title="New Highs / (New Highs + New Lows)")
            fig_nhnl.add_hline(y=0.5, line_dash="dash", line_color=BB_GRAY, annotation_text="50%")
            st.plotly_chart(fig_nhnl, use_container_width=True)


# ══════════════════════════════════════════════════════════════════════════════
# TAB 6: TREND
# ══════════════════════════════════════════════════════════════════════════════
with tabs[5]:
    df_trend = fetch("/trend", params)

    if df_trend.empty:
        st.warning("No trend data.")
    else:
        mcs_col = f"McClellanOsc_sum_{selected_index}"
        ma20_col = f"Above_Ma_20_{selected_index}"
        ma50_col = f"Above_Ma_50_{selected_index}"
        ma100_col = f"Above_Ma_100_{selected_index}"
        ma200_col = f"Above_Ma_200_{selected_index}"
        hl_col = f"HighLowIndex_{selected_index}"

        # KPIs
        ma_keys = [ma20_col, ma50_col, ma100_col, ma200_col]
        ma_labels = ["% > MA20", "% > MA50", "% > MA100", "% > MA200"]
        kpi_cols = st.columns(len(ma_keys))
        for col_ui, key, label in zip(kpi_cols, ma_keys, ma_labels):
            if key in df_trend.columns:
                v = df_trend[key].dropna().iloc[-1] if not df_trend[key].dropna().empty else 0
                col_ui.metric(label, f"{v:.1f}%",
                              delta_color="normal" if v > 50 else "inverse")

        # McClellan Summation
        if mcs_col in df_trend.columns:
            st.markdown('<div class="bb-section">McCLELLAN SUMMATION INDEX</div>', unsafe_allow_html=True)
            if show_vnindex_overlay and not vn_df.empty:
                fig = dual_axis_chart(
                    pd.concat([df_trend, vn_df], axis=1),
                    left_cols=[mcs_col], left_colors=[BB_CYAN],
                    right_cols=["VNINDEX"], right_colors=[BB_GRAY],
                    title=f"McClellan Summation Index — {selected_index}",
                )
            else:
                fig = line_chart(df_trend, [mcs_col], [BB_CYAN], title="McClellan Summation")
            fig.add_hline(y=0, line_dash="dash", line_color=BB_GRAY)
            st.plotly_chart(fig, use_container_width=True)

        # % Above MAs multi-line
        ma_avail = [c for c in [ma20_col, ma50_col, ma100_col, ma200_col] if c in df_trend.columns]
        if ma_avail:
            st.markdown('<div class="bb-section">% STOCKS ABOVE MOVING AVERAGES</div>', unsafe_allow_html=True)
            ma_colors = [BB_GREEN, BB_YELLOW, BB_ORANGE, BB_RED][:len(ma_avail)]
            fig_ma = line_chart(df_trend, ma_avail, ma_colors,
                                title=f"% Above MA — {selected_index}", yaxis_title="%")
            fig_ma.add_hline(y=50, line_dash="dash", line_color=BB_GRAY, annotation_text="50%")
            fig_ma.add_hline(y=80, line_dash="dot",  line_color="#443300", annotation_text="80%")
            fig_ma.add_hline(y=20, line_dash="dot",  line_color="#330044", annotation_text="20%")
            st.plotly_chart(fig_ma, use_container_width=True)

        # High-Low Index
        if hl_col in df_trend.columns:
            st.markdown('<div class="bb-section">HIGH-LOW INDEX</div>', unsafe_allow_html=True)
            fig_hl = line_chart(df_trend, [hl_col], [BB_YELLOW],
                                title="High-Low Index = NH / (NH + NL)", yaxis_title="%")
            fig_hl.add_hline(y=50, line_dash="dash", line_color=BB_GRAY)
            st.plotly_chart(fig_hl, use_container_width=True)


# ══════════════════════════════════════════════════════════════════════════════
# TAB 7: SECTOR
# ══════════════════════════════════════════════════════════════════════════════
with tabs[6]:
    df_sec = fetch("/sector", {
        "start": start_str, "end": end_str, "metrics": "price,adline,outperform"
    })

    if df_sec.empty:
        st.warning("No sector data.")
    else:
        # Heatmap
        st.markdown('<div class="bb-section">SECTOR PERFORMANCE HEATMAP (Last 20 Days)</div>', unsafe_allow_html=True)
        st.plotly_chart(heatmap_chart(df_sec, "Sector Daily Returns (%)"), use_container_width=True)

        # Sector AD Lines
        ad_cols = [c for c in df_sec.columns if c.endswith("_ADLine")]
        if ad_cols:
            st.markdown('<div class="bb-section">SECTOR AD LINES</div>', unsafe_allow_html=True)
            colors = px.colors.qualitative.Set1[:len(ad_cols)]
            fig_sec = line_chart(df_sec, ad_cols, colors, title="Sector Advance-Decline Lines")
            st.plotly_chart(fig_sec, use_container_width=True)

        # % Outperforming (rolling 20-day)
        outperf_cols = [c for c in df_sec.columns if c.endswith("_Outperf")]
        if outperf_cols:
            st.markdown('<div class="bb-section">% DAYS OUTPERFORMING VNINDEX (20-Day Rolling)</div>', unsafe_allow_html=True)
            roll_df = df_sec[outperf_cols].rolling(20).mean() * 100
            roll_df.columns = [c.replace("_Outperf", "") for c in roll_df.columns]
            fig_outperf = line_chart(
                roll_df,
                cols=list(roll_df.columns),
                colors=px.colors.qualitative.Set1[:len(roll_df.columns)],
                title="Sector Outperformance Rate (%)",
                yaxis_title="%",
            )
            fig_outperf.add_hline(y=50, line_dash="dash", line_color=BB_GRAY, annotation_text="50%")
            st.plotly_chart(fig_outperf, use_container_width=True)

        # Latest % Outperforming table
        if outperf_cols:
            st.markdown('<div class="bb-section">LATEST SECTOR RANKING</div>', unsafe_allow_html=True)
            last_outperf = df_sec[outperf_cols].tail(20).mean() * 100
            last_outperf.index = [c.replace("_Outperf", "") for c in last_outperf.index]
            ranking_df = pd.DataFrame({
                "Sector": [SECTOR_LABELS.get(s, s) for s in last_outperf.index],
                "Code": last_outperf.index,
                "% Outperforming (20D)": last_outperf.round(1).values,
            }).sort_values("% Outperforming (20D)", ascending=False)
            ranking_df["Signal"] = ranking_df["% Outperforming (20D)"].apply(
                lambda x: "🟢 Strong" if x > 60 else ("🔴 Weak" if x < 40 else "🟡 Neutral")
            )
            st.dataframe(
                ranking_df,
                use_container_width=True,
                hide_index=True,
            )
