import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from indicators import get_psx_data, calculate_indicators, get_live_price, calculate_pivots
from ai_engine import analyze_with_ai
import datetime

# Page Configuration
st.set_page_config(page_title="PSX Sentinel AI", layout="wide")

st.title("📊 PSX Sentinel AI Stock Analyzer")
st.markdown("Professional-grade technical analysis for the Pakistan Stock Exchange.")

# Sidebar - User Inputs
st.sidebar.header("Stock Configuration")
symbol = st.sidebar.text_input("Enter Ticker (e.g., SYS, LUCK, ENGRO)", value="SYS").upper()
timeframe = st.sidebar.selectbox("Select Timeframe", options=["1D", "1W", "1M"], index=0)

# Map Streamlit timeframe to yfinance parameters
tf_map = {
    "1D": {"period": "1y", "interval": "1d"},
    "1W": {"period": "max", "interval": "1wk"},
    "1M": {"period": "max", "interval": "1mo"}
}

# Cached data fetching
@st.cache_data(ttl=3600) # Cache historical data for 1 hour
def fetch_historical_data(symbol, start_date):
    return get_psx_data(symbol, start_date=start_date)

@st.cache_data(ttl=60) # Cache live data for 1 minute
def fetch_live_data(symbol):
    return get_live_price(symbol)

if st.sidebar.button("Analyze Stock"):
    with st.spinner(f"Fetching data for {symbol}..."):
        # 1. Get Live Snapshot
        live_data = fetch_live_data(symbol)
        
        # 2. Get Historical Data (Last 1 year by default)
        start_date = datetime.datetime.now() - datetime.timedelta(days=365)
        df = fetch_historical_data(symbol, start_date)
        
        if df is None or df.empty:
            st.error(f"No data found for {symbol}. Please check the ticker name.")
        else:
            # --- SPLIT ADJUSTMENT FOR SYS (Manual Hack for Accuracy) ---
            if symbol == "SYS":
                split_date = pd.to_datetime("2025-06-02")
                mask = df.index < split_date
                for col in ['Open', 'High', 'Low', 'Close']:
                    df.loc[mask, col] = df.loc[mask, col] / 5

            # 3. Calculate Indicators
            df = calculate_indicators(df)
            latest_data = df.iloc[-1]
            pivots = calculate_pivots(df, lookback=2)
            
            # Display Live Badge
            if live_data:
                st.info(f"🟢 **Live Price:** {live_data['price']:.2f} | **Last Updated:** {live_data['timestamp'].strftime('%Y-%m-%d %H:%M:%S')}")
            
            # 4. Main Layout
            col_pivots, col_chart = st.columns([1, 4])
            
            with col_pivots:
                st.subheader("📍 Pivot Points")
                if pivots:
                    # Traditional
                    st.markdown("**Traditional**")
                    trad = pivots['traditional']
                    trad_df = pd.DataFrame({
                        "Level": ["R3", "R2", "R1", "Pivot", "S1", "S2", "S3"],
                        "Price": [f"{trad['R3']:.2f}", f"{trad['R2']:.2f}", f"{trad['R1']:.2f}", 
                                  f"{trad['P']:.2f}", f"{trad['S1']:.2f}", f"{trad['S2']:.2f}", f"{trad['S3']:.2f}"]
                    })
                    st.table(trad_df)
                    
                    # Fibonacci
                    st.markdown("**Fibonacci**")
                    fib = pivots['fibonacci']
                    fib_df = pd.DataFrame({
                        "Level": ["R3", "R2", "R1", "Pivot", "S1", "S2", "S3"],
                        "Price": [f"{fib['R3']:.2f}", f"{fib['R2']:.2f}", f"{fib['R1']:.2f}", 
                                  f"{fib['P']:.2f}", f"{fib['S1']:.2f}", f"{fib['S2']:.2f}", f"{fib['S3']:.2f}"]
                    })
                    st.table(fib_df)

            with col_chart:
                # 4a. Display Metrics
                m1, m2, m3, m4 = st.columns(4)
                current_price = live_data['price'] if live_data else latest_data['Close']
                m1.metric("Current Price", f"{current_price:.2f}")
                m2.metric("RSI (14)", f"{latest_data['RSI']:.2f}")
                m3.metric("MACD", f"{latest_data['MACD_12_26_9']:.2f}")
                m4.metric("ADX (14)", f"{latest_data['ADX_14']:.2f}")

                # 4b. Interactive Chart (Enhanced)
                from plotly.subplots import make_subplots
                
                # Create subplots: Price/EMAs, Volume, RSI, MACD
                fig = make_subplots(
                    rows=4, cols=1, 
                    shared_xaxes=True, 
                    vertical_spacing=0.03, 
                    subplot_titles=(f"{symbol} Price Action", "Volume", "RSI (14)", "MACD (12, 26, 9)"),
                    row_heights=[0.5, 0.1, 0.2, 0.2]
                )

                # Candlestick (Row 1)
                fig.add_trace(go.Candlestick(
                    x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'],
                    name="Price", increasing_line_color='#26a69a', decreasing_line_color='#ef5350'
                ), row=1, col=1)

                # EMAs (Row 1)
                ema_colors = {'EMA_9': '#1e88e5', 'EMA_25': '#ffb300', 'EMA_44': '#8e24aa', 'EMA_100': '#fb8c00', 'EMA_200': '#f44336'}
                for ema_col, color in ema_colors.items():
                    if ema_col in df.columns:
                        fig.add_trace(go.Scatter(x=df.index, y=df[ema_col], mode='lines', name=ema_col.replace('_', ' '), line=dict(width=1, color=color)), row=1, col=1)

                # SuperTrend (Row 1)
                if 'SUPERT_20_2' in df.columns:
                    fig.add_trace(go.Scatter(x=df.index, y=df['SUPERT_20_2'], mode='lines', name='SuperTrend', line=dict(dash='dash', color='#4caf50')), row=1, col=1)

                # Volume (Row 2)
                fig.add_trace(go.Bar(x=df.index, y=df['Volume'], name="Volume", marker_color='#455a64'), row=2, col=1)

                # RSI (Row 3)
                fig.add_trace(go.Scatter(x=df.index, y=df['RSI'], name="RSI", line=dict(color='#7986cb', width=1.5)), row=3, col=1)
                fig.add_hline(y=70, line_dash="dash", line_color="#ef5350", row=3, col=1)
                fig.add_hline(y=30, line_dash="dash", line_color="#4caf50", row=3, col=1)

                # MACD (Row 4)
                fig.add_trace(go.Scatter(x=df.index, y=df['MACD_12_26_9'], name="MACD", line=dict(color='#2196f3')), row=4, col=1)
                fig.add_trace(go.Scatter(x=df.index, y=df['MACDs_12_26_9'], name="Signal", line=dict(color='#ff9800')), row=4, col=1)
                fig.add_trace(go.Bar(x=df.index, y=df['MACDh_12_26_9'], name="Histogram", marker_color='#bdbdbd'), row=4, col=1)

                # Professional Layout Styling
                fig.update_layout(
                    height=900,
                    template="plotly_dark",
                    xaxis_rangeslider_visible=False,
                    showlegend=True,
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                    margin=dict(l=10, r=10, t=50, b=10)
                )
                
                # Update axes for a cleaner look
                fig.update_xaxes(showgrid=True, gridwidth=1, gridcolor='#2d2d2d')
                fig.update_yaxes(showgrid=True, gridwidth=1, gridcolor='#2d2d2d')

                st.plotly_chart(fig, use_container_width=True)

            # 5. MTT Technical View
            st.divider()
            st.subheader("🤖 MTT Technical View")
            
            # Prepare data for AI
            ai_data_string = f"""
            Price: {latest_data['Close']}
            RSI: {latest_data['RSI']}
            MACD: {latest_data['MACD_12_26_9']}
            EMAs: 9:{latest_data['EMA_9']}, 50:{latest_data['EMA_100']}, 200:{latest_data['EMA_200']}
            Chaikin: {latest_data['Chaikin']}
            DMI/ADX: {latest_data['ADX_14']}
            SuperTrend: {latest_data['SUPERT_20_2']}
            Pivots (Trad): P:{pivots['traditional']['P']}, R1:{pivots['traditional']['R1']}, S1:{pivots['traditional']['S1']}
            """
            
            report = analyze_with_ai(symbol, timeframe, ai_data_string)
            st.markdown(report)

            # 6. Indicators Table (Summary) - AT THE BOTTOM
            st.divider()
            st.subheader("📈 Indicator Summary Table")
            indicator_summary = {
                "Indicator": ["RSI (14)", "MACD (12,26,9)", "Chaikin Osc", "ADX (14)", "EMA 9", "EMA 25", "EMA 44", "EMA 100", "EMA 200", "SuperTrend"],
                "Value": [
                    f"{latest_data['RSI']:.2f}",
                    f"{latest_data['MACD_12_26_9']:.2f}",
                    f"{latest_data['Chaikin']:.2e}",
                    f"{latest_data['ADX_14']:.2f}",
                    f"{latest_data['EMA_9']:.2f}",
                    f"{latest_data['EMA_25']:.2f}",
                    f"{latest_data['EMA_44']:.2f}",
                    f"{latest_data['EMA_100']:.2f}",
                    f"{latest_data['EMA_200']:.2f}",
                    f"{latest_data['SUPERT_20_2']:.2f}"
                ],
                "Interpretation": [
                    "Overbought > 70, Oversold < 30",
                    "Trend Momentum",
                    "Buying/Selling Pressure",
                    "Trend Strength (>25 is strong)",
                    "Short-term support/resistance",
                    "Short-term trend",
                    "Medium-term trend",
                    "Medium-term trend",
                    "Long-term trend support",
                    "Volatility-based trend"
                ]
            }
            st.table(pd.DataFrame(indicator_summary))

else:
    st.info("Enter a stock symbol in the sidebar and click 'Analyze Stock' to begin.")
