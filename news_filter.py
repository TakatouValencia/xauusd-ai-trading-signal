"""
Economic Calendar & News Blackout Filter (Pilar 1)
Halts signal generation during High-Impact Red Folder US news events
to protect from violent slippage, spread expansion, and stop hunts.
"""
from datetime import datetime

def is_news_blackout(dt: datetime) -> tuple[bool, str]:
    """
    Check if a given datetime falls within a High-Impact US News Blackout window.
    Returns (is_blackout: bool, event_reason: str)
    """
    hour = dt.hour
    minute = dt.minute
    weekday = dt.weekday() # 0=Monday, ..., 3=Thursday, 4=Friday

    # 1. Major US Data Releases (NFP, CPI, PPI, Retail Sales, Unemployment Claims)
    # Rilis pada 12:30 UTC (Musim Panas / EDT) atau 13:30 UTC (Musim Dingin / EST)
    # Periode Blackout: 12:15 - 13:45 UTC (19:15 - 20:45 WIB)
    if (hour == 12 and minute >= 15) or (hour == 13 and minute <= 45):
        # Setiap hari Kamis: US Initial Jobless Claims (Klaim Pengangguran Mingguan)
        if weekday == 3:
            return True, "Red Folder News: US Initial Jobless Claims (19:30 WIB)"
        # Jumat pertama setiap bulan: NFP (Non-Farm Payrolls)
        if weekday == 4 and dt.day <= 7:
            return True, "Major Red Folder News: US Non-Farm Payrolls (NFP)"
        # Hari Selasa/Rabu/Jumat reguler: Rilis CPI, PPI, Retail Sales
        return True, "High-Impact US Economic Data Release Window (19:15-20:45 WIB)"

    # 2. FOMC Interest Rate Decision & Fed Press Conference
    # Rilis pada 18:00 UTC / 19:00 UTC (01:00 - 02:30 WIB)
    if (hour == 18 or (hour == 19 and minute <= 30)) and weekday == 2:
        return True, "Critical News: FOMC Rate Decision & Press Conference"

    return False, "Clear (No High-Impact News)"
