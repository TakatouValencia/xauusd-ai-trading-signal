import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, time

def load_data():
    print("Downloading GC=F 5m data...")
    df = yf.download("GC=F", period="60d", interval="5m", progress=False)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.dropna()
    print(f"Data loaded: {len(df)} candles from {df.index[0]} to {df.index[-1]}")
    return df

def run_smc_experiment(df, min_sl_pips=45, max_sl_pips=65, tp1_pips=100, tp2_pips=150):
    # Ensure UTC timezone
    df = df.copy()
    if df.index.tz is None:
        df.index = df.index.tz_localize('UTC')
    else:
        df.index = df.index.tz_convert('UTC')

    df['Hour'] = df.index.hour
    df['Minute'] = df.index.minute
    df['Time'] = df.index.time
    df['Date'] = df.index.date

    # Indicators
    # ATR (14)
    tr = np.maximum(df['High'] - df['Low'], 
                    np.maximum(abs(df['High'] - df['Close'].shift(1)), 
                               abs(df['Low'] - df['Close'].shift(1))))
    df['ATR'] = tr.rolling(14).mean()
    df['Vol_SMA'] = df['Volume'].rolling(20).mean()
    df['EMA50'] = df['Close'].ewm(span=50, adjust=False).mean()
    df['EMA200'] = df['Close'].ewm(span=200, adjust=False).mean()

    # Calculate Session High and Lows
    # Asian Session: 00:00 to 06:00 UTC
    # London Killzone: 07:00 to 11:00 UTC
    # NY Killzone: 12:30 to 16:30 UTC

    trades = []
    
    # Track daily Asian session levels
    # Group by date to find Asian high and low
    asian_sessions = {}
    for date, group in df.groupby('Date'):
        asian_candles = group[(group['Hour'] >= 0) & (group['Hour'] < 6)]
        if len(asian_candles) > 0:
            asian_sessions[date] = {
                'high': asian_candles['High'].max(),
                'low': asian_candles['Low'].min()
            }

    # Swing high and low tracking (rolling 12 bars = 1 hour swing)
    df['Swing_High'] = df['High'].rolling(15).max()
    df['Swing_Low'] = df['Low'].rolling(15).min()

    # Detect signals
    # We step through candles
    in_trade = False
    current_trade = None

    for i in range(50, len(df)):
        current_time = df.index[i]
        date = current_time.date()
        hour = current_time.hour
        minute = current_time.minute

        c_open = df['Open'].iloc[i]
        c_high = df['High'].iloc[i]
        c_low = df['Low'].iloc[i]
        c_close = df['Close'].iloc[i]
        c_vol = df['Volume'].iloc[i]
        atr = df['ATR'].iloc[i]
        vol_sma = df['Vol_SMA'].iloc[i]
        ema50 = df['EMA50'].iloc[i]
        ema200 = df['EMA200'].iloc[i]

        # Check existing trade management
        if in_trade:
            entry_p = current_trade['entry_price']
            sl = current_trade['sl']
            tp1 = current_trade['tp1']
            tp2 = current_trade['tp2']
            direction = current_trade['direction']
            
            # Check high/low for exit
            if direction == 'BUY':
                # Check SL
                if c_low <= sl:
                    current_trade['exit_time'] = current_time
                    current_trade['exit_price'] = sl
                    current_trade['pnl_pips'] = (sl - entry_p) * 10.0 # 1 pip = $0.10
                    current_trade['result'] = 'LOSS' if not current_trade['hit_tp1'] else 'BE/PROFIT'
                    trades.append(current_trade)
                    in_trade = False
                    current_trade = None
                    continue
                # Check TP1
                if not current_trade['hit_tp1'] and c_high >= tp1:
                    current_trade['hit_tp1'] = True
                    # Move SL to entry + 5 pips (Risk Free)
                    current_trade['sl'] = entry_p + 0.5
                # Check TP2
                if c_high >= tp2:
                    current_trade['exit_time'] = current_time
                    current_trade['exit_price'] = tp2
                    current_trade['pnl_pips'] = (tp2 - entry_p) * 10.0
                    current_trade['result'] = 'WIN'
                    trades.append(current_trade)
                    in_trade = False
                    current_trade = None
                    continue

            elif direction == 'SELL':
                # Check SL
                if c_high >= sl:
                    current_trade['exit_time'] = current_time
                    current_trade['exit_price'] = sl
                    current_trade['pnl_pips'] = (entry_p - sl) * 10.0
                    current_trade['result'] = 'LOSS' if not current_trade['hit_tp1'] else 'BE/PROFIT'
                    trades.append(current_trade)
                    in_trade = False
                    current_trade = None
                    continue
                # Check TP1
                if not current_trade['hit_tp1'] and c_low <= tp1:
                    current_trade['hit_tp1'] = True
                    # Move SL to entry - 5 pips (Risk Free)
                    current_trade['sl'] = entry_p - 0.5
                # Check TP2
                if c_low <= tp2:
                    current_trade['exit_time'] = current_time
                    current_trade['exit_price'] = tp2
                    current_trade['pnl_pips'] = (entry_p - tp2) * 10.0
                    current_trade['result'] = 'WIN'
                    trades.append(current_trade)
                    in_trade = False
                    current_trade = None
                    continue

            # Time limit: max holding 16 hours
            holding_bars = i - current_trade['entry_index']
            if holding_bars > 192: # 16 hours on 5m
                exit_p = c_close
                pnl = (exit_p - entry_p if direction == 'BUY' else entry_p - exit_p) * 10.0
                current_trade['exit_time'] = current_time
                current_trade['exit_price'] = exit_p
                current_trade['pnl_pips'] = pnl
                current_trade['result'] = 'WIN' if pnl > 0 else 'LOSS'
                trades.append(current_trade)
                in_trade = False
                current_trade = None
                continue

        # If not in trade, scan for entry
        if not in_trade:
            # Session Filter: London KZ (07:00 - 11:00 UTC) or NY KZ (12:30 - 16:30 UTC)
            is_london = (hour >= 7 and hour < 11)
            is_ny = ((hour == 12 and minute >= 30) or (hour >= 13 and hour < 17))
            if not (is_london or is_ny):
                continue

            asian = asian_sessions.get(date, None)
            if not asian:
                continue

            asian_h = asian['high']
            asian_l = asian['low']

            # SMC Rules:
            # 1. Sweep of Asian Range or Recent Key Swing (past 20 bars)
            recent_low = df['Low'].iloc[i-15:i].min()
            recent_high = df['High'].iloc[i-15:i].max()

            # Previous 2 candles for FVG & Displacement detection
            c1_low = df['Low'].iloc[i-2]
            c1_high = df['High'].iloc[i-2]
            c2_close = df['Close'].iloc[i-1]
            c2_open = df['Open'].iloc[i-1]

            # Displacement check (Body > 1.2 * ATR and Vol > Vol_SMA)
            body_size = abs(c_close - c_open)
            is_displacement = body_size >= (1.1 * atr) and (c_vol >= 1.0 * vol_sma or vol_sma == 0)

            # BULLISH SETUP:
            # Price swept Asian Low or recent low in the last 1-4 bars
            swept_low = any(df['Low'].iloc[i-k] < asian_l for k in range(1, 6)) or any(df['Low'].iloc[i-k] < df['Low'].iloc[i-20:i-k].min() for k in range(1, 4))
            
            # Trend confirmation: Close > EMA50 or EMA50 > EMA200
            trend_bullish = c_close >= ema50 or ema50 > ema200

            # Bullish FVG: current Low > c1_high (imbalance)
            bullish_fvg = df['Low'].iloc[i-1] > df['High'].iloc[i-3] if i >= 3 else False
            
            # MSS: current close > high of previous 3 bars
            mss_bull = c_close > df['High'].iloc[i-4:i].max()

            if swept_low and is_displacement and c_close > c_open and mss_bull and trend_bullish:
                # Find sweep extreme
                sweep_ext = df['Low'].iloc[i-6:i+1].min()
                raw_sl_dist = (c_close - sweep_ext) * 10.0 # pips
                
                # Check SL bounds
                if min_sl_pips <= raw_sl_dist <= max_sl_pips:
                    sl_dist = raw_sl_dist + 5.0 # buffer 5 pips
                elif raw_sl_dist < min_sl_pips:
                    sl_dist = float(min_sl_pips)
                else:
                    continue # Too wide risk

                sl_price = c_close - (sl_dist / 10.0)
                tp1_price = c_close + (tp1_pips / 10.0)
                tp2_price = c_close + (tp2_pips / 10.0)

                in_trade = True
                current_trade = {
                    'entry_index': i,
                    'entry_time': current_time,
                    'direction': 'BUY',
                    'entry_price': c_close,
                    'sl': sl_price,
                    'sl_pips': sl_dist,
                    'tp1': tp1_price,
                    'tp2': tp2_price,
                    'tp1_pips': tp1_pips,
                    'tp2_pips': tp2_pips,
                    'hit_tp1': False,
                    'session': 'London' if is_london else 'New York',
                    'reason': 'Asian/Key SSL Sweep + Displacement MSS + Bullish Imbalance'
                }
                continue

            # BEARISH SETUP:
            swept_high = any(df['High'].iloc[i-k] > asian_h for k in range(1, 6)) or any(df['High'].iloc[i-k] > df['High'].iloc[i-20:i-k].max() for k in range(1, 4))
            trend_bearish = c_close <= ema50 or ema50 < ema200
            bearish_fvg = df['High'].iloc[i-1] < df['Low'].iloc[i-3] if i >= 3 else False
            mss_bear = c_close < df['Low'].iloc[i-4:i].min()

            if swept_high and is_displacement and c_close < c_open and mss_bear and trend_bearish:
                sweep_ext = df['High'].iloc[i-6:i+1].max()
                raw_sl_dist = (sweep_ext - c_close) * 10.0 # pips

                if min_sl_pips <= raw_sl_dist <= max_sl_pips:
                    sl_dist = raw_sl_dist + 5.0
                elif raw_sl_dist < min_sl_pips:
                    sl_dist = float(min_sl_pips)
                else:
                    continue

                sl_price = c_close + (sl_dist / 10.0)
                tp1_price = c_close - (tp1_pips / 10.0)
                tp2_price = c_close - (tp2_pips / 10.0)

                in_trade = True
                current_trade = {
                    'entry_index': i,
                    'entry_time': current_time,
                    'direction': 'SELL',
                    'entry_price': c_close,
                    'sl': sl_price,
                    'sl_pips': sl_dist,
                    'tp1': tp1_price,
                    'tp2': tp2_price,
                    'tp1_pips': tp1_pips,
                    'tp2_pips': tp2_pips,
                    'hit_tp1': False,
                    'session': 'London' if is_london else 'New York',
                    'reason': 'Asian/Key BSL Sweep + Displacement MSS + Bearish Imbalance'
                }
                continue

    return pd.DataFrame(trades)

if __name__ == '__main__':
    df = load_data()
    trades_df = run_smc_experiment(df, min_sl_pips=50, max_sl_pips=70, tp1_pips=100, tp2_pips=150)
    print("\n--- EXPERIMENT RESULTS ---")
    print(f"Total Trades: {len(trades_df)}")
    if not trades_df.empty:
        wins = trades_df[trades_df['result'].isin(['WIN', 'BE/PROFIT'])]
        losses = trades_df[trades_df['result'] == 'LOSS']
        pure_tp2 = trades_df[trades_df['result'] == 'WIN']
        wr = len(wins) / len(trades_df) * 100
        pure_wr = len(pure_tp2) / len(trades_df) * 100
        total_pips = trades_df['pnl_pips'].sum()
        print(f"Overall Win Rate (TP hit / Profit secured): {wr:.2f}%")
        print(f"Full TP2 Hit Rate (150 pips): {pure_wr:.2f}%")
        print(f"Total Pips: {total_pips:+.1f} pips")
        print(f"Wins: {len(wins)} | Losses: {len(losses)}")
        print(f"Avg Pips per Trade: {trades_df['pnl_pips'].mean():.2f}")
        print("\nFirst 5 trades:")
        print(trades_df[['entry_time', 'direction', 'entry_price', 'sl_pips', 'pnl_pips', 'result']].head(5))
        print("\nLast 5 trades:")
        print(trades_df[['entry_time', 'direction', 'entry_price', 'sl_pips', 'pnl_pips', 'result']].tail(5))
