import pandas as pd
import pandas_ta as ta
import yfinance as yf

def get_psx_data(symbol, period="1y", interval="1d"):
    """
    Fetches data for a PSX symbol using yfinance.
    Appends .KA to the symbol for PSX (Karachi).
    """
    ticker = f"{symbol}.KA"
    df = yf.download(ticker, period=period, interval=interval)
    return df

def calculate_indicators(df):
    """
    Calculates all user-specified indicators.
    """
    if df.empty:
        return df

    # RSI (14)
    df['RSI'] = ta.rsi(df['Close'], length=14)

    # MACD (12, 26, 9)
    macd = ta.macd(df['Close'], fast=12, slow=26, signal=9)
    df = pd.concat([df, macd], axis=1)

    # EMAs (9, 25, 44, 88, 100, 200)
    ema_lengths = [9, 25, 44, 88, 100, 200]
    for length in ema_lengths:
        df[f'EMA_{length}'] = ta.ema(df['Close'], length=length)

    # Chaikin Oscillator (3/10)
    # pandas-ta uses 'close', 'low', 'high', 'volume' for Chaikin
    df['Chaikin'] = ta.chosc(df['High'], df['Low'], df['Close'], df['Volume'], fast=3, slow=10)

    # DMI (14/14) - Returns ADX, +DI, -DI
    dmi = ta.adx(df['High'], df['Low'], df['Close'], length=14)
    df = pd.concat([df, dmi], axis=1)

    # SuperTrend (20, 2)
    st = ta.supertrend(df['High'], df['Low'], df['Close'], length=20, multiplier=2)
    df = pd.concat([df, st], axis=1)

    return df
