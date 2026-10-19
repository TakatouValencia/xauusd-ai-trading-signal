"""
Market Data Feed Provider for XAUUSD (Gold) & DXY (Dollar Index)
High-precision, real-time data feeds powered directly by TradingView FOREXCOM:XAUUSD.
Zero-delay WebSocket streaming for M5/M15 execution, with automatic fallback support.
"""
import os
import re
import json
import asyncio
import requests
import numpy as np
import pandas as pd
import yfinance as yf
from datetime import datetime, timezone
import websockets
import config

CACHE_FILE = "xauusd_5m_cache.csv"

def get_tradingview_forexcom_quote():
    """
    Fetch exact real-time quote for FOREXCOM:XAUUSD directly from TradingView CFD Scanner.
    Executes in ~0.1s without authentication.
    """
    url = 'https://scanner.tradingview.com/cfd/scan'
    payload = {
        'symbols': {'tickers': [getattr(config, 'TRADINGVIEW_SYMBOL', 'FOREXCOM:XAUUSD')]},
        'columns': ['close', 'open', 'high', 'low', 'bid', 'ask']
    }
    try:
        resp = requests.post(
            url,
            json=payload,
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'},
            timeout=5
        )
        if resp.status_code == 200:
            data = resp.json().get('data', [])
            if data:
                d = data[0]['d']
                return {
                    'close': float(d[0]),
                    'open': float(d[1]),
                    'high': float(d[2]),
                    'low': float(d[3]),
                    'bid': float(d[4]) if d[4] is not None else float(d[0]),
                    'ask': float(d[5]) if d[5] is not None else float(d[0])
                }
    except Exception as e:
        print(f"[WARN] Gagal mengambil quote TradingView ({e})", flush=True)
    return None

def fetch_tradingview_candles(symbol='FOREXCOM:XAUUSD', timeframe='5', n_bars=250, timeout=8):
    """
    Fetch true real-time intraday candles directly from TradingView via WebSocket.
    Zero delay, exact spot Gold prices, accurate Open/High/Low/Close.
    """
    async def _fetch():
        uri = 'wss://data.tradingview.com/socket.io/websocket'
        async with websockets.connect(uri, origin='https://data.tradingview.com') as ws:
            def pack(m, p):
                s = json.dumps({'m': m, 'p': p})
                return f'~m~{len(s)}~m~{s}'

            await ws.recv() # session init packet
            cs = 'cs_gold_live_' + str(int(datetime.now().timestamp()))
            await ws.send(pack('set_auth_token', ['unauthorized_user_token']))
            await ws.send(pack('chart_create_session', [cs, '']))
            symbol_spec = json.dumps({'symbol': symbol, 'adjustment': 'splits'})
            await ws.send(pack('resolve_symbol', [cs, 'sds_sym_1', f'={symbol_spec}']))
            await ws.send(pack('create_series', [cs, 'sds_1', 's1', 'sds_sym_1', str(timeframe), n_bars, '']))
            
            bars = []
            start_t = datetime.now()
            while (datetime.now() - start_t).total_seconds() < timeout:
                raw = await ws.recv()
                if '~h~' in raw:
                    await ws.send(raw)
                    continue
                packets = re.split(r'~m~\d+~m~', raw)
                for p in packets:
                    if not p.strip():
                        continue
                    try:
                        data = json.loads(p)
                        if data.get('m') == 'timescale_update':
                            sds = data['p'][1].get('sds_1', {})
                            series_bars = sds.get('s', [])
                            if series_bars:
                                for b in series_bars:
                                    v = b['v']
                                    ts = datetime.fromtimestamp(v[0], timezone.utc)
                                    bars.append({
                                        'Datetime': ts,
                                        'Open': float(v[1]),
                                        'High': float(v[2]),
                                        'Low': float(v[3]),
                                        'Close': float(v[4]),
                                        'Volume': float(v[5]) if len(v) > 5 else 0.0
                                    })
                                df = pd.DataFrame(bars).set_index('Datetime')
                                return df
                    except Exception:
                        pass
            return None

    try:
        return asyncio.run(asyncio.wait_for(_fetch(), timeout=timeout))
    except Exception as e:
        print(f"[WARN] TradingView WebSocket fetch error ({e}), mencoba fallback.", flush=True)
        return None

def fetch_tradingview_htf_indicators():
    """
    Fetch exact Daily Trend, H1 Trend, and DXY Trend in real time from TradingView CFD Scanner.
    """
    url = 'https://scanner.tradingview.com/cfd/scan'
    cols_gold = ['close', 'EMA20', 'EMA50', 'EMA200', 'close|60', 'EMA50|60', 'EMA200|60']
    cols_dxy = ['close', 'EMA20', 'EMA50']
    
    result = {
        'daily_trend': 0,
        'h1_trend': 0,
        'dxy_bullish': False,
        'dxy_bearish': False
    }
    try:
        r_gold = requests.post(
            url,
            json={'symbols': {'tickers': [getattr(config, 'TRADINGVIEW_SYMBOL', 'FOREXCOM:XAUUSD')]}, 'columns': cols_gold},
            headers={'User-Agent': 'Mozilla/5.0'},
            timeout=5
        ).json()
        if r_gold.get('data'):
            d_gold = r_gold['data'][0]['d']
            c_daily, ema20_d, ema50_d = d_gold[0], d_gold[1], d_gold[2]
            c_h1, ema50_h1, ema200_h1 = d_gold[4], d_gold[5], d_gold[6]
            
            # Daily Trend (Pilar 2)
            if c_daily >= ema50_d or ema20_d >= ema50_d:
                result['daily_trend'] = 1
            elif c_daily <= ema50_d or ema20_d <= ema50_d:
                result['daily_trend'] = -1
                
            # H1 Trend (Pilar 2)
            if c_h1 >= ema50_h1 and (ema200_h1 is None or c_h1 >= ema200_h1):
                result['h1_trend'] = 1
            elif c_h1 <= ema50_h1 and (ema200_h1 is None or c_h1 <= ema200_h1):
                result['h1_trend'] = -1

        # DXY Dollar Index (Pilar 3)
        r_dxy = requests.post(
            url,
            json={'symbols': {'tickers': ['TVC:DXY']}, 'columns': cols_dxy},
            headers={'User-Agent': 'Mozilla/5.0'},
            timeout=5
        ).json()
        if r_dxy.get('data'):
            d_dxy = r_dxy['data'][0]['d']
            d_close, d_ema20, d_ema50 = d_dxy[0], d_dxy[1], d_dxy[2]
            result['dxy_bullish'] = (d_close > d_ema50) and (d_ema20 >= d_ema50)
            result['dxy_bearish'] = (d_close < d_ema50) and (d_ema20 <= d_ema50)
    except Exception as e:
        print(f"[WARN] Failed to fetch TradingView HTF indicators: {e}", flush=True)
    return result

def fetch_gold_data(period="60d", interval="5m", use_cache=True) -> pd.DataFrame:
    """
    Download or load cached OHLCV data for Gold backtesting.
    """
    if use_cache and os.path.exists(CACHE_FILE):
        df = pd.read_csv(CACHE_FILE, index_col=0, parse_dates=True)
    else:
        df = yf.download(getattr(config, 'SYMBOL', 'GC=F'), period=period, interval=interval, progress=False)
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

def fetch_latest_live_candles(count=250) -> pd.DataFrame:
    """
    Fetch the most recent live candles for scanner execution.
    Primary: High-speed WebSocket from TradingView FOREXCOM:XAUUSD (Zero lag).
    Fallback: Yahoo Finance GC=F (Gold Futures) or local cache.
    """
    # 1. Primary: TradingView WebSocket
    tv_symbol = getattr(config, 'TRADINGVIEW_SYMBOL', 'FOREXCOM:XAUUSD')
    df = fetch_tradingview_candles(symbol=tv_symbol, timeframe='5', n_bars=count)
    if df is not None and not df.empty and len(df) >= 30:
        return df.sort_index()

    # 2. Fallback: Yahoo Finance GC=F
    print("[WARN] Menggunakan fallback Yahoo Finance untuk data market...", flush=True)
    try:
        df_yf = yf.download("GC=F", period="5d", interval="5m", progress=False)
        if isinstance(df_yf.columns, pd.MultiIndex):
            df_yf.columns = df_yf.columns.get_level_values(0)
        df_yf = df_yf.dropna()
        if df_yf.index.tz is None:
            df_yf.index = df_yf.index.tz_localize('UTC')
        else:
            df_yf.index = df_yf.index.tz_convert('UTC')
        return df_yf.tail(count).sort_index().copy()
    except Exception as e:
        print(f"[ERROR] Fallback download failed: {e}", flush=True)
        return pd.DataFrame()

def prepare_multi_timeframe_data(df_5m: pd.DataFrame, include_dxy=True, is_live=False):
    """
    Transform 5M raw data into:
    - Daily Macro Trend (Pilar 2)
    - 1-Hour Trend Context (Pilar 2)
    - 15-Minute Base Execution Data with FVG zones
    - DXY Dollar Index Inverse Alignment (Pilar 3)
    """
    if df_5m.empty:
        return pd.DataFrame()

    # 1. 15-Minute Base Execution Data
    df_15m = df_5m.resample('15min').agg({
        'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last', 'Volume': 'sum'
    }).dropna()

    if df_15m.empty:
        return pd.DataFrame()

    if is_live:
        # Live Mode: Dapatkan status HTF dan DXY langsung dari TradingView
        htf = fetch_tradingview_htf_indicators()
        df_15m['Daily_Trend'] = htf['daily_trend']
        df_15m['H1_Trend'] = htf['h1_trend']
        df_15m['HTF_Trend'] = htf['h1_trend']
        df_15m['DXY_Bullish'] = htf['dxy_bullish']
        df_15m['DXY_Bearish'] = htf['dxy_bearish']
    else:
        # Backtest Mode: Resample D1 dan H1 dari 5M
        df_1d = df_5m.resample('1D').agg({
            'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last', 'Volume': 'sum'
        }).dropna()
        df_1d['Daily_EMA20'] = df_1d['Close'].ewm(span=20, adjust=False).mean()
        df_1d['Daily_EMA50'] = df_1d['Close'].ewm(span=50, adjust=False).mean()
        df_1d['Daily_Trend'] = np.where(
            (df_1d['Close'] >= df_1d['Daily_EMA50']) | (df_1d['Daily_EMA20'] >= df_1d['Daily_EMA50']), 1,
            np.where((df_1d['Close'] <= df_1d['Daily_EMA50']) | (df_1d['Daily_EMA20'] <= df_1d['Daily_EMA50']), -1, 0)
        )

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

        df_15m['Date_Floor'] = pd.to_datetime(df_15m.index.date).tz_localize('UTC')
        df_1d_renamed = df_1d[['Daily_Trend']].copy()
        df_15m = df_15m.merge(df_1d_renamed, left_on='Date_Floor', right_index=True, how='left')
        df_15m['Daily_Trend'] = df_15m['Daily_Trend'].ffill().fillna(1).astype(int)

        df_15m['Hour_Floor'] = df_15m.index.floor('1h')
        df_1h_renamed = df_1h[['H1_Trend']].copy()
        df_15m = df_15m.merge(df_1h_renamed, left_on='Hour_Floor', right_index=True, how='left')
        df_15m['H1_Trend'] = df_15m['H1_Trend'].ffill().fillna(0).astype(int)
        df_15m['HTF_Trend'] = df_15m['H1_Trend']

        if include_dxy:
            try:
                from dxy_feed import get_dxy_data
                df_dxy = get_dxy_data(use_cache=True)
                df_15m = df_15m.merge(
                    df_dxy[['Close', 'DXY_Bullish', 'DXY_Bearish']].rename(columns={'Close': 'DXY_Close'}),
                    left_index=True, right_index=True, how='left'
                )
                df_15m['DXY_Bullish'] = df_15m['DXY_Bullish'].ffill().fillna(False)
                df_15m['DXY_Bearish'] = df_15m['DXY_Bearish'].ffill().fillna(False)
            except Exception as e:
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

    # Fair Value Gap (FVG) Zone Detection (Pilar 4)
    opens_arr = df_15m['Open']
    df_15m['Bull_FVG_Top'] = lows
    df_15m['Bull_FVG_Bottom'] = highs.shift(2)
    df_15m['Has_Bull_FVG'] = (lows > highs.shift(2)) & (closes > opens_arr)

    df_15m['Bear_FVG_Bottom'] = highs
    df_15m['Bear_FVG_Top'] = lows.shift(2)
    df_15m['Has_Bear_FVG'] = (highs < lows.shift(2)) & (closes < opens_arr)

    return df_15m
