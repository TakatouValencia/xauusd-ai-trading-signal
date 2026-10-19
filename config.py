"""
Configuration settings for XAUUSD Institutional SMC + Orderflow Signal Engine
"""
import os
from dotenv import load_dotenv

load_dotenv()

# ==============================================================================
# 1. DISCORD WEBHOOK CONFIGURATION
# ==============================================================================
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "").strip()
DISCORD_PING_MENTION = os.getenv("DISCORD_PING_MENTION", "@everyone").strip()

# ==============================================================================
# 2. INSTRUMENT & BOT IDENTITY
# ==============================================================================
BOT_NAME = "Novaire EA V2"
SYMBOL = "PAXG-USD"                      # Physical Spot Gold Base (London Good Delivery)
TRADINGVIEW_SYMBOL = "FOREXCOM:XAUUSD"  # Live Real-Time Feed dari TradingView Forex.com
DISPLAY_SYMBOL = "XAUUSD"                # Tampilan simbol di Discord

# ==============================================================================
# 3. TRADING SESSION HOURS (ZONA WAKTU UTC & WIB)
# ==============================================================================
# WIB = UTC + 7 Jam

# Sesi 1: Asian Session (Fase Akumulasi & Pembentukan Range Likuiditas)
# Jam: 00:00 - 06:00 UTC (07:00 - 13:00 WIB) -> HANYA MENCATAT HIGH & LOW (NO ENTRY)
ASIAN_START_HOUR_UTC = 0
ASIAN_END_HOUR_UTC = 6

# Sesi 2: London Open Killzone (Fase Manipulasi / Judas Swing & Ekspansi)
# Jam: 07:00 - 10:30 UTC (14:00 - 17:30 WIB) -> PRIME HUNTING WINDOW 1
ENABLE_LONDON_SESSION = True
LONDON_START_HOUR_UTC = 7
LONDON_END_HOUR_UTC = 10
LONDON_END_MINUTE_UTC = 30

# Sesi 3: London Lunch & Transition (Fase Konsolidasi / Fakeout)
# Jam: 10:30 - 12:30 UTC (17:30 - 19:30 WIB) -> FILTERED / DIHINDARI (HIGH CHOP)
AVOID_LONDON_LUNCH = True

# Sesi 4: New York Open & Silver Bullet Killzone (Fase Ekspansi Institusional US)
# Jam: 13:30 - 16:30 UTC (20:30 - 23:30 WIB) -> PRIME HUNTING WINDOW 2
# Note: 12:30 - 13:30 UTC dihindari karena rilis data berita High-Impact US (CPI/NFP/PPI)
ENABLE_NY_SESSION = True
NY_START_HOUR_UTC = 13
NY_START_MINUTE_UTC = 30
NY_END_HOUR_UTC = 16
NY_END_MINUTE_UTC = 30

# ==============================================================================
# 4. ORDER PARAMETERS & TARGET PIPS (1 pip = $0.10 pada Gold)
# ==============================================================================
# Menyesuaikan volatilitas Gold terkini ($4,180): ATR M15 rata-rata adalah ~70 pips.
# SL 75 pips melindungi posisi dari wick noise tanpa terkena stop-out prematur.
SL_PIPS = float(os.getenv("SL_PIPS", "75.0"))                  # Stop Loss Default: 75 pips ($7.50 move)
TP1_PIPS = float(os.getenv("TP1_PIPS", "100.0"))               # Take Profit 1: 100 pips ($10.00 move) - Lock BE + Partials
TP2_PIPS = float(os.getenv("TP2_PIPS", "160.0"))               # Take Profit 2: 160 pips ($16.00 move) - Full TP

BREAKEVEN_TRIGGER_PIPS = float(os.getenv("BREAKEVEN_TRIGGER_PIPS", "70.0"))   # Pindahkan SL ke BE setelah running +70 pips (mencegah exit prematur pada retest wajar)
BREAKEVEN_BUFFER_PIPS = 5.0     # Buffer pengaman di atas entry (+5 pips)
TRAILING_TP1_LOCK_PIPS = 60.0   # Saat TP1 kena, kunci profit minimal +60 pips untuk runner

# ==============================================================================
# 5. ORDER EXECUTION MODE (MARKET vs LIMIT)
# ==============================================================================
# 'MARKET': Eksekusi instan langsung saat candle M15 close terkonfirmasi (Disarankan untuk Gold)
# 'LIMIT' : Pasang pending order Buy Limit / Sell Limit dengan retest pullback wajar
ENTRY_MODE = os.getenv("ENTRY_MODE", "MARKET").strip().upper()
LIMIT_PULLBACK_PIPS = float(os.getenv("LIMIT_PULLBACK_PIPS", "5.0"))  # Pullback discount pips untuk mode LIMIT (default 5 pips = $0.50)
LIMIT_MAX_WAIT_BARS = int(os.getenv("LIMIT_MAX_WAIT_BARS", "4"))      # Maksimal menunggu 4 bar M15 (1 jam) sebelum limit dibatalkan jika tidak kena

# ==============================================================================
# 6. AI CONFLUENCE & QUALITY FILTERS
# ==============================================================================
MIN_CONFLUENCE_SCORE = 80       # Ambang batas skor setup A+ (0 - 100)
MAX_TRADES_PER_SESSION = 1      # Batasi maksimal 1 sinyal sniper per sesi (Cegah overtrading)
REQUIRE_HTF_ALIGNMENT = True    # Wajib searah dengan tren makro 1-Jam (EMA 50 & 200)

# ==============================================================================
# 7. RISK MANAGEMENT & DAILY CIRCUIT BREAKER
# ==============================================================================
ENABLE_CIRCUIT_BREAKER = os.getenv("ENABLE_CIRCUIT_BREAKER", "true").lower() in ("true", "1", "yes")
MAX_CONSECUTIVE_LOSSES_PER_DAY = int(os.getenv("MAX_CONSECUTIVE_LOSSES_PER_DAY", "3"))  # Berhenti trade hari itu jika 3x loss beruntun, lanjut besok

# ==============================================================================
# 8. SCANNER & TICK POLLING
# ==============================================================================
POLL_INTERVAL_SECONDS = int(os.getenv("POLL_INTERVAL_SECONDS", "15"))       # Interval pemantauan chart M15 (dalam detik)
ACTIVE_TRADE_POLL_SECONDS = int(os.getenv("ACTIVE_TRADE_POLL_SECONDS", "5")) # Pemantauan tick real-time saat posisi aktif (SL/TP/BE instan)


