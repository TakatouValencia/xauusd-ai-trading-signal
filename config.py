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

# ==============================================================================
# 2. INSTRUMENT & SYMBOL
# ==============================================================================
SYMBOL = "GC=F"           # Gold Futures (CME Comex Gold)
DISPLAY_SYMBOL = "XAUUSD" # Tampilan simbol di Discord

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
SL_PIPS = 60.0                  # Stop Loss Default: 60 pips ($6.00 move)
TP1_PIPS = 100.0                # Take Profit 1: 100 pips ($10.00 move) - Lock BE + Partials
TP2_PIPS = 150.0                # Take Profit 2: 150 pips ($15.00 move) - Full TP

BREAKEVEN_TRIGGER_PIPS = 50.0   # Saat running +50 pips, pindahkan SL ke BE + buffer
BREAKEVEN_BUFFER_PIPS = 5.0     # Buffer pengaman di atas entry (+5 pips)
TRAILING_TP1_LOCK_PIPS = 60.0   # Saat TP1 kena, kunci profit minimal +60 pips untuk runner

# ==============================================================================
# 5. AI CONFLUENCE & QUALITY FILTERS
# ==============================================================================
MIN_CONFLUENCE_SCORE = 80       # Ambang batas skor setup A+ (0 - 100)
MAX_TRADES_PER_SESSION = 1      # Batasi maksimal 1 sinyal sniper per sesi (Cegah overtrading)
REQUIRE_HTF_ALIGNMENT = True    # Wajib searah dengan tren makro 1-Jam (EMA 50 & 200)
WAIT_PULLBACK_ENTRY = True      # Tunggu retest / discount 3-5 pips daripada market high/low

# ==============================================================================
# 6. SCANNER POLLING
# ==============================================================================
POLL_INTERVAL_SECONDS = 60       # Interval pemantauan chart (dalam detik)
