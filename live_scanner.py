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
from data_feed import fetch_latest_live_candles, prepare_multi_timeframe_data, get_tradingview_forexcom_quote
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
        self.pending_order = None
        self.pending_bars_waited = 0
        self.last_signal_time = None
        self.last_session_id = None
        self.current_date = None
        self.consecutive_losses = 0
        self.circuit_breaker_active = False

    def check_new_day(self, today_date):
        if self.current_date != today_date:
            if self.circuit_breaker_active:
                print(f"🌅 [NEW DAY] Memasuki hari baru ({today_date}). Circuit breaker di-reset, scanner siap aktif kembali.", flush=True)
            self.current_date = today_date
            self.consecutive_losses = 0
            self.circuit_breaker_active = False

    def is_circuit_breaker_triggered(self):
        return config.ENABLE_CIRCUIT_BREAKER and self.circuit_breaker_active

    def has_active_trade(self):
        return (self.active_trade is not None) or (self.pending_order is not None)

    def place_order(self, signal: Signal):
        order_type = getattr(signal, 'order_type', f"{signal.direction} MARKET")
        is_limit = "LIMIT" in order_type

        order_data = {
            'direction': signal.direction,
            'order_type': order_type,
            'entry_price': signal.entry_price,
            'market_price_at_signal': getattr(signal, 'market_price', signal.entry_price),
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

        if is_limit:
            self.pending_order = order_data
            self.pending_bars_waited = 0
            print(f"[PENDING] Order {signal.direction} LIMIT dipasang di {signal.entry_price:.2f} (Retest -{config.LIMIT_PULLBACK_PIPS}p dari {order_data['market_price_at_signal']:.2f}). Menunggu fill...", flush=True)
        else:
            self.active_trade = order_data
            print(f"[FILLED] Order {signal.direction} MARKET dieksekusi instan di {signal.entry_price:.2f} (SL: {signal.sl_price:.2f}, TP1: {signal.tp1_price:.2f}, TP2: {signal.tp2_price:.2f})!", flush=True)

        self.last_signal_time = signal.timestamp

    def open_trade(self, signal: Signal):
        self.place_order(signal)

    def on_new_bar(self):
        """Called every time a new 15M candle is finalized."""
        if self.pending_order:
            self.pending_bars_waited += 1
            if self.pending_bars_waited > config.LIMIT_MAX_WAIT_BARS:
                print(f"[EXPIRED] Pending LIMIT order di {self.pending_order['entry_price']:.2f} dibatalkan setelah {config.LIMIT_MAX_WAIT_BARS} bar M15!", flush=True)
                notify_trade_update("ORDER_EXPIRED", self.pending_order)
                self.pending_order = None
                self.pending_bars_waited = 0

    def _handle_exit_pnl(self, pnl: float):
        """Tracks consecutive losses and triggers circuit breaker if threshold reached."""
        if pnl < 0:
            self.consecutive_losses += 1
            print(f"⚠️ [RISK] Loss terdeteksi! Loss beruntun hari ini: {self.consecutive_losses}/{config.MAX_CONSECUTIVE_LOSSES_PER_DAY}", flush=True)
            if config.ENABLE_CIRCUIT_BREAKER and self.consecutive_losses >= config.MAX_CONSECUTIVE_LOSSES_PER_DAY:
                self.circuit_breaker_active = True
                date_str = str(self.current_date or datetime.now(timezone.utc).date())
                print(f"🛑 [CIRCUIT BREAKER] {self.consecutive_losses}x Loss beruntun hari ini ({date_str})! Bot otomatis BERHENTI trading hari ini dan akan lanjut besok.", flush=True)
                notify_trade_update("CIRCUIT_BREAKER", {
                    'consecutive_losses': self.consecutive_losses,
                    'date': date_str
                })
        else:
            # Trailing SL atau TP menghasilkan profit / breakeven
            self.consecutive_losses = 0

    def update_with_price(self, current_price: float):
        """
        Evaluate real-time tick price against active trades and pending limit orders.
        Fires immediate Discord alerts when SL, BE, TP1, or TP2 is reached.
        """
        if not current_price or current_price <= 0:
            return

        # 1. Check Pending Order Fill
        if self.pending_order:
            p = self.pending_order
            dir = p['direction']
            entry_p = p['entry_price']
            filled = False

            if dir == 'BUY' and current_price <= entry_p:
                filled = True
            elif dir == 'SELL' and current_price >= entry_p:
                filled = True

            if filled:
                print(f"🎯 [FILLED] Pending LIMIT {dir} di {entry_p:.2f} terjemput pada harga market ${current_price:.2f}! Posisi AKTIF.", flush=True)
                self.active_trade = p
                self.active_trade['fill_time'] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
                self.pending_order = None
                notify_trade_update("ORDER_FILLED", self.active_trade)

        # 2. Check Active Trade TP / SL / Breakeven
        if not self.active_trade:
            return

        trade = self.active_trade
        dir = trade['direction']
        entry_p = trade['entry_price']

        if dir == 'BUY':
            # Check Stop Loss (Instant Alert)
            if current_price <= trade['sl']:
                pnl = round((trade['sl'] - entry_p) * 10.0, 1)
                print(f"🛑 [EXIT] BUY Position hit SL at {trade['sl']:.2f} (Current: ${current_price:.2f}, PnL: {pnl:+.1f} pips)", flush=True)
                notify_trade_update("SL_HIT", trade)
                self.active_trade = None
                self._handle_exit_pnl(pnl)
                return

            # Stage 1: Running +70 pips -> Move SL to BE + buffer
            if not trade['be_moved'] and current_price >= (entry_p + (config.BREAKEVEN_TRIGGER_PIPS / 10.0)):
                trade['be_moved'] = True
                trade['sl'] = round(entry_p + (config.BREAKEVEN_BUFFER_PIPS / 10.0), 2)
                print(f"🛡️ [PROTECTION] Running +{config.BREAKEVEN_TRIGGER_PIPS} pips! SL moved to BE at {trade['sl']:.2f}", flush=True)
                notify_trade_update("BREAKEVEN", trade)

            # Stage 2: Hit TP1 (+100 pips) -> Trail SL to +60 pips
            if not trade['tp1_hit'] and current_price >= trade['tp1']:
                trade['tp1_hit'] = True
                trade['sl'] = round(entry_p + (config.TRAILING_TP1_LOCK_PIPS / 10.0), 2)
                self.consecutive_losses = 0
                print(f"💰 [TP1 HIT] Target 1 (+{config.TP1_PIPS} pips) achieved at {trade['tp1']:.2f}!", flush=True)
                notify_trade_update("TP1_HIT", trade)

            # Stage 3: Hit TP2 (+160 pips)
            if current_price >= trade['tp2']:
                print(f"🚀 [TP2 HIT] FULL TARGET (+{config.TP2_PIPS} pips) achieved at {trade['tp2']:.2f}!", flush=True)
                notify_trade_update("TP2_HIT", trade)
                self.active_trade = None
                self.consecutive_losses = 0
                return

        elif dir == 'SELL':
            # Check Stop Loss (Instant Alert)
            if current_price >= trade['sl']:
                pnl = round((entry_p - trade['sl']) * 10.0, 1)
                print(f"🛑 [EXIT] SELL Position hit SL at {trade['sl']:.2f} (Current: ${current_price:.2f}, PnL: {pnl:+.1f} pips)", flush=True)
                notify_trade_update("SL_HIT", trade)
                self.active_trade = None
                self._handle_exit_pnl(pnl)
                return

            # Stage 1: Running +70 pips -> Move SL to BE - buffer
            if not trade['be_moved'] and current_price <= (entry_p - (config.BREAKEVEN_TRIGGER_PIPS / 10.0)):
                trade['be_moved'] = True
                trade['sl'] = round(entry_p - (config.BREAKEVEN_BUFFER_PIPS / 10.0), 2)
                print(f"🛡️ [PROTECTION] Running +{config.BREAKEVEN_TRIGGER_PIPS} pips! SL moved to BE at {trade['sl']:.2f}", flush=True)
                notify_trade_update("BREAKEVEN", trade)

            # Stage 2: Hit TP1 (+100 pips) -> Trail SL to +60 pips
            if not trade['tp1_hit'] and current_price <= trade['tp1']:
                trade['tp1_hit'] = True
                trade['sl'] = round(entry_p - (config.TRAILING_TP1_LOCK_PIPS / 10.0), 2)
                self.consecutive_losses = 0
                print(f"💰 [TP1 HIT] Target 1 (+{config.TP1_PIPS} pips) achieved at {trade['tp1']:.2f}!", flush=True)
                notify_trade_update("TP1_HIT", trade)

            # Stage 3: Hit TP2 (+160 pips)
            if current_price <= trade['tp2']:
                print(f"🚀 [TP2 HIT] FULL TARGET (+{config.TP2_PIPS} pips) achieved at {trade['tp2']:.2f}!", flush=True)
                notify_trade_update("TP2_HIT", trade)
                self.active_trade = None
                self.consecutive_losses = 0
                return

def test_discord_alert():
    """
    Send an immediate test alert using real-time market price to verify Discord Webhook configuration.
    """
    print("[TEST] Mengambil harga market real-time XAUUSD dari TradingView Forex.com...", flush=True)
    tv_quote = get_tradingview_forexcom_quote()
    if tv_quote:
        current_price = round(tv_quote['close'], 2)
        print(f"[TEST] Harga real-time TradingView FOREXCOM:XAUUSD terdeteksi: ${current_price:.2f}", flush=True)
    else:
        df_5m = fetch_latest_live_candles(count=20)
        current_price = round(float(df_5m['Close'].iloc[-1]), 2) if not df_5m.empty else 4185.00
        print(f"[TEST] Harga real-time market saat ini terdeteksi: ${current_price:.2f}", flush=True)

    sl_dist = config.SL_PIPS / 10.0
    tp1_dist = config.TP1_PIPS / 10.0
    tp2_dist = config.TP2_PIPS / 10.0

    is_limit = config.ENTRY_MODE == 'LIMIT'
    if is_limit:
        entry_price = round(current_price - (config.LIMIT_PULLBACK_PIPS / 10.0), 2)
        order_type = "BUY LIMIT"
    else:
        entry_price = current_price
        order_type = "BUY MARKET"

    print(f"[TEST] Mengirim sinyal uji coba {order_type} (Market: ${current_price:.2f}, Entry: ${entry_price:.2f}) ke Discord...", flush=True)
    mock_signal = Signal(
        timestamp=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        direction="BUY",
        entry_price=entry_price,
        sl_price=round(entry_price - sl_dist, 2),
        tp1_price=round(entry_price + tp1_dist, 2),
        tp2_price=round(entry_price + tp2_dist, 2),
        score=92,
        session="London Killzone",
        reasons=[
            "Pilar 2: Macro Bias Sempurna (Daily & H1 Keduanya Bullish)",
            "Pilar 3: DXY Mengonfirmasi (Indeks Dollar AS Bearish Rejection)",
            f"Institutional Fresh Area: Confluence Fresh OB (Demand) + FVG [${entry_price - 2.50:.2f} - ${entry_price:.2f}]",
            f"SMC: Swept Key Liquidity Level di ${entry_price - 5.00:.2f}",
            "Orderflow: Rejection Wick Kuat (Buyer Absorption > 35%)",
            "Volume Footprint Spike (1.4x dari SMA-20)",
            "Healthy RSI Expansion (56.4 - Non Exhausted)"
        ],
        zone_type="Confluence: Fresh OB (Demand) + FVG",
        zone_range=f"[${entry_price - 2.50:.2f} - ${entry_price:.2f}]",
        order_type=order_type,
        market_price=current_price
    )
    success = notify_signal_entry(mock_signal)
    if success:
        print(f"✅ [SUCCESS] Sinyal uji coba ({order_type}) berhasil dikirim ke Discord pada harga ${entry_price:.2f}!")
    else:
        print("⚠️ [NOTE] Webhook URL belum diisi di config.py / .env, atau URL tidak valid.")

def test_circuit_breaker_alert():
    """
    Send an immediate test alert to verify Discord Webhook for Daily Circuit Breaker.
    """
    print(f"[TEST] Mengirim sinyal uji coba Daily Circuit Breaker ({config.MAX_CONSECUTIVE_LOSSES_PER_DAY}x Loss) ke Discord...", flush=True)
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    success = notify_trade_update("CIRCUIT_BREAKER", {
        'consecutive_losses': config.MAX_CONSECUTIVE_LOSSES_PER_DAY,
        'date': today_str
    })
    if success:
        print(f"✅ [SUCCESS] Notifikasi Circuit Breaker berhasil dikirim ke Discord!")
    else:
        print("⚠️ [NOTE] Webhook URL belum diisi di config.py / .env, atau URL tidak valid.")

def run_live_loop():
    print("=" * 75)
    print(f"   🤖 {config.BOT_NAME} (XAUUSD 5-PILLAR AI ENGINE) STARTED 🤖")
    print(f"   Pair: {config.DISPLAY_SYMBOL} | Feed: TradingView Real-Time | Mode: {config.ENTRY_MODE}")
    print(f"   SL: {config.SL_PIPS}p | TP1: {config.TP1_PIPS}p | TP2: {config.TP2_PIPS}p | BE Trigger: +{config.BREAKEVEN_TRIGGER_PIPS}p")
    print(f"   Circuit Breaker: {'Aktif (Max ' + str(config.MAX_CONSECUTIVE_LOSSES_PER_DAY) + 'x Loss/Hari)' if config.ENABLE_CIRCUIT_BREAKER else 'Nonaktif'}")
    print(f"   Min Score: {config.MIN_CONFLUENCE_SCORE}/100 | Sesi: London & NY Killzone")
    print("=" * 75)

    tracker = LivePositionTracker()
    last_processed_bar = None
    last_candle_fetch_time = 0

    while True:
        try:
            now_utc = datetime.now(timezone.utc)
            hour_utc = now_utc.hour
            today_date = now_utc.date()
            current_timestamp = time.time()

            # Reset circuit breaker on new day
            tracker.check_new_day(today_date)

            # 1. Real-time fast tick tracking for open positions & limit orders
            if tracker.has_active_trade():
                tv_quote = get_tradingview_forexcom_quote()
                if tv_quote:
                    current_price = tv_quote['close']
                    tracker.update_with_price(current_price)

            # 2. Check if it's time to fetch candles (Every POLL_INTERVAL_SECONDS or when trade not active)
            time_since_last_fetch = current_timestamp - last_candle_fetch_time
            should_fetch_candles = (time_since_last_fetch >= config.POLL_INTERVAL_SECONDS) or (last_processed_bar is None)

            if should_fetch_candles:
                last_candle_fetch_time = current_timestamp
                df_5m = fetch_latest_live_candles(count=150)
                if df_5m.empty:
                    time.sleep(3)
                    continue

                df_15m = prepare_multi_timeframe_data(df_5m, is_live=True)
                if df_15m.empty:
                    time.sleep(3)
                    continue

                latest_candle = df_15m.iloc[-1]
                latest_bar_time = df_15m.index[-1]
                current_close = latest_candle['Close']

                # Check if this 15M bar is new (confirmed close of previous candle)
                if latest_bar_time != last_processed_bar:
                    last_processed_bar = latest_bar_time
                    tracker.on_new_bar()
                    bias_str = 'BULL' if latest_candle['HTF_Trend'] == 1 else ('BEAR' if latest_candle['HTF_Trend'] == -1 else 'NEUTRAL')
                    print(f"[{now_utc.strftime('%H:%M:%S UTC')}] Candle M15 Baru: {latest_bar_time} | Live Price: ${current_close:.2f} | 1H Bias: {bias_str}", flush=True)

                    # Scan for new setup if no active trade or pending order
                    if not tracker.has_active_trade():
                        if tracker.is_circuit_breaker_triggered():
                            print(f"   🛑 [CIRCUIT BREAKER AKTIF] {tracker.consecutive_losses}x Loss beruntun tercapai hari ini ({tracker.current_date}). Trading dihentikan, aktif kembali besok.", flush=True)
                        else:
                            # Evaluate previous completed candle (index -2) to ensure confirmed close
                            signal = analyze_candle_for_signal(df_15m, idx=-2)
                            if signal and signal.score >= config.MIN_CONFLUENCE_SCORE:
                                # Synchronize exact real-time market price at execution
                                tv_quote = get_tradingview_forexcom_quote()
                                live_price = round(tv_quote['close'], 2) if tv_quote else round(current_close, 2)

                                if config.ENTRY_MODE == 'MARKET':
                                    signal.entry_price = live_price
                                    signal.market_price = live_price
                                    if signal.direction == 'BUY':
                                        signal.sl_price = round(live_price - (signal.sl_pips / 10.0), 2)
                                        signal.tp1_price = round(live_price + (config.TP1_PIPS / 10.0), 2)
                                        signal.tp2_price = round(live_price + (config.TP2_PIPS / 10.0), 2)
                                    else:
                                        signal.sl_price = round(live_price + (signal.sl_pips / 10.0), 2)
                                        signal.tp1_price = round(live_price - (config.TP1_PIPS / 10.0), 2)
                                        signal.tp2_price = round(live_price - (config.TP2_PIPS / 10.0), 2)

                                print(f"\n🔥 [SIGNAL DETECTED] {signal.order_type} @ {signal.entry_price:.2f} | SL: {signal.sl_price:.2f} | Skor: {signal.score}/100", flush=True)
                                notify_signal_entry(signal)
                                tracker.place_order(signal)
                            else:
                                is_kz, session_name = check_trading_session(hour_utc, now_utc.minute)
                                status_str = f"Scanning A+ Setups di {session_name}" if is_kz else "Menunggu Jam Sesi Killzone (London/NY)"
                                print(f"   Status: {status_str} (Belum ada setup dengan skor >= {config.MIN_CONFLUENCE_SCORE})", flush=True)

        except Exception as e:
            print(f"[ERROR in loop]: {e}", flush=True)

        # Sleep interval: faster (5s) if monitoring an active trade, else normal (POLL_INTERVAL_SECONDS)
        sleep_sec = config.ACTIVE_TRADE_POLL_SECONDS if tracker.has_active_trade() else config.POLL_INTERVAL_SECONDS
        time.sleep(sleep_sec)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="XAUUSD Institutional Signal Bot")
    parser.add_argument("--test-discord", action="store_true", help="Kirim sinyal test ke Discord")
    parser.add_argument("--test-circuit-breaker", action="store_true", help="Kirim sinyal test Circuit Breaker ke Discord")
    args = parser.parse_args()

    if args.test_discord:
        test_discord_alert()
    elif args.test_circuit_breaker:
        test_circuit_breaker_alert()
    else:
        run_live_loop()
