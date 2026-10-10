"""
Market Data Feed Provider for XAUUSD (Gold) & DXY (Dollar Index)
Supports multi-timeframe aggregation (Daily, H1, M15) and DXY inverse correlation.
"""
import os
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timezone
import config
from dxy_feed import get_dxy_data

CACHE_FILE = "xauusd_5m_cache.csv"

def fetch_gold_data(period="60d", interval="5m", use_cache=True) -> pd.DataFrame:
    """
    Download or load cached OHLCV data for Gold.
    """
    if use_cache and os.path.exists(CACHE_FILE):
        df = pd.read_csv(CACHE_FILE, index_col=0, parse_dates=True)
    else:
        df = yf.download(config.SYMBOL, period=period, interval=interval, progress=False)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df = df.dropna()
        if use_cache:
            df.to_csv(CACHE_FILE)

    if df.index.tz is None:
        df.index = df.index.tz_localize('UTC')
    else:
        df.index = df.index.tz_convert('UTC')

    df = df.sort_index()
    return df

def fetch_latest_live_candles(count=200) -> pd.DataFrame:
    """
    Fetch the most recent live candles for scanner execution.
    """
    df = yf.download(config.SYMBOL, period="5d", interval="5m", progress=False)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.dropna()
    if df.index.tz is None:
        df.index = df.index.tz_localize('UTC')
    else:
        df.index = df.index.tz_convert('UTC')
    return df.tail(count).sort_index()

def prepare_multi_timeframe_data(df_5m: pd.DataFrame, include_dxy=True):
    """
    Transform 5M raw data into:
    - Daily Macro Trend (Pilar 2)
    - 1-Hour Trend Context (Pilar 2)
    - 15-Minute Base Execution Data with FVG zones
    - DXY Dollar Index Inverse Alignment (Pilar 3)
    """
    # 1. Daily (D1) Macro Trend Context (Pilar 2)
    df_1d = df_5m.resample('1D').agg({
        'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last', 'Volume': 'sum'
    }).dropna()
    df_1d['Daily_EMA20'] = df_1d['Close'].ewm(span=20, adjust=False).mean()
    df_1d['Daily_EMA50'] = df_1d['Close'].ewm(span=50, adjust=False).mean()
    df_1d['Daily_Trend'] = np.where(
        (df_1d['Close'] >= df_1d['Daily_EMA50']) | (df_1d['Daily_EMA20'] >= df_1d['Daily_EMA50']), 1,
        np.where((df_1d['Close'] <= df_1d['Daily_EMA50']) | (df_1d['Daily_EMA20'] <= df_1d['Daily_EMA50']), -1, 0)
    )

    # 2. 1-Hour (H1) Trend Context (Pilar 2)
    df_1h = df_5m.resample('1h').agg({
        'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last', 'Volume': 'sum'
    }).dropna()
    df_1h['H1_EMA20'] = df_1h['Close'].ewm(span=20, adjust=False).mean()
    df_1h['H1_EMA50'] = df_1h['Close'].ewm(span=50, adjust=False).mean()
    df_1h['H1_EMA200'] = df_1h['Close'].ewm(span=200, adjust=False).mean()
    df_1h['H1_Trend'] = np.where(
        (df_1h['Close'] >= df_1h['H1_EMA50']) & (df_1h['H1_EMA20'] >= df_1h['H1_EMA50']), 1,
        np.where((df_1h['Close'] <= df_1h['H1_EMA50']) & (df_1h['H1_EMA20'] <= df_1h['H1_EMA50']), -1, 0)
    )

    # 3. 15-Minute Base Execution Data
    df_15m = df_5m.resample('15min').agg({
        'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last', 'Volume': 'sum'
    }).dropna()

    # Merge Daily Trend
    df_15m['Date_Floor'] = pd.to_datetime(df_15m.index.date).tz_localize('UTC')
    df_1d_renamed = df_1d[['Daily_Trend', 'Daily_EMA50']].copy()
    df_15m = df_15m.merge(df_1d_renamed, left_on='Date_Floor', right_index=True, how='left')
    df_15m['Daily_Trend'] = df_15m['Daily_Trend'].ffill().fillna(1).astype(int)

    # Merge H1 Trend
    df_15m['Hour_Floor'] = df_15m.index.floor('1h')
    df_1h_renamed = df_1h[['H1_Trend', 'H1_EMA50', 'H1_EMA200']].copy()
    df_15m = df_15m.merge(df_1h_renamed, left_on='Hour_Floor', right_index=True, how='left')
    df_15m['H1_Trend'] = df_15m['H1_Trend'].ffill().fillna(0).astype(int)
    # Backward compatibility
    df_15m['HTF_Trend'] = df_15m['H1_Trend']

    # 4. DXY Dollar Index Inverse Correlation (Pilar 3)
    if include_dxy:
        try:
            df_dxy = get_dxy_data(use_cache=True)
            df_15m = df_15m.merge(
                df_dxy[['Close', 'DXY_Bullish', 'DXY_Bearish']].rename(columns={'Close': 'DXY_Close'}),
                left_index=True, right_index=True, how='left'
            )
            df_15m['DXY_Bullish'] = df_15m['DXY_Bullish'].ffill().fillna(False)
            df_15m['DXY_Bearish'] = df_15m['DXY_Bearish'].ffill().fillna(False)
        except Exception as e:
            print(f"[WARN] Failed to merge DXY: {e}")
            df_15m['DXY_Bullish'] = False
            df_15m['DXY_Bearish'] = False

    # Indicators on 15m
    closes = df_15m['Close']
    highs = df_15m['High']
    lows = df_15m['Low']
    volumes = df_15m['Volume']

    # ATR 14
    tr = np.maximum(highs - lows, np.maximum(abs(highs - closes.shift(1)), abs(lows - closes.shift(1))))
    df_15m['ATR'] = tr.rolling(14).mean().bfill()

    # EMAs
    df_15m['EMA21'] = closes.ewm(span=21, adjust=False).mean()
    df_15m['EMA50'] = closes.ewm(span=50, adjust=False).mean()

    # Volume SMA
    df_15m['Vol_SMA'] = volumes.rolling(20).mean().bfill()

    # RSI 14
    delta = closes.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    rs = gain.rolling(14).mean() / (loss.rolling(14).mean() + 1e-9)
    df_15m['RSI'] = 100 - (100 / (1 + rs))

    # Asian Session Range (00:00 - 06:00 UTC)
    hours = df_15m.index.hour
    dates = df_15m.index.date
    unique_dates = np.unique(dates)
    asian_high_map, asian_low_map = {}, {}

    for d in unique_dates:
        mask = (dates == d) & (hours >= 0) & (hours < 6)
        if np.any(mask):
            asian_high_map[d] = df_15m.loc[mask, 'High'].max()
            asian_low_map[d] = df_15m.loc[mask, 'Low'].min()

    df_15m['Asian_High'] = [asian_high_map.get(d, np.nan) for d in dates]
    df_15m['Asian_Low'] = [asian_low_map.get(d, np.nan) for d in dates]

    # Rolling Highs & Lows (12 bars = 3 hours)
    df_15m['Swing_High_12'] = highs.rolling(12).max().shift(1)
    df_15m['Swing_Low_12'] = lows.rolling(12).min().shift(1)

    # 5. Fair Value Gap (FVG) Zone Detection (Pilar 4)
    opens_arr = df_15m['Open']
    df_15m['Bull_FVG_Top'] = lows
    df_15m['Bull_FVG_Bottom'] = highs.shift(2)
    df_15m['Has_Bull_FVG'] = (lows > highs.shift(2)) & (closes > opens_arr)

    # Bearish FVG: High of bar i < Low of bar i-2
    df_15m['Bear_FVG_Bottom'] = highs
    df_15m['Bear_FVG_Top'] = lows.shift(2)
    df_15m['Has_Bear_FVG'] = (highs < lows.shift(2)) & (closes < opens_arr)

    return df_15m
