import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from indicators import get_psx_data, calculate_indicators
from ai_engine import analyze_with_ai

# Page Configuration
st.set_page_config(page_title="PSX Sentinel AI", layout="wide")

st.title("📊 PSX Sentinel AI Stock Analyzer")
st.markdown("Professional-grade technical analysis for the Pakistan Stock Exchange.")

# Sidebar - User Inputs
st.sidebar.header("Stock Configuration")
symbol = st.sidebar.text_input("Enter Ticker (e.g., SYS, LUCK, ENGRO)", value="SYS").upper()
timeframe = st.sidebar.selectbox("Select Timeframe", options=["1H", "1D", "1W", "1M"], index=1)

# Map Streamlit timeframe to yfinance parameters
tf_map = {
    "1H": {"period": "1mo", "interval": "1h"},
    "1D": {"period": "1y", "interval": "1d"},
    "1W": {"period": "max", "interval": "1wk"},
    "1M": {"period": "max", "interval": "1mo"}
}

if st.sidebar.button("Analyze Stock"):
    with st.spinner(f"Fetching data for {symbol}..."):
        # 1. Get Data
        df = get_psx_data(symbol, period=tf_map[timeframe]["period"], interval=tf_map[timeframe]["interval"])
        
        if df is None or df.empty:
            st.error(f"No data found for {symbol}. Please check the ticker name.")
        else:
            # 2. Calculate Indicators
            df = calculate_indicators(df)
            latest_data = df.iloc[-1]
            
            # 3. Display Metrics
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Current Price", f"{latest_data['Close']:.2f}")
            col2.metric("RSI (14)", f"{latest_data['RSI']:.2f}")
            col3.metric("MACD", f"{latest_data['MACD_12_26_9']:.2f}")
            col4.metric("ADX (14)", f"{latest_data['ADX_14']:.2f}")

            # 4. Interactive Chart
            st.subheader(f"Price Action & Technicals ({timeframe})")
            fig = go.Figure()

            # Candlestick
            fig.add_trace(go.Candlestick(
                x=df.index,
                open=df['Open'],
                high=df['High'],
                low=df['Low'],
                close=df['Close'],
                name="Price"
            ))

            # EMAs
            for length in [9, 25, 44, 88, 100, 200]:
                fig.add_trace(go.Scatter(x=df.index, y=df[f'EMA_{length}'], mode='lines', name=f'EMA {length}', line=dict(width=1)))

            # SuperTrend
            fig.add_trace(go.Scatter(x=df.index, y=df['SUPERT_20_2.0'], mode='lines', name='SuperTrend', line=dict(dash='dash', color='orange')))

            fig.update_layout(height=600, template="plotly_dark", xaxis_rangeslider_visible=False)
            st.plotly_chart(fig, use_container_width=True)

            # 5. Indicators Table (Summary)
            st.subheader("Indicator Summary")
            indicator_summary = {
                "Indicator": ["RSI", "MACD", "Chaikin", "ADX", "EMA 200", "SuperTrend"],
                "Value": [
                    f"{latest_data['RSI']:.2f}",
                    f"{latest_data['MACD_12_26_9']:.2f}",
                    f"{latest_data['Chaikin']:.2e}",
                    f"{latest_data['ADX_14']:.2f}",
                    f"{latest_data['EMA_200']:.2f}",
                    f"{latest_data['SUPERT_20_2.0']:.2f}"
                ]
            }
            st.table(pd.DataFrame(indicator_summary))

            # 6. AI Analyst Section
            st.divider()
            st.subheader("🤖 AI Analyst Report")
            
            # Prepare data for AI
            ai_data_string = f"""
            Price: {latest_data['Close']}
            RSI: {latest_data['RSI']}
            MACD: {latest_data['MACD_12_26_9']}
            EMAs: 9:{latest_data['EMA_9']}, 50:{latest_data['EMA_100']}, 200:{latest_data['EMA_200']}
            Chaikin: {latest_data['Chaikin']}
            DMI/ADX: {latest_data['ADX_14']}
            SuperTrend: {latest_data['SUPERT_20_2.0']}
            """
            
            report = analyze_with_ai(symbol, timeframe, ai_data_string)
            st.markdown(report)

else:
    st.info("Enter a stock symbol in the sidebar and click 'Analyze Stock' to begin.")
