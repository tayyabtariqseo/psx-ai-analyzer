import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from indicators import get_psx_data, calculate_indicators, get_live_price, calculate_pivots, get_company_info
from ai_engine import analyze_with_ai
import datetime

# Page Configuration
st.set_page_config(page_title="PSX AI Analyzer by Tayyab", layout="wide")

# Custom CSS for Professional Typography, Spacing, and Theme-aware metrics
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
    }
    
    .stMetric {
        background-color: rgba(128, 128, 128, 0.08);
        padding: 20px;
        border-radius: 12px;
        border: 1px solid rgba(128, 128, 128, 0.2);
    }
    
    h1, h2, h3 {
        font-weight: 700 !important;
        letter-spacing: -0.02em !important;
        line-height: 1.2 !important;
    }
    
    .reportview-container .main .block-container {
        padding-top: 2rem;
        padding-bottom: 5rem;
        max-width: 98%;
    }

    /* Improved word spacing and readability */
    p, li, span {
        letter-spacing: 0.01em;
        line-height: 1.6;
    }

    /* Mobile specific tweaks */
    @media (max-width: 768px) {
        .reportview-container .main .block-container {
            padding-left: 1rem;
            padding-right: 1rem;
        }
        .stMetric {
            margin-bottom: 10px;
        }
    }
    </style>
    """, unsafe_allow_html=True)

# Sidebar - User Inputs & Theme
st.sidebar.header("🎨 Theme Settings")
theme_choice = st.sidebar.radio("Dashboard Mode", options=["Dark", "Light"], index=0)

# Theme-based color palettes
if theme_choice == "Dark":
    chart_template = "plotly_dark"
    grid_color = "#2d2d2d"
    text_color = "#E0E0E0"
    card_bg = "#1e1e1e"
    card_text = "#ffffff"
    candle_up = "#26a69a"
    candle_down = "#ef5350"
else:
    chart_template = "plotly_white"
    grid_color = "#f0f0f0"
    text_color = "#121212"
    card_bg = "#f9f9f9"
    card_text = "#121212"
    candle_up = "#00c853"
    candle_down = "#ff5252"

st.sidebar.divider()
st.sidebar.header("📉 Stock Analysis")
symbol = st.sidebar.text_input("Enter Ticker", value="SYS").upper()
timeframe = st.sidebar.selectbox("Timeframe", options=["1D", "1W", "1M"], index=0)

# Cached data fetching
@st.cache_data(ttl=3600)
def fetch_historical_data(symbol, start_date):
    return get_psx_data(symbol, start_date=start_date)

@st.cache_data(ttl=60)
def fetch_live_data(symbol):
    # This specifically targets the DPS real-time JSON feed
    return get_live_price(symbol)

@st.cache_data(ttl=86400)
def fetch_company_info(symbol):
    return get_company_info(symbol)

st.title("📊 PSX AI Analyzer by Tayyab")

if st.sidebar.button("Analyze Stock"):
    with st.spinner(f"Fetching {symbol} details..."):
        full_name = fetch_company_info(symbol)
        
        # Header with Branding
        h_col1, h_col2 = st.columns([1, 12])
        with h_col1:
            st.image("https://dps.psx.com.pk/static/images/logo.png", width=80)
        with h_col2:
            st.markdown(f"<h1 style='margin:0; font-size: 2.2rem;'>{full_name}</h1>", unsafe_allow_html=True)
            st.markdown(f"<p style='color:gray; font-size: 1.1rem; margin-top:-5px;'>{symbol} | Pakistan Stock Exchange</p>", unsafe_allow_html=True)

        # 1. LIVE DATA IS THE SOURCE OF TRUTH FOR PRICE
        live_data = fetch_live_data(symbol)
        
        # 2. Historical Data for Indicators
        start_date = datetime.datetime.now() - datetime.timedelta(days=365)
        df = fetch_historical_data(symbol, start_date)
        
        if df is None or df.empty:
            st.error(f"No data found for {symbol}.")
        else:
            if symbol == "SYS":
                split_date = pd.to_datetime("2025-06-02")
                mask = df.index < split_date
                for col in ['Open', 'High', 'Low', 'Close']:
                    df.loc[mask, col] = df.loc[mask, col] / 5

            df = calculate_indicators(df)
            latest_hist = df.iloc[-1]
            pivots = calculate_pivots(df, lookback=2)
            
            # CRITICAL: Always use Live Price for the Metrics display to ensure accuracy (e.g. PSO 357.70)
            current_price = live_data['price'] if live_data else latest_hist['Close']
            
            if live_data:
                st.success(f"🟢 **Live Market Price:** {current_price:.2f} | **Updated:** {live_data['timestamp'].strftime('%H:%M:%S')}")
            
            # Metrics
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Current Price", f"{current_price:.2f}")
            m2.metric("RSI (14)", f"{latest_hist['RSI']:.2f}")
            m3.metric("MACD", f"{latest_hist['MACD_12_26_9']:.2f}")
            m4.metric("ADX (14)", f"{latest_hist['ADX_14']:.2f}")

            # Advanced Charting
            from plotly.subplots import make_subplots
            fig = make_subplots(
                rows=4, cols=1, 
                shared_xaxes=True, 
                vertical_spacing=0.03, 
                subplot_titles=("Price Action", "Volume", "RSI (14)", "MACD (12, 26, 9)"),
                row_heights=[0.5, 0.1, 0.2, 0.2]
            )

            # Row 1: Price
            fig.add_trace(go.Candlestick(
                x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'],
                name="Price", increasing_line_color=candle_up, decreasing_line_color=candle_down
            ), row=1, col=1)

            # EMAs
            ema_map = {'EMA_9': '#1e88e5', 'EMA_25': '#ffb300', 'EMA_44': '#8e24aa', 'EMA_100': '#fb8c00', 'EMA_200': '#f44336'}
            for ema_col, color in ema_map.items():
                fig.add_trace(go.Scatter(x=df.index, y=df[ema_col], mode='lines', name=ema_col.replace('_', ' '), line=dict(width=1.2, color=color)), row=1, col=1)

            if 'SUPERT_20_2' in df.columns:
                fig.add_trace(go.Scatter(x=df.index, y=df['SUPERT_20_2'], mode='lines', name='SuperTrend', line=dict(dash='dash', color='#4caf50', width=1.5)), row=1, col=1)

            # Row 2: Volume
            fig.add_trace(go.Bar(x=df.index, y=df['Volume'], name="Volume", marker_color='#607d8b'), row=2, col=1)

            # Row 3: RSI
            fig.add_trace(go.Scatter(x=df.index, y=df['RSI'], name="RSI", line=dict(color='#3f51b5', width=2)), row=3, col=1)
            fig.add_hline(y=70, line_dash="dash", line_color="#f44336", row=3, col=1)
            fig.add_hline(y=30, line_dash="dash", line_color="#4caf50", row=3, col=1)

            # Row 4: MACD
            fig.add_trace(go.Scatter(x=df.index, y=df['MACD_12_26_9'], name="MACD", line=dict(color='#2196f3')), row=4, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['MACDs_12_26_9'], name="Signal", line=dict(color='#ff9800')), row=4, col=1)
            fig.add_trace(go.Bar(x=df.index, y=df['MACDh_12_26_9'], name="Histogram", marker_color='#9e9e9e'), row=4, col=1)

            fig.update_layout(
                height=1100, template=chart_template, xaxis_rangeslider_visible=False,
                margin=dict(l=10, r=10, t=60, b=10),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
            )
            fig.update_xaxes(gridcolor=grid_color, zeroline=False)
            fig.update_yaxes(gridcolor=grid_color, zeroline=False)
            st.plotly_chart(fig, use_container_width=True)

            # MTT Section
            st.divider()
            st.subheader("🤖 MTT Technical View")
            
            ai_data_string = f"Co: {full_name}, P: {current_price}, RSI: {latest_hist['RSI']}, MACD: {latest_hist['MACD_12_26_9']}, EMAs: 9:{latest_hist['EMA_9']}, 100:{latest_hist['EMA_100']}, 200:{latest_hist['EMA_200']}"
            report = analyze_with_ai(symbol, timeframe, ai_data_string)
            st.markdown(f"<div style='background-color:{card_bg}; color:{card_text}; padding:25px; border-radius:12px; border: 1px solid rgba(128,128,128,0.2); font-size: 1.1rem; box-shadow: 0 4px 6px rgba(0,0,0,0.1);'>{report}</div>", unsafe_allow_html=True)

            # Data Tables
            st.divider()
            t_col1, t_col2 = st.columns(2)
            
            with t_col1:
                st.subheader("📍 Pivot Points")
                if pivots:
                    tab1, tab2 = st.tabs(["Traditional", "Fibonacci"])
                    with tab1:
                        st.table(pd.DataFrame({
                            "Level": ["R3", "R2", "R1", "Pivot", "S1", "S2", "S3"],
                            "Price": [f"{pivots['traditional'][k]:.2f}" for k in ["R3", "R2", "R1", "P", "S1", "S2", "S3"]]
                        }))
                    with tab2:
                        st.table(pd.DataFrame({
                            "Level": ["R3", "R2", "R1", "Pivot", "S1", "S2", "S3"],
                            "Price": [f"{pivots['fibonacci'][k]:.2f}" for k in ["R3", "R2", "R1", "P", "S1", "S2", "S3"]]
                        }))

            with t_col2:
                st.subheader("📈 Full Indicator Summary")
                ind_list = ["EMA_9", "EMA_25", "EMA_44", "EMA_88", "EMA_100", "EMA_200", "RSI", "MACD_12_26_9", "ADX_14", "Chaikin"]
                st.table(pd.DataFrame({
                    "Indicator": [i.replace('_', ' ') for i in ind_list],
                    "Value": [f"{latest_hist[i]:.2f}" if i != "Chaikin" else f"{latest_hist[i]:.2e}" for i in ind_list]
                }))
else:
    st.info("👈 Enter a ticker and click Analyze to begin.")
