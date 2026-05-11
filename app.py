from concurrent.futures import ThreadPoolExecutor
from streamlit.runtime.scriptrunner import get_script_run_ctx as get_script_run_context, add_script_run_ctx as add_script_run_context
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from indicators import get_psx_data, calculate_indicators, get_live_price, calculate_pivots, get_company_info
from ai_engine import analyze_with_ai_v2
from persistence import load_cached_analysis, save_analysis
import datetime
import re
import os
import json

# 1. THEME & GLOBAL UI STYLING
st.set_page_config(page_title="PSX-AI Analyzer by Tayyab", layout="wide")

# Initialize Session State
if 'analysis_data' not in st.session_state:
    st.session_state.analysis_data = None
if 'show_report' not in st.session_state:
    st.session_state.show_report = False
if 'view_mode' not in st.session_state:
    st.session_state.view_mode = "Analysis" # "Analysis" or "Calls"
if 'processed_calls' not in st.session_state:
    st.session_state.processed_calls = None
if 'ai_portfolio_report' not in st.session_state:
    st.session_state.ai_portfolio_report = None

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

# 2. HELPER FUNCTIONS
def is_market_open():
    """Checks if the Pakistan Stock Exchange is currently open (UTC+5)."""
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    now_pkt = now_utc.astimezone(datetime.timezone(datetime.timedelta(hours=5)))
    weekday = now_pkt.weekday() # 0=Mon, 4=Fri, 5=Sat, 6=Sun
    time_pkt = now_pkt.time()
    
    if weekday >= 5: # Weekend
        return False
    if weekday == 4: # Friday: 9:00 AM - 4:30 PM
        return datetime.time(9, 0) <= time_pkt <= datetime.time(16, 30)
    else: # Mon-Thu: 9:15 AM - 3:30 PM
        return datetime.time(9, 15) <= time_pkt <= datetime.time(15, 30)

def parse_calls_file(file_path):
    """Parses trade signals from the text file."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except FileNotFoundError:
        return []
    
    # Split by double newline or date markers
    blocks = re.split(r'\n(?=📅|\d{1,2}-[A-Za-z]+-\d{2})', content.strip())
    calls = []
    
    for block in blocks:
        if not block.strip(): continue
        
        call = {}
        # Date
        date_match = re.search(r'(?:📅\s*)?(\d{1,2}-[A-Za-z]+-\d{2})', block)
        call['date_str'] = date_match.group(1) if date_match else "N/A"
        try:
            call['date'] = pd.to_datetime(call['date_str'], dayfirst=True)
        except:
            call['date'] = datetime.datetime.now()
        
        # Symbol
        symbol_match = re.search(r'📌\s*([A-Z]+)', block)
        call['symbol'] = symbol_match.group(1) if symbol_match else "N/A"

        # Ref
        ref_match = re.search(r'🔖\s*Ref:\s*(.*)', block)
        call['ref'] = ref_match.group(1).strip() if ref_match else "N/A"
        
        # Buy1
        b1_match = re.search(r'Buy1:\s*([\d.]+)', block)
        call['buy1'] = float(b1_match.group(1)) if b1_match else 0.0
        
        # Buy2
        b2_match = re.search(r'Buy2:\s*([\d.]+)', block)
        call['buy2'] = float(b2_match.group(1)) if b2_match else 0.0
        
        # Targets
        t_match = re.search(r'Target:\s*([\d.]+)\s*\(S\)', block)
        call['tp1'] = float(t_match.group(1)) if t_match else 0.0
        
        tm_match = re.search(r'([\d.]+)\s*\(M\)', block)
        call['tp2m'] = float(tm_match.group(1)) if tm_match else 0.0
        
        call['target_l'] = "" # Placeholder
        
        # Stoploss
        sl_match = re.search(r'Stoploss:\s*([\d.]+)', block)
        call['sl'] = float(sl_match.group(1)) if sl_match else 0.0
        
        if call['symbol'] != "N/A":
            calls.append(call)
            
    return calls

def get_call_history():
    """Loads closure dates for calls to maintain the 15-day visibility rule."""
    if os.path.exists("call_history.json"):
        try:
            with open("call_history.json", "r") as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_call_history(history):
    """Persists closure dates to a JSON file."""
    try:
        with open("call_history.json", "w") as f:
            json.dump(history, f, indent=4)
    except Exception as e:
        print(f"Error saving call history: {e}")

def get_call_status(row):
    """Calculates status and hits with persistent closure tracking for the 15-day rule."""
    cp = row['current_price']
    if cp == 0: return "N/A", "Unknown"
    
    call_date = row['date']
    days_since_call = (datetime.datetime.now() - call_date).days
    tol = 0.05
    history = get_call_history()
    call_key = f"{row['symbol']}_{row['date_str']}"

    # 1. Check Targets (Highest to lowest)
    hit_type = ""
    if row['tp2m'] > 0 and cp >= row['tp2m']:
        hit_type = "TP2 Hit"
    elif row['tp1'] > 0 and cp >= row['tp1']:
        hit_type = "TP1 Hit"
    elif row['sl'] > 0 and cp <= row['sl']:
        hit_type = "SL Hit"

    if hit_type:
        # Check if we already have a closure date for this specific call
        if call_key in history:
            close_date_str = history[call_key]
        else:
            close_date_str = datetime.date.today().strftime('%Y-%m-%d')
            history[call_key] = close_date_str
            save_call_history(history)
            
        return hit_type, f"Call Closed ({close_date_str})"

    # 3. Check Buy Zones (with 5% tolerance)
    is_near_buy = False
    if abs(cp - row['buy1']) / row['buy1'] <= tol or (row['buy2'] > 0 and abs(cp - row['buy2']) / row['buy2'] <= tol):
        is_near_buy = True

    if is_near_buy:
        if days_since_call > 30:
            return "Buy Zone", "Again near to buy levels"
        else:
            return "Buy Zone", "Call open"
        
    return "Neutral", "In Progress"

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

@st.cache_data(ttl=600)
def get_ai_analysis_v3(symbol, timeframe, ai_data_string):
    cached_data = load_cached_analysis(symbol)
    if cached_data and cached_data.get('timeframe') == timeframe:
        return cached_data['report']
    report = analyze_with_ai_v2(symbol, timeframe, ai_data_string)
    if "Error" not in report and "Analysis is currently" not in report:
        save_analysis(symbol, timeframe, ai_data_string, report)
    return report

def process_single_call(call, ctx=None):
    """Fetches live data and calculates status for a single call (for parallel use)."""
    if ctx: add_script_run_context(ctx)
    live = fetch_live_data(call['symbol'])
    call['current_price'] = live['price'] if live else 0.0
    hit, status = get_call_status(call)
    call['tp_sl_hit'] = hit
    call['status'] = status
    return call

# 3. APP HEADER
st.title("📊 PSX-AI Analyzer by Tayyab")

# Sidebar - Stock Inputs
st.sidebar.divider()
st.sidebar.header("📉 Stock Analysis")
symbol = st.sidebar.text_input("Enter Ticker (e.g. SYS, PSO, FFL)", value="SYS").upper()
timeframe = st.sidebar.selectbox("Timeframe", options=["1D", "1W", "1M"], index=0)

# Sidebar Buttons
col_b1, col_b2 = st.sidebar.columns(2)
with col_b1:
    if st.button("Analyze Stock", width="stretch"):
        st.session_state.view_mode = "Analysis"
        with st.spinner(f"Accessing Live Exchange Data for {symbol}..."):
            market_status = is_market_open()
            full_name = fetch_company_info(symbol)
            live_json = fetch_live_data(symbol) if market_status else None
            start_date = datetime.datetime.now() - datetime.timedelta(days=365)
            df = fetch_historical_data(symbol, start_date)
            if df is not None and not df.empty:
                if symbol == "SYS":
                    split_date = pd.to_datetime("2025-06-02")
                    mask = df.index < split_date
                    for col in ['Open', 'High', 'Low', 'Close']:
                        df.loc[mask, col] = df.loc[mask, col] / 5
                df = calculate_indicators(df)
                latest_hist = df.iloc[-1]
                pivots = calculate_pivots(df, lookback=2)
                current_price = live_json['price'] if live_json else latest_hist['Close']
                st.session_state.analysis_data = {
                    "symbol": symbol, "full_name": full_name, "live_json": live_json,
                    "market_status": market_status, "df": df, "latest_hist": latest_hist,
                    "pivots": pivots, "current_price": current_price, "timeframe": timeframe
                }
                st.session_state.show_report = False
            else:
                st.error(f"No data found for {symbol}.")

with col_b2:
    if st.button("Calls", width="stretch"):
        st.session_state.view_mode = "Calls"
        st.session_state.processed_calls = None # Force refresh on explicit click

if st.sidebar.button("AI Report", width="stretch"):
    if st.session_state.analysis_data:
        st.session_state.show_report = True
        st.session_state.view_mode = "Analysis"
    else:
        st.sidebar.warning("Please Analyze Stock first!")

# 4. MAIN DISPLAY LOGIC
if st.session_state.view_mode == "Analysis" and st.session_state.analysis_data:
    data = st.session_state.analysis_data
    h_col1, h_col2 = st.columns([1, 12])
    with h_col1:
        st.image("https://dps.psx.com.pk/static/images/logo.png", width=80)
    with h_col2:
        st.markdown(f"<h1 style='margin:0;'>{data['full_name']}</h1>", unsafe_allow_html=True)
        st.markdown(f"<p style='color:gray !important; font-size: 1.1rem; margin-top:-5px;'>{data['symbol']} | Live from PSX Data Portal</p>", unsafe_allow_html=True)

    # Market Status Banner
    market_open = data.get('market_status', False)
    if market_open:
        st.success(f"🟢 **Official PSX Current Price:** {data['current_price']:.2f} | **Updated:** {data['live_json']['timestamp'].strftime('%H:%M:%S')}")
    else:
        st.warning(f"🟡 **Mkt is Close** | **Last Closing:** {data['current_price']:.2f}")
    
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Current Price", f"{data['current_price']:.2f}")
    m2.metric("RSI (14)", f"{data['latest_hist']['RSI']:.2f}")
    m3.metric("MACD", f"{data['latest_hist']['MACD_12_26_9']:.2f}")
    m4.metric("ADX (14)", f"{data['latest_hist']['ADX_14']:.2f}")

    # Chart logic
    from plotly.subplots import make_subplots
    fig = make_subplots(rows=4, cols=1, shared_xaxes=True, vertical_spacing=0.03, subplot_titles=("Price Action", "Volume", "RSI (14)", "MACD (12, 26, 9)"), row_heights=[0.5, 0.1, 0.2, 0.2])
    df = data['df']
    fig.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name="Price", increasing_line_color=candle_up, decreasing_line_color=candle_down), row=1, col=1)
    ema_map = {'EMA_9': '#1e88e5', 'EMA_25': '#ffb300', 'EMA_44': '#8e24aa', 'EMA_100': '#fb8c00', 'EMA_200': '#f44336'}
    for ema_col, color in ema_map.items():
        fig.add_trace(go.Scatter(x=df.index, y=df[ema_col], mode='lines', name=ema_col.replace('_', ' '), line=dict(width=1.2, color=color)), row=1, col=1)
    if 'SUPERT_20_2' in df.columns:
        fig.add_trace(go.Scatter(x=df.index, y=df['SUPERT_20_2'], mode='lines', name='SuperTrend', line=dict(dash='dash', color='#4caf50', width=1.5)), row=1, col=1)
    fig.add_trace(go.Bar(x=df.index, y=df['Volume'], name="Volume", marker_color='#607d8b'), row=2, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['RSI'], name="RSI", line=dict(color='#3f51b5', width=2)), row=3, col=1)
    fig.add_hline(y=70, line_dash="dash", line_color="#f44336", row=3, col=1)
    fig.add_hline(y=30, line_dash="dash", line_color="#4caf50", row=3, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['MACD_12_26_9'], name="MACD", line=dict(color='#2196f3')), row=4, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['MACDs_12_26_9'], name="Signal", line=dict(color='#ff9800')), row=4, col=1)
    fig.add_trace(go.Bar(x=df.index, y=df['MACDh_12_26_9'], name="Histogram", marker_color='#9e9e9e'), row=4, col=1)
    fig.update_layout(height=1100, template=chart_template, xaxis_rangeslider_visible=False, margin=dict(l=10, r=10, t=60, b=10), legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
    fig.update_xaxes(gridcolor=grid_color, zeroline=False)
    fig.update_yaxes(gridcolor=grid_color, zeroline=False)
    st.plotly_chart(fig, width="stretch")

    if st.session_state.show_report:
        st.divider()
        st.subheader("🤖 Gemini AI Technical Report")
        with st.spinner("Generating Professional AI Report..."):
            latest_hist = data['latest_hist']
            ai_data_string = f"Co: {data['full_name']}, P: {data['current_price']}, RSI: {latest_hist['RSI']}, MACD: {latest_hist['MACD_12_26_9']}, EMAs: 9:{latest_hist['EMA_9']}, 100:{latest_hist['EMA_100']}, 200:{latest_hist['EMA_200']}"
            report = get_ai_analysis_v3(data['symbol'], data['timeframe'], ai_data_string)
            st.markdown(f"<div style='background-color:{card_bg}; color:{card_text}; padding:25px; border-radius:12px; border: 1px solid rgba(128,128,128,0.2); font-size: 1.1rem; box-shadow: 0 4px 6px rgba(0,0,0,0.1);'>{report}</div>", unsafe_allow_html=True)

    st.divider()
    t_col1, t_col2 = st.columns(2)
    with t_col1:
        st.subheader("📍 Pivot Points")
        pivots = data['pivots']
        if pivots:
            tab1, tab2 = st.tabs(["Traditional", "Fibonacci"])
            with tab1: st.table(pd.DataFrame({"Level": ["R3","R2","R1","P","S1","S2","S3"], "Price": [f"{pivots['traditional'][k]:.2f}" for k in ["R3","R2","R1","P","S1","S2","S3"]]}))
            with tab2: st.table(pd.DataFrame({"Level": ["R3","R2","R1","P","S1","S2","S3"], "Price": [f"{pivots['fibonacci'][k]:.2f}" for k in ["R3","R2","R1","P","S1","S2","S3"]]}))
    with t_col2:
        st.subheader("📈 Indicator Summary")
        latest_hist = data['latest_hist']
        ind_list = ["EMA_9", "EMA_25", "EMA_44", "EMA_88", "EMA_100", "EMA_200", "RSI", "MACD_12_26_9", "ADX_14", "Chaikin"]
        st.table(pd.DataFrame({"Indicator": [i.replace('_', ' ') for i in ind_list], "Value": [f"{latest_hist[i]:.2f}" if i != "Chaikin" else f"{latest_hist[i]:.2e}" for i in ind_list]}))

elif st.session_state.view_mode == "Calls":
    # 1. PIN PROTECTION FOR VIEWING
    if 'view_pin_verified' not in st.session_state:
        st.session_state.view_pin_verified = False
    
    if not st.session_state.view_pin_verified:
        st.subheader("🔒 Secure Access Required")
        view_pin = st.text_input("Enter View PIN", type="password")
        if st.button("Verify View PIN"):
            if view_pin == "1234":
                st.session_state.view_pin_verified = True
                st.rerun()
            else:
                st.error("Invalid View PIN")
        st.stop()

    tab_calls, tab_editor = st.tabs(["🎯 Live Calls", "📝 Edit Calls"])
    
    with tab_editor:
        # 2. PIN PROTECTION FOR EDITING
        if 'edit_pin_verified' not in st.session_state:
            st.session_state.edit_pin_verified = False
        
        if not st.session_state.edit_pin_verified:
            st.subheader("🔐 Admin Access Required")
            admin_pin = st.text_input("Enter Edit PIN", type="password")
            if st.button("Verify Edit PIN"):
                if admin_pin == "5678":
                    st.session_state.edit_pin_verified = True
                    st.rerun()
                else:
                    st.error("Invalid Edit PIN")
        else:
            try:
                with open("calls.txt", "r", encoding="utf-8") as f:
                    calls_content = f.read()
            except FileNotFoundError:
                calls_content = ""
            new_content = st.text_area("Update calls.txt content", value=calls_content, height=400)
            col_save, col_lock = st.columns([1, 4])
            with col_save:
                if st.button("Save Changes"):
                    with open("calls.txt", "w", encoding="utf-8") as f:
                        f.write(new_content)
                    st.session_state.processed_calls = None
                    st.success("calls.txt updated!")
                    st.rerun()
            with col_lock:
                if st.button("Lock Editor"):
                    st.session_state.edit_pin_verified = False
                    st.rerun()

    with tab_calls:
        # Performance optimization: Fetch all prices in parallel
        if st.session_state.processed_calls is None:
            with st.spinner("Fetching Live Prices and Filtering..."):
                raw_calls = parse_calls_file("calls.txt")
                ctx = get_script_run_context()
                with ThreadPoolExecutor(max_workers=10) as executor:
                    all_processed = list(executor.map(lambda c: process_single_call(c, ctx), raw_calls))
                st.session_state.processed_calls = all_processed
        else:
            all_processed = st.session_state.processed_calls

        if all_processed:
            current_time = datetime.datetime.now()
            history = get_call_history()
            
            # --- FILTERING & LOGIC ---
            open_calls_list = []
            closed_calls_list = []
            
            for c in all_processed:
                is_closed = "Closed" in c['status']
                if is_closed:
                    # Check 15-day rule from history
                    call_key = f"{c['symbol']}_{c['date_str']}"
                    close_date_str = history.get(call_key)
                    if close_date_str:
                        close_dt = pd.to_datetime(close_date_str)
                        days_since_close = (current_time - close_dt).days
                        if days_since_close <= 15:
                            closed_calls_list.append(c)
                        else:
                            # Move to archive? For now just don't show.
                            pass
                    else:
                        # Fallback if history missing
                        closed_calls_list.append(c)
                else:
                    open_calls_list.append(c)

            # --- METRICS SECTION ---
            st.subheader("📈 Fund Performance Summary")
            m1, m2, m3, m4 = st.columns(4)
            monthly_issued = sum(1 for c in all_processed if c['date'].month == current_time.month and c['date'].year == current_time.year)
            m1.metric("Total Monthly Signals", monthly_issued)
            m2.metric("Total Active Signals", len(all_processed))
            m3.metric("Currently Open", len(open_calls_list))
            m4.metric("Recently Closed", len(closed_calls_list))
            
            # --- TABLES SECTION ---
            def render_call_table(data_list, title):
                if not data_list:
                    st.info(f"No {title.lower()} at this time.")
                    return
                st.markdown(f"#### {title}")
                df = pd.DataFrame(data_list).sort_values(by="date", ascending=False)
                df.reset_index(drop=True, inplace=True)
                df.index += 1
                df.insert(0, "S.No", df.index)
                
                col_order = ['S.No', 'date_str', 'symbol', 'ref', 'buy1', 'buy2', 'tp1', 'tp2m', 'sl', 'current_price', 'tp_sl_hit', 'status']
                df_disp = df[col_order].copy()
                df_disp.columns = ["S.No", "Date", "Symbol", "Ref", "Buy1", "Buy2", "Target S", "Target M", "SL", "Current Price", "TP/SL Hit", "Status"]
                
                price_cols = ["Buy1", "Buy2", "Target S", "Target M", "SL", "Current Price"]
                format_dict = {col: "{:.2f}" for col in price_cols}
                
                def style_status(val):
                    if 'Closed' in val: return 'background-color: #ef5350; color: white'
                    if 'Call open' in val: return 'background-color: #26a69a; color: white'
                    if 'Again' in val: return 'background-color: #ffb300; color: black'
                    return ''

                st.table(df_disp.style.format(format_dict).map(style_status, subset=['Status']))

            st.divider()
            render_call_table(open_calls_list, "🎯 Open Trading Calls")
            st.divider()
            render_call_table(closed_calls_list, "🏁 Recently Closed Calls")

            # --- AI ANALYSIS SECTION (SECOND PIN REQUIRED) ---
            if st.session_state.edit_pin_verified:
                st.divider()
                st.subheader("🤖 Fund Manager AI Deep Dive")
                if not open_calls_list:
                    st.info("No open calls for AI analysis.")
                elif st.session_state.ai_portfolio_report:
                    st.markdown(f"<div style='background-color:{card_bg}; color:{card_text}; padding:25px; border-radius:12px; border: 1px solid rgba(128,128,128,0.2);'>{st.session_state.ai_portfolio_report}</div>", unsafe_allow_html=True)
                    if st.button("Refresh AI Insights"):
                        st.session_state.ai_portfolio_report = None
                        st.rerun()
                else:
                    if st.button("Execute AI Portfolio Review"):
                        with st.spinner("Analyzing Market Structure for all Open Positions..."):
                            def f_s(v):
                                try: return f"{float(v):.2f}"
                                except: return "N/A"
                            
                            def get_ai_data(row, ctx_in):
                                add_script_run_context(ctx_in)
                                sym = row['symbol']
                                hist = fetch_historical_data(sym, datetime.datetime.now() - datetime.timedelta(days=60))
                                if hist is not None and not hist.empty:
                                    l = calculate_indicators(hist).iloc[-1]
                                    return f"Sym: {sym}, Price: {f_s(row['current_price'])}, RSI: {f_s(l['RSI'])}, MACD: {f_s(l['MACD_12_26_9'])}, ADX: {f_s(l['ADX_14'])}"
                                return None

                            ctx_p = get_script_run_context()
                            with ThreadPoolExecutor(max_workers=5) as ex:
                                prompts = [p for p in list(ex.map(lambda r: get_ai_data(r, ctx_p), open_calls_list)) if p]
                            
                            if prompts:
                                report = analyze_with_ai_v2("Portfolio", "1D", "\n".join(prompts))
                                st.session_state.ai_portfolio_report = report
                                st.rerun()
            else:
                st.info("💡 *AI Technical Deep Dive is locked. Enter Admin PIN in the 'Manage Signals' tab to unlock.*")
        else:
            st.warning("No signal data found.")

    if st.button("Terminal Logout"):
        st.session_state.view_pin_verified = False
        st.session_state.edit_pin_verified = False
        st.rerun()

else:
    st.info("👈 Enter a ticker and click Analyze to begin, or view active Calls.")
