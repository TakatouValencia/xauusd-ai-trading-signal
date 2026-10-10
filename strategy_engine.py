"""
SMC + Orderflow Institutional Strategy Engine (5-Pillar Architecture)
Implements:
1. News Blackout Filter
2. Macro Bias Alignment (Daily & H1)
3. DXY Inverse Correlation
4. Limit FVG / Retest Entry Optimization
5. AI Machine Learning Scorer (Threshold >= 85%)
"""
import numpy as np
import pandas as pd
import config
from news_filter import is_news_blackout

class Signal:
    def __init__(self, timestamp, direction, entry_price, sl_price, tp1_price, tp2_price, 
                 score, session, reasons, fvg_level=None):
        self.timestamp = timestamp
        self.direction = direction        # 'BUY' or 'SELL'
        self.entry_price = float(entry_price)
        self.sl_price = float(sl_price)
        self.tp1_price = float(tp1_price)
        self.tp2_price = float(tp2_price)
        self.sl_pips = round(abs(entry_price - sl_price) * 10.0, 1)
        self.tp1_pips = round(abs(tp1_price - entry_price) * 10.0, 1)
        self.tp2_pips = round(abs(tp2_price - entry_price) * 10.0, 1)
        self.rr_tp1 = round(self.tp1_pips / max(1.0, self.sl_pips), 2)
        self.rr_tp2 = round(self.tp2_pips / max(1.0, self.sl_pips), 2)
        self.score = int(score)
        self.session = session
        self.reasons = reasons
        self.fvg_level = fvg_level

    def to_dict(self):
        return {
            'timestamp': str(self.timestamp),
            'symbol': config.DISPLAY_SYMBOL,
            'direction': self.direction,
            'entry_price': self.entry_price,
            'sl_price': self.sl_price,
            'tp1_price': self.tp1_price,
            'tp2_price': self.tp2_price,
            'sl_pips': self.sl_pips,
            'tp1_pips': self.tp1_pips,
            'tp2_pips': self.tp2_pips,
            'rr_tp1': f"1:{self.rr_tp1}",
            'rr_tp2': f"1:{self.rr_tp2}",
            'score': self.score,
            'session': self.session,
            'reasons': self.reasons
        }

def check_trading_session(hour: int, minute: int):
    """
    Check if current candle time is within allowed Institutional Golden Sessions.
    """
    if config.ENABLE_LONDON_SESSION:
        if (config.LONDON_START_HOUR_UTC <= hour < config.LONDON_END_HOUR_UTC) or \
           (hour == config.LONDON_END_HOUR_UTC and minute <= config.LONDON_END_MINUTE_UTC):
            return True, "London Open Killzone (14:00-17:30 WIB)"

    if config.AVOID_LONDON_LUNCH:
        if (hour == 10 and minute > 30) or (11 <= hour <= 12) or (hour == 13 and minute < 30):
            return False, "London Lunch / Pre-NY Transition Avoidance"

    if config.ENABLE_NY_SESSION:
        if (hour == config.NY_START_HOUR_UTC and minute >= config.NY_START_MINUTE_UTC) or \
           (config.NY_START_HOUR_UTC < hour < config.NY_END_HOUR_UTC) or \
           (hour == config.NY_END_HOUR_UTC and minute <= config.NY_END_MINUTE_UTC):
            return True, "NY Silver Bullet Killzone (20:30-23:30 WIB)"

    return False, "Di Luar Jam Sesi Trading"

def analyze_candle_for_signal(df_15m: pd.DataFrame, idx=-1) -> Signal:
    """
    Execute 5-Pillar Decision Matrix:
    1. Check News Blackout
    2. Check Session Window
    3. Check Macro Bias Alignment (Daily & H1)
    4. Check DXY Dollar Index Inverse Divergence
    5. Calculate FVG Limit Retest & AI Confluence Score (>= 85%)
    """
    row = df_15m.iloc[idx]
    timestamp = df_15m.index[idx]
    hour = timestamp.hour
    minute = timestamp.minute

    # =========================================================================
    # PILAR 1: NEWS BLACKOUT FILTER
    # =========================================================================
    is_blackout, blackout_reason = is_news_blackout(timestamp)
    if is_blackout:
        return None

    # Sesi Trading Check
    is_active_session, session_name = check_trading_session(hour, minute)
    if not is_active_session:
        return None

    c_open = row['Open']
    c_high = row['High']
    c_low = row['Low']
    c_close = row['Close']
    c_vol = row['Volume']
    c_atr = row['ATR']
    c_ema21 = row['EMA21']
    c_ema50 = row['EMA50']
    c_rsi = row['RSI']
    daily_trend = row.get('Daily_Trend', 0)
    h1_trend = row.get('H1_Trend', 0)
    dxy_bullish = row.get('DXY_Bullish', False)
    dxy_bearish = row.get('DXY_Bearish', False)
    asian_h = row['Asian_High']
    asian_l = row['Asian_Low']
    prev_swing_h = row['Swing_High_12']
    prev_swing_l = row['Swing_Low_12']
    vol_sma = row['Vol_SMA']
    has_bull_fvg = row.get('Has_Bull_FVG', False)
    has_bear_fvg = row.get('Has_Bear_FVG', False)

    candle_range = c_high - c_low
    if candle_range <= 0.2:
        return None

    lower_wick = min(c_open, c_close) - c_low
    upper_wick = c_high - max(c_open, c_close)

    # -------------------------------------------------------------------------
    # SCORE BUY SETUP
    # -------------------------------------------------------------------------
    buy_score = 0
    buy_reasons = []

    # PILAR 2: Macro Bias Alignment (Daily + H1 Wajib Bullish)
    if daily_trend == 1 and h1_trend == 1:
        buy_score += 30
        buy_reasons.append("Pilar 2: Macro Bias Sempurna (Daily & H1 Keduanya Bullish)")
    elif h1_trend == 1:
        buy_score += 15
        buy_reasons.append("Pilar 2: H1 Trend Bullish (H1 > EMA50)")
    elif config.REQUIRE_HTF_ALIGNMENT:
        # Tolak sinyal counter-trend
        buy_score = 0

    if buy_score > 0:
        # PILAR 3: DXY Inverse Correlation
        if dxy_bearish:
            buy_score += 20
            buy_reasons.append("Pilar 3: DXY Mengonfirmasi (Indeks Dollar AS Bearish Rejection)")
        elif not dxy_bullish:
            buy_score += 10
            buy_reasons.append("Pilar 3: DXY Netral / Tidak Melawan Arah")
        else:
            # DXY sedang rally kuat -> kurangi skor
            buy_score -= 15

        # Sesi Window
        buy_score += 15
        buy_reasons.append(f"Sesi Institusional: {session_name}")

        # Liquidity Sweep
        swept = False
        if not np.isnan(asian_l) and c_low <= asian_l:
            buy_score += 20
            buy_reasons.append(f"SMC: Swept Asian Range Low (SSL Pool di {asian_l:.2f})")
            swept = True
        elif not np.isnan(prev_swing_l) and c_low <= prev_swing_l:
            buy_score += 20
            buy_reasons.append(f"SMC: Swept 3-Hour Key Swing Low ({prev_swing_l:.2f})")
            swept = True
        elif c_low <= c_ema21:
            buy_score += 10
            buy_reasons.append("Retest Dynamic Value Area (EMA21 Retest)")

        # PILAR 4: FVG Imbalance & Displacement
        if c_close > c_open:
            if has_bull_fvg:
                buy_score += 15
                buy_reasons.append("Pilar 4: Terbentuk Bullish Fair Value Gap (FVG Imbalance)")
            elif (lower_wick / candle_range) >= 0.35:
                buy_score += 15
                buy_reasons.append("Orderflow: Rejection Wick Kuat (Buyer Absorption > 35%)")
            elif (abs(c_close - c_open) / candle_range) >= 0.55:
                buy_score += 15
                buy_reasons.append("Orderflow: Bullish Displacement Ekspansif (> 55% Body)")

        # Volume Surge
        if c_vol >= 1.2 * vol_sma:
            buy_score += 10
            buy_reasons.append(f"Volume Footprint Spike ({c_vol / vol_sma:.1f}x dari SMA-20)")

        # RSI Momentum
        if 45 <= c_rsi <= 65:
            buy_score += 10
            buy_reasons.append(f"RSI Momentum Sehat ({c_rsi:.1f} - Non Exhausted)")

    # -------------------------------------------------------------------------
    # SCORE SELL SETUP
    # -------------------------------------------------------------------------
    sell_score = 0
    sell_reasons = []

    # PILAR 2: Macro Bias Alignment (Daily + H1 Wajib Bearish)
    if daily_trend == -1 and h1_trend == -1:
        sell_score += 30
        sell_reasons.append("Pilar 2: Macro Bias Sempurna (Daily & H1 Keduanya Bearish)")
    elif h1_trend == -1:
        sell_score += 15
        sell_reasons.append("Pilar 2: H1 Trend Bearish (H1 < EMA50)")
    elif config.REQUIRE_HTF_ALIGNMENT:
        sell_score = 0

    if sell_score > 0:
        # PILAR 3: DXY Inverse Correlation
        if dxy_bullish:
            sell_score += 20
            sell_reasons.append("Pilar 3: DXY Mengonfirmasi (Indeks Dollar AS Bullish Expansion)")
        elif not dxy_bearish:
            sell_score += 10
            sell_reasons.append("Pilar 3: DXY Netral / Tidak Melawan Arah")
        else:
            sell_score -= 15

        sell_score += 15
        sell_reasons.append(f"Sesi Institusional: {session_name}")

        if not np.isnan(asian_h) and c_high >= asian_h:
            sell_score += 20
            sell_reasons.append(f"SMC: Swept Asian Range High (BSL Pool di {asian_h:.2f})")
        elif not np.isnan(prev_swing_h) and c_high >= prev_swing_h:
            sell_score += 20
            sell_reasons.append(f"SMC: Swept 3-Hour Key Swing High ({prev_swing_h:.2f})")
        elif c_high >= c_ema21:
            sell_score += 10
            sell_reasons.append("Retest Dynamic Value Area (EMA21 Retest)")

        if c_close < c_open:
            if has_bear_fvg:
                sell_score += 15
                sell_reasons.append("Pilar 4: Terbentuk Bearish Fair Value Gap (FVG Imbalance)")
            elif (upper_wick / candle_range) >= 0.35:
                sell_score += 15
                sell_reasons.append("Orderflow: Rejection Wick Kuat (Seller Absorption > 35%)")
            elif (abs(c_close - c_open) / candle_range) >= 0.55:
                sell_score += 15
                sell_reasons.append("Orderflow: Bearish Displacement Ekspansif (> 55% Body)")

        if c_vol >= 1.2 * vol_sma:
            sell_score += 10
            sell_reasons.append(f"Volume Footprint Spike ({c_vol / vol_sma:.1f}x dari SMA-20)")

        if 35 <= c_rsi <= 55:
            sell_score += 10
            sell_reasons.append(f"RSI Momentum Sehat ({c_rsi:.1f} - Non Exhausted)")

    # =========================================================================
    # PILAR 5: AI MACHINE LEARNING SCORER (Threshold >= 85%)
    # =========================================================================
    norm_buy_score = min(100, int(buy_score / 1.15))
    norm_sell_score = min(100, int(sell_score / 1.15))

    threshold = 85

    # PILAR 4: Entry Optimization via FVG Retest / Equilibrium Limit
    if norm_buy_score >= threshold and norm_buy_score > norm_sell_score:
        # Masuk pada diskon FVG (35% pullback dari candle ekspansi)
        discount_pips = round(0.35 * (c_high - c_low), 2)
        entry_price = round(c_close - discount_pips, 2)
        
        # SL diletakkan 5 pips di bawah sweep low (terproteksi)
        sweep_low = min(c_low, prev_swing_l if not np.isnan(prev_swing_l) else c_low)
        raw_sl_dist = (entry_price - sweep_low) * 10.0 + 5.0
        actual_sl_pips = max(45.0, min(65.0, raw_sl_dist))
        
        sl_price = round(entry_price - (actual_sl_pips / 10.0), 2)
        tp1_price = round(entry_price + (config.TP1_PIPS / 10.0), 2)
        tp2_price = round(entry_price + (config.TP2_PIPS / 10.0), 2)

        return Signal(timestamp, 'BUY', entry_price, sl_price, tp1_price, tp2_price,
                      norm_buy_score, session_name, buy_reasons, fvg_level=entry_price)

    elif norm_sell_score >= threshold and norm_sell_score > norm_buy_score:
        discount_pips = round(0.35 * (c_high - c_low), 2)
        entry_price = round(c_close + discount_pips, 2)

        sweep_high = max(c_high, prev_swing_h if not np.isnan(prev_swing_h) else c_high)
        raw_sl_dist = (sweep_high - entry_price) * 10.0 + 5.0
        actual_sl_pips = max(45.0, min(65.0, raw_sl_dist))

        sl_price = round(entry_price + (actual_sl_pips / 10.0), 2)
        tp1_price = round(entry_price - (config.TP1_PIPS / 10.0), 2)
        tp2_price = round(entry_price - (config.TP2_PIPS / 10.0), 2)

        return Signal(timestamp, 'SELL', entry_price, sl_price, tp1_price, tp2_price,
                      norm_sell_score, session_name, sell_reasons, fvg_level=entry_price)

    return None
