import os
import yfinance as yf
import pandas as pd

DXY_CACHE = "dxy_15m_60d.csv"

def get_dxy_data(period="60d", interval="15m", use_cache=True):
    if use_cache and os.path.exists(DXY_CACHE):
        df = pd.read_csv(DXY_CACHE, index_col=0, parse_dates=True)
    else:
        print("[DXY] Downloading Dollar Index (DX-Y.NYB) 15m data...", flush=True)
        df = yf.download("DX-Y.NYB", period=period, interval=interval, progress=False)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df = df.dropna()
        if use_cache:
            df.to_csv(DXY_CACHE)

    if df.index.tz is None:
        df.index = df.index.tz_localize('UTC')
    else:
        df.index = df.index.tz_convert('UTC')
    df = df.sort_index()

    # Calculate DXY Trend and EMAs
    df['DXY_EMA20'] = df['Close'].ewm(span=20, adjust=False).mean()
    df['DXY_EMA50'] = df['Close'].ewm(span=50, adjust=False).mean()
    df['DXY_Bullish'] = (df['Close'] > df['DXY_EMA50']) & (df['DXY_EMA20'] >= df['DXY_EMA50'])
    df['DXY_Bearish'] = (df['Close'] < df['DXY_EMA50']) & (df['DXY_EMA20'] <= df['DXY_EMA50'])
    return df

def get_live_dxy():
    """
    Fetch real-time DXY candles (5d) for live scanner.
    """
    try:
        return get_dxy_data(period="5d", interval="15m", use_cache=False)
    except Exception as e:
        print(f"[WARN] Live DXY download error: {e}, falling back to cache", flush=True)
        return get_dxy_data(period="60d", interval="15m", use_cache=True)

if __name__ == "__main__":
    df = get_dxy_data(use_cache=False)
    print(f"DXY cached: {len(df)} candles from {df.index[0]} to {df.index[-1]}")
