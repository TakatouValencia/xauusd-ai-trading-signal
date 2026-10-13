"""
Live Scanner & Real-Time Alert Engine for XAUUSD
Monitors live Gold candles, evaluates SMC & Orderflow signals,
manages open positions, and sends instant rich embeds to Discord.
"""
import sys
import os
import time
import argparse
from datetime import datetime, timezone
import pandas as pd
import config
from data_feed import fetch_latest_live_candles, prepare_multi_timeframe_data
from strategy_engine import analyze_candle_for_signal, check_trading_session, Signal
from discord_notifier import notify_signal_entry, notify_trade_update

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

class LivePositionTracker:
    def __init__(self):
        self.active_trade = None
        self.last_signal_time = None
        self.last_session_id = None

    def has_active_trade(self):
        return self.active_trade is not None

    def open_trade(self, signal: Signal):
        self.active_trade = {
            'direction': signal.direction,
            'entry_price': signal.entry_price,
            'sl': signal.sl_price,
            'initial_sl': signal.sl_price,
            'sl_pips': signal.sl_pips,
            'tp1': signal.tp1_price,
            'tp2': signal.tp2_price,
            'be_moved': False,
            'tp1_hit': False,
            'entry_time': signal.timestamp,
            'session': signal.session
        }
        self.last_signal_time = signal.timestamp

    def update_with_price(self, current_price: float, current_high: float, current_low: float):
        if not self.active_trade:
            return

        trade = self.active_trade
        dir = trade['direction']
        entry_p = trade['entry_price']

        if dir == 'BUY':
            # Check Stop Loss
            if current_low <= trade['sl']:
                pnl = (trade['sl'] - entry_p) * 10.0
                print(f"[EXIT] BUY Position hit SL at {trade['sl']:.2f} ({pnl:+.1f} pips)")
                notify_trade_update("SL_HIT", trade)
                self.active_trade = None
                return

            # Stage 1: Running +50 pips -> Move SL to BE + 5 pips
            if not trade['be_moved'] and current_high >= (entry_p + (config.BREAKEVEN_TRIGGER_PIPS / 10.0)):
                trade['be_moved'] = True
                trade['sl'] = round(entry_p + (config.BREAKEVEN_BUFFER_PIPS / 10.0), 2)
                print(f"[PROTECTION] Running +50 pips! SL moved to BE at {trade['sl']:.2f}")
                notify_trade_update("BREAKEVEN", trade)

            # Stage 2: Hit TP1 (+100 pips)
            if not trade['tp1_hit'] and current_high >= trade['tp1']:
                trade['tp1_hit'] = True
                trade['sl'] = round(entry_p + 6.0, 2) # Trail SL to +60 pips
                print(f"[TP1 HIT] Target 1 (+100 pips) achieved at {trade['tp1']:.2f}!")
                notify_trade_update("TP1_HIT", trade)

            # Stage 3: Hit TP2 (+150 pips)
            if current_high >= trade['tp2']:
                print(f"[TP2 HIT] FULL TARGET (+150 pips) achieved at {trade['tp2']:.2f}!")
                notify_trade_update("TP2_HIT", trade)
                self.active_trade = None
                return

        elif dir == 'SELL':
            if current_high >= trade['sl']:
                pnl = (entry_p - trade['sl']) * 10.0
                print(f"[EXIT] SELL Position hit SL at {trade['sl']:.2f} ({pnl:+.1f} pips)")
                notify_trade_update("SL_HIT", trade)
                self.active_trade = None
                return

            if not trade['be_moved'] and current_low <= (entry_p - (config.BREAKEVEN_TRIGGER_PIPS / 10.0)):
                trade['be_moved'] = True
                trade['sl'] = round(entry_p - (config.BREAKEVEN_BUFFER_PIPS / 10.0), 2)
                print(f"[PROTECTION] Running +50 pips! SL moved to BE at {trade['sl']:.2f}")
                notify_trade_update("BREAKEVEN", trade)

            if not trade['tp1_hit'] and current_low <= trade['tp1']:
                trade['tp1_hit'] = True
                trade['sl'] = round(entry_p - 6.0, 2)
                print(f"[TP1 HIT] Target 1 (+100 pips) achieved at {trade['tp1']:.2f}!")
                notify_trade_update("TP1_HIT", trade)

            if current_low <= trade['tp2']:
                print(f"[TP2 HIT] FULL TARGET (+150 pips) achieved at {trade['tp2']:.2f}!")
                notify_trade_update("TP2_HIT", trade)
                self.active_trade = None
                return

def test_discord_alert():
    """
    Send an immediate test alert using real-time market price to verify Discord Webhook configuration.
    """
    print("[TEST] Mengambil harga market real-time XAUUSD dari TradingView Forex.com...", flush=True)
    try:
        from data_feed import get_tradingview_forexcom_quote
        tv_quote = get_tradingview_forexcom_quote()
        if tv_quote:
            current_price = round(tv_quote['close'], 2)
            print(f"[TEST] Harga real-time TradingView FOREXCOM:XAUUSD terdeteksi: ${current_price:.2f}", flush=True)
        else:
            df_5m = fetch_latest_live_candles(count=20)
            current_price = round(float(df_5m['Close'].iloc[-1]), 2)
            print(f"[TEST] Harga real-time market saat ini terdeteksi: ${current_price:.2f}", flush=True)
    except Exception as e:
        print(f"[WARN] Gagal mengambil candle real-time ({e}), menggunakan fallback.", flush=True)
        current_price = 4185.00

    sl_dist = config.SL_PIPS / 10.0
    tp1_dist = config.TP1_PIPS / 10.0
    tp2_dist = config.TP2_PIPS / 10.0

    print(f"[TEST] Mengirim sinyal uji coba dengan harga real-time (${current_price:.2f}) ke Discord...", flush=True)
    mock_signal = Signal(
        timestamp=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        direction="BUY",
        entry_price=current_price,
        sl_price=round(current_price - sl_dist, 2),
        tp1_price=round(current_price + tp1_dist, 2),
        tp2_price=round(current_price + tp2_dist, 2),
        score=92,
        session="London Killzone",
        reasons=[
            "Pilar 2: Macro Bias Sempurna (Daily & H1 Keduanya Bullish)",
            "Pilar 3: DXY Mengonfirmasi (Indeks Dollar AS Bearish Rejection)",
            f"Institutional Fresh Area: Confluence Fresh OB (Demand) + FVG [${current_price - 2.50:.2f} - ${current_price:.2f}]",
            f"SMC: Swept Key Liquidity Level di ${current_price - 5.00:.2f}",
            "Orderflow: Rejection Wick Kuat (Buyer Absorption > 35%)",
            "Volume Footprint Spike (1.4x dari SMA-20)",
            "Healthy RSI Expansion (56.4 - Non Exhausted)"
        ],
        zone_type="Confluence: Fresh OB (Demand) + FVG",
        zone_range=f"[${current_price - 2.50:.2f} - ${current_price:.2f}]"
    )
    success = notify_signal_entry(mock_signal)
    if success:
        print(f"✅ [SUCCESS] Sinyal uji coba berhasil dikirim ke Discord pada harga ${current_price:.2f}!")
    else:
        print("⚠️ [NOTE] Webhook URL belum diisi di config.py / .env, atau URL tidak valid.")

def run_live_loop():
    print("=" * 75)
    print(f"   🤖 {config.BOT_NAME} (XAUUSD 5-PILLAR AI ENGINE) STARTED 🤖")
    print(f"   Pair: {config.DISPLAY_SYMBOL} | SL: {config.SL_PIPS}p | TP1: {config.TP1_PIPS}p | TP2: {config.TP2_PIPS}p")
    print(f"   Min Score: {config.MIN_CONFLUENCE_SCORE}/100 | Sesi: London & NY Killzone")
    print("=" * 75)

    tracker = LivePositionTracker()
    last_processed_bar = None

    while True:
        try:
            now_utc = datetime.now(timezone.utc)
            hour_utc = now_utc.hour

            # Fetch recent candles
            df_5m = fetch_latest_live_candles(count=150)
            if df_5m.empty:
                print("[WARN] Data feed kosong, mencoba kembali...", flush=True)
                time.sleep(config.POLL_INTERVAL_SECONDS)
                continue

            df_15m = prepare_multi_timeframe_data(df_5m, is_live=True)
            if df_15m.empty:
                time.sleep(config.POLL_INTERVAL_SECONDS)
                continue

            latest_candle = df_15m.iloc[-1]
            latest_bar_time = df_15m.index[-1]
            current_close = latest_candle['Close']
            current_high = latest_candle['High']
            current_low = latest_candle['Low']

            # Update open trade monitoring
            if tracker.has_active_trade():
                tracker.update_with_price(current_close, current_high, current_low)

            # Check if this 15M bar is new
            if latest_bar_time != last_processed_bar:
                last_processed_bar = latest_bar_time
                print(f"[{now_utc.strftime('%H:%M:%S UTC')}] Candle M15 Baru: {latest_bar_time} | Close: {current_close:.2f} | 1H Bias: {'BULL' if latest_candle['HTF_Trend']==1 else ('BEAR' if latest_candle['HTF_Trend']==-1 else 'NEUTRAL')}", flush=True)

                # Scan for new setup if no active trade
                if not tracker.has_active_trade():
                    # Evaluate previous completed candle (index -2) to ensure confirmed close
                    signal = analyze_candle_for_signal(df_15m, idx=-2)
                    if signal and signal.score >= config.MIN_CONFLUENCE_SCORE:
                        print(f"\n🔥 [SIGNAL DETECTED] {signal.direction} @ {signal.entry_price:.2f} | Skor: {signal.score}/100", flush=True)
                        notify_signal_entry(signal)
                        tracker.open_trade(signal)
                    else:
                        is_kz, session_name = check_trading_session(hour_utc, now_utc.minute)
                        status_str = f"Scanning A+ Setups di {session_name}" if is_kz else "Menunggu Jam Sesi Killzone (London/NY)"
                        print(f"   Status: {status_str} (Belum ada setup dengan skor >= {config.MIN_CONFLUENCE_SCORE})", flush=True)

        except Exception as e:
            print(f"[ERROR in loop]: {e}", flush=True)

        time.sleep(config.POLL_INTERVAL_SECONDS)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="XAUUSD Institutional Signal Bot")
    parser.add_argument("--test-discord", action="store_true", help="Kirim sinyal test ke Discord")
    args = parser.parse_args()

    if args.test_discord:
        test_discord_alert()
    else:
        run_live_loop()
