import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from indicators import get_psx_data, calculate_indicators, get_live_price, calculate_pivots, get_company_info
from ai_engine import analyze_with_ai
import datetime

# 1. THEME & GLOBAL UI STYLING
st.set_page_config(page_title="PSX AI Analyzer by Tayyab", layout="wide")

# Sidebar - Theme Toggle
st.sidebar.header("🎨 Theme Settings")
theme_choice = st.sidebar.radio("Dashboard Mode", options=["Dark", "Light"], index=0)

# Define Colors based on Theme
if theme_choice == "Dark":
    chart_template = "plotly_dark"
    bg_color = "#0e1117"
    text_color = "#E0E0E0"
    card_bg = "#1e1e1e"
    card_text = "#ffffff"
    grid_color = "#2d2d2d"
    candle_up = "#26a69a"
    candle_down = "#ef5350"
else:
    chart_template = "plotly_white"
    bg_color = "#ffffff"
    text_color = "#121212"
    card_bg = "#f9f9f9"
    card_text = "#121212"
    grid_color = "#f0f0f0"
    candle_up = "#00c853"
    candle_down = "#ff5252"

# Apply Global CSS for Full Background and Typography
st.markdown(f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500&display=swap');
    
    /* Full Page Background */
    .stApp {{
        background-color: {bg_color} !important;
        color: {text_color} !important;
    }}
    
    html, body, [class*="css"] {{
        font-family: 'Inter', sans-serif;
    }}
    
    .stMetric {{
        background-color: {card_bg};
        padding: 20px;
        border-radius: 12px;
        border: 1px solid rgba(128, 128, 128, 0.2);
    }}
    
    h1, h2, h3, h4 {{
        color: {text_color} !important;
        font-weight: 700 !important;
        letter-spacing: -0.02em !important;
    }}
    
    p, li, span {{
        color: {text_color} !important;
        letter-spacing: 0.01em;
        line-height: 1.6;
    }}

    .stTable {{
        background-color: {card_bg};
    }}
    </style>
    """, unsafe_allow_html=True)

# 2. APP HEADER
st.title("📊 PSX AI Analyzer by Tayyab")

# Sidebar - Stock Inputs
st.sidebar.divider()
st.sidebar.header("📉 Stock Analysis")
symbol = st.sidebar.text_input("Enter Ticker (e.g. SYS, PSO, FFL)", value="SYS").upper()
timeframe = st.sidebar.selectbox("Timeframe", options=["1D", "1W", "1M"], index=0)

# Cached fetching
@st.cache_data(ttl=3600)
def fetch_historical_data(symbol, start_date):
    return get_psx_data(symbol, start_date=start_date)

@st.cache_data(ttl=30) # Rapid refresh for live price
def fetch_live_data(symbol):
    return get_live_price(symbol)

@st.cache_data(ttl=86400)
def fetch_company_info(symbol):
    return get_company_info(symbol)

if st.sidebar.button("Analyze Stock"):
    with st.spinner(f"Accessing Live Exchange Data for {symbol}..."):
        full_name = fetch_company_info(symbol)
        
        # Header with Logo
        h_col1, h_col2 = st.columns([1, 12])
        with h_col1:
            st.image("https://dps.psx.com.pk/static/images/logo.png", width=80)
        with h_col2:
            st.markdown(f"<h1 style='margin:0;'>{full_name}</h1>", unsafe_allow_html=True)
            st.markdown(f"<p style='color:gray !important; font-size: 1.1rem; margin-top:-5px;'>{symbol} | Live from PSX Data Portal</p>", unsafe_allow_html=True)

        # 1. LIVE DATA - CRITICAL SOURCE OF TRUTH
        # fetch_live_data returns the last point from timeseries/int/{symbol}
        # For PSO, this correctly returns 357.70
        live_json = fetch_live_data(symbol)
        
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
            
            # THE FIX: Priority 1 is Live Price, Fallback only if market closed/no data
            current_price = live_json['price'] if live_json else latest_hist['Close']
            
            if live_json:
                st.success(f"🟢 **Official PSX Current Price:** {current_price:.2f} | **Updated:** {live_json['timestamp'].strftime('%H:%M:%S')}")
            
            # Metrics Row
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Current Price", f"{current_price:.2f}")
            m2.metric("RSI (14)", f"{latest_hist['RSI']:.2f}")
            m3.metric("MACD", f"{latest_hist['MACD_12_26_9']:.2f}")
            m4.metric("ADX (14)", f"{latest_hist['ADX_14']:.2f}")

            # 4. TECHNICAL CHART
            from plotly.subplots import make_subplots
            fig = make_subplots(
                rows=4, cols=1, shared_xaxes=True, vertical_spacing=0.03, 
                subplot_titles=("Price Action", "Volume", "RSI (14)", "MACD (12, 26, 9)"),
                row_heights=[0.5, 0.1, 0.2, 0.2]
            )

            fig.add_trace(go.Candlestick(
                x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'],
                name="Price", increasing_line_color=candle_up, decreasing_line_color=candle_down
            ), row=1, col=1)

            ema_map = {'EMA_9': '#1e88e5', 'EMA_25': '#ffb300', 'EMA_44': '#8e24aa', 'EMA_100': '#fb8c00', 'EMA_200': '#f44336'}
            for ema_col, color in ema_map.items():
                fig.add_trace(go.Scatter(x=df.index, y=df[ema_col], mode='lines', name=ema_col.replace('_', ' '), line=dict(width=1.2, color=color)), row=1, col=1)

            fig.add_trace(go.Bar(x=df.index, y=df['Volume'], name="Volume", marker_color='#607d8b'), row=2, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['RSI'], name="RSI", line=dict(color='#3f51b5', width=2)), row=3, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['MACD_12_26_9'], name="MACD", line=dict(color='#2196f3')), row=4, col=1)

            fig.update_layout(height=1000, template=chart_template, xaxis_rangeslider_visible=False, margin=dict(l=10, r=10, t=60, b=10))
            st.plotly_chart(fig, use_container_width=True)

            # 5. MTT VIEW (AI REPORT)
            st.divider()
            st.subheader("🤖 MTT Technical View")
            ai_data_string = f"Co: {full_name}, P: {current_price}, RSI: {latest_hist['RSI']}, MACD: {latest_hist['MACD_12_26_9']}, EMAs: 9:{latest_hist['EMA_9']}, 100:{latest_hist['EMA_100']}, 200:{latest_hist['EMA_200']}"
            report = analyze_with_ai(symbol, timeframe, ai_data_string)
            st.markdown(f"<div style='background-color:{card_bg}; color:{card_text}; padding:25px; border-radius:12px; border: 1px solid rgba(128,128,128,0.2); font-size: 1.1rem;'>{report}</div>", unsafe_allow_html=True)

            # 6. BOTTOM TABLES
            st.divider()
            t_col1, t_col2 = st.columns(2)
            with t_col1:
                st.subheader("📍 Pivot Points")
                if pivots:
                    tab1, tab2 = st.tabs(["Traditional", "Fibonacci"])
                    with tab1:
                        st.table(pd.DataFrame({"Level": ["R3","R2","R1","P","S1","S2","S3"], "Price": [f"{pivots['traditional'][k]:.2f}" for k in ["R3","R2","R1","P","S1","S2","S3"]]}))
                    with tab2:
                        st.table(pd.DataFrame({"Level": ["R3","R2","R1","P","S1","S2","S3"], "Price": [f"{pivots['fibonacci'][k]:.2f}" for k in ["R3","R2","R1","P","S1","S2","S3"]]}))
            with t_col2:
                st.subheader("📈 Indicator Summary")
                ind_list = ["EMA_9", "EMA_25", "EMA_44", "EMA_88", "EMA_100", "EMA_200", "RSI", "MACD_12_26_9", "ADX_14", "Chaikin"]
                st.table(pd.DataFrame({
                    "Indicator": [i.replace('_', ' ') for i in ind_list],
                    "Value": [f"{latest_hist[i]:.2f}" if i != "Chaikin" else f"{latest_hist[i]:.2e}" for i in ind_list]
                }))
else:
    st.info("👈 Enter a ticker and click Analyze to begin.")
