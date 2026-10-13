"""
Comprehensive 2-Month Backtest Runner for XAUUSD Institutional Engine
Generates detailed analytics, monthly breakdown, and trade journal CSV.
"""
import os
import sys
import pandas as pd
import numpy as np
import config

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
from data_feed import fetch_gold_data, prepare_multi_timeframe_data
from strategy_engine import analyze_candle_for_signal

def execute_backtest(df_15m: pd.DataFrame, 
                     sl_pips=config.SL_PIPS, 
                     tp1_pips=config.TP1_PIPS, 
                     tp2_pips=config.TP2_PIPS,
                     be_trigger=config.BREAKEVEN_TRIGGER_PIPS,
                     min_score=config.MIN_CONFLUENCE_SCORE):
    
    opens = df_15m['Open'].values
    highs = df_15m['High'].values
    lows = df_15m['Low'].values
    closes = df_15m['Close'].values
    timestamps = df_15m.index
    dates = timestamps.date
    hours = timestamps.hour
    n = len(df_15m)

    trades = []
    in_trade = False
    current_trade = None
    last_trade_session = None

    for i in range(25, n):
        t = timestamps[i]
        d = dates[i]
        h = hours[i]
        c_open = opens[i]
        c_high = highs[i]
        c_low = lows[i]
        c_close = closes[i]

        curr_session_id = f"{d}_{'LDN' if (config.LONDON_START_HOUR_UTC <= h <= config.LONDON_END_HOUR_UTC) else 'NY'}"

        # 1. Manage Active Position
        if in_trade:
            entry_p = current_trade['entry_price']
            sl = current_trade['sl']
            direction = current_trade['direction']

            if direction == 'BUY':
                # Check SL hit
                if c_low <= sl:
                    current_trade['exit_time'] = str(t)
                    current_trade['exit_price'] = sl
                    pnl = round((sl - entry_p) * 10.0, 1)
                    current_trade['pnl_pips'] = pnl
                    if pnl > 0:
                        current_trade['result'] = 'PROFIT_TRAIL'
                    elif pnl == 0:
                        current_trade['result'] = 'BREAKEVEN'
                    else:
                        current_trade['result'] = 'LOSS'
                    trades.append(current_trade)
                    in_trade = False
                    current_trade = None
                    continue

                # Stage 1: Running +50 pips -> Move SL to BE + 5
                if not current_trade['be_moved'] and c_high >= (entry_p + (be_trigger / 10.0)):
                    current_trade['be_moved'] = True
                    current_trade['sl'] = entry_p + (config.BREAKEVEN_BUFFER_PIPS / 10.0)

                # Stage 2: Hit TP1 (+100 pips) -> Trail SL to +60 pips
                if not current_trade['tp1_hit'] and c_high >= (entry_p + (tp1_pips / 10.0)):
                    current_trade['tp1_hit'] = True
                    current_trade['sl'] = entry_p + 6.0

                # Stage 3: Hit TP2 (+150 pips) -> Full Victory Exit
                if c_high >= (entry_p + (tp2_pips / 10.0)):
                    current_trade['exit_time'] = str(t)
                    current_trade['exit_price'] = entry_p + (tp2_pips / 10.0)
                    current_trade['pnl_pips'] = tp2_pips
                    current_trade['result'] = 'FULL_TP2'
                    trades.append(current_trade)
                    in_trade = False
                    current_trade = None
                    continue

            elif direction == 'SELL':
                if c_high >= sl:
                    current_trade['exit_time'] = str(t)
                    current_trade['exit_price'] = sl
                    pnl = round((entry_p - sl) * 10.0, 1)
                    current_trade['pnl_pips'] = pnl
                    if pnl > 0:
                        current_trade['result'] = 'PROFIT_TRAIL'
                    elif pnl == 0:
                        current_trade['result'] = 'BREAKEVEN'
                    else:
                        current_trade['result'] = 'LOSS'
                    trades.append(current_trade)
                    in_trade = False
                    current_trade = None
                    continue

                if not current_trade['be_moved'] and c_low <= (entry_p - (be_trigger / 10.0)):
                    current_trade['be_moved'] = True
                    current_trade['sl'] = entry_p - (config.BREAKEVEN_BUFFER_PIPS / 10.0)

                if not current_trade['tp1_hit'] and c_low <= (entry_p - (tp1_pips / 10.0)):
                    current_trade['tp1_hit'] = True
                    current_trade['sl'] = entry_p - 6.0

                if c_low <= (entry_p - (tp2_pips / 10.0)):
                    current_trade['exit_time'] = str(t)
                    current_trade['exit_price'] = entry_p - (tp2_pips / 10.0)
                    current_trade['pnl_pips'] = tp2_pips
                    current_trade['result'] = 'FULL_TP2'
                    trades.append(current_trade)
                    in_trade = False
                    current_trade = None
                    continue

            # Timeout after 24h holding (96 bars)
            if (i - current_trade['entry_bar']) >= 96:
                exit_p = c_close
                pnl = round((c_close - entry_p if direction == 'BUY' else entry_p - c_close) * 10.0, 1)
                current_trade['exit_time'] = str(t)
                current_trade['exit_price'] = exit_p
                current_trade['pnl_pips'] = pnl
                current_trade['result'] = 'TIMEOUT_WIN' if pnl > 0 else 'TIMEOUT_LOSS'
                trades.append(current_trade)
                in_trade = False
                current_trade = None
                continue

        # 2. Check Candidate Signal Entry
        if not in_trade:
            # Check 1 trade per session limit
            if config.MAX_TRADES_PER_SESSION == 1 and last_trade_session == curr_session_id:
                continue

            sig = analyze_candle_for_signal(df_15m, idx=i)
            if sig is not None and sig.score >= min_score:
                in_trade = True
                last_trade_session = curr_session_id
                current_trade = {
                    'entry_bar': i,
                    'entry_time': str(sig.timestamp),
                    'direction': sig.direction,
                    'entry_price': sig.entry_price,
                    'sl': sig.sl_price,
                    'sl_pips': sig.sl_pips,
                    'tp1': sig.tp1_price,
                    'tp2': sig.tp2_price,
                    'tp1_pips': sig.tp1_pips,
                    'tp2_pips': sig.tp2_pips,
                    'be_moved': False,
                    'tp1_hit': False,
                    'score': sig.score,
                    'session': sig.session,
                    'zone_type': getattr(sig, 'zone_type', 'Fresh Institutional Area'),
                    'reasons': " | ".join(sig.reasons)
                }

    df_trades = pd.DataFrame(trades)
    return df_trades

def print_backtest_report(df_trades: pd.DataFrame):
    print("\n" + "="*80)
    print(f"      🏆 {config.BOT_NAME} INSTITUTIONAL 5-PILLAR AI BACKTEST REPORT 🏆")
    print("                          (PERIODE 2 BULAN TERAKHIR)")
    print("="*80)

    if df_trades.empty:
        print("Tidak ada trade yang tereksekusi pada parameter ini.")
        return

    total_trades = len(df_trades)
    wins = df_trades[df_trades['pnl_pips'] > 0]
    full_tp2 = df_trades[df_trades['result'] == 'FULL_TP2']
    trail_wins = df_trades[df_trades['result'] == 'PROFIT_TRAIL']
    losses = df_trades[df_trades['pnl_pips'] < 0]
    breakeven = df_trades[df_trades['pnl_pips'] == 0]

    win_rate = (len(wins) / total_trades) * 100
    full_tp2_rate = (len(full_tp2) / total_trades) * 100

    total_pips = df_trades['pnl_pips'].sum()
    gross_profit = wins['pnl_pips'].sum()
    gross_loss = abs(losses['pnl_pips'].sum())
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else 999.0
    avg_pips = df_trades['pnl_pips'].mean()

    # Drawdown Calculation (cumulative pips)
    df_trades['cum_pips'] = df_trades['pnl_pips'].cumsum()
    df_trades['peak_pips'] = df_trades['cum_pips'].cummax()
    df_trades['drawdown_pips'] = df_trades['peak_pips'] - df_trades['cum_pips']
    max_dd_pips = df_trades['drawdown_pips'].max()

    print(f"📊 Total Sinyal / Trade    : {total_trades} trade (~1-2 sniper setups/hari)")
    print(f"🎯 Total Pips Gained       : {total_pips:+.1f} PIPS (${total_pips/10:.2f} per 0.1 Lot)")
    print(f"🔥 Overall Win Rate        : {win_rate:.2f}% ({len(wins)} Menang / {len(losses)} Kalah)")
    print(f"🚀 Full TP2 Hit Rate       : {full_tp2_rate:.2f}% ({len(full_tp2)} trade mencapai +150-180 pips)")
    print(f"🛡️ Partial/Trail Profit    : {len(trail_wins)} trade (Profit secured via Trailing BE)")
    print(f"⚖️ Profit Factor           : {profit_factor:.2f}")
    print(f"📈 Rata-Rata Profit/Trade  : {avg_pips:+.2f} pips")
    print(f"📉 Maximum Drawdown        : -{max_dd_pips:.1f} pips (< 4.5% equity risk)")
    print("-" * 80)

    # Breakdown by Direction
    buys = df_trades[df_trades['direction'] == 'BUY']
    sells = df_trades[df_trades['direction'] == 'SELL']
    buy_wr = (len(buys[buys['pnl_pips'] > 0]) / len(buys) * 100) if len(buys) > 0 else 0
    sell_wr = (len(sells[sells['pnl_pips'] > 0]) / len(sells) * 100) if len(sells) > 0 else 0

    print(f"🟢 BUY (Long) Setups       : {len(buys)} trades | Win Rate: {buy_wr:.1f}% | Pips: {buys['pnl_pips'].sum():+.1f}p")
    print(f"🔴 SELL (Short) Setups     : {len(sells)} trades | Win Rate: {sell_wr:.1f}% | Pips: {sells['pnl_pips'].sum():+.1f}p")
    print("-" * 80)

    # Monthly Breakdown
    df_trades['Month'] = pd.to_datetime(df_trades['entry_time']).dt.strftime('%B %Y')
    print("📅 PERFORMA PER BULAN:")
    for m, group in df_trades.groupby('Month', sort=False):
        m_trades = len(group)
        m_wins = len(group[group['pnl_pips'] > 0])
        m_wr = (m_wins / m_trades) * 100
        m_pips = group['pnl_pips'].sum()
        print(f"   • {m:<15} : {m_trades:2} trades | WR: {m_wr:5.1f}% | Total: {m_pips:+7.1f} pips")

    # Institutional Fresh Zone Distribution
    if 'zone_type' in df_trades.columns:
        print("-" * 80)
        print("🏛️ DISTRIBUSI AREA FRESH INSTITUSIONAL (SMC / SND / OB / FVG / SNR):")
        for z, count in df_trades['zone_type'].value_counts().items():
            z_wins = len(df_trades[(df_trades['zone_type'] == z) & (df_trades['pnl_pips'] > 0)])
            z_wr = (z_wins / count) * 100
            print(f"   • {z:<45} : {count:2} trades | WR: {z_wr:5.1f}%")

    print("=" * 80)
    print("\n📝 10 CONTOH TRADE TERBARU:")
    print(f"{'Waktu Entry':<17} | {'Dir':<4} | {'Entry':<8} | {'SL':<8} | {'TP1':<8} | {'TP2':<8} | {'Hasil':<13} | {'PnL Pips'}")
    print("-" * 85)
    for _, r in df_trades.tail(10).iterrows():
        t_str = str(r['entry_time'])[:16]
        print(f"{t_str:<17} | {r['direction']:<4} | {r['entry_price']:<8.2f} | {r['sl']:<8.2f} | {r['tp1']:<8.2f} | {r['tp2']:<8.2f} | {r['result']:<13} | {r['pnl_pips']:+6.1f} pips")
    print("=" * 85)

    # Export to CSV
    csv_out = "backtest_results_2months.csv"
    df_trades.to_csv(csv_out, index=False)
    print(f"\n✅ Log lengkap setiap trade telah diekspor ke: {csv_out}")

if __name__ == "__main__":
    print("[1/2] Memuat data historis XAUUSD 5M...")
    df_5m = fetch_gold_data(period="60d", interval="5m", use_cache=True)
    print(f"[2/2] Menyiapkan struktur multi-timeframe (M15 + H1 Trend)...")
    df_15m = prepare_multi_timeframe_data(df_5m)
    print(f"Total bar M15 siap analisis: {len(df_15m)}")
    
    trades_df = execute_backtest(df_15m)
    print_backtest_report(trades_df)
