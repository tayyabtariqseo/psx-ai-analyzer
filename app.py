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
if 'data_is_live' not in st.session_state:
    st.session_state.data_is_live = False

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

# Apply Global CSS
st.markdown(f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500&display=swap');
    .stApp {{ background-color: {bg_color} !important; color: {text_color} !important; }}
    html, body, [class*="css"] {{ font-family: 'Inter', sans-serif; }}
    .stMetric {{ background-color: {card_bg}; padding: 20px; border-radius: 12px; border: 1px solid rgba(128, 128, 128, 0.2); }}
    h1, h2, h3, h4 {{ color: {text_color} !important; font-weight: 700 !important; }}
    p, li, span {{ color: {text_color} !important; line-height: 1.6; }}
    .stTable {{ background-color: {card_bg}; }}
    </style>
    """, unsafe_allow_html=True)

# 2. HELPER FUNCTIONS
def is_market_open():
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    now_pkt = now_utc.astimezone(datetime.timezone(datetime.timedelta(hours=5)))
    weekday = now_pkt.weekday()
    time_pkt = now_pkt.time()
    if weekday >= 5: return False
    if weekday == 4: return datetime.time(9, 0) <= time_pkt <= datetime.time(16, 30)
    else: return datetime.time(9, 15) <= time_pkt <= datetime.time(15, 30)

def parse_calls_file(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except FileNotFoundError: return []
    blocks = re.split(r'\n(?=📅|\d{1,2}-[A-Za-z]+-\d{2})', content.strip())
    calls = []
    for block in blocks:
        if not block.strip(): continue
        call = {}
        date_match = re.search(r'(?:📅\s*)?(\d{1,2}-[A-Za-z]+-\d{2})', block)
        call['date_str'] = date_match.group(1) if date_match else "N/A"
        try: call['date'] = pd.to_datetime(call['date_str'], dayfirst=True)
        except: call['date'] = datetime.datetime.now()
        symbol_match = re.search(r'📌\s*([A-Z]+)', block)
        call['symbol'] = symbol_match.group(1) if symbol_match else "N/A"
        ref_match = re.search(r'🔖\s*Ref:\s*(.*)', block)
        call['ref'] = ref_match.group(1).strip() if ref_match else "N/A"
        b1_match = re.search(r'(?:🛒|Buy1):\s*([\d.]+)', block)
        call['buy1'] = float(b1_match.group(1)) if b1_match else 0.0
        b2_match = re.search(r'(?:🛒|Buy2):\s*([\d.]+)', block)
        call['buy2'] = float(b2_match.group(1)) if b2_match else 0.0
        t_match = re.search(r'Target:\s*([\d.]+)\s*\(S\)', block)
        call['tp1'] = float(t_match.group(1)) if t_match else 0.0
        tm_match = re.search(r'([\d.]+)\s*\(M\)', block)
        call['tp2m'] = float(tm_match.group(1)) if tm_match else 0.0
        sl_match = re.search(r'Stoploss:\s*([\d.]+)', block)
        call['sl'] = float(sl_match.group(1)) if sl_match else 0.0
        if call['symbol'] != "N/A": calls.append(call)
    return calls

def get_call_history():
    if os.path.exists("call_history.json"):
        try:
            with open("call_history.json", "r") as f: return json.load(f)
        except: return {}
    return {}

def save_call_history(history):
    with open("call_history.json", "w") as f: json.dump(history, f, indent=4)

def get_price_cache():
    if os.path.exists("price_cache.json"):
        try:
            with open("price_cache.json", "r") as f: return json.load(f)
        except: return {}
    return {}

def save_price_cache(cache):
    with open("price_cache.json", "w") as f: json.dump(cache, f, indent=4)

def get_call_status(row):
    cp = row['current_price']
    if cp == 0: return "N/A", "Unknown"
    call_date = row['date']
    days_since_call = (datetime.datetime.now() - call_date).days
    tol = 0.05
    history = get_call_history()
    call_key = f"{row['symbol']}_{row['date_str']}"
    hit_type = ""
    if row['tp2m'] > 0 and cp >= row['tp2m']: hit_type = "TP2 Hit"
    elif row['tp1'] > 0 and cp >= row['tp1']: hit_type = "TP1 Hit"
    elif row['sl'] > 0 and cp <= row['sl']: hit_type = "SL Hit"
    if hit_type:
        close_date_str = history.get(call_key, datetime.date.today().strftime('%Y-%m-%d'))
        if call_key not in history:
            history[call_key] = close_date_str
            save_call_history(history)
        return hit_type, f"Call Closed ({close_date_str})"
    buy1, buy2, tp1, sl = row['buy1'], row['buy2'], row['tp1'], row['sl']
    is_in_buy_zone = False
    if buy1 > 0:
        lower_b = min(buy1, buy2) if buy2 > 0 else buy1 * 0.95
        upper_b = max(buy1, buy2) if buy2 > 0 else buy1 * 1.05
        if lower_b * (1-tol) <= cp <= upper_b * (1+tol): is_in_buy_zone = True
    if is_in_buy_zone:
        return "Buy Zone", "Again near to buy levels" if days_since_call > 30 else "Call open"
    if buy1 > 0:
        if tp1 > buy1:
            prog_tp = (cp - buy1) / (tp1 - buy1)
            if prog_tp >= 0.7: return "Bullish", "🚀 Almost at TP1"
            if prog_tp >= 0.3: return "Bullish", "📈 Going towards TP1"
            if cp > buy1: return "Bullish", "✅ Positive: Above Buy 1"
        if sl > 0 and sl < buy1:
            prog_sl = (buy1 - cp) / (buy1 - sl)
            if prog_sl >= 0.7: return "Bearish", "⚠️ Near Stoploss"
            if prog_sl >= 0.3: return "Bearish", "📉 Going towards SL"
            if cp < buy1: return "Bearish", "❌ Negative: Below Buy 1"
    return "Neutral", "In Progress"

# Cached fetching
@st.cache_data(ttl=3600)
def fetch_historical_data(symbol, start_date): return get_psx_data(symbol, start_date=start_date)
@st.cache_data(ttl=30)
def fetch_live_data(symbol): return get_live_price(symbol)
@st.cache_data(ttl=86400)
def fetch_company_info(symbol): return get_company_info(symbol)
@st.cache_data(ttl=600)
def get_ai_analysis_v3(symbol, timeframe, ai_data_string):
    cached = load_cached_analysis(symbol)
    if cached and cached.get('timeframe') == timeframe: return cached['report']
    report = analyze_with_ai_v2(symbol, timeframe, ai_data_string)
    if "Error" not in report: save_analysis(symbol, timeframe, ai_data_string, report)
    return report

def process_single_call(call, ctx=None):
    if ctx: add_script_run_context(ctx)
    live = fetch_live_data(call['symbol'])
    call['current_price'] = live['price'] if live else 0.0
    hit, status = get_call_status(call)
    call['tp_sl_hit'], call['status'] = hit, status
    return call

# 3. APP HEADER
st.title("📊 PSX-AI Analyzer by Tayyab")
st.sidebar.divider()
st.sidebar.header("📉 Stock Analysis")
symbol_input = st.sidebar.text_input("Enter Ticker", value="SYS").upper()
timeframe = st.sidebar.selectbox("Timeframe", options=["1D", "1W", "1M"], index=0)

col_b1, col_b2 = st.sidebar.columns(2)
with col_b1:
    if st.button("Analyze Stock", width="stretch"):
        st.session_state.view_mode = "Analysis"
        with st.spinner(f"Fetching {symbol_input}..."):
            m_status = is_market_open()
            f_name = fetch_company_info(symbol_input)
            l_json = fetch_live_data(symbol_input) if m_status else None
            df = fetch_historical_data(symbol_input, datetime.datetime.now() - datetime.timedelta(days=365))
            if df is not None and not df.empty:
                if symbol_input == "SYS":
                    mask = df.index < pd.to_datetime("2025-06-02")
                    for c in ['Open', 'High', 'Low', 'Close']: df.loc[mask, c] = df.loc[mask, c] / 5
                df = calculate_indicators(df)
                st.session_state.analysis_data = {
                    "symbol": symbol_input, "full_name": f_name, "live_json": l_json,
                    "market_status": m_status, "df": df, "latest_hist": df.iloc[-1],
                    "pivots": calculate_pivots(df, lookback=2), "current_price": l_json['price'] if l_json else df.iloc[-1]['Close'], "timeframe": timeframe
                }
                st.session_state.show_report = False
            else: st.error("No data found.")
with col_b2:
    if st.button("Calls", width="stretch"):
        st.session_state.view_mode = "Calls"
        st.session_state.processed_calls = None
        st.session_state.data_is_live = False

if st.sidebar.button("AI Report", width="stretch"):
    if st.session_state.analysis_data:
        st.session_state.show_report = True
        st.session_state.view_mode = "Analysis"
    else: st.sidebar.warning("Analyze Stock first!")

# 4. MAIN DISPLAY LOGIC
if st.session_state.view_mode == "Analysis" and st.session_state.analysis_data:
    data = st.session_state.analysis_data
    st.markdown(f"<h1>{data['full_name']} ({data['symbol']})</h1>", unsafe_allow_html=True)
    if data['market_status']: st.success(f"🟢 Live: {data['current_price']:.2f}")
    else: st.warning(f"🟡 Mkt Closed: {data['current_price']:.2f}")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Price", f"{data['current_price']:.2f}")
    m2.metric("RSI", f"{data['latest_hist']['RSI']:.2f}")
    m3.metric("MACD", f"{data['latest_hist']['MACD_12_26_9']:.2f}")
    m4.metric("ADX", f"{data['latest_hist']['ADX_14']:.2f}")

    fig = go.Figure(data=[go.Candlestick(x=data['df'].index, open=data['df']['Open'], high=data['df']['High'], low=data['df']['Low'], close=data['df']['Close'])])
    fig.update_layout(height=600, template=chart_template, xaxis_rangeslider_visible=False)
    st.plotly_chart(fig, use_container_width=True)

    if st.session_state.show_report:
        with st.spinner("AI analyzing..."):
            l = data['latest_hist']
            s = f"Co: {data['full_name']}, P: {data['current_price']}, RSI: {l['RSI']}, MACD: {l['MACD_12_26_9']}, EMAs: 9:{l['EMA_9']}, 100:{l['EMA_100']}, 200:{l['EMA_200']}"
            r = get_ai_analysis_v3(data['symbol'], data['timeframe'], s)
            st.markdown(f"<div style='background-color:{card_bg}; padding:20px; border-radius:10px;'>{r}</div>", unsafe_allow_html=True)

elif st.session_state.view_mode == "Calls":
    if not st.session_state.get('view_pin_verified', False):
        p = st.text_input("Enter View PIN", type="password")
        if st.button("Verify"):
            if p == "1234": st.session_state.view_pin_verified = True; st.rerun()
            else: st.error("Invalid")
        st.stop()

    tab1, tab2 = st.tabs(["🎯 Live Calls", "📝 Edit Calls"])
    with tab2:
        if not st.session_state.get('edit_pin_verified', False):
            p = st.text_input("Enter Edit PIN", type="password")
            if st.button("Admin Verify"):
                if p == "5678": st.session_state.edit_pin_verified = True; st.rerun()
        else:
            with open("calls.txt", "r", encoding="utf-8") as f: content = f.read()
            nc = st.text_area("Update calls.txt", value=content, height=300)
            if st.button("Save"):
                with open("calls.txt", "w", encoding="utf-8") as f: f.write(nc)
                st.session_state.processed_calls = None; st.success("Saved!"); st.rerun()

    with tab1:
        if st.session_state.processed_calls is None:
            cache = get_price_cache()
            raw = parse_calls_file("calls.txt")
            for c in raw:
                px = cache.get(c['symbol'], {'price': 0.0})['price']
                c['current_price'] = px
                c['tp_sl_hit'], c['status'] = get_call_status(c)
            st.session_state.processed_calls = raw
        
        all_c = st.session_state.processed_calls
        open_c = [c for c in all_c if "Closed" not in c['status']]
        closed_c = [c for c in all_c if "Closed" in c['status']]

        # --- METRICS SECTION ---
        st.subheader("📈 Fund Performance Summary")
        if not st.session_state.data_is_live:
            st.info("⚡ *Showing cached prices. Updating live in background...*")
        
        m1, m2, m3, m4 = st.columns(4)
        now = datetime.datetime.now()
        monthly_issued = sum(1 for c in all_c if c['date'].month == now.month and c['date'].year == now.year)
        m1.metric("Total Monthly Signals", monthly_issued)
        m2.metric("Total Active Signals", len(all_c))
        m3.metric("Currently Open", len(open_c))
        m4.metric("Recently Closed", len(closed_c))
        st.divider()

        def render_table(data_list, title):
            if not data_list:
                st.info(f"No {title.lower()} at this time.")
                return
            st.subheader(title)
            df = pd.DataFrame(data_list)
            # Formatting
            cols = ['date_str', 'symbol', 'ref', 'buy1', 'buy2', 'tp1', 'tp2m', 'sl', 'current_price', 'status']
            df_disp = df[cols].copy()
            df_disp.columns = ["Date", "Symbol", "Ref", "Buy1", "Buy2", "Target S", "Target M", "SL", "CMP", "Status"]
            
            # 2 Decimal Formatting
            price_cols = ["Buy1", "Buy2", "Target S", "Target M", "SL", "CMP"]
            format_dict = {col: "{:.2f}" for col in price_cols}
            
            def style_status(val):
                v = str(val).lower()
                if 'closed' in v: return 'background-color: #ef5350; color: white'
                if 'call open' in v: return 'background-color: #26a69a; color: white'
                if 'zone' in v: return 'background-color: #ffb300; color: black'
                if 'towards tp1' in v: return 'background-color: #ffff00; color: black'
                if 'almost' in v: return 'background-color: #00ff00; color: black'
                return ''

            st.table(df_disp.style.format(format_dict).map(style_status, subset=['Status']))

        render_table(open_c, "🎯 Open Trading Calls")
        st.divider()
        render_table(closed_c, "🏁 All Closed Calls")
        
        if not st.session_state.data_is_live:
            with st.spinner("Refreshing prices..."):
                ctx = get_script_run_context()
                with ThreadPoolExecutor(max_workers=10) as ex:
                    res = list(ex.map(lambda c: process_single_call(c, ctx), parse_calls_file("calls.txt")))
                cache = get_price_cache()
                for r in res:
                    if r['current_price'] > 0: cache[r['symbol']] = {'price': r['current_price']}
                save_price_cache(cache)
                st.session_state.processed_calls = res
                st.session_state.data_is_live = True
                st.rerun()
